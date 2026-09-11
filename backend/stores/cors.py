"""Small, explicit CORS middleware for the separately hosted React frontend."""

from django.conf import settings
from django.http import HttpResponse


class CorsMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        origin = request.headers.get("Origin")
        allowed = origin in settings.CORS_ALLOWED_ORIGINS
        response = HttpResponse(status=204) if allowed and request.method == "OPTIONS" else self.get_response(request)
        if allowed:
            response["Access-Control-Allow-Origin"] = origin
            response["Access-Control-Allow-Credentials"] = "true"
            response["Access-Control-Allow-Headers"] = "Content-Type, X-CSRFToken, X-Store-ID"
            response["Access-Control-Allow-Methods"] = "GET, POST, PUT, PATCH, OPTIONS"
            response["Vary"] = "Origin"
        return response
