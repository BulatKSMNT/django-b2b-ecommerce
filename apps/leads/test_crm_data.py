from datetime import datetime, timedelta
from unittest.mock import patch

from django.test import TestCase, SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import EmployeeProfile
from apps.leads import management_service as operations
from apps.leads.models import Lead, LeadHandlingCycle
from apps.leads.test_management import LeadFixtures
from apps.tracking.models import PageVisit, UserEvent, Visitor


class CRMExistingDataTests(LeadFixtures, TestCase):
    def setUp(self):
        self.setup_leads()
        self.operate(operations.claim_lead)
        self.client = APIClient()
        self.client.force_authenticate(self.manager)
        self.url = f"/api/v1/crm/leads/{self.lead.pk}/behavior/"

    def test_direct_behavior_without_identity_includes_creation_but_not_other_leads_or_auth(self):
        direct = UserEvent.objects.create(lead=self.lead, event_type="lead_contact_created", metadata={"secret": "private"})
        foreign_lead = self.make_lead()
        UserEvent.objects.create(lead=foreign_lead, event_type="lead_contact_created")
        UserEvent.objects.create(event_type="lead_contact_created")
        UserEvent.objects.create(lead=self.lead, event_type="login", metadata={"private": "identity"})
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data["count"], 1)
        event = response.data["results"][0]
        self.assertEqual(event["id"], direct.pk)
        self.assertEqual(event["association"], "lead")
        self.assertEqual(event["kind"], "lead_contact_created")
        self.assertNotIn("private", str(response.data))
        self.assertEqual(self.client.get(self.url, {"kind": "lead_contact_created"}).data["count"], 1)
        self.assertEqual(self.client.get(self.url, {"created_to": self.lead.created_at.isoformat()}).data["count"], 0)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_direct_and_inferred_activity_share_pagination_without_duplicates(self):
        visitor = Visitor.objects.create()
        self.lead.visitor = visitor
        self.lead.save(update_fields=["visitor"])
        page = PageVisit.objects.create(visitor=visitor, path="/catalog/", route_name="catalog:list")
        direct = UserEvent.objects.create(visitor=visitor, lead=self.lead, event_type="cart_add")
        inferred = UserEvent.objects.create(visitor=visitor, event_type="cart_add")
        before = self.lead.created_at - timedelta(hours=1)
        PageVisit.objects.filter(pk=page.pk).update(created_at=before)
        UserEvent.objects.filter(pk__in=[direct.pk, inferred.pk]).update(created_at=before)
        future = UserEvent.objects.create(lead=self.lead, event_type="cart_add")
        UserEvent.objects.filter(pk=future.pk).update(created_at=timezone.now() + timedelta(days=1))
        response = self.client.get(self.url, {"page_size": 2})
        self.assertEqual(response.data["count"], 3)
        rows = response.data["results"] + self.client.get(self.url, {"page_size": 2, "page": 2}).data["results"]
        self.assertEqual(len({(row["kind"], row["id"]) for row in rows}), 3)
        self.assertEqual(sum(row["association"] == "lead" for row in rows), 1)
        self.assertEqual(sum(row["association"] == "visitor" for row in rows), 2)

    def test_overview_and_filters_use_own_leads_and_count_attention_only_once(self):
        now = timezone.now()
        LeadHandlingCycle.objects.filter(lead=self.lead).update(response_warning_at=now - timedelta(minutes=1))
        Lead.objects.filter(pk=self.lead.pk).update(next_action_at=now - timedelta(minutes=1))
        foreign = self.make_lead()
        Lead.objects.filter(pk=foreign.pk).update(assignee=self.other, status="assigned")
        LeadHandlingCycle.objects.filter(lead=foreign).update(response_due_at=now - timedelta(hours=1))
        dashboard = self.client.get("/api/v1/crm/dashboard/")
        self.assertEqual(dashboard.status_code, 200, dashboard.data)
        counts = dashboard.data["leads"]
        self.assertEqual(counts["total"], 1)
        self.assertEqual(counts["awaiting_response"], 1)
        self.assertEqual(counts["requires_attention"], 1)
        self.assertEqual(counts["sla_overdue"], 0)
        self.assertEqual(counts["sla_warning"], 1)
        self.assertEqual(counts["next_action_overdue"], 1)
        for query in [{"attention": "true"}, {"awaiting_response": "true"}]:
            response = self.client.get("/api/v1/crm/leads/", query)
            self.assertEqual([row["id"] for row in response.data["results"]], [self.lead.pk])
        self.operate(operations.register_interaction, channel="phone", direction="outbound", result="no_answer", description="Не ответили")
        self.assertEqual(self.client.get("/api/v1/crm/dashboard/").data["leads"]["awaiting_response"], 0)
        self.assertEqual(self.client.get("/api/v1/crm/leads/", {"awaiting_response": "false"}).data["count"], 1)
        self.assertEqual(self.client.get("/api/v1/crm/leads/", {"attention": "false"}).data["count"], 0)

    def test_today_uses_local_midnight_and_excludes_closed_and_next_day_actions(self):
        with timezone.override("Europe/Moscow"):
            day = timezone.make_aware(datetime(2026, 9, 22))
            now = day + timedelta(minutes=10)
            tomorrow = self.make_lead()
            yesterday = self.make_lead()
            closed = self.make_lead()
            ids = [self.lead.pk, tomorrow.pk, yesterday.pk, closed.pk]
            Lead.objects.filter(pk__in=ids).update(assignee=self.manager, status="assigned", created_at=day)
            Lead.objects.filter(pk=self.lead.pk).update(next_action_at=day + timedelta(minutes=5))
            Lead.objects.filter(pk=tomorrow.pk).update(next_action_at=day + timedelta(days=1))
            Lead.objects.filter(pk=yesterday.pk).update(next_action_at=day - timedelta(microseconds=1), created_at=day - timedelta(microseconds=1))
            Lead.objects.filter(pk=closed.pk).update(status="canceled", next_action_at=day + timedelta(hours=1))
            LeadHandlingCycle.objects.filter(lead=closed).update(started_at=day - timedelta(hours=1), ended_at=day)
            with patch("apps.leads.crm_services.timezone.now", return_value=now):
                dashboard = self.client.get("/api/v1/crm/dashboard/").data
                self.assertEqual(dashboard["leads"]["next_actions_today"], 1)
                self.assertEqual(dashboard["leads"]["created_today"], 3)
                self.assertEqual(self.client.get("/api/v1/crm/leads/", {"next_action_today": "true"}).data["count"], 1)
                self.client.force_authenticate(self.supervisor)
                team = self.client.get("/api/v1/crm/team/", {"search": "manager"}).data["results"][0]
                self.assertEqual(team["due_today_count"], 1)
                self.assertEqual(team["next_action_overdue_count"], 2)
                # Date filtering still refers to lead creation, also for daily counters.
                filtered = self.client.get("/api/v1/crm/dashboard/", {"created_to": (day - timedelta(microseconds=1)).isoformat()}).data
                self.assertEqual(filtered["leads"]["next_actions_today"], 0)

    def test_team_counts_current_cycles_and_keeps_unavailable_employees_visible(self):
        self.operate(operations.close_lead, status="canceled", result="Отказ")
        self.operate(operations.reopen_lead, reason="Повторно")
        now = timezone.now()
        LeadHandlingCycle.objects.filter(lead=self.lead, ended_at__isnull=False).update(response_due_at=now - timedelta(days=1))
        LeadHandlingCycle.objects.filter(lead=self.lead, ended_at__isnull=True).update(response_warning_at=now - timedelta(minutes=1))
        EmployeeProfile.objects.filter(user=self.manager).update(is_available=False)
        self.assertEqual(self.client.get("/api/v1/crm/team/").status_code, 403)
        self.client.force_authenticate(self.supervisor)
        response = self.client.get("/api/v1/crm/team/", {"ordering": "-awaiting_response_count"})
        self.assertEqual(response.status_code, 200, response.data)
        employee = response.data["results"][0]
        self.assertEqual(employee["user_id"], self.manager.pk)
        self.assertFalse(employee["is_available"])
        self.assertEqual(employee["assigned_count"], 1)
        self.assertEqual(employee["open_count"], 1)
        self.assertEqual(employee["warning_count"], 1)
        self.assertEqual(employee["awaiting_response_count"], 1)
        self.assertEqual(employee["overdue_count"], 0)


class CRMDataSchemaTests(SimpleTestCase):
    def test_schema_describes_scoring_state_and_existing_data_extensions(self):
        from drf_spectacular.generators import SchemaGenerator
        schema = SchemaGenerator().get_schema(public=True)
        models = schema["components"]["schemas"]
        self.assertIn("scoring", models["LeadList"]["properties"])
        self.assertIn("scoring", models["CRMLeadScore"]["properties"])
        self.assertIn("model_version", models["CRMLeadScore"]["properties"])
        self.assertIn("features", models["CRMLeadScore"]["properties"])
        self.assertIn("association", models["CRMBehavior"]["properties"])
        self.assertIn("awaiting_response", models["CRMLeadCounts"]["properties"])
        self.assertIn("awaiting_response_count", models["CRMTeam"]["properties"])
