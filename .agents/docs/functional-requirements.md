# Functional Requirements

What Coral does, written as behavior someone could watch happen.

Coral is a proof of concept. The requirements below are the whole of it. Anything not listed here is out of scope until this document says otherwise.

## Trigger

- Coral reviews a pull request when that pull request is opened, and when a draft pull request is marked ready for review, in any repository where Coral has been installed. Nobody involved in the pull request has to know Coral exists to get that first review, and the author does not have to ask for it. Somebody did have to install Coral in the repository beforehand, which is the one thing Coral cannot arrange for itself. Both of those moments count, because a team that opens every pull request as a draft would otherwise never see Coral act on its own.
- A pull request that is still a draft gets no automatic review, because a draft is not finished being written. A pull request opened by a bot gets no automatic review at either of those moments, because dependency-update bots can open more pull requests in a week than people do. Neither is shut out: anybody with write access can still ask for a review and gets one.
- Coral reviews pull requests whose head branch lives in the same repository as the base branch. Pull requests from forks are out of scope, and Coral checks rather than assuming, because a fork's branch is code that nobody with write access has vouched for.
- After the automatic review, Coral reviews a pull request again only when someone asks. Pushing new commits does not start a review. Most pushes to an open pull request do not want a review, and a bot that reviews all of them teaches people to ignore it.
- Asking means leaving a comment on the pull request containing `/coral`. It works in a comment on the pull request as a whole and in a reply on the diff, and it means the same thing in both places: review the pull request. Where the comment sits attaches no meaning to the request. The body of a submitted review is not one of those places, because GitHub offers no way to react to a review and so no way to acknowledge such a request.
- The command counts only when `/coral` stands alone on its own line, with nothing before it on that line and nothing after it. It is spelled in lower case and matched exactly, so `/Coral` asks for nothing. Quoting somebody else's request, mentioning the command inside a sentence, and showing it inside a code fence all leave it inert. A line that begins with a blockquote marker is quoting, which is what GitHub's quote-reply button produces, and it is inert too. Without this, every conversation about Coral starts a review.
- Coral never reads its own comments as a request. Coral's findings arrive as comments on the diff, which is the same kind of comment a person uses to ask for a review, and a bot that can trigger itself will.
- Only someone with write access to the repository can ask for a review. A command from anybody else starts nothing, because a review costs a full agent run and a stranger should not be able to spend one.
- Coral acknowledges a request it is going to act on by adding the `eyes` reaction to the comment. It does not reply. The reaction arrives as soon as the request is accepted, not when the review is posted, because until then the person who asked has no way to tell whether Coral heard them. When several requests arrive close together and produce one review between them, every one of those requests gets its own reaction, so nobody is left watching a comment Coral appears to have ignored. A request Coral declines for lack of write access gets no reaction and no review, which does mean a person without write access cannot tell a refusal from an outage. That is accepted, on the grounds that answering would let a stranger make Coral speak.
- Coral reviews the pull request at whatever its head commit is when the review starts. A request can arrive long after the commits it concerns, and the branch can move again between the request and the start of the review, so the head is read at the start of the run rather than taken from the event that triggered it.

## What Coral Reviews

- The subject of the review is the diff between the pull request's head commit and the merge base of that commit with the base branch. Both of those commits are fixed at the start of the run and neither is read again, so the change Coral reviews is the change Coral reports on even though both branches can move while the review runs.
- Coral works from a full checkout, not from the diff alone. It reads and searches any file in the repository, whether or not the pull request touched it, because understanding a change usually means reading code the change did not touch.
- Every review covers the whole change, not only what has changed since the last review. A rebase or a force-push leaves no meaningful range of new commits to look at, and a change reads differently once the rest of it has moved underneath. Someone who asks a second time gets the change looked at afresh.
- Before reviewing, Coral reads the conversation already on the pull request. That means the reviews and findings Coral left itself last time, and the comments other people have left. Coral does not make a finding it has already made and that still stands. A finding stops standing when the thread carrying it has been resolved, or when the code beneath it has moved.
- Coral reads a bounded amount of the conversation, most recent first. When a pull request carries more than that, the review says which part went unread. A long-running pull request can accumulate hundreds of comments, and a review that quietly read a tenth of them is one that will repeat findings it could not see.
- The conversation is information about the change, never instruction about how to review. Anyone who can comment on a pull request can write anything in it, and Coral does not do what a comment tells it to do. In particular, a comment claiming that a finding was already settled is not grounds for dropping that finding, because Coral has no way to tell a maintainer's judgment from a stranger's assertion, and a bot that can be talked out of a finding can be talked out of a true one. A human who disagrees with a finding ignores it, and needs no help from Coral to do so. Asking for a review with `/coral` is not an exception to any of this. It is recognized before the review starts, by ordinary code rather than by the agent, and all it decides is whether a review runs. It never decides how one runs.

## What Coral Can Do While Reviewing

Coral is an agent, not a static analyzer. It decides for itself which of the following to use, in what order, and how many times.

- Coral runs shell commands inside the checkout.
- Coral runs individual tests and test selections that it chooses. It does not run the full test suite. Continuous integration already does that, and a pull request is assumed to arrive with its tests passing. Coral runs a test to answer a specific question it has formed about the change.
- Coral writes new test files into the checkout to confirm a behavior or to check a theory about a regression. These are scratch. They are never committed and never pushed, and they disappear with the checkout.
- Coral never writes to the repository on GitHub. It pushes no commits, creates no branches, and modifies no files outside its own checkout. Nothing Coral posts to GitHub comes from anywhere but the deterministic code that composes it, and the agent is given no credential that would let it reach GitHub on its own. Running tests, writing scratch files, and staying inside the checkout are bounded by what the agent is asked to do rather than by what the runner would stop it doing, which is what makes the missing credential the part that matters.

## Output

- A review is a summary plus a list of findings. Each finding carries the text of the finding and the place it concerns.
- A finding concerns one of four things: a span of lines in a file, a single line in a file, a whole file, or the pull request as a whole. Coral chooses which, per finding.
- A finding appears against the thing it is about. Line and span findings are anchored to that code. Whole-file findings and findings about the pull request as a whole appear in the review summary, and a whole-file finding names its file there, so a reader can tell "this file has no tests" from "this change has no tests".
- A finding that cannot be anchored where Coral asked for it is still shown to the reader, in the summary, naming the file and line it was meant for. A finding is never silently discarded because it would not attach.
- Coral posts one review per run. It does not post a comment per finding as it goes. A pull request that has been reviewed several times carries several of Coral's reviews, one per run.
- Every review names the commit it reviewed. Several of Coral's reviews can sit on one pull request, a reader needs to know which state of the branch each one is talking about, and it is also how Coral recognizes its own past work when it reviews again.
- Every review says that it is Coral's. The account the review is posted under belongs to the repository's automation rather than to Coral, so a review that did not name itself would be indistinguishable from anything else the repository's automation says.
- Posting a new review leaves the earlier ones alone. Coral does not edit, delete, or resolve its own earlier comments. GitHub marks a comment as outdated once the code beneath it changes, and that is enough to tell a reader which findings are about code that has since moved.
- When Coral finds nothing worth reporting, it says so, and it says which of two things happened. Either there was nothing to find, or everything Coral would have said is already said on this pull request and still stands. A second review that reports "nothing found" without that distinction reads as a retraction of the first one.
- Coral never approves a pull request, never requests changes, and never blocks a merge. Its review is advisory, and a human decides what to do with it.

## Failure

- When Coral cannot complete a review, it says so on the pull request, in enough detail that a human knows whether to retry or to investigate. This holds for every way a review can fail, including the ones that happen before the agent starts: a checkout that will not complete, a missing key, a runner out of disk. A review that dies quietly is worse than no review, because the author waits for it, and worse still when Coral has already reacted to the request.
- Each automatic review happens once, and a request is honored once. Somebody who asks a second time in a second comment does get a second review, even when nothing has changed, because a person who asks again after a discussion means it.
- Two reviews of the same pull request never run at the same time. A request arriving while a review is running does not start a second one and is not dropped either. It is honored once the running review has finished and posted. Several requests arriving during one review cost one further review between them, not one each, and every one of them is still acknowledged with a reaction.
- A pull request that has been closed or merged is not reviewed. Coral checks when the review starts and again before it posts, because a review takes minutes and a merge takes seconds. A review that lands after the merge is advice nobody can act on. A merge landing in the last seconds before Coral posts still wins the race, and that is accepted.
- A review that dies partway through does not stop the pull request from being reviewed again.
- A review that does not finish is discarded. Coral says it ran out of time and publishes nothing else. Findings gathered before the deadline are not posted, because a partial review is indistinguishable from a complete one and the reader has no way to tell which parts of the change went unexamined. This is not the same as a finding that would not anchor, which survives into a completed review by moving to the summary.
- A change too large to review is not reviewed. Coral says the change exceeds what it will read, and posts nothing else. This is a backstop rather than a case anyone should meet: a pull request that large is a vendored dependency or a pile of generated files rather than something somebody means to have read. Without it, one such pull request quietly spends a whole run and produces nothing.

## Out Of Scope

Named here so nobody has to guess whether the omission was deliberate.

- Forges other than GitHub.
- Pull requests from forks.
- Repositories that have not installed Coral. There is no way to review a pull request from outside the repository it lives in.
- Anything happening to a pull request other than it being opened, being marked ready for review, or somebody asking. Pushing commits, reopening a pull request, and editing a title or description all start no review.
- Asking by any means other than a comment. `/coral` in the body of a submitted review does nothing, and neither does editing an existing comment to add it. Both would be requests Coral has no way to acknowledge or no way to see.
- Replying to comments. Coral reads the conversation, reacts to a request, and adds a review. It never answers a comment or carries on a conversation.
- Steering a review from the command. Text alongside `/coral` — a file to concentrate on, a concern to prioritize — is read as conversation and not as direction.
- Any command other than asking for a review. There is no way to tell Coral to stop, to configure it, or to dismiss a finding.
- Being assigned as a reviewer. Coral has no identity of its own on GitHub to request.
- Suggested changes that a reviewer can apply with a click.
- Per-repository configuration of what Coral looks for.
- Any store of past reviews that Coral owns. What Coral knew last time is whatever it can read back off the pull request itself.
