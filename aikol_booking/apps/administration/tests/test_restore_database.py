"""The restore command's choice of backup and its refusals."""

from __future__ import annotations

import datetime as dt

from django.core.management.base import CommandError
from django.test import SimpleTestCase

from apps.administration.management.commands.restore_database import (
    COUNTED_TABLES,
    Command,
    newest_key,
)
from django.apps import apps


class NewestBackupTests(SimpleTestCase):
    def test_the_most_recently_written_backup_is_chosen(self):
        old = {"Key": "database-backups/a.dump", "LastModified": dt.datetime(2026, 10, 1)}
        new = {"Key": "database-backups/b.dump", "LastModified": dt.datetime(2026, 10, 17)}
        self.assertEqual(newest_key([new, old]), "database-backups/b.dump")

    def test_an_empty_bucket_is_an_error_not_a_silent_success(self):
        with self.assertRaises(CommandError):
            newest_key([])

    def test_the_counted_tables_are_real_tables(self):
        real = {m._meta.db_table for m in apps.get_models()}
        self.assertTrue(set(COUNTED_TABLES) <= real, set(COUNTED_TABLES) - real)

    def test_it_runs_without_system_checks_so_an_empty_database_is_enough(self):
        self.assertEqual(Command.requires_system_checks, [])
