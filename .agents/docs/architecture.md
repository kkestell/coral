# Architecture

THIS FILE MUST BE KEPT UP TO DATE AT ALL TIMES

A scaffold, not a cage. Drop sections that don't apply and expand the ones that matter.

What this project is built out of, where each part lives, and how the parts fit together. Read this before planning a change, so the change lands where the code already expects it to.

## Tech Stack

- **Language(s):** Python — {version, and the file that pins it}
- **Frameworks:** DeepAgents
- **Build system:** `uv`, against a committed lockfile
- **Datastores:** DynamoDB — one table of review records, keyed by repository and pull request number. It is what Coral knows about its own past and current work, and nothing else about a review is persisted.
- **Model provider:** OpenRouter — `~deepseek/deepseek-v4-flash-latest`
- **Deployment target:** AWS `us-east-1`, provisioned with Terraform — a Lambda function URL receiving webhooks, SQS carrying work to a second Lambda that runs the review, DynamoDB, and Secrets Manager

## Codebase Map

{A short description of each major part of the codebase — what it is, what it does, and where it lives. Organize this however suits the project: by directory, by layer, by domain area. One line per entry. Only break into subsections if the project has genuinely separate deployable units with different stacks, such as "### Client" and "### Server".}

- `{path/}` — {what this part does}

## How It Fits Together

{The path a real unit of work takes through the parts named above: a pull request event arriving, the repository being cloned, the tests being run, the review being written, the comments being posted. Name the modules it passes through in order, and say where the significant boundaries are — the layer everything goes through, the seam where the domain stops and the framework starts, the one place a particular kind of state is allowed to change. This is the section that saves a plan from putting new code in the wrong place, so write it as prose rather than a list.}

## Invariants

{Facts that stay true as the code moves, recorded so a later plan does not have to re-derive them. One line each. `/build` appends to this section as plans land.}

- {Invariant}
