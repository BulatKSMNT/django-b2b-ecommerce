from django.test import TestCase
from apps.analytics.predictors import score_lead_features

class ScoringFunctionTests(TestCase):

    def test_cart_lead_gets_high_priority(self):
        features = {
            "source": "cart",
            "status": "new",
            "has_profile": True,
            "has_visitor": True,
            "has_items": True,
            "items_count": 5,
            "total_quantity": 10,
            "total_amount": 120000,
            "has_unpriced_items": False,
            "comment_length": 80,
            "is_business_email": True,
            "page_visits_24h": 5,
            "page_visits_7d": 12,
            "product_views_7d": 6,
            "cart_adds_7d": 2,
            "favorite_adds_7d": 1,
            "viewed_requested_products_7d": 1,
            "previous_leads_30d": 0,
            "previous_leads_90d": 0,
            "has_utm": True,
            "requested_product_ids_count": 5,
            "email_domain": "company.com",
        }
        result = score_lead_features(features)
        self.assertEqual(result["priority"], "high")
        self.assertGreaterEqual(result["score"], 70)

    def test_empty_contact_lead_gets_low_priority(self):
        features = {
            "source": "contact",
            "status": "new",
            "has_profile": False,
            "has_visitor": False,
            "has_items": False,
            "items_count": 0,
            "total_quantity": 0,
            "total_amount": 0,
            "has_unpriced_items": False,
            "comment_length": 0,
            "is_business_email": False,
            "page_visits_24h": 0,
            "page_visits_7d": 0,
            "product_views_7d": 0,
            "cart_adds_7d": 0,
            "favorite_adds_7d": 0,
            "viewed_requested_products_7d": 0,
            "previous_leads_30d": 0,
            "previous_leads_90d": 0,
            "has_utm": False,
            "requested_product_ids_count": 0,
            "email_domain": "gmail.com",
        }
        result = score_lead_features(features)
        self.assertEqual(result["priority"], "low")
        self.assertLess(result["score"], 40)

    def test_business_email_adds_points(self):
        features = {
            "source": "contact",
            "is_business_email": True,
            "email_domain": "mycompany.ru",
            # остальные нули
            "status": "new",
            "has_profile": False,
            "has_visitor": False,
            "has_items": False,
            "items_count": 0,
            "total_quantity": 0,
            "total_amount": 0,
            "has_unpriced_items": False,
            "comment_length": 0,
            "page_visits_24h": 0,
            "page_visits_7d": 0,
            "product_views_7d": 0,
            "cart_adds_7d": 0,
            "favorite_adds_7d": 0,
            "viewed_requested_products_7d": 0,
            "previous_leads_30d": 0,
            "previous_leads_90d": 0,
            "has_utm": False,
            "requested_product_ids_count": 0,
        }
        result = score_lead_features(features)
        # базовый бал source_contact=8 + business_email=8 = 16
        self.assertAlmostEqual(result["score"], 16.0, places=1)

    def test_score_clamped_to_100(self):
        features = {
            "source": "cart",
            "status": "new",
            "has_profile": True,
            "has_visitor": True,
            "has_items": True,
            "items_count": 10,
            "total_quantity": 100,
            "total_amount": 500000,
            "has_unpriced_items": True,
            "comment_length": 200,
            "is_business_email": True,
            "page_visits_24h": 10,
            "page_visits_7d": 30,
            "product_views_7d": 20,
            "cart_adds_7d": 10,
            "favorite_adds_7d": 5,
            "viewed_requested_products_7d": 5,
            "previous_leads_30d": 5,
            "previous_leads_90d": 10,
            "has_utm": True,
            "requested_product_ids_count": 10,
            "email_domain": "corp.com",
        }
        result = score_lead_features(features)
        self.assertEqual(result["score"], 100.0)

class ScoringLogicTests(TestCase):
    def get_base_features(self):
        return {
            "source": "contact",
            "status": "new",
            "has_profile": False,
            "has_visitor": False,
            "has_items": False,
            "items_count": 0,
            "total_quantity": 0,
            "total_amount": 0.0,
            "has_unpriced_items": False,
            "comment_length": 0,
            "is_business_email": False,
            "email_domain": "gmail.com",
            "page_visits_24h": 0,
            "page_visits_7d": 0,
            "product_views_7d": 0,
            "cart_adds_7d": 0,
            "favorite_adds_7d": 0,
            "viewed_requested_products_7d": 0,
            "previous_leads_30d": 0,
            "previous_leads_90d": 0,
            "has_utm": False,
            "requested_product_ids_count": 0,
        }

    def test_empty_contact_lead_gets_low_priority(self):
        features = self.get_base_features()
        result = score_lead_features(features)
        
        self.assertEqual(result["priority"], "low")
        self.assertLess(result["score"], 40)

    def test_cart_lead_with_high_amount_gets_high_priority(self):
        features = self.get_base_features()
        features.update({
            "source": "cart",
            "has_items": True,
            "items_count": 5,
            "total_quantity": 50,
            "total_amount": 250000.0,
            "is_business_email": True,
        })
        result = score_lead_features(features)
        
        self.assertEqual(result["priority"], "high")
        self.assertGreaterEqual(result["score"], 70)

    def test_active_user_gets_bonus_points(self):
        features = self.get_base_features()
        base_result = score_lead_features(features)
        
        features.update({
            "page_visits_24h": 10,
            "product_views_7d": 15,
            "cart_adds_7d": 5,
        })
        active_result = score_lead_features(features)
        
        self.assertGreater(active_result["score"], base_result["score"])
        self.assertTrue(any(r["code"] == "active_last_24h" for r in active_result["explanation"]))

    def test_score_does_not_exceed_100(self):
        features = self.get_base_features()
        features.update({
            "source": "cart",
            "items_count": 100,
            "total_quantity": 1000,
            "total_amount": 1000000.0,
            "is_business_email": True,
            "page_visits_24h": 100,
            "cart_adds_7d": 100,
            "previous_leads_90d": 10,
        })
        result = score_lead_features(features)
        
        self.assertEqual(result["score"], 100.0)  # Скор должен быть обрезан до 100
