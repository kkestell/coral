# Development

THIS FILE MUST BE KEPT UP TO DATE AT ALL TIMES

A scaffold, not a cage. Drop sections that don't apply and expand the ones that matter.

Everything needed to build, run, and check this project on a working machine. Every command here is a real command from this repository — never a plausible guess.

## Prerequisites

{The toolchain and its versions, plus anything that has to exist outside the repository — a database, a container runtime, a credential. Where a version is pinned in a file, name the file rather than repeating the number, so this document cannot drift out of agreement with it.}

- {Tool and version, or the file that pins it}

## Setup

{What a fresh checkout needs before any of the commands below will work: installing dependencies, creating a config file from an example, running migrations, seeding data. Numbered steps, in order. Omit this section if `git clone` is enough.}

1. {Step}

## Commands

{The commands this project actually defines. Omit any line you cannot verify from a manifest, a task runner, a CI config, or the README. If distinct parts of the project have different toolchains, use one subsection per part.}

- Build: `{command}`
- Run: `{command}`
- Test: `{command}`
- Lint: `{command}`
- Format: `{command}`
- Type-check: `{command}`

## Environment

{The environment variables the project reads, one line each: what it is for, whether it is required, and where a real value comes from. Coral needs at least an OpenRouter credential and something that authorizes it against the forge it comments on, but the variable names are not chosen yet. Name the file that documents or loads them — `.env.example`, a config module — and never record a secret here.}

- `{VAR}` — {what it controls, required or optional, where the value comes from}

## Services and Ports

{What listens where when the project is running locally, including anything started by a container definition. Omit if nothing does.}

- {Service} — {port, and how it is started}

## Gotchas

{The things that waste an hour: a step that must run after a dependency change, a cache that has to be cleared, a command that fails in a confusing way for a mundane reason. One line each, and only what this repository actually does.}

- {Gotcha}
