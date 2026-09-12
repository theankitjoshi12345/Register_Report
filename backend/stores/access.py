"""Resolve report access from the authenticated user's store memberships."""

from functools import wraps

from django.http import JsonResponse

from .models import Store


def accessible_stores(user):
    if not user.is_authenticated:
        return Store.objects.none()
    if user.is_superuser:
        return Store.objects.all()
    return Store.objects.filter(memberships__user=user)


def store_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return JsonResponse({"errors": "Sign in to access reports."}, status=401)
        stores = accessible_stores(request.user)
        selected = request.headers.get("X-Store-ID")
        if selected is not None:
            if not selected.isascii() or not selected.isdecimal() or len(selected) > 18 or int(selected) < 1:
                return JsonResponse({"errors": "Choose a valid store."}, status=400)
            store = stores.filter(pk=int(selected)).first()
            if store is None:
                return JsonResponse({"errors": "Store not found.", "code": "store_access_denied"}, status=404)
        else:
            store = stores.first()
            if store is None:
                return JsonResponse({"errors": "Your account has no store access. Ask an administrator to add you to a store.", "code": "store_access_denied"}, status=403)
        request.store = store
        response = view(request, *args, **kwargs)
        response["Cache-Control"] = "no-store"
        return response

    return wrapped
