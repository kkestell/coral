"""The console script: `coral resolve`, `coral review`, and `coral report`."""

import argparse


def resolve() -> None:
    raise NotImplementedError


def review() -> None:
    raise NotImplementedError


def report() -> None:
    raise NotImplementedError


def main() -> int:
    parser = argparse.ArgumentParser(prog="coral", description="Review a pull request.")
    subcommands = parser.add_subparsers(required=True)

    resolve_command = subcommands.add_parser("resolve", help="Decide whether to review.")
    resolve_command.set_defaults(handler=resolve)

    review_command = subcommands.add_parser("review", help="Review the change and post the result.")
    review_command.set_defaults(handler=review)

    report_command = subcommands.add_parser("report", help="Report a failure on the way here.")
    report_command.set_defaults(handler=report)

    arguments = parser.parse_args()
    # An attribute off a Namespace is typed Any, so call the handler and return 0 separately.
    arguments.handler()
    return 0
