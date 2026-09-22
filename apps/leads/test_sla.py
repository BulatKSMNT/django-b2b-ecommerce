from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier, Event
from unittest.mock import patch

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import close_old_connections, connection, connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analytics.models import LeadScore
from apps.leads import management_service as operations
from apps.leads.models import Lead, LeadEvent, LeadHandlingCycle, Notification, SLAPolicy
from apps.leads.sla import next_action_summary, sla_summary
from apps.leads.test_management import LeadFixtures


class SLARulesTests(LeadFixtures, TestCase):
    def setUp(self):
        self.setup_leads()

    def policy(self, **changes):
        return operations.create_sla_policy(
            actor=self.supervisor, response_minutes=240, resolution_minutes=1440, **changes,
        )

    def test_missing_score_uses_agreed_medium_and_freezes_full_policy(self):
        self.policy(priority_overrides={"medium": {"response_minutes": 30, "resolution_minutes": 120}})
        lead = self.make_lead()
        cycle = lead.cycles.get()
        self.assertFalse(LeadScore.objects.filter(lead=lead).exists())
        self.assertEqual((cycle.priority, cycle.priority_source), ("medium", "default"))
        self.assertEqual(cycle.response_due_at - cycle.started_at, timedelta(minutes=30))
        self.assertEqual(cycle.response_warning_at - cycle.started_at, timedelta(minutes=24))
        self.assertEqual(cycle.policy_snapshot["applied_priority"], "medium")
        self.assertEqual(cycle.policy_snapshot["effective_resolution_minutes"], 120)
        self.assertEqual(cycle.policy_snapshot["response_basis"], "outbound_attempt")

    def test_existing_score_selects_priority_but_later_score_does_not_move_deadlines(self):
        self.policy(priority_overrides={"high": {"response_minutes": 10, "resolution_minutes": 60}})
        lead = Lead.objects.create(fullname="Клиент", email="client@example.com", phone_number="+79991234567")
        score = LeadScore.objects.create(lead=lead, score=95, priority="high")
        operations.initialize_lead(lead)
        cycle = lead.cycles.get()
        self.assertEqual((cycle.priority, cycle.priority_source), ("high", "score"))
        self.assertEqual(cycle.response_due_at - cycle.started_at, timedelta(minutes=10))
        self.assertEqual(cycle.policy_snapshot["score"]["value"], "95.00")
        snapshot = cycle.policy_snapshot
        LeadScore.objects.filter(pk=score.pk).update(priority="low", score=5)
        self.policy(default_priority="low", warning_percent=90)
        cycle.refresh_from_db()
        self.assertEqual(cycle.policy_snapshot, snapshot)
        self.assertEqual(sla_summary(lead)["priority"], "high")

    def test_reassignment_preserves_snapshot_and_reopening_uses_new_settings(self):
        self.operate(operations.claim_lead)
        old = self.lead.cycles.get()
        snapshot = old.policy_snapshot.copy()
        self.policy(warning_percent=50, priority_overrides={"medium": {"response_minutes": 20, "resolution_minutes": 60}})
        self.operate(operations.assign_lead, actor=self.supervisor, assignee_id=self.other.pk)
        old.refresh_from_db()
        self.assertEqual(old.policy_snapshot, snapshot)
        self.operate(operations.close_lead, actor=self.other, status="canceled", result="Отказ")
        self.operate(operations.reopen_lead, actor=self.other, reason="Вернулся")
        current = self.lead.cycles.get(ended_at__isnull=True)
        self.assertEqual(current.response_due_at - current.started_at, timedelta(minutes=20))
        self.assertEqual(current.response_warning_at - current.started_at, timedelta(minutes=10))
        self.assertIsNone(current.first_response_at)
        self.assertNotEqual(current.policy_snapshot["version"], snapshot["version"])

    def test_views_comments_and_inbound_contact_are_not_first_response(self):
        self.operate(operations.claim_lead)
        self.operate(operations.add_comment, text="Посмотрел заявку")
        self.operate(operations.register_interaction, channel="email", direction="inbound", result="success", description="Входящее письмо")
        client = APIClient()
        client.force_authenticate(self.manager)
        self.assertEqual(client.get(f"/api/v1/crm/leads/{self.lead.pk}/").status_code, 200)
        cycle = self.lead.cycles.get()
        self.assertIsNone(cycle.first_response_at)
        self.assertIsNotNone(cycle.first_contact_at)
        self.assertEqual(operations.check_lead_sla(self.lead.pk, cycle.response_due_at), 1)

    def test_unsuccessful_outbound_attempt_is_a_response_but_not_successful_contact(self):
        self.operate(operations.claim_lead)
        self.operate(operations.change_status, status="in_progress")
        self.operate(operations.register_interaction, channel="phone", direction="outbound", result="failed", description="Не удалось дозвониться")
        cycle = self.lead.cycles.get()
        self.assertIsNotNone(cycle.first_response_at)
        self.assertIsNone(cycle.first_contact_at)
        self.assertEqual(operations.check_lead_sla(self.lead.pk, cycle.response_due_at), 0)
        with self.assertRaises(ValidationError):
            self.operate(operations.change_status, status="contacted")

    def test_earliest_registered_outbound_attempt_is_used(self):
        self.operate(operations.claim_lead)
        now = timezone.now()
        LeadHandlingCycle.objects.filter(lead=self.lead).update(started_at=now - timedelta(hours=2))
        first = now - timedelta(minutes=20)
        for occurred in [first, now - timedelta(minutes=30), now - timedelta(minutes=5)]:
            self.operate(operations.register_interaction, channel="phone", direction="outbound", result="no_answer", description="Попытка", occurred_at=occurred)
        self.assertEqual(self.lead.cycles.get().first_response_at, now - timedelta(minutes=30))

    def test_late_response_is_breached_and_stops_future_response_notifications(self):
        self.operate(operations.claim_lead)
        now = timezone.now()
        LeadHandlingCycle.objects.filter(lead=self.lead).update(started_at=now - timedelta(hours=2), response_due_at=now - timedelta(hours=1))
        self.operate(operations.register_interaction, channel="phone", direction="outbound", result="no_answer", description="Поздняя попытка")
        self.assertEqual(sla_summary(self.lead)["response"]["state"], "breached")
        self.assertEqual(operations.check_lead_sla(self.lead.pk), 0)

    def test_warning_and_overdue_are_sent_once_at_exact_boundaries(self):
        self.operate(operations.claim_lead)
        cycle = self.lead.cycles.get()
        self.assertEqual(operations.check_lead_sla(self.lead.pk, cycle.response_warning_at - timedelta(microseconds=1)), 0)
        self.assertEqual(operations.check_lead_sla(self.lead.pk, cycle.response_warning_at), 1)
        self.assertEqual(operations.check_lead_sla(self.lead.pk, cycle.response_warning_at), 0)
        self.assertEqual(sla_summary(self.lead, cycle.response_warning_at)["response"]["state"], "warning")
        self.assertEqual(operations.check_lead_sla(self.lead.pk, cycle.response_due_at), 1)
        self.assertEqual(operations.check_lead_sla(self.lead.pk, cycle.response_due_at), 0)
        self.assertEqual(sla_summary(self.lead, cycle.response_due_at)["response"]["state"], "overdue")
        event = self.lead.history_events.get(kind="sla_response_warning")
        self.assertEqual(set(event.notifications.values_list("recipient_id", flat=True)), {self.manager.pk, self.supervisor.pk, self.administrator.pk})

    def test_missed_warning_window_does_not_create_stale_warning(self):
        cycle = self.lead.cycles.get()
        self.assertEqual(operations.check_lead_sla(self.lead.pk, cycle.response_due_at), 1)
        self.assertFalse(self.lead.history_events.filter(kind="sla_response_warning").exists())

    def test_next_action_is_separate_and_rescheduling_creates_a_new_reminder_revision(self):
        self.operate(operations.claim_lead)
        cycle = self.lead.cycles.get()
        due = timezone.now() + timedelta(hours=2)
        self.operate(operations.set_next_action, next_action="Позвонить", next_action_at=due)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.next_action_remind_at, due - timedelta(minutes=30))
        self.assertEqual(operations.check_lead_sla(self.lead.pk, due - timedelta(minutes=30)), 1)
        self.operate(operations.add_comment, text="Без нового напоминания")
        self.assertEqual(operations.check_lead_sla(self.lead.pk, due - timedelta(minutes=30)), 0)
        self.assertEqual(operations.check_lead_sla(self.lead.pk, due), 1)
        self.assertEqual(next_action_summary(self.lead, due)["state"], "overdue")
        self.assertEqual(sla_summary(self.lead, due)["response"]["state"], "pending")
        event = self.lead.history_events.get(kind="next_action_warning")
        self.assertEqual(list(event.notifications.values_list("recipient_id", flat=True)), [self.manager.pk])
        self.operate(operations.set_next_action, next_action="Позвонить ещё раз", next_action_at=due)
        self.assertEqual(operations.check_lead_sla(self.lead.pk, due - timedelta(minutes=30)), 1)
        self.assertEqual(list(self.lead.history_events.filter(kind="next_action_warning").values_list("reminder_revision", flat=True)), [1, 2])
        cycle.refresh_from_db()
        self.assertEqual(cycle.response_due_at, self.lead.created_at + timedelta(minutes=240))

    def test_next_action_settings_are_copied_when_scheduling_and_can_be_disabled(self):
        self.operate(operations.claim_lead)
        due = timezone.now() + timedelta(hours=2)
        with override_settings(CRM_NEXT_ACTION_REMINDER_MINUTES=10):
            self.operate(operations.set_next_action, next_action="Действие", next_action_at=due)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.next_action_remind_at, due - timedelta(minutes=10))
        with override_settings(CRM_NEXT_ACTION_REMINDER_MINUTES=0):
            self.operate(operations.set_next_action, next_action="Действие", next_action_at=due)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.next_action_remind_at)
        self.assertEqual(operations.check_lead_sla(self.lead.pk, due - timedelta(minutes=1)), 0)
        self.assertEqual(operations.check_lead_sla(self.lead.pk, due), 1)

    def test_close_cancels_future_checks_and_reopen_has_no_old_next_action(self):
        self.operate(operations.claim_lead)
        self.operate(operations.set_next_action, next_action="Звонок", next_action_at=timezone.now() + timedelta(hours=1))
        self.operate(operations.close_lead, status="canceled", result="Отказ")
        self.assertEqual(operations.check_lead_sla(self.lead.pk, timezone.now() + timedelta(days=2)), 0)
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.next_action_remind_at)
        self.operate(operations.reopen_lead, reason="Вернулся")
        self.lead.refresh_from_db()
        self.assertEqual(next_action_summary(self.lead)["state"], "not_scheduled")

    def test_failed_notification_rolls_back_alert_and_does_not_change_lead_version(self):
        cycle = self.lead.cycles.get()
        with patch("apps.leads.management_service._notify", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                operations.check_lead_sla(self.lead.pk, cycle.response_warning_at)
        self.assertFalse(self.lead.history_events.filter(kind="sla_response_warning").exists())
        self.assertEqual(operations.check_lead_sla(self.lead.pk, cycle.response_warning_at), 1)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.version, 1)

    def test_command_checks_warnings_and_independent_reminders_idempotently(self):
        self.operate(operations.claim_lead)
        due = timezone.now() + timedelta(minutes=10)
        self.operate(operations.set_next_action, next_action="Скоро звонок", next_action_at=due)
        output = StringIO()
        call_command("check_lead_sla", stdout=output)
        self.assertIn("напоминаний: 1", output.getvalue())
        output = StringIO()
        call_command("check_lead_sla", stdout=output)
        self.assertIn("напоминаний: 0", output.getvalue())

    def test_policy_api_validates_priority_rules_and_returns_snapshot_in_card(self):
        client = APIClient()
        client.force_authenticate(self.supervisor)
        data = {"response_minutes": 60, "resolution_minutes": 120, "default_priority": "medium",
                "warning_percent": 75, "priority_overrides": {"high": {"response_minutes": 10, "resolution_minutes": 30}}}
        response = client.post("/api/v1/crm/sla-policies/", data, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        for extra in [
            {"default_priority": "unknown"}, {"warning_percent": 100},
            {"priority_overrides": {"urgent": {"response_minutes": 10, "resolution_minutes": 30}}},
            {"priority_overrides": {"high": {"response_minutes": 30, "resolution_minutes": 10}}},
            {"priority_overrides": {"high": {"response_minutes": 10, "resolution_minutes": 30, "extra": 1}}},
        ]:
            invalid = client.post("/api/v1/crm/sla-policies/", {**data, **extra}, format="json")
            self.assertEqual(invalid.status_code, 400, invalid.data)
        lead = self.make_lead()
        card = client.get(f"/api/v1/crm/leads/{lead.pk}/").data
        self.assertEqual(card["sla"]["priority"], "medium")
        self.assertEqual(card["current_cycle"]["policy_snapshot"]["warning_percent"], 75)
        self.assertIn("next_action_reminder", card)

    def test_lists_dashboard_and_filters_use_outbound_reaction_and_separate_next_action(self):
        self.operate(operations.claim_lead)
        now = timezone.now()
        LeadHandlingCycle.objects.filter(lead=self.lead).update(response_warning_at=now - timedelta(minutes=1))
        self.operate(operations.set_next_action, next_action="Действие", next_action_at=now + timedelta(minutes=10))
        client = APIClient()
        client.force_authenticate(self.manager)
        listing = client.get("/api/v1/crm/leads/", {"warning": "true", "next_action_warning": "true"})
        self.assertEqual(listing.data["count"], 1)
        self.assertEqual(listing.data["results"][0]["sla"]["response"]["state"], "warning")
        dashboard = client.get("/api/v1/crm/dashboard/").data
        self.assertEqual(dashboard["leads"]["sla_warning"], 1)
        self.assertEqual(dashboard["leads"]["next_action_warning"], 1)
        self.operate(operations.register_interaction, channel="phone", direction="outbound", result="no_answer", description="Позвонил")
        self.assertEqual(client.get("/api/v1/crm/leads/", {"warning": "true"}).data["count"], 0)
        self.assertEqual(client.get("/api/v1/crm/leads/", {"next_action_warning": "true"}).data["count"], 1)


class SLAMigrationTests(TransactionTestCase):
    def test_existing_deadlines_are_preserved_and_response_uses_real_outbound_records(self):
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        target = [("leads", "0004_import_existing_leads")]
        executor.migrate(target)
        try:
            apps = executor.loader.project_state(target).apps
            Lead = apps.get_model("leads", "Lead")
            Cycle = apps.get_model("leads", "LeadHandlingCycle")
            Interaction = apps.get_model("leads", "LeadInteraction")
            Policy = apps.get_model("leads", "SLAPolicy")
            policy, _ = Policy.objects.get_or_create(version=1)
            now = timezone.now()
            lead = Lead.objects.create(fullname="Клиент", phone_number="+79991234567", email="legacy@example.com", next_action_at=now + timedelta(hours=1))
            cycle = Cycle.objects.create(lead=lead, number=1, started_at=now, policy=policy,
                                         response_due_at=now + timedelta(hours=4), resolution_due_at=now + timedelta(days=1),
                                         first_contact_at=now + timedelta(minutes=1))
            Interaction.objects.create(lead=lead, cycle=cycle, channel="phone", direction="inbound", result="success", description="Входящий", occurred_at=now + timedelta(minutes=1))
            Interaction.objects.create(lead=lead, cycle=cycle, channel="phone", direction="outbound", result="no_answer", description="Попытка", occurred_at=now + timedelta(minutes=2))
            MigrationExecutor(connection).migrate(latest)
            from apps.leads.models import Lead as CurrentLead, LeadHandlingCycle as CurrentCycle
            current = CurrentCycle.objects.get(pk=cycle.pk)
            self.assertEqual(current.response_due_at, cycle.response_due_at)
            self.assertEqual(current.resolution_due_at, cycle.resolution_due_at)
            self.assertEqual(current.first_contact_at, cycle.first_contact_at)
            self.assertEqual(current.first_response_at, now + timedelta(minutes=2))
            self.assertEqual(current.priority_source, "legacy")
            self.assertEqual(current.policy_snapshot["effective_response_minutes"], 240)
            self.assertIsNone(current.response_warning_at)
            self.assertIsNone(current.resolution_warning_at)
            self.assertEqual(CurrentLead.objects.get(pk=lead.pk).next_action_revision, 1)
            self.assertFalse(LeadEvent.objects.exists())
            self.assertFalse(Notification.objects.exists())
        finally:
            MigrationExecutor(connection).migrate(latest)


@skipUnlessDBFeature("has_select_for_update")
class SLAConcurrencyTests(LeadFixtures, TransactionTestCase):
    def setUp(self):
        self.setup_leads()

    def test_parallel_warning_checks_have_one_event_and_one_notification_per_recipient(self):
        self.operate(operations.claim_lead)
        warning_at = self.lead.cycles.get().response_warning_at
        barrier = Barrier(2)

        def run():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return operations.check_lead_sla(self.lead.pk, warning_at)
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: run(), range(2)))
        self.assertEqual(sorted(results), [0, 1])
        event = LeadEvent.objects.get(kind="sla_response_warning")
        self.assertEqual(event.notifications.count(), 3)

    def test_checker_waits_for_reschedule_and_does_not_send_obsolete_warning(self):
        self.operate(operations.claim_lead)
        due = timezone.now() + timedelta(hours=2)
        self.operate(operations.set_next_action, next_action="Действие", next_action_at=due)
        started = Event()

        def check():
            close_old_connections()
            try:
                started.set()
                return operations.check_lead_sla(self.lead.pk, due - timedelta(minutes=30))
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=1) as pool:
            with transaction.atomic():
                Lead.objects.select_for_update().get(pk=self.lead.pk)
                future = pool.submit(check)
                self.assertTrue(started.wait(timeout=10))
                self.operate(operations.set_next_action, next_action="Перенесено", next_action_at=due + timedelta(hours=1))
            self.assertEqual(future.result(timeout=15), 0)
        self.assertFalse(LeadEvent.objects.filter(kind__startswith="next_action_").exists())
