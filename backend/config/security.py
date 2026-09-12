"""Bound API request parsing and prevent caching of private API responses."""

from django.conf import settings
from django.core.exceptions import RequestDataTooBig
from django.http import JsonResponse
from django.utils.cache import patch_vary_headers


class ApiBoundaryMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if not request.path.startswith("/api/"):
            return self.get_response(request)

        response = None
        if request.method in ("POST", "PUT", "PATCH", "DELETE"):
            limit = 16 * 1024 if request.path == "/api/auth/login/" else settings.DATA_UPLOAD_MAX_MEMORY_SIZE
            try:
                content_length = int(request.META.get("CONTENT_LENGTH") or 0)
                if content_length < 0:
                    raise ValueError
                if content_length > limit or len(request.body) > limit:
                    raise RequestDataTooBig
            except RequestDataTooBig:
                response = JsonResponse({"errors": "The request is too large. Reduce the number or size of entries."}, status=413)
            except ValueError:
                response = JsonResponse({"errors": "Invalid request length."}, status=400)
        if response is None:
            response = self.get_response(request)
        # Include errors and unauthorized responses, not just successful views.
        response["Cache-Control"] = "private, no-store"
        patch_vary_headers(response, ("Cookie", "X-Store-ID"))
        return response
