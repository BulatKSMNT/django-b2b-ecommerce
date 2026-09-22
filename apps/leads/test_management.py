from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import close_old_connections, connections, transaction
from django.test import TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import EmployeeProfile, User
from apps.leads.management_service import (
    LeadConflict, add_comment, assign_lead, change_status, check_lead_sla,
    claim_lead, close_lead, create_sla_policy, initialize_lead,
    register_interaction, reopen_lead, set_next_action,
)
from apps.leads.models import Lead, LeadEvent, Notification, SLAPolicy


class LeadFixtures:
    def make_employee(self, name, role="manager"):
        user = User.objects.create_user(username=name, email=f"{name}@example.com")
        EmployeeProfile.objects.create(user=user, role=role)
        return user

    def make_lead(self):
        with transaction.atomic():
            lead = Lead.objects.create(fullname="Секретный клиент", email="secret@example.com", phone_number="+79991111111", comment="Секретный комментарий")
            return initialize_lead(lead)

    def setup_leads(self):
        SLAPolicy.objects.get_or_create(version=1)
        self.manager = self.make_employee("manager")
        self.other = self.make_employee("other")
        self.supervisor = self.make_employee("supervisor", "supervisor")
        self.administrator = self.make_employee("administrator", "administrator")
        self.lead = self.make_lead()

    def operate(self, operation, actor=None, **data):
        self.lead.refresh_from_db()
        return operation(
            lead_id=self.lead.pk, actor=actor or self.manager,
            expected_version=self.lead.version, idempotency_key=str(uuid4()), **data,
        )


class LeadOperationTests(LeadFixtures, TestCase):
    def setUp(self):
        self.setup_leads()

    def test_full_lifecycle_requires_contact_and_qualified_result(self):
        self.operate(claim_lead)
        self.operate(change_status, status="in_progress")
        with self.assertRaises(ValidationError):
            self.operate(change_status, status="contacted")
        self.operate(register_interaction, channel="phone", direction="outbound", result="no_answer", description="Не ответил")
        with self.assertRaises(ValidationError):
            self.operate(change_status, status="contacted")
        self.operate(register_interaction, channel="phone", direction="outbound", result="success", description="Обсудили заказ")
        self.operate(change_status, status="contacted")
        with self.assertRaises(ValidationError):
            self.operate(close_lead, status="completed", result="Заказ оформлен")
        self.operate(change_status, status="qualified")
        self.operate(close_lead, status="completed", result="Заказ №123")
        self.lead.refresh_from_db()
        cycle = self.lead.cycles.get()
        self.assertEqual(self.lead.status, "completed")
        self.assertEqual(cycle.result_description, "Заказ №123")
        self.assertIsNotNone(cycle.ended_at)
        self.assertIsNotNone(cycle.first_contact_at)
        self.assertEqual(self.lead.processed_by, self.manager)
        self.assertEqual(self.lead.history_events.count(), self.lead.version)

    def test_negative_close_requires_reason_and_clears_next_action(self):
        self.operate(claim_lead)
        self.operate(set_next_action, next_action="Позвонить", next_action_at=timezone.now() + timedelta(days=1))
        with self.assertRaises(ValidationError):
            self.operate(close_lead, status="canceled", result=" ")
        self.operate(close_lead, status="canceled", result="Нет бюджета")
        self.lead.refresh_from_db()
        self.assertIsNone(self.lead.next_action_at)
        self.assertEqual(self.lead.next_action, "")
        with self.assertRaises(ValidationError):
            self.operate(add_comment, text="Закрытая заявка")

    def test_cannot_skip_states_or_use_status_to_close(self):
        self.operate(claim_lead)
        for status in ["new", "contacted", "qualified", "completed", "canceled"]:
            with self.subTest(status=status), self.assertRaises(ValidationError):
                self.operate(change_status, status=status)

    def test_reassignment_preserves_cycle_and_deadlines(self):
        original = self.lead.cycles.get()
        self.operate(assign_lead, actor=self.supervisor, assignee_id=self.manager.pk)
        self.operate(assign_lead, actor=self.supervisor, assignee_id=self.other.pk)
        current = self.lead.cycles.get()
        self.assertEqual((current.pk, current.started_at, current.response_due_at, current.resolution_due_at),
                         (original.pk, original.started_at, original.response_due_at, original.resolution_due_at))

    def test_reopen_starts_new_policy_and_does_not_reuse_previous_contacts(self):
        self.operate(claim_lead)
        self.operate(register_interaction, channel="email", direction="inbound", result="success", description="Письмо")
        self.operate(close_lead, status="canceled", result="Отложено")
        policy = create_sla_policy(actor=self.supervisor, response_minutes=30, resolution_minutes=120)
        self.operate(reopen_lead, reason="Клиент вернулся")
        current = self.lead.cycles.get(ended_at__isnull=True)
        self.assertEqual(current.number, 2)
        self.assertEqual(current.policy, policy)
        self.assertEqual(current.response_due_at - current.started_at, timedelta(minutes=30))
        self.assertIsNone(current.first_contact_at)
        self.operate(change_status, status="in_progress")
        with self.assertRaises(ValidationError):
            self.operate(change_status, status="contacted")

    def test_unavailable_or_inactive_employee_cannot_be_assigned(self):
        for field in ("is_available", "is_active"):
            EmployeeProfile.objects.filter(user=self.manager).update(is_active=True, is_available=True)
            EmployeeProfile.objects.filter(user=self.manager).update(**{field: False})
            with self.assertRaises(ValidationError):
                self.operate(assign_lead, actor=self.supervisor, assignee_id=self.manager.pk)
        EmployeeProfile.objects.filter(user=self.manager).update(is_active=True, is_available=True)
        User.objects.filter(pk=self.manager.pk).update(is_active=False)
        with self.assertRaises(ValidationError):
            self.operate(assign_lead, actor=self.supervisor, assignee_id=self.manager.pk)

    def test_service_permissions_are_enforced_without_api(self):
        self.operate(claim_lead)
        with self.assertRaises(PermissionDenied):
            self.operate(add_comment, actor=self.other, text="Чужая заявка")
        with self.assertRaises(PermissionDenied):
            self.operate(assign_lead, assignee_id=self.other.pk)

    def test_failed_history_or_notification_rolls_back_everything(self):
        for target in ("apps.leads.management_service.LeadEvent.objects.create", "apps.leads.management_service._notify"):
            with self.subTest(target=target):
                with patch(target, side_effect=RuntimeError("storage failure")):
                    with self.assertRaises(RuntimeError):
                        self.operate(assign_lead, actor=self.supervisor, assignee_id=self.manager.pk)
                self.lead.refresh_from_db()
                self.assertEqual(self.lead.version, 1)
                self.assertIsNone(self.lead.assignee_id)
                self.assertEqual(self.lead.history_events.count(), 1)
                self.assertFalse(Notification.objects.exists())

    def test_comment_failure_rolls_back_resource(self):
        self.operate(claim_lead)
        with patch("apps.leads.management_service._notify", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.operate(add_comment, text="Не сохранять частично")
        self.assertFalse(self.lead.comments.exists())

    def test_idempotency_replays_original_result_even_after_later_action(self):
        self.operate(claim_lead)
        params = dict(lead_id=self.lead.pk, actor=self.manager, expected_version=2, idempotency_key="comment-key", text="Комментарий")
        response = add_comment(**params)
        self.operate(change_status, status="in_progress")
        self.assertEqual(add_comment(**params), response)
        self.assertEqual(self.lead.comments.count(), 1)
        with self.assertRaises(LeadConflict):
            add_comment(**{**params, "text": "Другой комментарий"})

    def test_stale_versions_rejected(self):
        self.operate(claim_lead)
        with self.assertRaises(LeadConflict):
            change_status(lead_id=self.lead.pk, actor=self.manager, expected_version=1, idempotency_key="stale", status="in_progress")
        with self.assertRaises(LeadConflict):
            assign_lead(lead_id=self.lead.pk, actor=self.supervisor, expected_version=1, idempotency_key="stale", assignee_id=self.other.pk)

    def test_contact_time_and_next_action_validation(self):
        self.operate(claim_lead)
        for date in [timezone.now() + timedelta(days=1), self.lead.created_at - timedelta(days=1)]:
            with self.assertRaises(ValidationError):
                self.operate(register_interaction, channel="phone", direction="outbound", result="success", description="Звонок", occurred_at=date)
        with self.assertRaises(ValidationError):
            self.operate(set_next_action, next_action="Позвонить", next_action_at=timezone.now() - timedelta(hours=1))

    def test_sla_alerts_once_per_cycle_and_no_alert_after_close(self):
        self.operate(assign_lead, actor=self.supervisor, assignee_id=self.manager.pk)
        future = timezone.now() + timedelta(days=2)
        self.assertEqual(check_lead_sla(self.lead.pk, future), 2)
        count = Notification.objects.count()
        self.assertEqual(check_lead_sla(self.lead.pk, future), 0)
        self.assertEqual(Notification.objects.count(), count)
        self.operate(close_lead, status="canceled", result="Отказ")
        self.assertEqual(check_lead_sla(self.lead.pk, future), 0)

    def test_outbound_attempt_stops_response_timer(self):
        self.operate(claim_lead)
        self.operate(register_interaction, channel="phone", direction="outbound", result="no_answer", description="Попытка звонка")
        self.assertEqual(check_lead_sla(self.lead.pk, timezone.now() + timedelta(hours=5)), 0)


class LeadManagementAPITests(LeadFixtures, TestCase):
    def setUp(self):
        self.setup_leads()
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def post(self, action, payload=None, key=None, lead=None):
        return self.client.post(f"/api/v1/leads/{(lead or self.lead).pk}/{action}/", payload or {}, format="json", HTTP_IDEMPOTENCY_KEY=key or str(uuid4()))

    def test_queue_is_whitelisted_and_search_cannot_probe_contacts(self):
        for suffix in ["", "?search=secret@example.com", "?search=absent", "?ordering=email"]:
            response = self.client.get("/api/v1/leads/queue/" + suffix)
            self.assertEqual(response.status_code, 200)
            payload = response.json()
            self.assertEqual(payload["count"], 1)
            self.assertEqual(set(payload["results"][0]), {"id", "source", "status", "created_at", "version"})

    def test_manager_cannot_read_or_mutate_foreign_resources(self):
        self.operate(assign_lead, actor=self.supervisor, assignee_id=self.other.pk)
        self.assertEqual(self.client.get("/api/v1/leads/").json()["count"], 0)
        for suffix in ["", "comments/", "interactions/", "history/", "cycles/", "score/"]:
            with self.subTest(suffix=suffix):
                response = self.client.get(f"/api/v1/leads/{self.lead.pk}/{suffix}")
                self.assertEqual(response.status_code, 404)
        for suffix, payload in [("comments", {"text": "Чужой", "expected_version": 2}), ("status", {"status": "in_progress", "expected_version": 2}), ("score/recalculate", {})]:
            self.assertEqual(self.post(suffix, payload).status_code, 404)
        self.assertEqual(self.post("assign", {"assignee_id": self.manager.pk, "expected_version": 2}).status_code, 403)

    def test_claim_conflict_and_version_contract(self):
        response = self.post("claim", key="claim")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["version"], 2)
        self.assertEqual(self.post("claim", key="claim").json(), response.json())
        self.assertEqual(self.post("claim").status_code, 409)
        self.assertEqual(self.post("status", {"status": "in_progress", "expected_version": 1}).status_code, 409)
        self.assertEqual(self.post("status", {"status": "in_progress"}).status_code, 400)
        self.assertEqual(self.post("status", {"status": "in_progress", "expected_version": 2}).status_code, 200)

    def test_missing_idempotency_key_rejected(self):
        response = self.client.post(f"/api/v1/leads/{self.lead.pk}/claim/", {}, format="json")
        self.assertEqual(response.status_code, 400)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.version, 1)

    def test_comment_and_interaction_endpoints_and_history(self):
        self.post("claim")
        self.assertEqual(self.post("comments", {"expected_version": 2, "text": "Комментарий"}).status_code, 200)
        self.assertEqual(self.post("interactions", {"expected_version": 3, "channel": "email", "direction": "inbound", "result": "success", "description": "Письмо"}).status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/leads/{self.lead.pk}/comments/").json()["count"], 1)
        history = self.client.get(f"/api/v1/leads/{self.lead.pk}/history/").json()
        self.assertEqual(history["count"], 4)
        self.assertNotIn("idempotency_key", history["results"][-1])

    def test_retry_after_reassignment_does_not_bypass_access(self):
        self.post("claim", key="claim")
        self.operate(assign_lead, actor=self.supervisor, assignee_id=self.other.pk)
        self.assertEqual(self.post("claim", key="claim").status_code, 403)
        self.assertEqual(self.client.get(f"/api/v1/leads/{self.lead.pk}/").status_code, 404)

    def test_notification_access_and_idempotent_read(self):
        self.operate(assign_lead, actor=self.supervisor, assignee_id=self.manager.pk)
        notice = Notification.objects.get(recipient=self.manager)
        url = f"/api/v1/notifications/{notice.pk}/read/"
        self.assertEqual(self.client.get("/api/v1/notifications/").json()["count"], 1)
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["read_at"], self.client.post(url).json()["read_at"])
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.post(url).status_code, 404)

    def test_employee_and_sla_permissions(self):
        self.assertEqual(self.client.get("/api/v1/employees/me/").status_code, 200)
        self.assertEqual(self.client.get("/api/v1/employees/").status_code, 403)
        self.assertEqual(self.client.get("/api/v1/sla-policies/").status_code, 403)
        self.client.force_authenticate(self.supervisor)
        self.assertEqual(self.client.get("/api/v1/employees/").status_code, 200)
        data = {"response_minutes": 15, "resolution_minutes": 60}
        response = self.client.post("/api/v1/sla-policies/", data, format="json")
        self.assertEqual(response.status_code, 201)
        employee = self.manager.employee_profile
        url = f"/api/v1/employees/{employee.pk}/"
        self.assertEqual(self.client.patch(url, {"role": "administrator"}, format="json").status_code, 403)
        self.client.force_authenticate(self.administrator)
        self.assertEqual(self.client.patch(url, {"is_available": False}, format="json").status_code, 200)
        self.assertEqual(self.client.post("/api/v1/sla-policies/", {"response_minutes": 60, "resolution_minutes": 15}, format="json").status_code, 400)

    def test_administrator_creates_employee_without_django_admin_privileges(self):
        self.client.force_authenticate(self.administrator)
        response = self.client.post("/api/v1/employees/", {"username": "newemployee", "email": "new@example.com", "password": "S3cure-long-password!"}, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        user = User.objects.get(username="newemployee")
        self.assertFalse(user.is_staff)
        self.assertTrue(user.check_password("S3cure-long-password!"))
        self.assertNotIn("password", response.data)

    def test_public_contact_preserves_contract_and_creates_cycle(self):
        self.client.force_authenticate(None)
        response = self.client.post("/api/v1/leads/contact/", {"fullname": "Иван Иванов", "email": "ivan@example.com", "phone_number": "+79991234567", "agree_to_policy": True}, format="json")
        self.assertEqual(response.status_code, 201)
        lead = Lead.objects.get(email="ivan@example.com")
        self.assertEqual(lead.cycles.count(), 1)
        self.assertEqual(lead.history_events.get().kind, "created")
        self.assertFalse(Notification.objects.exists())

    def test_public_product_and_cart_forms_keep_snapshots_and_tracking(self):
        from apps.catalog.models import Category, Product
        from apps.tracking.models import UserEvent
        category = Category.objects.create(name="Категория", is_active=True)
        product = Product.objects.create(category=category, name="Товар", price="125.00", is_active=True)
        self.client.force_authenticate(None)
        data = {"fullname": "Иван Иванов", "email": "buyer@example.com", "phone_number": "+79991234567", "agree_to_policy": True, "quantity": 3}
        self.assertEqual(self.client.post(f"/leads/product/{product.pk}/", data).status_code, 302)
        self.assertEqual(self.client.post(f"/cart/add/{product.pk}/", {"quantity": 3}).status_code, 302)
        self.assertEqual(self.client.post("/leads/cart/", data).status_code, 302)
        leads = Lead.objects.filter(email="buyer@example.com")
        self.assertEqual(leads.count(), 2)
        for lead in leads:
            item = lead.items.get()
            self.assertEqual(item.quantity, 3)
            self.assertEqual(str(item.line_total), "375.00")
            self.assertEqual(item.snapshot["product_name"], "Товар")
            self.assertEqual(lead.cycles.count(), 1)
            self.assertEqual(lead.history_events.get().kind, "created")
            self.assertTrue(UserEvent.objects.filter(lead=lead).exists())
        # Cart must have been cleared by the original public flow.
        self.client.post("/leads/cart/", data)
        self.assertEqual(Lead.objects.filter(email="buyer@example.com").count(), 2)

    def test_session_auth_requires_csrf_for_mutations(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.manager)
        response = client.post(f"/api/v1/leads/{self.lead.pk}/claim/", {}, format="json", HTTP_IDEMPOTENCY_KEY="csrf")
        self.assertEqual(response.status_code, 403)

    def test_nonemployee_and_disabled_employee_are_denied(self):
        EmployeeProfile.objects.filter(user=self.manager).update(is_active=False)
        self.assertEqual(self.client.get("/api/v1/leads/queue/").status_code, 403)
        self.assertEqual(self.post("claim").status_code, 403)

    def test_malformed_lead_identifier_returns_404(self):
        response = self.client.post("/api/v1/leads/not-an-id/claim/", {}, format="json", HTTP_IDEMPOTENCY_KEY="bad-id")
        self.assertEqual(response.status_code, 404)

    def test_admin_blocks_foreign_data_even_with_legacy_permissions(self):
        self.manager.is_staff = True
        self.manager.save()
        self.manager.user_permissions.set(Permission.objects.all())
        self.client.force_login(self.manager)
        self.operate(assign_lead, actor=self.supervisor, assignee_id=self.other.pk)
        for url in ["/admin/analytics/dashboard/", "/admin/analytics/leadscore/", "/admin/tracking/userevent/", "/admin/tracking/visitor/", "/admin/accounts/user/", "/admin/accounts/profile/"]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)
        response = self.client.get(f"/admin/leads/lead/{self.lead.pk}/change/")
        self.assertNotContains(response, "secret@example.com", status_code=response.status_code)

    def test_admin_action_uses_services_and_expected_version(self):
        self.supervisor.is_staff = True
        self.supervisor.save()
        self.supervisor.user_permissions.set(Permission.objects.filter(codename__in=["view_lead", "change_lead"]))
        self.client.force_login(self.supervisor)
        url = f"/admin/leads/lead/{self.lead.pk}/operate/"
        response = self.client.post(url, {"operation": "assign", "assignee_id": self.manager.pk, "expected_version": 1, "idempotency_key": "admin-assign"})
        self.assertEqual(response.status_code, 302)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.assignee_id, self.manager.pk)
        response = self.client.post(url, {"operation": "change_status", "status": "in_progress", "expected_version": 1, "idempotency_key": "admin-status"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Текущая версия: 2")
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.status, "assigned")


@skipUnlessDBFeature("has_select_for_update")
class LeadConcurrencyTests(LeadFixtures, TransactionTestCase):
    def setUp(self):
        self.setup_leads()

    def race(self, functions):
        barrier = Barrier(len(functions))

        def run(function):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return function()
            except LeadConflict:
                return "conflict"
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            return list(pool.map(run, functions))

    def test_two_claims_have_exactly_one_winner(self):
        def claim(user):
            return lambda: claim_lead(lead_id=self.lead.pk, actor=user, idempotency_key=str(uuid4()))
        results = self.race([claim(self.manager), claim(self.other)])
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(LeadEvent.objects.filter(kind="claim").count(), 1)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.version, 2)

    def test_concurrent_duplicate_request_creates_one_comment(self):
        self.operate(claim_lead)
        def comment():
            return add_comment(lead_id=self.lead.pk, actor=self.manager, expected_version=2, idempotency_key="same-key", text="Один комментарий")
        results = self.race([comment, comment])
        self.assertEqual(results[0], results[1])
        self.assertEqual(self.lead.comments.count(), 1)
        self.assertEqual(LeadEvent.objects.filter(kind="add_comment").count(), 1)

    def test_status_and_assignment_compete_on_version(self):
        self.operate(claim_lead)
        results = self.race([
            lambda: change_status(lead_id=self.lead.pk, actor=self.supervisor, expected_version=2, idempotency_key="status", status="in_progress"),
            lambda: assign_lead(lead_id=self.lead.pk, actor=self.supervisor, expected_version=2, idempotency_key="assign", assignee_id=self.other.pk),
        ])
        self.assertEqual(results.count("conflict"), 1)
        self.lead.refresh_from_db()
        self.assertEqual(self.lead.version, 3)

    def test_parallel_sla_checks_do_not_duplicate_notifications(self):
        future = timezone.now() + timedelta(days=2)
        results = self.race([lambda: check_lead_sla(self.lead.pk, future), lambda: check_lead_sla(self.lead.pk, future)])
        self.assertEqual(sorted(results), [0, 2])
        self.assertEqual(LeadEvent.objects.filter(kind__startswith="sla_").count(), 2)

    def test_parallel_reopens_create_exactly_one_new_cycle(self):
        self.operate(claim_lead)
        self.operate(close_lead, status="canceled", result="Отказ")
        results = self.race([
            lambda: reopen_lead(lead_id=self.lead.pk, actor=self.supervisor, expected_version=3, idempotency_key="reopen-1", reason="Вернулся"),
            lambda: reopen_lead(lead_id=self.lead.pk, actor=self.supervisor, expected_version=3, idempotency_key="reopen-2", reason="Вернулся"),
        ])
        self.assertEqual(results.count("conflict"), 1)
        self.assertEqual(self.lead.cycles.count(), 2)
        self.assertEqual(self.lead.cycles.filter(ended_at__isnull=True).count(), 1)

    def test_parallel_policy_changes_allocate_distinct_versions(self):
        results = self.race([
            lambda: create_sla_policy(actor=self.supervisor, response_minutes=15, resolution_minutes=60).version,
            lambda: create_sla_policy(actor=self.supervisor, response_minutes=30, resolution_minutes=90).version,
        ])
        self.assertEqual(sorted(results), [2, 3])
