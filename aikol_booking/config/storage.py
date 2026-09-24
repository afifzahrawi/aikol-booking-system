"""Cloud object storage with a deliberately conservative free-tier ceiling."""

import hashlib

from django.conf import settings
from django.core.cache import cache
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

    def url(self, name, parameters=None, expire=None, http_method=None):
        # A signed URL carries its signing time, so signing afresh on every page
        # gives the browser a new address for the same image each time: it
        # downloads the header logo again on every click and the logo flashes.
        # Reusing one URL for most of its lifetime lets the browser cache it.
        if parameters or expire or http_method:
            return super().url(name, parameters, expire, http_method)
        key = "r2-url:" + hashlib.sha256(name.encode()).hexdigest()
        signed = cache.get(key)
        if signed is None:
            signed = super().url(name)
            # Leave ten minutes of validity for a page rendered just before expiry.
            reuse = max(self.querystring_expire - 600, 0)
            if reuse:
                cache.set(key, signed, reuse)
        return signed
