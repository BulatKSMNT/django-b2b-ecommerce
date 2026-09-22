from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier, Event
from unittest.mock import patch

from django.core.management import call_command
from django.db import close_old_connections, connections, transaction
from django.test import RequestFactory, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from apps.analytics import services
from apps.analytics.models import LeadScore, LeadScoringState
from apps.analytics.predictors import score_lead_features
from apps.accounts.models import Profile, User
from apps.leads import management_service as operations
from apps.leads.models import Lead, LeadItem
from apps.leads.test_management import LeadFixtures
from apps.tracking.models import PageVisit, Visitor
from apps.tracking.services import merge_visitor_tracking_to_profile


class ScoringStateTests(LeadFixtures, TestCase):
    def setUp(self):
        self.setup_leads()

    def summary(self):
        self.lead.refresh_from_db()
        return services.scoring_summary(self.lead)

    def test_creation_persists_pending_without_calculating_in_commit_callback(self):
        with patch("apps.analytics.services.score_lead_features") as calculate:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                lead = self.make_lead()
        calculate.assert_not_called()
        self.assertEqual(callbacks, [])
        self.assertEqual(services.scoring_summary(lead)["state"], "pending")
        self.assertFalse(LeadScore.objects.filter(lead=lead).exists())

    def test_legacy_absence_is_missing_and_legacy_result_is_ready_without_fabricated_attempts(self):
        LeadScoringState.objects.filter(lead=self.lead).delete()
        self.assertEqual(self.summary()["state"], "missing")
        LeadScore.objects.create(lead=self.lead, score=0, model_version="legacy", explanation={"reasons": []})
        summary = self.summary()
        self.assertEqual(summary["state"], "ready")
        self.assertTrue(summary["has_result"])
        self.assertIsNone(summary["requested_at"])
        self.assertIsNone(summary["completed_revision"])

    def test_input_change_keeps_last_result_until_pending_calculation_finishes(self):
        original = services.process_score_lead(self.lead.pk)
        self.lead.email = "client@business.example"
        self.lead.save(update_fields=["email"])
        summary = self.summary()
        self.assertEqual(summary["state"], "pending")
        self.assertTrue(summary["is_stale"])
        self.assertEqual(self.lead.score.predicted_at, original.predicted_at)
        updated = services.process_score_lead(self.lead.pk)
        self.assertEqual(updated.features["email_domain"], "business.example")
        self.assertEqual(self.summary()["state"], "ready")
        self.assertFalse(self.summary()["is_stale"])
        self.assertEqual(self.summary()["requested_revision"], self.summary()["completed_revision"])

    def test_tracking_identity_merge_queues_refresh_and_preserves_existing_behavior(self):
        visitor = Visitor.objects.create()
        self.lead.visitor = visitor
        self.lead.save(update_fields=["visitor"])
        page = PageVisit.objects.create(visitor=visitor, path="/catalog/")
        PageVisit.objects.filter(pk=page.pk).update(created_at=self.lead.created_at - timedelta(hours=1))
        original = services.process_score_lead(self.lead.pk)
        customer = User.objects.create_user(username="customer", email="customer@example.com")
        profile = Profile.objects.create(user=customer, name="Компания")
        request = RequestFactory().get("/")
        request.visitor = visitor
        merge_visitor_tracking_to_profile(request, profile)
        self.assertEqual(self.summary()["state"], "pending")
        self.assertEqual(self.lead.score.predicted_at, original.predicted_at)
        self.assertEqual(self.lead.profile_id, profile.pk)
        refreshed = services.process_score_lead(self.lead.pk)
        self.assertTrue(refreshed.features["has_profile"])
        self.assertEqual(refreshed.features["page_visits_7d"], 1)

    def test_failure_retains_successful_result_and_stores_only_safe_error_code(self):
        original = services.process_score_lead(self.lead.pk)
        services.schedule_score_lead(self.lead.pk)
        with patch("apps.analytics.services.score_lead_features", side_effect=RuntimeError("private token")):
            with self.assertLogs("apps.analytics.services", level="ERROR"):
                with self.assertRaises(services.ScoringUnavailable):
                    services.process_score_lead(self.lead.pk)
        summary = self.summary()
        self.assertEqual(summary["state"], "error")
        self.assertEqual(summary["error_code"], "calculation_failed")
        self.assertNotIn("private", str(summary))
        self.assertTrue(summary["is_stale"])
        self.assertEqual(self.lead.score.predicted_at, original.predicted_at)
        self.assertEqual(self.lead.score.features, original.features)

    def test_calculation_publication_and_ready_state_are_atomic(self):
        original = LeadScoringState.save

        def fail_ready(instance, *args, **kwargs):
            if instance.status == "ready":
                raise RuntimeError("Cannot publish completion")
            return original(instance, *args, **kwargs)

        with patch.object(LeadScoringState, "save", fail_ready):
            with self.assertLogs("apps.analytics.services", level="ERROR"):
                with self.assertRaises(services.ScoringUnavailable):
                    services.process_score_lead(self.lead.pk)
        self.assertFalse(LeadScore.objects.filter(lead=self.lead).exists())
        self.assertEqual(self.summary()["state"], "error")

    def test_rolled_back_input_does_not_queue_new_revision(self):
        revision = self.summary()["requested_revision"]
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                self.lead.email = "rollback@example.net"
                self.lead.save(update_fields=["email"])
                raise RuntimeError("rollback")
        self.assertEqual(self.summary()["requested_revision"], revision)
        self.assertEqual(self.lead.email, "secret@example.com")

    def test_item_change_queues_refresh_and_lead_cascade_does_not_recreate_state(self):
        services.process_score_lead(self.lead.pk)
        item = LeadItem.objects.create(lead=self.lead, product_name="Снимок", quantity=1)
        self.assertEqual(self.summary()["state"], "pending")
        revision = self.summary()["requested_revision"]
        item.delete()
        self.assertEqual(self.summary()["requested_revision"], revision + 1)
        # A raw/imported lead without protected CRM history can still be deleted.
        raw_lead = Lead.objects.create(fullname="Импорт", email="import@example.com", phone_number="+79991234567")
        LeadItem.objects.create(lead=raw_lead, product_name="Снимок", quantity=1)
        lead_id = raw_lead.pk
        raw_lead.delete()
        self.assertFalse(LeadScoringState.objects.filter(lead_id=lead_id).exists())

    def test_handling_actions_do_not_wait_for_or_restart_failed_scoring(self):
        LeadScoringState.objects.filter(lead=self.lead).update(status="error", error_code="calculation_failed")
        revision = self.summary()["requested_revision"]
        with patch("apps.analytics.services.score_lead_features", side_effect=RuntimeError) as calculate:
            self.operate(operations.claim_lead)
            self.operate(operations.add_comment, text="Обработка продолжается")
            self.operate(operations.change_status, status="in_progress")
            self.operate(operations.register_interaction, channel="phone", direction="outbound", result="success", description="Дозвонился")
            self.operate(operations.close_lead, status="canceled", result="Отказ")
            self.operate(operations.reopen_lead, reason="Повторное обращение")
        calculate.assert_not_called()
        self.assertEqual(self.summary()["requested_revision"], revision)
        self.assertEqual(self.summary()["state"], "error")
        self.assertEqual(self.lead.cycles.get(ended_at__isnull=True).priority, "medium")

    def test_pending_worker_retries_expired_lease_and_skips_active_and_failed_requests(self):
        other = self.make_lead()
        failed = self.make_lead()
        LeadScoringState.objects.filter(lead=failed).update(status="error")
        services._begin_calculation(other.pk, False)  # Simulate a still-running process.
        services._begin_calculation(self.lead.pk, False)  # Simulate a crashed process.
        LeadScoringState.objects.filter(lead=self.lead).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        output = StringIO()
        call_command("score_leads", pending=True, stdout=output)
        self.assertIn("Пересчитано заявок: 1; ошибок: 0", output.getvalue())
        self.assertEqual(self.summary()["state"], "ready")
        self.assertFalse(LeadScore.objects.filter(lead__in=[other, failed]).exists())
        call_command("score_leads", failed=True, stdout=StringIO())
        self.assertTrue(LeadScore.objects.filter(lead=failed).exists())

    def test_worker_records_failure_continues_and_does_not_auto_retry_error(self):
        other = self.make_lead()
        def compute(features):
            if features["email_domain"] == "example.com":
                raise RuntimeError("broken scoring")
            return score_lead_features(features)
        other.email = "client@business.test"
        other.save(update_fields=["email"])
        output = StringIO()
        with patch("apps.analytics.services.score_lead_features", compute):
            with self.assertLogs("apps.analytics.services", level="ERROR"):
                call_command("score_leads", pending=True, stdout=output)
        self.assertIn("Пересчитано заявок: 1; ошибок: 1", output.getvalue())
        output = StringIO()
        call_command("score_leads", pending=True, stdout=output)
        self.assertIn("Пересчитано заявок: 0; ошибок: 0", output.getvalue())
        self.assertEqual(self.summary()["state"], "error")


class ScoringAPITests(LeadFixtures, TestCase):
    def setUp(self):
        self.setup_leads()
        self.operate(operations.claim_lead)
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.url = f"/api/v1/crm/leads/{self.lead.pk}/"

    def test_card_and_score_distinguish_missing_pending_error_and_ready(self):
        state = self.lead.scoring_state
        for status in ["pending", "error", "missing"]:
            if status == "missing":
                state.delete()
            else:
                LeadScoringState.objects.filter(pk=state.pk).update(status=status)
            card = self.client.get(self.url)
            self.assertEqual(card.status_code, 200)
            self.assertEqual(card.data["scoring"]["state"], status)
            score = self.client.get(self.url + "score/")
            self.assertEqual(score.status_code, 404)
            self.assertEqual(score.data["error"]["details"]["scoring"]["state"], status)
        result = services.score_lead_by_id(self.lead.pk)
        score = self.client.get(self.url + "score/")
        self.assertEqual(score.status_code, 200)
        self.assertEqual(score.data["scoring"]["state"], "ready")
        self.assertEqual(score.data["model_version"], result.model_version)
        self.assertEqual(score.data["features"], result.features)
        self.assertEqual(score.data["explanation"], result.explanation)
        services.schedule_score_lead(self.lead.pk)
        score = self.client.get(self.url + "score/")
        self.assertEqual(score.status_code, 200)
        self.assertTrue(score.data["scoring"]["is_stale"])
        self.assertEqual(score.data["score"], str(result.score))

    def test_score_outage_has_safe_legacy_error_and_does_not_break_public_creation(self):
        with patch("apps.analytics.services.score_lead_features", side_effect=RuntimeError("private")):
            with self.assertLogs("apps.analytics.services", level="ERROR"):
                response = self.client.post(f"/api/v1/leads/{self.lead.pk}/score/recalculate/")
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("private", str(response.data))
            with self.captureOnCommitCallbacks(execute=True):
                public = self.client.post("/api/v1/leads/contact/", {
                    "fullname": "Клиент", "phone_number": "+79991234567", "email": "client@example.com",
                    "agree_to_policy": True,
                }, format="json")
            self.assertEqual(public.status_code, 201, public.data)
            self.assertEqual(self.client.get(self.url).status_code, 200)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url + "score/").status_code, 404)


@skipUnlessDBFeature("has_select_for_update")
class ScoringConcurrencyTests(LeadFixtures, TransactionTestCase):
    def setUp(self):
        self.setup_leads()

    def worker(self, fn):
        close_old_connections()
        try:
            return fn()
        finally:
            connections.close_all()

    def test_parallel_pending_workers_publish_only_once(self):
        barrier = Barrier(2)
        def calculate():
            barrier.wait(timeout=10)
            try:
                services.process_score_lead(self.lead.pk)
                return "ready"
            except services.ScoringBusy:
                return "busy"
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.worker(calculate), range(2)))
        self.assertEqual(sorted(results), ["busy", "ready"])
        self.assertEqual(LeadScore.objects.filter(lead=self.lead).count(), 1)

    def test_slow_scoring_does_not_lock_lead_handling(self):
        started, release = Event(), Event()
        def slow(features):
            started.set()
            if not release.wait(timeout=15):
                raise RuntimeError("test timeout")
            return score_lead_features(features)
        with patch("apps.analytics.services.score_lead_features", slow):
            with ThreadPoolExecutor(max_workers=2) as pool:
                calculation = pool.submit(self.worker, lambda: services.process_score_lead(self.lead.pk))
                try:
                    self.assertTrue(started.wait(timeout=10))
                    claim = pool.submit(self.worker, lambda: operations.claim_lead(
                        lead_id=self.lead.pk, actor=self.manager, idempotency_key="during-scoring",
                    ))
                    self.assertEqual(claim.result(timeout=5)["status"], "assigned")
                finally:
                    release.set()
                self.assertIsNotNone(calculation.result(timeout=10))
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.version, 2)
        self.assertEqual(self.lead.scoring_state.requested_revision, 1)

    def test_old_calculation_cannot_overwrite_newer_input_and_result(self):
        started, release = Event(), Event()
        def slow_old(features):
            if features["email_domain"] == "example.com":
                started.set()
                if not release.wait(timeout=15):
                    raise RuntimeError("test timeout")
            return score_lead_features(features)
        with patch("apps.analytics.services.score_lead_features", slow_old):
            with ThreadPoolExecutor(max_workers=1) as pool:
                old = pool.submit(self.worker, lambda: services.process_score_lead(self.lead.pk))
                try:
                    self.assertTrue(started.wait(timeout=10))
                    self.lead.email = "client@new.example"
                    self.lead.save(update_fields=["email"])
                    current = services.process_score_lead(self.lead.pk)
                finally:
                    release.set()
                with self.assertRaises(services.ScoringBusy):
                    old.result(timeout=10)
        persisted = LeadScore.objects.get(lead=self.lead)
        self.assertEqual(persisted.predicted_at, current.predicted_at)
        self.assertEqual(persisted.features["email_domain"], "new.example")
        self.assertEqual(LeadScoringState.objects.get(lead=self.lead).status, "ready")
