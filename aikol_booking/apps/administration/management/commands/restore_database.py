"""Restore a PostgreSQL dump from external R2 storage into the configured database.

The counterpart of `backup_database`. Two uses:

  * `--check` downloads the backup and lists what is in it, writing nothing. It
    is the "does this backup actually open" test the retention policy asks for.
  * Without it, the dump is loaded into DATABASE_URL. The target should be an
    empty database; `--clean --if-exists` drops and recreates what the dump
    contains, so a half-finished earlier attempt can be repeated.

By default the newest backup is used. Name one with `--key`. When the data is
loaded the command prints a row count for the main tables, so a restore is
judged on numbers rather than on the absence of an error: pg_restore exits
non-zero for harmless things (an extension that already exists), and a
non-zero exit alone does not mean the restore failed.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import boto3
from django.core.management.base import BaseCommand, CommandError

COUNTED_TABLES = (
    "accounts_user",
    "resources_resource",
    "bookings_booking",
    "bookings_bookingseries",
    "bookings_keyhandover",
    "audit_auditlog",
    "notifications_emailoutbox",
    "administration_systemsetting",
)


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise CommandError(f"{name} is required to restore a database backup.")
    return value


def newest_key(objects: list[dict]) -> str:
    """The most recently written backup. Raises when there is none."""
    if not objects:
        raise CommandError("No backups were found in the backup bucket.")
    return max(objects, key=lambda item: item["LastModified"])["Key"]


class Command(BaseCommand):
    help = "Restore a PostgreSQL dump from the R2 backup bucket into DATABASE_URL."
    # No system checks. They import the URL configuration, and the booking form
    # reads the booking window from the database while it is being imported, so
    # a check against an empty or unreachable database fails before the restore
    # has begun. The command talks to PostgreSQL itself and needs none of it.
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument("--key", help="Object key of the backup. Default: the newest.")
        parser.add_argument(
            "--check",
            action="store_true",
            help="Download and list the backup's contents; change no database.",
        )

    def handle(self, *args, **options):
        bucket = required("R2_BACKUP_BUCKET_NAME")
        client = boto3.client(
            "s3",
            endpoint_url=required("R2_ENDPOINT_URL"),
            aws_access_key_id=required("R2_ACCESS_KEY_ID"),
            aws_secret_access_key=required("R2_SECRET_ACCESS_KEY"),
            region_name="auto",
        )
        listing = []
        for page in client.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix="database-backups/"
        ):
            listing.extend(page.get("Contents", []))
        for item in sorted(listing, key=lambda i: i["LastModified"]):
            self.stdout.write(f"  {item['Key']}  {item['Size']:,} bytes  {item['LastModified']:%Y-%m-%d %H:%M} UTC")
        key = options["key"] or newest_key(listing)
        self.stdout.write(f"Using {key}")

        with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as handle:
            dump_path = Path(handle.name)
        try:
            client.download_file(bucket, key, str(dump_path))
            self.stdout.write(f"Downloaded {dump_path.stat().st_size:,} bytes.")
            if options["check"]:
                self._check(dump_path)
            else:
                self._restore(dump_path, required("DATABASE_URL"))
        finally:
            dump_path.unlink(missing_ok=True)

    def _run(self, command: list[str]) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(command, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise CommandError("pg_restore is not installed in this environment.") from exc

    def _check(self, dump_path: Path) -> None:
        result = self._run(["pg_restore", "--list", str(dump_path)])
        if result.returncode != 0:
            raise CommandError(f"The backup could not be read: {result.stderr.strip()[:500]}")
        lines = [ln for ln in result.stdout.splitlines() if ln and not ln.startswith(";")]
        tables = [ln for ln in lines if " TABLE DATA " in ln]
        self.stdout.write(f"The backup opens: {len(lines)} items, {len(tables)} tables with data.")
        for table in COUNTED_TABLES:
            present = any(f" {table} " in ln for ln in tables)
            self.stdout.write(f"  {table}: {'present' if present else 'MISSING'}")
        self.stdout.write(self.style.SUCCESS("check=ok"))

    def _restore(self, dump_path: Path, database_url: str) -> None:
        result = self._run(
            [
                "pg_restore",
                "--no-owner",
                "--no-privileges",
                "--clean",
                "--if-exists",
                "--dbname",
                database_url,
                str(dump_path),
            ]
        )
        # Printed trimmed: a restore into a fresh database reports a few
        # harmless errors, and a real one needs to be seen.
        if result.stderr.strip():
            self.stdout.write("pg_restore reported:")
            self.stdout.write(result.stderr.strip()[-3000:])
        from django.db import connection

        missing = []
        with connection.cursor() as cursor:
            for table in COUNTED_TABLES:
                try:
                    cursor.execute(f'SELECT count(*) FROM "{table}"')
                    self.stdout.write(f"  {table}: {cursor.fetchone()[0]} rows")
                except Exception as exc:  # noqa: BLE001 - report every missing table
                    connection.rollback()
                    missing.append(table)
                    self.stdout.write(f"  {table}: NOT RESTORED ({exc.__class__.__name__})")
        if missing:
            raise CommandError("The restore is incomplete: " + ", ".join(missing))
        self.stdout.write(self.style.SUCCESS("restore=ok"))
