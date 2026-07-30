from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.leads.models import Lead


class LeadAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        User = get_user_model()

        self.staff_user = User.objects.create_user(
            username="staff",
            email="staff@example.com",
            password="test-password",
            is_staff=True,
        )

        self.regular_user = User.objects.create_user(
            username="user",
            email="user@example.com",
            password="test-password",
            is_staff=False,
        )

        self.lead = Lead.objects.create(
            source=Lead.Source.CONTACT,
            status=Lead.Status.NEW,
            fullname="Ivan Petrov",
            phone_number="+79991234567",
            email="ivan@example.com",
            comment="Test lead comment",
        )

    def test_anonymous_user_cannot_list_leads(self):
        response = self.client.get("/api/v1/leads/")

        self.assertIn(
            response.status_code,
            [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN],
        )

    def test_regular_user_cannot_list_leads(self):
        self.client.force_authenticate(user=self.regular_user)

        response = self.client.get("/api/v1/leads/")

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_staff_user_can_list_leads(self):
        self.client.force_authenticate(user=self.staff_user)

        response = self.client.get("/api/v1/leads/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = response.json()
        results = payload["results"] if isinstance(payload, dict) and "results" in payload else payload

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["id"], self.lead.id)

    def test_staff_user_can_retrieve_lead_detail(self):
        self.client.force_authenticate(user=self.staff_user)

        response = self.client.get(f"/api/v1/leads/{self.lead.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = response.json()

        self.assertEqual(payload["id"], self.lead.id)
        self.assertEqual(payload["fullname"], self.lead.fullname)
        self.assertIn("items", payload)

    def test_public_contact_lead_can_be_created_via_api(self):
        response = self.client.post(
            "/api/v1/leads/contact/",
            data={
                "fullname": "Petr Sidorov",
                "phone_number": "+79998887766",
                "email": "petr@example.com",
                "comment": "Created from API",
                "agree_to_policy": True,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.assertTrue(
            Lead.objects.filter(
                fullname="Petr Sidorov",
                email="petr@example.com",
                source=Lead.Source.CONTACT,
            ).exists()
        )

    def test_contact_lead_api_requires_policy_agreement(self):
        response = self.client.post(
            "/api/v1/leads/contact/",
            data={
                "fullname": "Petr Sidorov",
                "phone_number": "+79998887766",
                "email": "petr@example.com",
                "comment": "Created from API",
                "agree_to_policy": False,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_get_score_returns_404_if_score_not_calculated(self):
        self.client.force_authenticate(user=self.staff_user)

        response = self.client.get(f"/api/v1/leads/{self.lead.id}/score/")

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_staff_user_can_recalculate_lead_score(self):
        self.client.force_authenticate(user=self.staff_user)

        response = self.client.post(
            f"/api/v1/leads/{self.lead.id}/score/recalculate/",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = response.json()

        self.assertEqual(payload["lead_id"], self.lead.id)
        self.assertIn("score", payload)
        self.assertIn("priority", payload)
        self.assertEqual(payload["model_name"], "rule_based_lead_scoring")

        self.lead.refresh_from_db()
        self.assertTrue(hasattr(self.lead, "score"))

    def test_staff_user_can_get_score_after_recalculation(self):
        self.client.force_authenticate(user=self.staff_user)

        self.client.post(f"/api/v1/leads/{self.lead.id}/score/recalculate/")

        response = self.client.get(f"/api/v1/leads/{self.lead.id}/score/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = response.json()

        self.assertEqual(payload["lead_id"], self.lead.id)
        self.assertEqual(payload["model_name"], "rule_based_lead_scoring")
