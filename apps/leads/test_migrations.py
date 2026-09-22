from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone


class ExistingLeadMigrationTests(TransactionTestCase):
    """Exercise real schema + data migration with historical models on the test DB."""

    def test_old_leads_items_scores_and_employee_access_survive(self):
        old_targets = [
            ("accounts", "0001_initial"),
            ("leads", "0002_lead_referer_lead_utm_campaign_lead_utm_content_and_more"),
        ]
        executor = MigrationExecutor(connection)
        latest = executor.loader.graph.leaf_nodes()
        # Only the disposable test DB: forget the irreversible import receipt, then
        # reverse schema to construct realistic old records before migrating forward.
        executor.migrate([("leads", "0004_import_existing_leads")])
        executor = MigrationExecutor(connection)
        executor.migrate([("leads", "0003_lead_management")], fake=True)
        try:
            executor = MigrationExecutor(connection)
            executor.migrate(old_targets)
            apps = executor.loader.project_state(old_targets).apps
            User = apps.get_model("accounts", "User")
            Lead = apps.get_model("leads", "Lead")
            Item = apps.get_model("leads", "LeadItem")
            staff = User.objects.create(username="legacy-staff", email="legacy@example.com", is_staff=True)
            customer = User.objects.create(username="customer", email="customer@example.com")
            ids = []
            for status in ("new", "in_progress", "completed", "canceled"):
                lead = Lead.objects.create(
                    status=status, fullname="Старый клиент", email="old@example.com",
                    phone_number="+79991234567", processed_by=staff,
                    processed_at=timezone.now(), manager_comment="Историческая заметка",
                )
                Item.objects.create(lead=lead, product_name="Снимок", quantity=3, product_price="12.00", line_total="36.00", snapshot={"legacy": "unchanged"})
                ids.append(lead.pk)
            # Analytics tables already exist and are unaffected by these migrations.
            from apps.analytics.models import LeadScore
            score = LeadScore.objects.create(lead_id=ids[0], score=72, features={"legacy": True})
            executor = MigrationExecutor(connection)
            executor.migrate(latest)
            apps = executor.loader.project_state(latest).apps
            Lead = apps.get_model("leads", "Lead")
            Cycle = apps.get_model("leads", "LeadHandlingCycle")
            Employee = apps.get_model("accounts", "EmployeeProfile")
            self.assertEqual(Employee.objects.get(user_id=staff.pk).role, "supervisor")
            self.assertFalse(Employee.objects.filter(user_id=customer.pk).exists())
            self.assertEqual(list(Lead.objects.filter(pk__in=ids).order_by("pk").values_list("status", flat=True)), ["new", "in_progress", "completed", "canceled"])
            self.assertIsNone(Lead.objects.get(pk=ids[0]).assignee_id)
            self.assertEqual(Lead.objects.get(pk=ids[1]).assignee_id, staff.pk)
            self.assertEqual(Cycle.objects.filter(lead_id__in=ids, is_imported=True).count(), 4)
            self.assertEqual(Cycle.objects.filter(lead_id__in=ids, ended_at__isnull=False).count(), 2)
            self.assertFalse(Cycle.objects.filter(first_contact_at__isnull=False).exists())
            self.assertFalse(Cycle.objects.filter(response_due_at__isnull=False).exists())
            for model in ("LeadEvent", "LeadInteraction", "LeadComment", "Notification"):
                self.assertEqual(apps.get_model("leads", model).objects.count(), 0)
            Item = apps.get_model("leads", "LeadItem")
            for item in Item.objects.filter(lead_id__in=ids):
                self.assertEqual(item.snapshot, {"legacy": "unchanged"})
                self.assertEqual(str(item.line_total), "36.00")
                self.assertEqual(item.quantity, 3)
            self.assertEqual(Lead.objects.filter(pk__in=ids, manager_comment="Историческая заметка").count(), 4)
            score.refresh_from_db()
            self.assertEqual(score.features, {"legacy": True})
            self.assertEqual(apps.get_model("analytics", "LeadScoringState").objects.count(), 0)
        finally:
            MigrationExecutor(connection).migrate(latest)
