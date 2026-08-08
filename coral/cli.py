"""The console script: `coral resolve`, `coral review`, `coral publish`, and `coral rehearse`."""

import argparse
import logging
import sys

from coral.publish import publish
from coral.rehearse import add_rehearse_arguments, rehearse
from coral.resolve import resolve
from coral.review import review


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    parser = argparse.ArgumentParser(prog="coral", description="Review a pull request.")
    subcommands = parser.add_subparsers(required=True)

    # The three run steps read everything from the runner's environment, so their handlers take
    # nothing; rehearse is driven by a person and takes its arguments from the command line.
    resolve_command = subcommands.add_parser("resolve", help="Decide whether to review.")
    resolve_command.set_defaults(handler=lambda arguments: resolve())

    review_command = subcommands.add_parser("review", help="Review the change and verify findings.")
    review_command.set_defaults(handler=lambda arguments: review())

    publish_command = subcommands.add_parser("publish", help="Post what this run produced.")
    publish_command.set_defaults(handler=lambda arguments: publish())

    rehearse_command = subcommands.add_parser(
        "rehearse", help="Review one commit of a local clone, with no GitHub."
    )
    add_rehearse_arguments(rehearse_command)
    rehearse_command.set_defaults(handler=rehearse)

    arguments = parser.parse_args()
    # An attribute off a Namespace is typed Any, so call the handler and return 0 separately.
    arguments.handler(arguments)
    return 0
