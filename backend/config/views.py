"""Application infrastructure endpoints."""

from django.http import JsonResponse
from django.views.decorators.http import require_GET


@require_GET
def health(request):
    """Report application liveness without querying the database."""
    return JsonResponse({"status": "ok", "service": "register-report-api"})
