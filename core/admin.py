"""Django admin — this is the daily 'director seat' review surface.

The ApprovalItem admin is where you spend 15-20 minutes each morning:
approve / edit / reject what the agents drafted overnight.
"""
from django.contrib import admin
from django.utils import timezone

from . import models


@admin.register(models.Watershed)
class WatershedAdmin(admin.ModelAdmin):
    list_display = ("huc_code", "name", "created_at")
    search_fields = ("huc_code", "name")


@admin.register(models.MonitoredSite)
class MonitoredSiteAdmin(admin.ModelAdmin):
    list_display = ("reference", "name", "customer_id", "is_public_index")
    list_filter = ("is_public_index",)
    search_fields = ("reference", "name", "customer_id")


@admin.register(models.RawDataRecord)
class RawDataRecordAdmin(admin.ModelAdmin):
    list_display = ("source", "metric", "value", "observed_at", "watershed")
    list_filter = ("source", "metric")
    date_hierarchy = "observed_at"


@admin.register(models.WaterRiskScore)
class WaterRiskScoreAdmin(admin.ModelAdmin):
    list_display = ("watershed", "score", "computed_at")
    date_hierarchy = "computed_at"


@admin.register(models.RiskChange)
class RiskChangeAdmin(admin.ModelAdmin):
    list_display = ("watershed", "previous_score", "new_score", "magnitude", "content_generated")
    list_filter = ("content_generated",)


@admin.register(models.AgentTask)
class AgentTaskAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "status", "stage", "attempts", "updated_at")
    list_filter = ("status", "kind")
    search_fields = ("objective",)


@admin.register(models.ApprovalItem)
class ApprovalItemAdmin(admin.ModelAdmin):
    list_display = ("id", "content_type", "action_type", "state", "summary", "created_at")
    list_filter = ("state", "action_type", "content_type")
    actions = ("approve_selected", "reject_selected")
    readonly_fields = ("result", "executed_at")

    @admin.action(description="Approve selected items")
    def approve_selected(self, request, queryset):
        updated = queryset.filter(state=models.ApprovalItem.State.PENDING).update(
            state=models.ApprovalItem.State.APPROVED, decided_at=timezone.now()
        )
        self.message_user(request, f"Approved {updated} item(s). They run on the next sweep.")

    @admin.action(description="Reject selected items")
    def reject_selected(self, request, queryset):
        updated = queryset.filter(state=models.ApprovalItem.State.PENDING).update(
            state=models.ApprovalItem.State.REJECTED, decided_at=timezone.now()
        )
        self.message_user(request, f"Rejected {updated} item(s).")


@admin.register(models.ContentItem)
class ContentItemAdmin(admin.ModelAdmin):
    list_display = ("id", "trigger_change", "created_at")


@admin.register(models.MailboxCredential)
class MailboxCredentialAdmin(admin.ModelAdmin):
    list_display = ("customer_id", "provider", "email_address", "status", "updated_at")
    exclude = ("encrypted_tokens",)  # never render secrets in admin
