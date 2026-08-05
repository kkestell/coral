# Code Style

THIS FILE MUST BE KEPT UP TO DATE AT ALL TIMES

The conventions code in this repository follows, and the rules this project has chosen for itself. Code that satisfies the formatter and the linter can still be wrong for this codebase; this is where that difference is written down.

This document is the user's. `/init` fills in only what the repository's own configuration proves, and leaves the judgment calls below for a human to answer. An unanswered heading is an open question, not a claim that the project has no opinion — delete the ones this project genuinely does not care about.

## Enforced Automatically

{The rules a tool already checks, and the file that configures each one. Name the file rather than restating its contents, so this document cannot fall out of agreement with it. The commands that run these tools live in `.agents/docs/development.md`. No formatter, linter, or type-checker is configured in this repository yet.}

- {Formatter, linter, or type-checker} — configured in `{file}`

## Naming

{What things are called: modules, types, functions, variables, test names, files. Whatever this project does consistently that a newcomer would otherwise get wrong.}

## Structure

{How code is organized within a file and across files: what belongs in one module, when something is split out, how imports are arranged, how large is too large.}

## Errors

{How failure is represented and handled — the error type, whether errors are wrapped or bare, what gets logged and what gets returned, when a failure is allowed to be swallowed.}

## Comments and Documentation

{What gets a comment and what does not, which public items are documented and in what form.}

## Preferences

{Choices this project has made that a reasonable person could have made differently, and would otherwise re-litigate in every review. Which library to reach for, which pattern is house style, which language feature is avoided here and why.}

## Project Rules

<!-- Rules that apply to every task in this repository, whether or not they concern style. One line each. This section is the user's; no ox stage writes to it. -->
