"""Cloud object storage with a deliberately conservative free-tier ceiling."""

from django.conf import settings
from django.core.exceptions import SuspiciousOperation
from storages.backends.s3 import S3Storage


class CappedR2Storage(S3Storage):
    """Refuse writes before media storage can approach the provider allowance.

    Cloudflare's alerts are informational and delayed.  The application therefore
    keeps media far below the 10 GB R2 allowance instead of treating an alert as a
    spending control.  Cloud Run is limited to one instance, and the 2 GB ceiling
    leaves ample headroom even if several 5 MB uploads pass this check together.
    """

    def _stored_bytes(self) -> int:
        total = 0
        paginator = self.connection.meta.client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self.bucket_name):
            total += sum(item.get("Size", 0) for item in page.get("Contents", []))
        return total

    def _save(self, name, content):
        limit = settings.R2_MEDIA_SOFT_LIMIT_BYTES
        if self._stored_bytes() + content.size > limit:
            raise SuspiciousOperation(
                "Media storage has reached its configured safety ceiling. "
                "Remove unused images before uploading another file."
            )
        return super()._save(name, content)
