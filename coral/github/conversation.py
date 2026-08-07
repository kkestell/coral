"""The conversation on the pull request: the query that reads it, the bound, and the file it
crosses the step boundary on.

Three connections make up a conversation and they do not agree on what a unit is. A comment here
is one piece of prose somebody wrote: an issue comment, a review whose body is not empty, or a
comment inside a review thread. A review with an empty body is the envelope GitHub creates to
hold a single inline comment, and nearly every review on a busy pull request is one of those, so
counting them as discussion would spend the bound on nothing.

Every comment in that sense carries a timestamp of its own, which is what makes one global
ordering possible. Only a thread has none, and a thread does not need one: a thread is kept when
a comment inside it is kept.

Coral recognizes its own work by the marker on the comment and never by the author login, which
belongs to the repository's automation and is shared with everything else that account posts.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Final

from pydantic import TypeAdapter

from coral.github.client import GitHub
from coral.github.marker import is_mine, reviewed_commit

log = logging.getLogger(__name__)

# The connection cap is GitHub's own: `first` and `last` must be between 1 and 100, so any bound
# above 100 costs a round trip. The rest are chosen rather than measured.
PER_PAGE: Final = 100
THREAD_COMMENTS: Final = 20
MAX_COMMENTS: Final = 200
MAX_CHARACTERS: Final = 400_000
MAX_PAGES: Final = 4

# The reaction Coral acknowledges a request with, spelled as GraphQL spells the enum. The REST
# endpoint that leaves one takes the same name in lower case, and `coral/github/reactions.py`
# reads it from here so the two spellings stay one fact.
EYES: Final = "EYES"

# The field list for each node type, shared by the first query and the query that pages one
# connection back, so there is one definition of what a review, a thread, and a comment are.
# Comments are read under `reviewThreads` and never under `reviews`: every inline comment is
# reachable both ways, the resolution and staleness flags live only on the thread, and asking
# both ways returns each comment twice.
#
# `databaseId` is the REST comment id, which is what the reaction endpoints take and what the
# GraphQL node id is not. `reactionGroups` is how Coral knows it has already reacted. Both are
# asked for on reviews as well, because the review dataclass inherits the comment's fields and
# not because a review is ever a reaction target.

REVIEW_FIELDS: Final = """
fragment ReviewFields on PullRequestReview {
  id
  databaseId
  author { login }
  authorAssociation
  state
  submittedAt
  body
  commit { oid }
  reactionGroups { content viewerHasReacted }
}
"""

THREAD_FIELDS: Final = """
fragment ThreadFields on PullRequestReviewThread {
  id
  isResolved
  isOutdated
  path
  line
  startLine
  diffSide
  subjectType
  comments(first: $threadComments) {
    totalCount
    nodes {
      id
      databaseId
      author { login }
      authorAssociation
      body
      createdAt
      outdated
      originalLine
      reactionGroups { content viewerHasReacted }
    }
  }
}
"""

COMMENT_FIELDS: Final = """
fragment CommentFields on IssueComment {
  id
  databaseId
  author { login }
  authorAssociation
  body
  createdAt
  reactionGroups { content viewerHasReacted }
}
"""

# Every connection is read with `last:` and none of them is given an ordering. Neither `reviews`
# nor `reviewThreads` accepts one at all, and the only ordering field for issue comments is
# `UPDATED_AT`, which would rank an ancient comment edited yesterday above one written last week.
# So all three take the connection's default order, and `last:` returning the newest is a
# behavior observed against a real pull request rather than one GitHub promises.
CONVERSATION_QUERY: Final = (
    REVIEW_FIELDS
    + THREAD_FIELDS
    + COMMENT_FIELDS
    + """
query Conversation(
  $owner: String!
  $repo: String!
  $number: Int!
  $page: Int!
  $threadComments: Int!
) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviews(last: $page) {
        totalCount
        pageInfo { hasPreviousPage startCursor }
        nodes { ...ReviewFields }
      }
      reviewThreads(last: $page) {
        totalCount
        pageInfo { hasPreviousPage startCursor }
        nodes { ...ThreadFields }
      }
      comments(last: $page) {
        totalCount
        pageInfo { hasPreviousPage startCursor }
        nodes { ...CommentFields }
      }
    }
  }
  rateLimit { cost remaining nodeCount }
}
"""
)

# One connection at a time, walking backwards from a cursor. Each aliases the connection it asks
# for to `connection`, so one reader handles the answer whichever of the three it was.
REVIEWS_PAGE_QUERY: Final = (
    REVIEW_FIELDS
    + """
query ReviewsPage(
  $owner: String!
  $repo: String!
  $number: Int!
  $page: Int!
  $before: String!
) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      connection: reviews(last: $page, before: $before) {
        totalCount
        pageInfo { hasPreviousPage startCursor }
        nodes { ...ReviewFields }
      }
    }
  }
  rateLimit { cost remaining nodeCount }
}
"""
)

THREADS_PAGE_QUERY: Final = (
    THREAD_FIELDS
    + """
query ThreadsPage(
  $owner: String!
  $repo: String!
  $number: Int!
  $page: Int!
  $threadComments: Int!
  $before: String!
) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      connection: reviewThreads(last: $page, before: $before) {
        totalCount
        pageInfo { hasPreviousPage startCursor }
        nodes { ...ThreadFields }
      }
    }
  }
  rateLimit { cost remaining nodeCount }
}
"""
)

COMMENTS_PAGE_QUERY: Final = (
    COMMENT_FIELDS
    + """
query CommentsPage(
  $owner: String!
  $repo: String!
  $number: Int!
  $page: Int!
  $before: String!
) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      connection: comments(last: $page, before: $before) {
        totalCount
        pageInfo { hasPreviousPage startCursor }
        nodes { ...CommentFields }
      }
    }
  }
  rateLimit { cost remaining nodeCount }
}
"""
)


@dataclass(frozen=True)
class Comment:
    """One piece of prose somebody wrote on the pull request as a whole."""

    id: str
    # The REST id, which is the one the reaction endpoints take.
    database_id: int
    # `None` when the account that wrote it has been deleted. The association survives that.
    author: str | None
    # A `str` rather than a `Literal`: an association GitHub adds later is not a reason to crash.
    association: str
    body: str
    written_at: str
    mine: bool
    reacted: bool


@dataclass(frozen=True)
class PastReview(Comment):
    """A review somebody submitted, with prose of its own in the body."""

    state: str
    commit: str | None


@dataclass(frozen=True)
class ThreadComment(Comment):
    """A comment inside a review thread."""

    outdated: bool
    original_line: int | None


@dataclass(frozen=True)
class Thread:
    """A discussion attached to a place in the diff, with its resolution and staleness."""

    id: str
    path: str
    # Null on an outdated thread whose line no longer exists in the file.
    line: int | None
    start_line: int | None
    diff_side: str
    subject_type: str
    resolved: bool
    outdated: bool
    comments: list[ThreadComment]
    total_comments: int


@dataclass(frozen=True)
class Bound:
    """What the bound kept and what it left behind."""

    read: int
    unread: int
    oldest_read: str | None


@dataclass(frozen=True)
class Conversation:
    """Everything Coral reads off a pull request before reviewing it."""

    comments: list[Comment]
    reviews: list[PastReview]
    threads: list[Thread]
    bound: Bound
    reviewed_commits: list[str]


@dataclass(frozen=True)
class Fetched:
    """What the connections gave up, before the bound cut it down."""

    comments: list[Comment]
    reviews: list[PastReview]
    threads: list[Thread]
    reviewed_commits: list[str]
    # Nodes the connections said they held and nobody asked for, because the paging stopped.
    unfetched: int


@dataclass(frozen=True)
class Page:
    """One connection's answer: its nodes, its size, and where the older ones start."""

    nodes: list[Any]
    total: int
    has_previous: bool
    cursor: str | None


@dataclass(frozen=True)
class Candidate:
    """One comment reduced to what the bound sorts and counts."""

    id: str
    written_at: str
    length: int


def author_of(node: dict[str, Any]) -> str | None:
    """The login that wrote a node, or `None` when the account is gone."""
    return node["author"]["login"] if node["author"] else None


def already_reacted(node: dict[str, Any]) -> bool:
    """Whether Coral's reaction is already on this comment.

    The viewer `viewerHasReacted` answers for is the account the job's token belongs to. Reading
    it off the conversation is what saves a REST call per comment before each reaction, and a
    wrong answer costs one duplicate POST and nothing else: posting a reaction that is already
    there returns 200 and creates nothing.
    """
    return any(
        group["content"] == EYES and group["viewerHasReacted"] for group in node["reactionGroups"]
    )


def parse_comments(nodes: list[Any]) -> list[Comment]:
    """The issue comments, which are the comments on the pull request as a whole."""
    return [
        Comment(
            id=node["id"],
            database_id=node["databaseId"],
            author=author_of(node),
            association=node["authorAssociation"],
            body=node["body"],
            written_at=node["createdAt"],
            mine=is_mine(node["body"]),
            reacted=already_reacted(node),
        )
        for node in nodes
    ]


def parse_reviews(nodes: list[Any]) -> list[PastReview]:
    """The reviews that are discussion, which is the ones somebody wrote prose in."""
    reviews = []
    for node in nodes:
        # An empty body is an envelope around a single inline comment, which is read through its
        # thread instead. A review with no `submittedAt` is unsubmitted and is visible to nobody
        # but its author, so it is skipped rather than sorted with a missing timestamp.
        if not node["body"].strip() or node["submittedAt"] is None:
            continue
        reviews.append(
            PastReview(
                id=node["id"],
                database_id=node["databaseId"],
                author=author_of(node),
                association=node["authorAssociation"],
                body=node["body"],
                written_at=node["submittedAt"],
                mine=is_mine(node["body"]),
                reacted=already_reacted(node),
                state=node["state"],
                commit=node["commit"]["oid"] if node["commit"] else None,
            )
        )
    return reviews


def parse_thread_comments(nodes: list[Any]) -> list[ThreadComment]:
    """The comments inside one review thread."""
    return [
        ThreadComment(
            id=node["id"],
            database_id=node["databaseId"],
            author=author_of(node),
            association=node["authorAssociation"],
            body=node["body"],
            written_at=node["createdAt"],
            mine=is_mine(node["body"]),
            reacted=already_reacted(node),
            outdated=node["outdated"],
            original_line=node["originalLine"],
        )
        for node in nodes
    ]


def parse_threads(nodes: list[Any]) -> list[Thread]:
    """The review threads, with the flags item 6 reads to decide whether a finding still stands."""
    return [
        Thread(
            id=node["id"],
            path=node["path"],
            line=node["line"],
            start_line=node["startLine"],
            diff_side=node["diffSide"],
            subject_type=node["subjectType"],
            resolved=node["isResolved"],
            outdated=node["isOutdated"],
            comments=parse_thread_comments(node["comments"]["nodes"]),
            total_comments=node["comments"]["totalCount"],
        )
        for node in nodes
    ]


def reviewed_commits(nodes: list[Any]) -> list[str]:
    """The commits Coral has already reviewed, read from every review the fetch returned.

    Read before the bound and before the empty-body filter, because Coral's memory must not be a
    function of how much other people talked. Read from review bodies only: an inline finding
    carries a marker naming a commit too, and so will the failure comment, and neither of those
    means the commit was reviewed.
    """
    found = (reviewed_commit(node["body"]) for node in nodes)
    return list(dict.fromkeys(commit for commit in found if commit is not None))


def read_page(connection: dict[str, Any]) -> Page:
    """Read one connection's answer out of the response."""
    return Page(
        nodes=connection["nodes"],
        total=connection["totalCount"],
        has_previous=connection["pageInfo"]["hasPreviousPage"],
        cursor=connection["pageInfo"]["startCursor"],
    )


def wants_another_page(has_previous: bool, comments_so_far: int, pages: int) -> bool:
    """Whether one connection is worth walking further back.

    The rule is per connection rather than global, and it has to be. The bound takes the most
    recent comments across all three connections, so a comment can only be missed if its own
    connection was not paged deep enough to offer it, and a connection that has already offered
    the whole bound cannot be hiding one that belongs in the answer. The page cap is what stops a
    pull request carrying a thousand empty reviews from walking its whole history.
    """
    return has_previous and comments_so_far < MAX_COMMENTS and pages < MAX_PAGES


def fetch_conversation(github: GitHub, owner: str, repo: str, number: int) -> Fetched:
    """Ask GitHub for the conversation, paging each connection back as far as the bound needs."""
    target = {"owner": owner, "repo": repo, "number": number, "page": PER_PAGE}
    spent: list[Any] = []

    def ask(query: str, variables: dict[str, Any]) -> Any:
        answer = github.graphql(query, variables)
        spent.append(answer["rateLimit"])
        return answer["repository"]["pullRequest"]

    def gather(
        query: str, variables: dict[str, Any], first: Page, comments_in: Callable[[list[Any]], int]
    ) -> list[Any]:
        page = first
        nodes = list(first.nodes)
        pages = 1
        while wants_another_page(page.has_previous, comments_in(nodes), pages):
            assert page.cursor is not None, "A connection with a previous page has a cursor."
            page = read_page(ask(query, variables | {"before": page.cursor})["connection"])
            # Older nodes go in front, which keeps the connection's own ascending order.
            nodes = page.nodes + nodes
            pages += 1
        return nodes

    pull_request = ask(CONVERSATION_QUERY, target | {"threadComments": THREAD_COMMENTS})
    reviews = read_page(pull_request["reviews"])
    threads = read_page(pull_request["reviewThreads"])
    comments = read_page(pull_request["comments"])

    review_nodes = gather(REVIEWS_PAGE_QUERY, target, reviews, lambda ns: len(parse_reviews(ns)))
    thread_nodes = gather(
        THREADS_PAGE_QUERY,
        target | {"threadComments": THREAD_COMMENTS},
        threads,
        lambda ns: sum(len(thread.comments) for thread in parse_threads(ns)),
    )
    comment_nodes = gather(
        COMMENTS_PAGE_QUERY, target, comments, lambda ns: len(parse_comments(ns))
    )

    log.info(
        "Read the conversation in %d queries costing %d points and %d nodes, %d points left.",
        len(spent),
        sum(answer["cost"] for answer in spent),
        sum(answer["nodeCount"] for answer in spent),
        spent[-1]["remaining"],
    )

    return Fetched(
        comments=parse_comments(comment_nodes),
        reviews=parse_reviews(review_nodes),
        threads=parse_threads(thread_nodes),
        reviewed_commits=reviewed_commits(review_nodes),
        unfetched=(
            (reviews.total - len(review_nodes))
            + (threads.total - len(thread_nodes))
            + (comments.total - len(comment_nodes))
        ),
    )


def in_time_order[T: Comment](comments: list[T]) -> list[T]:
    """Oldest first, which is the order a conversation reads in."""
    return sorted(comments, key=lambda comment: comment.written_at)


def bound(fetched: Fetched) -> Conversation:
    """Cut the conversation down to the most recent comments that fit, and say what was left.

    Timestamps are compared as the strings GitHub returned, which is correct because they are
    ISO-8601 in UTC with a `Z` suffix and so sort lexically.
    """
    candidates = [
        Candidate(id=comment.id, written_at=comment.written_at, length=len(comment.body))
        for comment in [
            *fetched.comments,
            *fetched.reviews,
            *(comment for thread in fetched.threads for comment in thread.comments),
        ]
    ]

    kept: set[str] = set()
    characters = 0
    oldest: str | None = None
    for candidate in sorted(candidates, key=lambda c: c.written_at, reverse=True):
        if len(kept) == MAX_COMMENTS or characters + candidate.length > MAX_CHARACTERS:
            break
        kept.add(candidate.id)
        characters += candidate.length
        oldest = candidate.written_at

    # A thread survives when a comment inside it survives, and keeps its flags, its path, and its
    # lines whole, because those are what decide later whether a finding still stands.
    threads = [
        replace(thread, comments=in_time_order([c for c in thread.comments if c.id in kept]))
        for thread in fetched.threads
    ]

    # Overstating what went unread is the safe direction for a promise made to a reader, and the
    # last term does overstate: an empty-bodied review nobody asked for is counted as a comment.
    unread = (
        (len(candidates) - len(kept))
        + sum(thread.total_comments - len(thread.comments) for thread in fetched.threads)
        + fetched.unfetched
    )

    return Conversation(
        comments=in_time_order([c for c in fetched.comments if c.id in kept]),
        reviews=in_time_order([r for r in fetched.reviews if r.id in kept]),
        threads=[thread for thread in threads if thread.comments],
        bound=Bound(read=len(kept), unread=unread, oldest_read=oldest),
        reviewed_commits=fetched.reviewed_commits,
    )


# The same validator the agent framework runs over the review object, so the project has one
# answer to "JSON back into a frozen dataclass" rather than two.
CONVERSATIONS: Final = TypeAdapter(Conversation)


def write_conversation(path: Path, conversation: Conversation) -> None:
    """Leave the conversation where the review step will read it."""
    path.write_bytes(CONVERSATIONS.dump_json(conversation))


def read_conversation(path: Path) -> Conversation:
    """Read the conversation back into the dataclasses it was written from."""
    return CONVERSATIONS.validate_json(path.read_bytes())
