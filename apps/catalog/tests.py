from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductImage, Attribute, ProductAttributeValue


class CatalogModelTests(TestCase):

    def setUp(self):
        self.category = Category.objects.create(name="Test Category", is_active=True)
        self.product = Product.objects.create(
            category=self.category,
            name="Test Product",
            price=100.00,
            is_active=True,
        )

    def test_slug_is_generated_on_save(self):
        # Категория без slug должна получить slug автоматически
        cat = Category(name="New Category")
        cat.save()
        self.assertIsNotNone(cat.slug)
        self.assertNotEqual(cat.slug, "")

    def test_product_slug(self):
        # Slug товара генерируется
        self.assertIsNotNone(self.product.slug)
        self.assertIn("test-product", self.product.slug)

    def test_unique_slug_per_product_in_category(self):
        # Попытка создать товар с дублирующимся slug в той же категории
        product2 = Product(category=self.category, name="Test Product")
        product2.save()
        self.assertNotEqual(product2.slug, self.product.slug)

    def test_product_image_cannot_have_two_primary(self):
        # Создаем первое основное изображение
        img1 = ProductImage.objects.create(product=self.product, image="test1.jpg", is_primary=True)
        # Создаем второе основное изображение - должно вызвать ValidationError
        img2 = ProductImage(product=self.product, image="test2.jpg", is_primary=True)
        with self.assertRaises(ValidationError):
            img2.full_clean()

    def test_attribute_value_must_match_category(self):
        # Создаем атрибут для другой категории
        other_category = Category.objects.create(name="Other")
        attr = Attribute.objects.create(category=other_category, name="TestAttr")
        # Привязываем атрибут к товару из категории, где этого атрибута нет
        value = ProductAttributeValue(product=self.product, attribute=attr, value="x")
        with self.assertRaises(ValidationError):
            value.full_clean()


class CatalogAPITests(TestCase):
    def setUp(self):
        self.client = APIClient()

        self.category = Category.objects.create(name="Pumps", is_active=True, sort_order=1)
        self.inactive_category = Category.objects.create(name="Hidden", is_active=False, sort_order=2)

        self.product = Product.objects.create(
            category=self.category, name="Industrial Pump", price="120000.00", is_active=True
        )
        Product.objects.create(category=self.category, name="Inactive Pump", is_active=False)

    def get_results(self, response):
        payload = response.json()
        return payload.get("results", payload) if isinstance(payload, dict) else payload

    def test_categories_list_returns_only_active_categories(self):
        response = self.client.get("/api/v1/categories/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self.get_results(response)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], self.category.name)

    def test_category_detail_by_slug(self):
        response = self.client.get(f"/api/v1/categories/{self.category.slug}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["name"], self.category.name)

    def test_products_list_returns_only_active_products(self):
        response = self.client.get("/api/v1/products/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        results = self.get_results(response)
        self.assertEqual(len(results), 1)

    def test_product_detail_by_id(self):
        response = self.client.get(f"/api/v1/products/{self.product.id}/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.json()["name"], self.product.name)

    def test_products_can_be_filtered_by_category_slug(self):
        response = self.client.get("/api/v1/products/", {"category_slug": self.category.slug})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self.get_results(response)), 1)

    def test_products_can_be_searched(self):
        response = self.client.get("/api/v1/products/", {"search": "Pump"})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(self.get_results(response)), 1)

    def test_openapi_schema_is_available(self):
        response = self.client.get("/api/schema/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_swagger_docs_are_available(self):
        response = self.client.get("/api/docs/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
