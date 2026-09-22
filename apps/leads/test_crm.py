from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import patch
from uuid import uuid4

from django.db import close_old_connections, connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase, skipUnlessDBFeature
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import EmployeeProfile, Profile, User
from apps.analytics.services import score_lead_by_id
from apps.leads import management_service as operations
from apps.leads.crm_services import mark_all_notifications_read
from apps.leads.models import LeadEvent, LeadHandlingCycle, Notification
from apps.leads.test_management import LeadFixtures
from apps.tracking.models import PageVisit, UserEvent, Visitor

BASE = "/api/v1/crm"


class CRMContractTests(LeadFixtures, TestCase):
    def setUp(self):
        self.setup_leads()
        self.client = APIClient()
        self.client.force_authenticate(self.manager)

    def get(self, path, **query):
        return self.client.get(f"{BASE}{path}", query)

    def post(self, path, data=None, *, key=None, method="post"):
        return getattr(self.client, method)(f"{BASE}{path}", data or {}, format="json", HTTP_IDEMPOTENCY_KEY=key or str(uuid4()))

    def lead_url(self, suffix=""):
        return f"/leads/{self.lead.pk}/{suffix}"

    def claim(self):
        response = self.post(self.lead_url("claim/"))
        self.assertEqual(response.status_code, 200, response.data)
        return response

    def assert_error(self, response, status, code):
        self.assertEqual(response.status_code, status, response.data)
        self.assertEqual(set(response.data), {"error"})
        self.assertEqual(set(response.data["error"]), {"code", "message", "details"})
        self.assertEqual(response.data["error"]["code"], code)

    def test_read_routes_are_defined_and_have_expected_shapes(self):
        self.claim()
        score_lead_by_id(self.lead.pk)
        for path in ["/me/", "/dashboard/", "/dictionaries/", self.lead_url(), self.lead_url("score/")]:
            with self.subTest(path=path):
                response = self.get(path)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertIsInstance(response.data, dict)
        for path in ["/leads/", "/queue/", "/notifications/", self.lead_url("timeline/"), self.lead_url("comments/"), self.lead_url("interactions/"), self.lead_url("behavior/")]:
            with self.subTest(path=path):
                response = self.get(path)
                self.assertEqual(response.status_code, 200, response.data)
                self.assertEqual(set(response.data), {"count", "next", "previous", "results"})
        self.client.force_authenticate(self.supervisor)
        for path in ["/team/", "/employees/assignable/", "/sla-policies/current/"]:
            response = self.get(path)
            self.assertEqual(response.status_code, 200, response.data)

    def test_anonymous_and_nonemployee_are_denied(self):
        for actor in [None, User.objects.create_user(username="customer", email="customer@test.ru")]:
            self.client.force_authenticate(actor)
            for path in ["/me/", "/dashboard/", "/leads/", "/queue/", "/team/", "/employees/assignable/", "/notifications/", "/dictionaries/", "/sla-policies/current/"]:
                self.assert_error(self.get(path), 403, "permission_denied")

    def test_managers_cannot_access_foreign_lead_and_related_resources(self):
        self.operate(operations.assign_lead, actor=self.supervisor, assignee_id=self.other.pk)
        self.assertEqual(self.get("/leads/").data["count"], 0)
        for suffix in ["", "timeline/", "comments/", "interactions/", "behavior/", "score/"]:
            self.assert_error(self.get(self.lead_url(suffix)), 404, "not_found")
        for suffix, data in [("transition/", {"status": "in_progress", "expected_version": 2}), ("comments/", {"text": "Чужая", "expected_version": 2})]:
            self.assert_error(self.post(self.lead_url(suffix), data), 404, "not_found")
        for path in ["/team/", "/employees/assignable/", "/sla-policies/current/"]:
            self.assert_error(self.get(path), 403, "permission_denied")

    def test_queue_search_cannot_probe_contacts_and_sort_is_whitelisted(self):
        first = self.get("/queue/").data
        item = first["results"][0]
        self.assertEqual(set(item), {"id", "source", "status", "created_at", "version", "available_actions", "sla"})
        self.assertTrue(item["available_actions"]["claim"])
        self.assertFalse(item["available_actions"]["assign"])
        self.assertEqual(self.get("/queue/", search=self.lead.pk).data["count"], 1)
        for value in ["secret@example.com", "Секретный клиент", "not-found"]:
            self.assertEqual(self.get("/queue/", search=value).data["count"], 0)
        self.assert_error(self.get("/queue/", ordering="email"), 400, "validation_error")
        self.assert_error(self.get("/queue/", priority="high"), 400, "validation_error")

    def test_lead_filters_sorting_and_pagination_use_authorized_scope(self):
        self.claim()
        second = self.make_lead()
        third = self.make_lead()
        for lead, user in [(second, self.manager), (third, self.other)]:
            operations.assign_lead(lead_id=lead.pk, actor=self.supervisor, assignee_id=user.pk, expected_version=1, idempotency_key=str(uuid4()))
        response = self.get("/leads/", status="assigned", assignee_id=self.manager.pk, page_size=1, ordering="id")
        self.assertEqual(response.data["count"], 2)
        self.assertEqual(response.data["results"][0]["id"], self.lead.pk)
        self.assertIsNotNone(response.data["next"])
        page2 = self.get("/leads/", page_size=1, page=2, ordering="id")
        self.assertEqual(page2.data["results"][0]["id"], second.pk)
        self.assertEqual(self.get("/leads/", assignee_id=self.other.pk).data["count"], 0)
        self.assertEqual(self.get("/leads/", search="secret@example.com").data["count"], 2)
        score_lead_by_id(second.pk)
        self.assertEqual(self.get("/leads/", ordering="-score").data["results"][0]["id"], second.pk)

    def test_invalid_filters_and_repeated_parameters_have_uniform_errors(self):
        for query in [{"page_size": 101}, {"page": 0}, {"assignee_id": "²"}, {"status": "invalid"}, {"overdue": "maybe"}, {"ordering": "--id"}, {"unknown": 1}, {"created_from": "2026-10-02T00:00:00Z", "created_to": "2026-10-01T00:00:00Z"}]:
            with self.subTest(query=query):
                self.assert_error(self.get("/leads/", **query), 400, "validation_error")
        self.assert_error(self.client.get(f"{BASE}/leads/?status=new&status=assigned"), 400, "validation_error")
        self.assert_error(self.get("/leads/", page=999), 404, "not_found")

    def test_card_available_actions_match_contact_and_close_rules(self):
        self.claim()
        card = self.get(self.lead_url()).data
        self.assertEqual([item["status"] for item in card["available_transitions"]], ["in_progress", "canceled"])
        self.assertFalse(card["available_actions"]["assign"])
        self.assertTrue(card["available_actions"]["add_comment"])
        self.assertEqual(card["current_cycle"]["number"], 1)
        self.post(self.lead_url("transition/"), {"expected_version": 2, "status": "in_progress"})
        self.assertEqual([item["status"] for item in self.get(self.lead_url()).data["available_transitions"]], ["canceled"])
        self.post(self.lead_url("interactions/"), {"expected_version": 3, "channel": "phone", "direction": "inbound", "result": "success", "description": "Разговор"})
        self.assertEqual([item["status"] for item in self.get(self.lead_url()).data["available_transitions"]], ["contacted", "canceled"])
        self.post(self.lead_url("transition/"), {"expected_version": 4, "status": "canceled", "result": "Отказ"})
        card = self.get(self.lead_url()).data
        self.assertIsNone(card["current_cycle"])
        self.assertEqual(card["available_transitions"], [])
        self.assertTrue(card["available_actions"]["reopen"])
        self.assertFalse(card["available_actions"]["add_comment"])

    def test_transition_close_and_reopen_reuse_existing_cycles(self):
        self.claim()
        self.assert_error(self.post(self.lead_url("transition/"), {"status": "canceled", "expected_version": 2}), 400, "validation_error")
        body = {"status": "canceled", "expected_version": 2, "result": "Нет бюджета"}
        result = self.post(self.lead_url("transition/"), body, key="close")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.post(self.lead_url("transition/"), body, key="close").data, result.data)
        self.assertEqual(self.lead.cycles.get().result_description, "Нет бюджета")
        response = self.post(self.lead_url("reopen/"), {"expected_version": 3, "reason": "Новая потребность"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.lead.cycles.count(), 2)

    def test_claim_and_assign_conflicts_and_cross_prefix_idempotency(self):
        self.client.force_authenticate(self.supervisor)
        body = {"expected_version": 1, "assignee_id": self.manager.pk}
        response = self.post(self.lead_url("assign/"), body, key="shared")
        old = self.client.post(f"/api/v1/leads/{self.lead.pk}/assign/", body, format="json", HTTP_IDEMPOTENCY_KEY="shared")
        self.assertEqual(response.data, old.data)
        self.assertEqual(LeadEvent.objects.filter(kind="assign").count(), 1)
        self.assert_error(self.post(self.lead_url("assign/"), {**body, "assignee_id": self.other.pk}), 409, "conflict")
        self.client.force_authenticate(self.other)
        self.assert_error(self.post(self.lead_url("claim/")), 409, "conflict")

    def test_general_patch_and_extra_protected_fields_are_rejected(self):
        self.claim()
        self.assert_error(self.post(self.lead_url(), {"status": "completed", "assignee_id": self.other.pk}, method="patch"), 405, "method_not_allowed")
        body = {"expected_version": 2, "next_action": "Позвонить", "next_action_at": (timezone.now() + timedelta(days=1)).isoformat()}
        self.assert_error(self.post(self.lead_url("next-action/"), {**body, "status": "completed"}, method="patch"), 400, "validation_error")
        self.assert_error(self.post(self.lead_url("next-action/"), body), 405, "method_not_allowed")
        response = self.post(self.lead_url("next-action/"), body, method="patch", key="next")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.post(self.lead_url("next-action/"), body, method="patch", key="next").data, response.data)
        self.assert_error(self.post(self.lead_url("next-action/"), body, method="patch"), 409, "conflict")

    def test_timeline_contains_comments_and_contacts_once(self):
        self.claim()
        self.post(self.lead_url("comments/"), {"expected_version": 2, "text": "Уточнить наличие"})
        self.post(self.lead_url("interactions/"), {"expected_version": 3, "channel": "email", "direction": "inbound", "result": "success", "description": "Письмо клиента"})
        timeline = self.get(self.lead_url("timeline/"), ordering="id").data
        self.assertEqual(timeline["count"], 4)
        self.assertEqual(timeline["results"][2]["comment"]["text"], "Уточнить наличие")
        self.assertEqual(timeline["results"][3]["interaction"]["description"], "Письмо клиента")
        self.assertNotIn("request_hash", timeline["results"][2])
        self.assertNotIn("response", timeline["results"][2])
        self.assertEqual(self.get(self.lead_url("comments/"), search="наличие").data["count"], 1)
        self.assertEqual(self.get(self.lead_url("interactions/"), channel="phone").data["count"], 0)
        self.assertEqual(self.get(self.lead_url("timeline/"), kind="register_interaction").data["count"], 1)

    def test_dashboard_aggregates_only_visible_leads_and_current_sla(self):
        self.claim()
        foreign = self.make_lead()
        operations.assign_lead(lead_id=foreign.pk, actor=self.supervisor, assignee_id=self.other.pk, expected_version=1, idempotency_key="foreign")
        self.make_lead()
        LeadHandlingCycle.objects.filter(lead=self.lead).update(response_due_at=timezone.now() - timedelta(minutes=1))
        data = self.get("/dashboard/").data
        self.assertEqual(data["leads"]["total"], 1)
        self.assertEqual(data["leads"]["sla_overdue"], 1)
        self.assertEqual(data["by_status"]["assigned"], 1)
        self.assertEqual(data["queue_count"], 1)
        self.assertEqual(self.get("/leads/", overdue=True).data["count"], 1)
        self.client.force_authenticate(self.supervisor)
        self.assertEqual(self.get("/dashboard/").data["leads"]["total"], 3)

    def test_team_counts_and_assignable_exclude_unavailable_employees(self):
        self.operate(operations.assign_lead, actor=self.supervisor, assignee_id=self.manager.pk)
        EmployeeProfile.objects.filter(user=self.other).update(is_available=False)
        self.client.force_authenticate(self.supervisor)
        team = self.get("/team/", search="manager").data
        self.assertEqual(team["count"], 1)
        self.assertEqual(team["results"][0]["open_count"], 1)
        self.assertEqual(team["results"][0]["assigned_count"], 1)
        ids = [item["user_id"] for item in self.get("/employees/assignable/").data["results"]]
        self.assertNotIn(self.other.pk, ids)
        self.assertIn(self.manager.pk, ids)

    def test_notifications_read_all_updates_only_visible_own_and_preserves_dates(self):
        self.operate(operations.assign_lead, actor=self.supervisor, assignee_id=self.manager.pk)
        first = Notification.objects.get(recipient=self.manager)
        self.operate(operations.add_comment, actor=self.supervisor, text="Для менеджера")
        self.assertEqual(self.get("/notifications/", unread=True).data["count"], 2)
        self.assertEqual(self.post(f"/notifications/{first.pk}/read/").status_code, 200)
        first.refresh_from_db()
        read_at = first.read_at
        self.assertEqual(self.post("/notifications/read-all/").data, {"updated_count": 1})
        self.assertEqual(self.post("/notifications/read-all/").data, {"updated_count": 0})
        first.refresh_from_db()
        self.assertEqual(first.read_at, read_at)
        self.assertEqual(self.get("/notifications/", unread=True).data["count"], 0)
        self.client.force_authenticate(self.other)
        self.assert_error(self.post(f"/notifications/{first.pk}/read/"), 404, "not_found")

    def test_read_all_does_not_read_notifications_after_access_is_lost(self):
        self.operate(operations.assign_lead, actor=self.supervisor, assignee_id=self.manager.pk)
        self.operate(operations.assign_lead, actor=self.supervisor, assignee_id=self.other.pk)
        self.assertEqual(self.post("/notifications/read-all/").data["updated_count"], 0)
        self.assertTrue(Notification.objects.filter(recipient=self.manager, read_at__isnull=True).exists())
        self.assertEqual(self.get("/notifications/").data["count"], 0)

    def test_current_sla_and_version_creation_reuse_models(self):
        self.client.force_authenticate(self.supervisor)
        initial = self.get("/sla-policies/current/").data["version"]
        response = self.post("/sla-policies/", {"response_minutes": 30, "resolution_minutes": 90})
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["version"], initial + 1)
        self.assertEqual(self.get("/sla-policies/current/").data["id"], response.data["id"])
        self.assert_error(self.post("/sla-policies/", {"response_minutes": 30, "resolution_minutes": 90, "version": 123}), 400, "validation_error")

    def test_missing_score_unknown_route_invalid_json_and_csrf_share_errors(self):
        self.claim()
        self.assert_error(self.get(self.lead_url("score/")), 404, "not_found")
        self.assert_error(self.get("/does-not-exist/"), 404, "not_found")
        malformed = self.client.post(f"{BASE}{self.lead_url('comments/')}", "{", content_type="application/json")
        self.assert_error(malformed, 400, "validation_error")
        unsupported = self.client.post(f"{BASE}{self.lead_url('comments/')}", "text", content_type="text/plain")
        self.assert_error(unsupported, 415, "unsupported_media_type")
        csrf = APIClient(enforce_csrf_checks=True)
        csrf.force_login(self.manager)
        self.assert_error(csrf.post(f"{BASE}/notifications/read-all/", {}, format="json"), 403, "permission_denied")

    def test_missing_key_and_unavailable_claim_are_consistent_with_queue(self):
        response = self.client.post(f"{BASE}{self.lead_url('claim/')}", {}, format="json")
        self.assert_error(response, 400, "validation_error")
        EmployeeProfile.objects.filter(user=self.manager).update(is_available=False)
        self.assertFalse(self.get("/queue/").data["results"][0]["available_actions"]["claim"])
        self.assert_error(self.post(self.lead_url("claim/")), 400, "validation_error")

    def test_unexpected_errors_are_json_without_internal_details(self):
        with patch("apps.leads.crm_services.dashboard", side_effect=RuntimeError("secret database details")):
            with self.assertLogs("apps.leads.api.crm.base", level="ERROR"):
                response = self.get("/dashboard/")
        self.assert_error(response, 500, "internal_error")
        self.assertNotIn("secret", str(response.data))


class CRMBehaviorTests(LeadFixtures, TestCase):
    def setUp(self):
        self.setup_leads()
        self.operate(operations.claim_lead)
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.visitor = Visitor.objects.create()
        self.lead.visitor = self.visitor
        self.lead.save(update_fields=["visitor"])
        self.url = f"{BASE}/leads/{self.lead.pk}/behavior/"

    def test_behavior_merges_sources_with_bounded_window_and_no_metadata_leaks(self):
        old = self.lead.created_at - timedelta(days=1)
        page = PageVisit.objects.create(visitor=self.visitor, path="/catalog/", route_name="catalog:list", full_path="/catalog/?email=secret", query_string="email=secret", ip_hash="secret")
        event = UserEvent.objects.create(visitor=self.visitor, event_type="cart_add", metadata={"email": "secret"})
        PageVisit.objects.filter(pk=page.pk).update(created_at=old)
        UserEvent.objects.filter(pk=event.pk).update(created_at=old)
        UserEvent.objects.create(visitor=self.visitor, event_type="product_view")
        too_old = UserEvent.objects.create(visitor=self.visitor, event_type="favorite_add")
        UserEvent.objects.filter(pk=too_old.pk).update(created_at=old - timedelta(days=31))
        foreign_lead = self.make_lead()
        foreign = UserEvent.objects.create(visitor=self.visitor, lead=foreign_lead, event_type="cart_add", metadata={"email": "foreign"})
        UserEvent.objects.filter(pk=foreign.pk).update(created_at=old)
        private_page = PageVisit.objects.create(visitor=self.visitor, path="/accounts/dashboard/", route_name="accounts:dashboard")
        PageVisit.objects.filter(pk=private_page.pk).update(created_at=old)
        response = self.client.get(self.url, {"page_size": 1})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 2)
        self.assertIsNotNone(response.data["next"])
        self.assertNotIn("secret", str(response.data))
        self.assertEqual(set(response.data["results"][0]), {"id", "kind", "occurred_at", "product_id", "product_name", "route_name", "duration_ms", "association"})
        events = self.client.get(self.url, {"kind": "cart_add"})
        self.assertEqual(events.data["count"], 1)
        pages = self.client.get(self.url, {"search": "catalog"})
        self.assertEqual(pages.data["count"], 1)
        self.assertEqual(pages.data["results"][0]["kind"], "page_view")

    def test_absent_identity_does_not_match_all_anonymous_tracking(self):
        self.lead.visitor = None
        self.lead.save(update_fields=["visitor"])
        event = UserEvent.objects.create(event_type="cart_add")
        UserEvent.objects.filter(pk=event.pk).update(created_at=self.lead.created_at - timedelta(hours=1))
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 0)

    def test_guest_identity_does_not_include_other_profiles_on_shared_visitor(self):
        user = User.objects.create_user(username="buyer", email="buyer@example.com")
        profile = Profile.objects.create(user=user, name="Компания")
        event = UserEvent.objects.create(visitor=self.visitor, profile=profile, event_type="cart_add")
        UserEvent.objects.filter(pk=event.pk).update(created_at=self.lead.created_at - timedelta(hours=1))
        self.assertEqual(self.client.get(self.url).data["count"], 0)
        self.lead.profile = profile
        self.lead.save(update_fields=["profile"])
        self.assertEqual(self.client.get(self.url).data["count"], 1)


class CRMSchemaTests(SimpleTestCase):
    def test_schema_has_all_page_contracts_and_required_action_arguments(self):
        from drf_spectacular.generators import SchemaGenerator
        schema = SchemaGenerator().get_schema(request=None, public=True)
        paths = schema["paths"]
        get_paths = ["me", "dashboard", "leads", "queue", "leads/{id}", "leads/{id}/timeline",
                     "leads/{id}/comments", "leads/{id}/interactions", "leads/{id}/behavior",
                     "leads/{id}/score", "team", "employees/assignable", "notifications",
                     "sla-policies/current", "dictionaries"]
        post_paths = ["leads/{id}/claim", "leads/{id}/assign", "leads/{id}/transition", "leads/{id}/reopen",
                      "leads/{id}/comments", "leads/{id}/interactions", "notifications/{id}/read",
                      "notifications/read-all", "sla-policies"]
        for method, endings in [("get", get_paths), ("post", post_paths), ("patch", ["leads/{id}/next-action"])]:
            for ending in endings:
                operation = paths[f"{BASE}/{ending}/"][method]
                self.assertEqual(operation["responses"]["403"]["content"]["application/json"]["schema"]["$ref"], "#/components/schemas/CRMError")
        self.assertNotIn("patch", paths[f"{BASE}/leads/{{id}}/"])
        action = paths[f"{BASE}/leads/{{id}}/next-action/"]["patch"]
        self.assertTrue(action["requestBody"]["required"])
        ref = action["requestBody"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
        self.assertEqual(set(schema["components"]["schemas"][ref]["required"]), {"expected_version", "next_action", "next_action_at"})
        self.assertTrue(next(item for item in action["parameters"] if item["name"] == "Idempotency-Key")["required"])
        for ending in ["queue", "team", "employees/assignable", "leads", "notifications", "leads/{id}/behavior", "leads/{id}/timeline"]:
            ref = paths[f"{BASE}/{ending}/"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].split("/")[-1]
            self.assertEqual(set(schema["components"]["schemas"][ref]["properties"]), {"count", "next", "previous", "results"})


@skipUnlessDBFeature("has_select_for_update")
class CRMNotificationConcurrencyTests(LeadFixtures, TransactionTestCase):
    def test_simultaneous_read_all_does_not_change_read_timestamps_twice(self):
        self.setup_leads()
        self.operate(operations.assign_lead, actor=self.supervisor, assignee_id=self.manager.pk)
        self.operate(operations.add_comment, actor=self.supervisor, text="Комментарий")
        barrier = Barrier(2)

        def read_all():
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return mark_all_notifications_read(self.manager)["updated_count"]
            finally:
                connections.close_all()

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: read_all(), range(2)))
        self.assertEqual(sorted(results), [0, 2])
        self.assertFalse(Notification.objects.filter(recipient=self.manager, read_at__isnull=True).exists())
        self.assertEqual(Notification.objects.filter(recipient=self.manager).values("read_at").distinct().count(), 1)
