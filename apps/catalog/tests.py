from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product


class CatalogAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.category = Category.objects.create(
            name="Pumps",
            description="Industrial pumps",
            is_active=True,
            sort_order=1,
        )

        self.inactive_category = Category.objects.create(
            name="Hidden category",
            is_active=False,
            sort_order=2,
        )

        self.product = Product.objects.create(
            category=self.category,
            name="Industrial Pump X100",
            description="High performance industrial pump",
            price="120000.00",
            is_active=True,
            sort_order=1,
        )

        Product.objects.create(
            category=self.category,
            name="Inactive Pump",
            price="50000.00",
            is_active=False,
            sort_order=2,
        )

        Product.objects.create(
            category=self.inactive_category,
            name="Hidden Product",
            price="10000.00",
            is_active=True,
            sort_order=3,
        )

    def get_results(self, response):
        payload = response.json()

        if isinstance(payload, dict) and "results" in payload:
            return payload["results"]

        return payload

    def test_categories_list_returns_only_active_categories(self):
        response = self.client.get("/api/v1/categories/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self.get_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], self.category.name)
        self.assertEqual(results[0]["slug"], self.category.slug)

    def test_category_detail_by_slug(self):
        response = self.client.get(f"/api/v1/categories/{self.category.slug}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = response.json()

        self.assertEqual(payload["name"], self.category.name)
        self.assertEqual(payload["slug"], self.category.slug)

    def test_products_list_returns_only_active_products_from_active_categories(self):
        response = self.client.get("/api/v1/products/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self.get_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], self.product.name)

    def test_product_detail_by_id(self):
        response = self.client.get(f"/api/v1/products/{self.product.id}/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        payload = response.json()

        self.assertEqual(payload["id"], self.product.id)
        self.assertEqual(payload["name"], self.product.name)
        self.assertEqual(payload["category"]["id"], self.category.id)
        self.assertIn("attributes", payload)
        self.assertIn("images", payload)

    def test_products_can_be_filtered_by_category_slug(self):
        response = self.client.get(
            "/api/v1/products/",
            {"category_slug": self.category.slug},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self.get_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], self.product.name)

    def test_products_can_be_searched(self):
        response = self.client.get(
            "/api/v1/products/",
            {"search": "Pump"},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        results = self.get_results(response)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], self.product.name)

    def test_openapi_schema_is_available(self):
        response = self.client.get("/api/schema/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_swagger_docs_are_available(self):
        response = self.client.get("/api/docs/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
