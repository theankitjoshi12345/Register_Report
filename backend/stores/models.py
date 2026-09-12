"""Stores and the users allowed to enter and review their reports."""

from django.conf import settings
from django.db import models


class Store(models.Model):
    name = models.CharField(max_length=120)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name", "id"]

    def __str__(self):
        return self.name


class StoreMembership(models.Model):
    store = models.ForeignKey(Store, on_delete=models.CASCADE, related_name="memberships")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="store_memberships",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["store", "user"], name="unique_store_member"),
        ]

    def __str__(self):
        return f"{self.user} — {self.store}"


class LoginAttemptBucket(models.Model):
    """Shared login limits; keys contain keyed hashes, never credentials or IPs."""

    key = models.CharField(max_length=64, primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)
