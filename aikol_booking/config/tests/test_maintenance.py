from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.urls import reverse


class MaintenanceEndpointTests(SimpleTestCase):
    @override_settings(MAINTENANCE_SERVICE=False)
    def test_endpoint_is_hidden_on_the_public_service(self):
        response = self.client.post(reverse("maintenance-task", args=["email"]))

        self.assertEqual(response.status_code, 404)

    @override_settings(MAINTENANCE_SERVICE=True)
    @patch("config.maintenance.call_command")
    def test_email_task_is_allow_listed(self, call_command):
        response = self.client.post(reverse("maintenance-task", args=["email"]))

        self.assertEqual(response.status_code, 200)
        call_command.assert_called_once_with("send_queued_email", limit=100)

    @override_settings(MAINTENANCE_SERVICE=True)
    @patch("config.maintenance.call_command")
    def test_unknown_task_is_not_executable(self, call_command):
        response = self.client.post(reverse("maintenance-task", args=["shell"]))

        self.assertEqual(response.status_code, 404)
        call_command.assert_not_called()

    @override_settings(MAINTENANCE_SERVICE=True)
    def test_get_is_rejected(self):
        response = self.client.get(reverse("maintenance-task", args=["email"]))

        self.assertEqual(response.status_code, 405)
