from django.core.management.base import BaseCommand
from django.db.models import Q
from django.utils import timezone

from apps.leads.management_service import check_lead_sla
from apps.leads.models import LeadHandlingCycle
from apps.leads.sla import overdue_cycles_filter, warning_cycles_filter


class Command(BaseCommand):
    help = "Проверить предупреждения и просрочки SLA и следующих действий (повторный запуск безопасен)."

    def handle(self, *args, **options):
        now = timezone.now()
        lead_ids = LeadHandlingCycle.objects.filter(ended_at__isnull=True).filter(
            overdue_cycles_filter(now) | warning_cycles_filter(now)
            | Q(lead__next_action_at__lte=now) | Q(lead__next_action_remind_at__lte=now)
        ).values_list("lead_id", flat=True)
        count = sum(check_lead_sla(pk, now) for pk in lead_ids.iterator())
        self.stdout.write(self.style.SUCCESS(f"Создано событий SLA и напоминаний: {count}"))
