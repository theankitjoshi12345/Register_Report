"""Database-backed login limits shared by API/admin and serverless instances."""

import ipaddress
import math
import unicodedata
from datetime import timedelta

from django.conf import settings
from django.db.models import F
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.utils.crypto import salted_hmac
from django.utils.deprecation import MiddlewareMixin

from .credentials import parse_login_credentials, validate_username
from .models import LoginAttemptBucket


def _client_address(request):
    address = request.META.get("REMOTE_ADDR", "")
    # Trust only Vercel's overwritten header when actually running on Vercel.
    # Generic X-Forwarded-For is user-controlled on other deployments.
    if settings.LOGIN_TRUST_VERCEL_IP:
        address = request.META.get("HTTP_X_VERCEL_FORWARDED_FOR", address)
    try:
        address = ipaddress.ip_address(address)
    except ValueError:
        return "unknown"
    if isinstance(address, ipaddress.IPv6Address):
        if address.ipv4_mapped:
            return str(address.ipv4_mapped)
        # IPv6 clients can otherwise rotate through addresses in one subnet.
        return str(ipaddress.ip_network(f"{address}/64", strict=False))
    return str(address)


def _take_attempt(scope, value, limit, now):
    key = salted_hmac("stores.login-throttle", f"{scope}:{value}", algorithm="sha256").hexdigest()
    expires_at = now + timedelta(seconds=settings.LOGIN_WINDOW_SECONDS)
    LoginAttemptBucket.objects.get_or_create(key=key, defaults={"expires_at": expires_at})
    LoginAttemptBucket.objects.filter(key=key, expires_at__lte=now).update(attempts=0, expires_at=expires_at)
    # The conditional increment is atomic, including on SQLite. A read followed
    # by a save would allow concurrent workers to exceed the configured limit.
    taken = LoginAttemptBucket.objects.filter(key=key, expires_at__gt=now, attempts__lt=limit).update(
        attempts=F("attempts") + 1,
    )
    if taken:
        return 0
    expiration = LoginAttemptBucket.objects.values_list("expires_at", flat=True).get(key=key)
    return max(1, math.ceil((expiration - now).total_seconds()))


class LoginThrottleMiddleware(MiddlewareMixin):
    def process_view(self, request, view_func, view_args, view_kwargs):
        if request.method != "POST" or request.resolver_match.view_name not in {"login", "admin:login"}:
            return None

        now = timezone.now()
        # Retain no historical IP/account counters. The indexed cleanup keeps
        # abandoned usernames from accumulating indefinitely in a serverless app.
        LoginAttemptBucket.objects.filter(expires_at__lte=now - timedelta(days=1)).delete()
        retry_after = _take_attempt("ip", _client_address(request), settings.LOGIN_IP_LIMIT, now)
        if not retry_after:
            try:
                if request.resolver_match.view_name == "login":
                    username, _ = parse_login_credentials(request.body)
                else:
                    username = validate_username(request.POST.get("username"))
            except ValueError:
                username = None
            if username:
                username = unicodedata.normalize("NFKC", username).casefold()
                retry_after = _take_attempt("account", username, settings.LOGIN_ACCOUNT_LIMIT, now)

        if not retry_after:
            return None
        message = "Too many sign-in attempts. Try again in a few minutes."
        response = (
            JsonResponse({"errors": message}, status=429)
            if request.path.startswith("/api/")
            else HttpResponse(message, status=429, content_type="text/plain")
        )
        response["Retry-After"] = str(retry_after)
        add_never_cache_headers(response)
        return response
