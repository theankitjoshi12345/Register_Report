"""Session login for the React app, using Django's session and CSRF protections."""

import json

from django.contrib.auth import authenticate, login, logout
from django.http import JsonResponse
from django.middleware.csrf import get_token
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import ensure_csrf_cookie
from django.views.decorators.http import require_GET, require_POST

from .access import accessible_stores


def session_data(request):
    user = request.user
    return {
        "user": {"id": user.pk, "username": user.get_username()} if user.is_authenticated else None,
        "stores": list(accessible_stores(user).values("id", "name")),
        "csrfToken": get_token(request),
    }


@never_cache
@ensure_csrf_cookie
@require_GET
def session(request):
    return JsonResponse(session_data(request))


@never_cache
@require_POST
def sign_in(request):
    try:
        if len(request.body) > 16384:
            raise ValueError
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError
        username, password = data.get("username"), data.get("password")
        if not isinstance(username, str) or not isinstance(password, str) or not username.strip() or not password:
            raise ValueError
        if len(username) > 150 or len(password) > 4096:
            raise ValueError
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({"errors": "Enter your username and password."}, status=400)
    user = authenticate(request, username=username.strip(), password=password)
    if user is None:
        return JsonResponse({"errors": "The username or password is incorrect."}, status=401)
    login(request, user)
    return JsonResponse(session_data(request))


@never_cache
@require_POST
def sign_out(request):
    logout(request)
    return JsonResponse(session_data(request))


def csrf_failure(request, reason=""):
    if request.path.startswith("/api/"):
        return JsonResponse({"errors": "Your session token has expired. Reload the page and try again."}, status=403)
    from django.views.csrf import csrf_failure as default_csrf_failure

    return default_csrf_failure(request, reason=reason)

