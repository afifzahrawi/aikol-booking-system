from io import BytesIO
from unittest import mock

from django.core.exceptions import SuspiciousOperation
from django.test import SimpleTestCase, override_settings

from config.storage import CappedR2Storage


class CappedR2StorageTests(SimpleTestCase):
    @override_settings(R2_MEDIA_SOFT_LIMIT_BYTES=100)
    def test_write_is_refused_before_media_ceiling_is_crossed(self):
        storage = CappedR2Storage(bucket_name="media")
        storage._stored_bytes = mock.Mock(return_value=90)
        content = BytesIO(b"x" * 11)
        content.size = 11

        with self.assertRaises(SuspiciousOperation):
            storage._save("resource/test.jpg", content)

    def test_stored_bytes_sums_every_paginated_object(self):
        storage = CappedR2Storage(bucket_name="media")
        paginator = mock.Mock()
        paginator.paginate.return_value = [
            {"Contents": [{"Size": 10}, {"Size": 20}]},
            {"Contents": [{"Size": 5}]},
        ]
        client = mock.Mock()
        client.get_paginator.return_value = paginator
        storage._connections.connection = mock.Mock(meta=mock.Mock(client=client))

        self.assertEqual(storage._stored_bytes(), 35)
