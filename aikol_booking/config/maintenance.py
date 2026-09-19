"""Private request-based maintenance endpoints for Cloud Scheduler.

These URLs exist in both container deployments, but are deliberately invisible
unless the dedicated private maintenance service enables them. Cloud Run IAM
authenticates Scheduler before Django receives the request.
"""

from django.conf import settings
from django.core.management import call_command
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


COMMANDS = {
    "email": ("send_queued_email", {"limit": 100}),
    "complete": ("complete_bookings", {}),
    "backup": ("backup_database", {}),
}


@csrf_exempt
@require_POST
def run_maintenance(request, task: str):
    """Run one allow-listed task on the IAM-protected maintenance service."""

    if not getattr(settings, "MAINTENANCE_SERVICE", False):
        raise Http404

    try:
        command, options = COMMANDS[task]
    except KeyError as exc:
        raise Http404 from exc

    call_command(command, **options)
    return JsonResponse({"status": "completed", "task": task})
