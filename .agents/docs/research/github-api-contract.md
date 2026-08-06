# GitHub's API Contract For A Reviewing Bot

Status: Living document (last updated 2026-08-06)

## Question

A bot that reviews pull requests has to do three things through GitHub's API, and each one has a documented requirement that is easy to get wrong on the first attempt. It leaves a reaction on the comment that asked for the review. It reads the whole conversation on the pull request, including whether past inline discussions were resolved or went stale. It posts one batched review carrying inline comments. The question is what GitHub actually requires for each: which fine-grained permission each endpoint needs, whether one GraphQL query can return the conversation inside GitHub's node limits, and which fields a batched review's comment entries may carry.

## Summary

Reactions are the case where the two endpoints diverge. A reaction on a pull request comment posted through the issues namespace needs the Issues permission at write, and the Pull requests permission does not grant it. A reaction on a comment attached to the diff needs the Pull requests permission at write, and the Issues permission does not grant it. Posting an ordinary comment on a pull request, by contrast, works with either one, because GitHub publishes that endpoint as accepting two alternative permission sets.

The conversation does fit in one GraphQL query. A query returning the reviews, the review threads with their resolution and staleness flags, and the issue comments costs one rate limit point and counts 2,300 nodes against a ceiling of 500,000. Two limits shape it. No connection may ask for more than 100 items, so any bound above 100 needs pagination. Neither the reviews connection nor the review threads connection accepts an ordering argument, and a review thread carries no timestamp of its own, so a most-recent bound on threads can only be approximated by taking the tail of GitHub's default order.

The comment entries in a batched review accept exactly seven fields, and `subject_type` is not among them. It exists only on the endpoint that posts a single review comment, which also requires a commit SHA that the batched endpoint takes once for the whole review.

## Where the permission requirements are published

The public OpenAPI description carries no permission data at all. Every operation in it has an `x-github` object, and across all 808 paths those objects only ever hold `category`, `subcategory`, `enabledForGitHubApps`, `githubCloudOnly`, `triggersNotification`, `previews`, `requestBodyParameterName`, `deprecationDate`, and `removalDate`. There is no permissions key to read. Anyone consulting the machine-readable description alone will conclude that GitHub does not state the requirement.

GitHub states it in two other places, and they agree with each other.

The first is a set of generated data files in the documentation repository, one per token type per API version. For a GitHub App installation token on the current API version the file is `github/docs/src/github-apps/data/fpt-2022-11-28/server-to-server-permissions.json`. It is keyed by permission name, and each permission holds an array of the operations that permission reaches, each entry carrying `verb`, `requestPath`, `access`, and a boolean called `additional-permissions`.

The second is the rendered reference page for each endpoint, which embeds a `progAccess` object per operation in the page's own JSON payload. That object holds a `permissions` array, and the array is the authoritative form because it encodes the relationship between multiple permissions that the data file's boolean flattens away. The component that renders it states the rule in a comment at `github/docs/src/rest/components/RestAuth.tsx:86-90`: "progAccess.permissions is an array of objects ... Each object represents a set of permissions containing one or more key-value pairs. All permissions in a set are required. If there is more than one set of permissions, any set can be used." The two headings it chooses between are in `github/docs/data/ui.yml:256-257` — "The fine-grained token must have at least one of the following permission sets" when there is more than one set, and "The fine-grained token must have the following permission set" when there is one.

So an array of two single-key objects means either permission suffices. A single object with two keys would mean both are required. The `additional-permissions` boolean in the data file cannot tell those apart, and its own documentation says as much, at `github/docs/data/reusables/rest-api/additional-permissions.md`: "Some endpoints require more than one permission. Other endpoints work with any one permission from a set of permissions. In these cases, the 'Additional permissions' column will include a checkmark."

A workflow's `permissions` block names the same permissions. The Actions page on controlling the job token's permissions does not list them itself; it refers the reader to the fine-grained personal access token documentation "to see the list of permissions available for use and their parameterized names". The parameterized names are the block's keys, and `issues` and `pull-requests` are both among them. Two rules from the workflow syntax reference apply: "`write` includes `read`", and "If you specify the access for any of these permissions, all of those that are not specified are set to `none`."

## What each endpoint requires

Read from `server-to-server-permissions.json` and confirmed against the `progAccess` payload on the rendered reference pages for reactions, issue comments, pull request reviews, and pull requests. A permission set written with "or" is two alternative sets, either of which suffices.

| Method and path | Permission sets |
| --- | --- |
| `POST /repos/{owner}/{repo}/issues/comments/{comment_id}/reactions` | Issues (write) |
| `GET /repos/{owner}/{repo}/issues/comments/{comment_id}/reactions` | Issues (read) |
| `POST /repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions` | Pull requests (write) |
| `GET /repos/{owner}/{repo}/pulls/comments/{comment_id}/reactions` | Pull requests (read) |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/reactions` | Issues (write) |
| `POST /repos/{owner}/{repo}/issues/{issue_number}/comments` | Issues (write) or Pull requests (write) |
| `GET /repos/{owner}/{repo}/issues/{issue_number}/comments` | Issues (read) or Pull requests (read) |
| `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews` | Pull requests (write) |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}/reviews` | Pull requests (read) |
| `GET /repos/{owner}/{repo}/pulls/{pull_number}` | Contents (read) or Pull requests (read) |

The reaction endpoints under the issues namespace list one set, and that set holds Issues alone. This is true whether the reaction target is a comment or the issue itself, and it is true whether the issue is really a pull request. Nothing about the target being a pull request comment moves the endpoint into the Pull requests permission. GitHub's separate reaction endpoint for a comment on the diff lives under the pulls namespace, and that one lists Pull requests alone.

Every read in the table also carries `allowsPublicRead`, which the documentation renders as "This endpoint can be used without authentication or the aforementioned permissions if only public resources are requested." No write in the table carries it.

## The conversation in one GraphQL query

This query was run against a real pull request and returns everything a review needs to know about a past discussion. Every field in it was checked against the schema by introspection, and the whole query was executed.

```graphql
query Conversation($owner: String!, $repo: String!, $number: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      reviews(last: 100) {
        totalCount
        pageInfo { hasPreviousPage startCursor }
        nodes {
          author { login }
          authorAssociation
          state
          submittedAt
          body
          commit { oid }
        }
      }
      reviewThreads(last: 100) {
        totalCount
        pageInfo { hasPreviousPage startCursor }
        nodes {
          isResolved
          isOutdated
          isCollapsed
          path
          line
          startLine
          diffSide
          subjectType
          comments(first: 20) {
            totalCount
            nodes {
              author { login }
              authorAssociation
              body
              createdAt
              outdated
              originalLine
            }
          }
        }
      }
      comments(last: 100, orderBy: {field: UPDATED_AT, direction: ASC}) {
        totalCount
        pageInfo { hasPreviousPage startCursor }
        nodes {
          author { login }
          authorAssociation
          body
          createdAt
        }
      }
    }
  }
  rateLimit { cost remaining nodeCount limit }
}
```

### It fits the limits with room to spare

GitHub's rule is that "Individual calls cannot request more than 500,000 total nodes", and that node count is the product of the `first` and `last` arguments down each nested path. This query asks for 100 reviews, 100 review threads, 20 comments inside each of those threads, and 100 issue comments, which is 100 plus 100 plus 2,000 plus 100, or 2,300. GitHub's own accounting agrees: the `rateLimit` block on the response reports `nodeCount` of exactly 2,300 and `cost` of 1. The 500,000 ceiling is two orders of magnitude away, so the node limit is not the binding constraint on a query of this shape.

The binding constraint is the per-connection cap, stated in the same document as "Values of `first` and `last` must be within 1-100". Any bound above 100 items in a single connection needs a second round trip driven by the `pageInfo` cursors, which is why they are in the query above.

### Every field exists, and the author association is on all three

Introspection confirms `authorAssociation` on `PullRequestReview`, on `PullRequestReviewComment`, and on `IssueComment`, all typed `CommentAuthorAssociation`. It is not on `PullRequestReviewThread`, which is a container rather than a comment, so a thread's association comes from its first comment.

`PullRequestReviewThread` carries `isResolved`, `isOutdated`, `isCollapsed`, `resolvedBy`, `path`, `line`, `startLine`, `diffSide`, `startDiffSide`, `subjectType`, `originalLine`, and `originalStartLine`. The individual comment inside a thread carries its own `outdated` boolean alongside `line`, `originalLine`, `path`, and `diffHunk`.

### What it returned against a real pull request

Run against pull request 10513 in `cli/cli`, a change with 84 review threads and 117 reviews:

- Reviews: 117 in total, 100 returned by `last: 100`. Author associations were `MEMBER` and `CONTRIBUTOR`. States were `APPROVED` and `COMMENTED`. Submission timestamps ran from 2025-03-06 to 2025-04-15 in ascending order, which confirms that `last:` returns the most recent reviews and that GitHub's default order for the connection is oldest first.
- Review threads: 84 in total, all 84 returned. 82 were resolved and 74 were outdated. Every `subjectType` was `LINE`.
- Issue comments: 6 in total, all returned, with author associations `MEMBER`, `CONTRIBUTOR`, and `NONE`.
- The whole response was 129,834 bytes of JSON, of which 62,475 characters were comment and review body text.

### Ordering has a hole in it

The `comments` connection on `PullRequest` takes an `orderBy` argument of type `IssueCommentOrder`. Neither `reviews` nor `reviewThreads` takes one. `reviews` takes only `first`, `last`, `before`, `after`, `states`, and `author`; `reviewThreads` takes only `first`, `last`, `before`, and `after`. A review at least carries `submittedAt`, so its position in time is recoverable after the fact. A review thread carries no timestamp at all — not a creation time, not an update time — so the only handle on a thread's recency is the position GitHub gives it in the connection, and `last:` taking the newest is an observed behavior rather than a documented guarantee.

### Where duplication creeps in

`PullRequestReview` has its own `comments` connection, and every inline comment reachable that way is also reachable through the review thread it belongs to. Requesting comments under both `reviews` and `reviewThreads` returns each inline comment twice, doubling both the node count and the payload. The resolution and staleness flags live only on the thread, so the thread is where an inline comment has to be read; the query above omits `reviews { comments }` for that reason. The link back from a comment to its review survives on `PullRequestReviewComment.pullRequestReview` if it is needed.

## What a batched review's comment entries accept

The request body for `POST /repos/{owner}/{repo}/pulls/{pull_number}/reviews` has exactly four top-level properties: `body`, `comments`, `commit_id`, and `event`. Each entry in the `comments` array is an object whose schema declares exactly seven properties — `path`, `position`, `body`, `line`, `side`, `start_line`, and `start_side` — and requires `path` and `body`.

`subject_type` is absent, and it is absent only here. The endpoint that posts one review comment at a time, `POST /repos/{owner}/{repo}/pulls/{pull_number}/comments`, declares ten properties including `subject_type`, typed as a string with the enumeration `line` and `file`. So a file-level comment is reachable only one request at a time. That endpoint also requires `body`, `commit_id`, and `path`, meaning every one of those requests repeats the commit SHA. The batched endpoint takes `commit_id` once for the whole review, and its documentation warns that "Not using the latest commit SHA may render your review comment outdated if a subsequent commit modifies the line you specify as the `position`".

The comment entry schema does not set `additionalProperties: false`, so nothing in the schema itself says whether GitHub rejects an undeclared field or accepts and ignores it.

## Cautionary findings

**An omitted `event` creates a review nobody sees.** The `event` property on the create-review endpoint chooses between `APPROVE`, `REQUEST_CHANGES`, and `COMMENT`. Leaving it out is not a neutral default: "Pull request reviews created in the `PENDING` state are not submitted", and a pending review needs a second call to the submit endpoint before anyone but its author can read it. A caller that wants a plain non-approving review has to say `COMMENT` explicitly.

**The header GitHub offers as the run-time authority does not always appear.** The documentation says that "To help you choose the correct permissions, you will receive the `X-Accepted-GitHub-Permissions` header in the REST API response." Responses to a classic OAuth token do not carry it. A `GET` against `/repos/cli/cli/pulls/10513/reviews` with such a token returned `X-Accepted-Oauth-Scopes` and `X-Oauth-Scopes` and no `X-Accepted-GitHub-Permissions` at all. The header is a fine-grained-token facility, so it can confirm a requirement from inside a job holding an installation token, and it cannot be used to check one from a developer's machine holding an ordinary personal token.

**Most reviews on a busy pull request have no body.** Of the 100 reviews returned for `cli/cli` 10513, 94 had an empty `body` string. GitHub creates a review object for a single inline comment left outside a formal review, so the reviews connection on an active pull request is mostly empty envelopes wrapping inline comments that are also in the threads. A budget that counts reviews as units of discussion will badly misjudge how much prose is actually there.

## Open threads

The permission GraphQL requires was not established. GitHub publishes fine-grained permission requirements per REST endpoint and publishes nothing equivalent for GraphQL fields, and `reviewThreads` has no REST counterpart to borrow a requirement from. The query above was run with a classic OAuth token carrying the `repo` scope, which proves the fields exist and the node accounting holds, and proves nothing about the minimum fine-grained permission. Settling it needs a fine-grained token granting Pull requests read and nothing else, or an observation from inside a real Actions job.

Whether the batched create-review endpoint rejects or silently ignores an undeclared field such as `subject_type` was not tested. Testing it means actually posting a review, which was out of scope for a documentation pass.

Whether a 422 from the create-review endpoint identifies which comment entry was out of range was not tested, for the same reason. What the schema does say narrows the possibilities. The endpoint declares three responses — 200, 403, and 422 — and its 422 references `validation_failed_simple` rather than the richer validation error used elsewhere in the API. That schema requires `message` and `documentation_url` and has one optional `errors` property, and `errors` is an array of plain strings, not of objects carrying `resource`, `field`, and `code`. So there is no structured field for GitHub to name an offending array index in. Anything identifying a bad anchor would have to be parsed out of English prose.

The two-permission case was not observed anywhere in the endpoints surveyed. Every endpoint checked here has either one permission set or two single-key alternatives, so the "all permissions in a set are required" half of the rule in `RestAuth.tsx` was confirmed only as documented behavior and never seen in the data.

## Sources

- `github/rest-api-description` — https://github.com/github/rest-api-description at `e50419c4bb8f2d1d34735044bb3b410863dc0a10`. The file read is `descriptions/api.github.com/api.github.com.json`, 12.9 MB, whose `info.version` reads `1.1.4`.
- `github/docs` — https://github.com/github/docs at `0b11cf08b8d4328a404753313d0dcd7f14bd97c6`. Files read: `src/github-apps/data/fpt-2022-11-28/server-to-server-permissions.json`, `src/github-apps/components/PermissionsList.tsx`, `src/rest/components/RestAuth.tsx`, `data/ui.yml`, `data/reusables/rest-api/additional-permissions.md`, `data/reusables/rest-api/permission-header.md`, `data/reusables/rest-api/public-access.md`, `content/rest/authentication/permissions-required-for-github-apps.md`.
- GitHub REST API reference, API version `2022-11-28`, the pages for reactions, issue comments, pull request reviews, and pull requests, read 2026-08-06. Cited for the `progAccess` payload embedded in each rendered page.
- GitHub GraphQL API documentation, "Rate limits and node limits for the GraphQL API", read 2026-08-06. Cited for the 500,000-node ceiling, the 1-to-100 range on `first` and `last`, and the point calculation.
- GitHub Actions documentation, "Workflow syntax for GitHub Actions", the `permissions` section, read 2026-08-06. Cited for the scope key list, for "`write` includes `read`", and for unspecified permissions becoming `none`.
- GitHub Actions documentation, "Controlling permissions for GITHUB_TOKEN", read 2026-08-06. Cited for the referral to the fine-grained token documentation for the parameterized permission names.
- The GitHub GraphQL schema, reached by introspection against `api.github.com` on 2026-08-06, for the fields and connection arguments on `PullRequest`, `PullRequestReview`, `PullRequestReviewThread`, `PullRequestReviewComment`, and `IssueComment`.
- Pull request 10513 in https://github.com/cli/cli, queried 2026-08-06, as the live subject the conversation query was measured against.
