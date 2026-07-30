from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health_check_returns_ok():
    response = client.get("/health")

    assert response.status_code == 200

    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["service"] == "lead_scoring_api"


def test_contact_lead_gets_low_priority():
    response = client.post(
        "/api/v1/score",
        json={
            "source": "contact",
            "items_count": 0,
            "total_quantity": 0,
            "total_amount": 0,
            "comment_length": 0,
            "is_business_email": False,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["score"] < 40
    assert payload["priority"] == "low"
    assert payload["model_name"] == "rule_based_fastapi_scoring"


def test_cart_lead_gets_high_priority():
    response = client.post(
        "/api/v1/score",
        json={
            "source": "cart",
            "has_profile": True,
            "has_items": True,
            "items_count": 5,
            "total_quantity": 10,
            "total_amount": 120000,
            "has_unpriced_items": False,
            "comment_length": 80,
            "is_business_email": True,
            "page_visits_24h": 4,
            "page_visits_7d": 12,
            "product_views_7d": 6,
            "cart_adds_7d": 2,
            "favorite_adds_7d": 1,
            "viewed_requested_products_7d": 1,
            "previous_leads_90d": 0,
            "has_utm": True,
        },
    )

    assert response.status_code == 200

    payload = response.json()

    assert payload["score"] >= 70
    assert payload["priority"] == "high"
    assert len(payload["explanation"]) > 0


def test_score_endpoint_rejects_negative_values():
    response = client.post(
        "/api/v1/score",
        json={
            "source": "cart",
            "items_count": -1,
        },
    )

    assert response.status_code == 422

def test_invalid_source_rejected():
    response = client.post("/api/v1/score", json={
        "source": "invalid",
        "items_count": 0,
        "total_quantity": 0,
        "total_amount": 0,
        "comment_length": 0,
        "is_business_email": False,
    })
    assert response.status_code == 422

def test_negative_items_count_rejected():
    response = client.post("/api/v1/score", json={
        "source": "cart",
        "items_count": -1,
    })
    assert response.status_code == 422

def test_missing_required_field():
    response = client.post("/api/v1/score", json={})
    assert response.status_code == 422
