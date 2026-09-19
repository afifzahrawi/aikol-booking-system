from __future__ import annotations

from io import StringIO
from datetime import datetime, timedelta, timezone
from unittest import mock

from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings

from apps.administration.management.commands.backup_database import Command


class BackupDatabaseCommandTests(SimpleTestCase):
    @mock.patch("apps.administration.management.commands.backup_database.boto3.client")
    @mock.patch("apps.administration.management.commands.backup_database.subprocess.run")
    def test_backup_uses_pg_dump_and_uploads_an_encrypted_object(self, run, boto_client):
        storage = boto_client.return_value
        storage.get_paginator.return_value.paginate.return_value = []
        environment = {
            "DATABASE_URL": "postgresql://user:password@db.example.test/aikol",
            "R2_BACKUP_BUCKET_NAME": "aikol-backups",
            "R2_ENDPOINT_URL": "https://account.r2.cloudflarestorage.com",
            "R2_ACCESS_KEY_ID": "access",
            "R2_SECRET_ACCESS_KEY": "secret",
        }

        output = StringIO()
        with mock.patch.dict("os.environ", environment, clear=False):
            call_command("backup_database", stdout=output)

        command = run.call_args.args[0]
        self.assertEqual(command[0], "pg_dump")
        self.assertIn("--format=custom", command)
        upload = storage.upload_file.call_args
        self.assertEqual(upload.args[1], "aikol-backups")
        self.assertTrue(upload.args[2].startswith("database-backups/aikol-"))
        self.assertEqual(upload.kwargs["ExtraArgs"], {"ServerSideEncryption": "AES256"})
        self.assertIn("backup=database-backups/aikol-", output.getvalue())

    @staticmethod
    def objects(count: int, size: int) -> list[dict]:
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        return [
            {
                "Key": f"database-backups/{index:02d}.dump",
                "Size": size,
                "LastModified": start + timedelta(days=index),
            }
            for index in range(count)
        ]

    @override_settings(R2_BACKUP_SOFT_LIMIT_BYTES=100)
    def test_backup_deletes_oldest_objects_to_make_room_but_keeps_seven(self):
        storage = mock.Mock()
        Command()._make_room(storage, "backups", self.objects(9, 10), 30)
        deleted = [call.kwargs["Key"] for call in storage.delete_object.call_args_list]
        self.assertEqual(deleted, ["database-backups/00.dump", "database-backups/01.dump"])

    @override_settings(R2_BACKUP_SOFT_LIMIT_BYTES=100)
    def test_backup_refuses_write_when_seven_retained_objects_fill_ceiling(self):
        storage = mock.Mock()
        with self.assertRaises(CommandError):
            Command()._make_room(storage, "backups", self.objects(7, 14), 10)
        storage.delete_object.assert_not_called()

    @override_settings(R2_BACKUP_MAX_OBJECTS=3)
    def test_backup_prunes_count_after_successful_upload(self):
        command = Command()
        storage = mock.Mock()
        command._objects = mock.Mock(return_value=self.objects(5, 1))
        command._prune_count(storage, "backups")
        deleted = [call.kwargs["Key"] for call in storage.delete_object.call_args_list]
        self.assertEqual(deleted, ["database-backups/00.dump", "database-backups/01.dump"])
