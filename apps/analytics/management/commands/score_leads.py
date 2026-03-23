from django.core.management.base import BaseCommand

from apps.leads.models import Lead
from apps.analytics.services import score_lead


class Command(BaseCommand):
    help = "Пересчитывает score для заявок"

    def add_arguments(self, parser):
        parser.add_argument("--lead-id", type=int, help="ID одной заявки")
        parser.add_argument("--all", action="store_true", help="Пересчитать все заявки")
        parser.add_argument("--limit", type=int, default=0, help="Ограничить количество заявок")

    def handle(self, *args, **options):
        lead_id = options.get("lead_id")
        rescore_all = options.get("all")
        limit = options.get("limit") or 0

        if lead_id:
            leads = Lead.objects.filter(pk=lead_id)
        elif rescore_all:
            leads = Lead.objects.all().order_by("-created_at")
        else:
            leads = Lead.objects.filter(score__isnull=True).order_by("-created_at")

        if limit > 0:
            leads = leads[:limit]

        count = 0
        for lead in leads.iterator():
            score_lead(lead)
            count += 1

        self.stdout.write(self.style.SUCCESS(f"Пересчитано заявок: {count}"))
