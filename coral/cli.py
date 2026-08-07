"""The console script: `coral resolve`, `coral review`, and `coral publish`."""

import argparse
import logging
import sys

from coral.publish import publish
from coral.resolve import resolve
from coral.review import review


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    parser = argparse.ArgumentParser(prog="coral", description="Review a pull request.")
    subcommands = parser.add_subparsers(required=True)

    resolve_command = subcommands.add_parser("resolve", help="Decide whether to review.")
    resolve_command.set_defaults(handler=resolve)

    review_command = subcommands.add_parser("review", help="Review the change and verify findings.")
    review_command.set_defaults(handler=review)

    publish_command = subcommands.add_parser("publish", help="Post what this run produced.")
    publish_command.set_defaults(handler=publish)

    arguments = parser.parse_args()
    # An attribute off a Namespace is typed Any, so call the handler and return 0 separately.
    arguments.handler()
    return 0
