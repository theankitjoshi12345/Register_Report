"""Recalculate saved totals after upgrading reconciliation rules."""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import DatabaseError

from reports.views import recalculate_store_history
from stores.models import Store


class Command(BaseCommand):
    help = "Recalculate report history atomically for each store, preserving entered values."

    def add_arguments(self, parser):
        parser.add_argument("--store", type=int, help="Only recalculate this store ID.")
        parser.add_argument("--dry-run", action="store_true", help="Validate the recalculation and roll back every change.")

    def handle(self, *args, **options):
        stores = Store.objects.order_by("pk")
        if options["store"] is not None:
            stores = stores.filter(pk=options["store"])
            if not stores.exists():
                raise CommandError(f"Store {options['store']} does not exist.")
        for store in stores:
            try:
                count = recalculate_store_history(store, dry_run=options["dry_run"])
            except (ValidationError, DatabaseError) as error:
                details = "; ".join(error.messages) if isinstance(error, ValidationError) else str(error)
                raise CommandError(f"Store {store.pk} was not changed: {details}") from error
            action = "Validated" if options["dry_run"] else "Recalculated"
            suffix = " No changes saved." if options["dry_run"] else ""
            self.stdout.write(self.style.SUCCESS(f"{action} {count} report(s) for store {store.pk}.{suffix}"))
