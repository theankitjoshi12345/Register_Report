from django.contrib import admin

from .models import Store, StoreMembership


class StoreMembershipInline(admin.TabularInline):
    model = StoreMembership
    extra = 1
    autocomplete_fields = ["user"]


@admin.register(Store)
class StoreAdmin(admin.ModelAdmin):
    list_display = ["name", "created_at"]
    search_fields = ["name"]
    inlines = [StoreMembershipInline]

