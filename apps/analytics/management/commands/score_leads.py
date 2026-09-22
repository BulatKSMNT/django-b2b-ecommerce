from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from apps.leads.models import Lead
from apps.analytics.services import ScoringBusy, ScoringUnavailable, pending_scores, process_score_lead


class Command(BaseCommand):
    help = "Пересчитывает score для заявок"

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--lead-id", type=int, help="ID одной заявки")
        mode.add_argument("--all", action="store_true", help="Пересчитать все заявки")
        mode.add_argument("--pending", action="store_true", help="Обработать только ожидающие расчёта заявки")
        mode.add_argument("--failed", action="store_true", help="Повторить расчёты, завершившиеся ошибкой")
        parser.add_argument("--limit", type=int, default=0, help="Ограничить количество заявок")

    def handle(self, *args, **options):
        lead_id = options.get("lead_id")
        rescore_all = options.get("all")
        limit = options.get("limit") or 0
        if limit < 0 or (lead_id is not None and lead_id < 1):
            raise CommandError("--limit должен быть неотрицательным, --lead-id — положительным.")

        pending_ids = pending_scores().values("lead_id")
        if options["pending"]:
            leads = Lead.objects.filter(pk__in=pending_ids).order_by("scoring_state__requested_at", "pk")
        elif options["failed"]:
            leads = Lead.objects.filter(scoring_state__status="error").order_by("pk")
        elif lead_id:
            leads = Lead.objects.filter(pk=lead_id)
        elif rescore_all:
            leads = Lead.objects.all().order_by("-created_at")
        else:
            # Preserve the old default (unscored leads), also picking up requested refreshes.
            leads = Lead.objects.filter(Q(score__isnull=True) | Q(pk__in=pending_ids)).order_by("-created_at")

        if limit > 0:
            leads = leads[:limit]

        count = failed = skipped = 0
        for lead in leads.select_related("scoring_state").iterator():
            state = getattr(lead, "scoring_state", None)
            force = bool(lead_id or rescore_all or options["failed"] or state is None or state.status != "pending")
            try:
                result = process_score_lead(lead.pk, force=force)
                if result is not None:
                    count += 1
                else:
                    skipped += 1
            except ScoringBusy:
                skipped += 1
            except ScoringUnavailable:
                failed += 1

        self.stdout.write(f"Пересчитано заявок: {count}; ошибок: {failed}; пропущено: {skipped}")
