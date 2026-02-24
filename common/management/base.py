"""
Shared base command class for Doorito management commands.

Provides common argument patterns (--dry-run, --json) and
helper methods used across multiple commands.
"""

import json
import time

from django.core.management.base import BaseCommand


class DooritoBaseCommand(BaseCommand):
    """
    Base command with common patterns for Doorito commands.

    Subclasses can set class attributes to opt-in to common arguments:
        supports_dry_run = True — adds --dry-run flag
        supports_json = True    — adds --json flag
    """

    supports_dry_run = False
    supports_json = False

    def add_arguments(self, parser):
        if self.supports_dry_run:
            parser.add_argument(
                "--dry-run",
                action="store_true",
                help="Show what would happen without making changes",
            )
        if self.supports_json:
            parser.add_argument(
                "--json",
                action="store_true",
                dest="json_output",
                help="Output results as JSON",
            )

    def output_json(self, data):
        """Write data as formatted JSON to stdout."""
        self.stdout.write(json.dumps(data, indent=2, default=str))

    def start_timer(self):
        """Start the execution timer."""
        self._start_time = time.time()

    def elapsed(self):
        """Return elapsed time since start_timer() in seconds."""
        return time.time() - getattr(self, "_start_time", time.time())
