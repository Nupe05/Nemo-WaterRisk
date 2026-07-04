"""Publish approved social content on a schedule (drip posting).

Posts up to --limit approved social items (oldest first) per run. Run it from
Heroku Scheduler every few hours and a batch you approved in the admin gets
spaced out across the day instead of posted all at once. Reports and other
actions are untouched — this only handles X/Instagram/YouTube items.

    python manage.py post_scheduled --limit 1
"""
from django.core.management.base import BaseCommand

from agents.action_runner import ActionError, execute_item
from core.models import ApprovalItem

SOCIAL = [
    ApprovalItem.ActionType.POST_TWITTER,
    ApprovalItem.ActionType.POST_INSTAGRAM,
    ApprovalItem.ActionType.POST_YOUTUBE,
]


class Command(BaseCommand):
    help = "Publish up to N approved social items (oldest first). For scheduled drip posting."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=1, help="Max items to post this run.")

    def handle(self, *args, **options):
        limit = max(1, options["limit"])
        queue = ApprovalItem.objects.filter(
            state=ApprovalItem.State.APPROVED, action_type__in=SOCIAL
        ).order_by("created_at")

        posted = 0
        for item in list(queue[:limit]):
            try:
                execute_item(item)
                posted += 1
                self.stdout.write(self.style.SUCCESS(f"posted #{item.pk} {item.action_type}"))
            except ActionError as exc:
                self.stderr.write(self.style.ERROR(f"failed #{item.pk}: {exc}"))

        remaining = ApprovalItem.objects.filter(
            state=ApprovalItem.State.APPROVED, action_type__in=SOCIAL
        ).count()
        self.stdout.write(f"post_scheduled done: {posted} posted, {remaining} still queued")
