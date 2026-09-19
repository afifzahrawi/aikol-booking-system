"""Create an encrypted-at-rest PostgreSQL dump in external R2 storage."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path

import boto3
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


def required(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise CommandError(f"{name} is required to create an external database backup.")
    return value


class Command(BaseCommand):
    help = "Upload a PostgreSQL custom-format dump to the configured R2 backup bucket."

    def handle(self, *args, **options):
        database_url = required("DATABASE_URL")
        bucket = required("R2_BACKUP_BUCKET_NAME")
        timestamp = timezone.now().strftime("%Y%m%dT%H%M%SZ")
        object_key = f"database-backups/aikol-{timestamp}.dump"

        with tempfile.NamedTemporaryFile(suffix=".dump", delete=False) as temporary:
            dump_path = Path(temporary.name)

        try:
            try:
                subprocess.run(
                    [
                        "pg_dump",
                        "--format=custom",
                        "--no-owner",
                        "--no-privileges",
                        "--file",
                        str(dump_path),
                        database_url,
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except FileNotFoundError as exc:
                raise CommandError("pg_dump is not installed in this environment.") from exc
            except subprocess.CalledProcessError as exc:
                detail = (exc.stderr or "pg_dump failed").strip()
                raise CommandError(detail) from exc

            client = boto3.client(
                "s3",
                endpoint_url=required("R2_ENDPOINT_URL"),
                aws_access_key_id=required("R2_ACCESS_KEY_ID"),
                aws_secret_access_key=required("R2_SECRET_ACCESS_KEY"),
                region_name="auto",
            )
            current = self._objects(client, bucket)
            self._make_room(client, bucket, current, dump_path.stat().st_size)
            client.upload_file(
                str(dump_path),
                bucket,
                object_key,
                ExtraArgs={"ServerSideEncryption": "AES256"},
            )
            self._prune_count(client, bucket)
        finally:
            dump_path.unlink(missing_ok=True)

        self.stdout.write(self.style.SUCCESS(f"backup={object_key}"))

    @staticmethod
    def _objects(client, bucket: str) -> list[dict]:
        objects = []
        paginator = client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix="database-backups/"):
            objects.extend(page.get("Contents", []))
        return sorted(objects, key=lambda item: item["LastModified"])

    def _make_room(self, client, bucket: str, objects: list[dict], new_size: int) -> None:
        limit = settings.R2_BACKUP_SOFT_LIMIT_BYTES
        total = sum(item.get("Size", 0) for item in objects)
        removable = list(objects)
        while total + new_size > limit and len(removable) > 7:
            oldest = removable.pop(0)
            client.delete_object(Bucket=bucket, Key=oldest["Key"])
            total -= oldest.get("Size", 0)
        if total + new_size > limit:
            raise CommandError(
                "The backup safety ceiling would be exceeded. At least seven recent "
                "backups were preserved and no new object was uploaded."
            )

    def _prune_count(self, client, bucket: str) -> None:
        objects = self._objects(client, bucket)
        excess = max(0, len(objects) - settings.R2_BACKUP_MAX_OBJECTS)
        for item in objects[:excess]:
            client.delete_object(Bucket=bucket, Key=item["Key"])
