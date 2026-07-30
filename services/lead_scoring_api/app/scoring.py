from app.schemas import LeadScoringRequest, LeadScoringResponse, ScoreReason


MODEL_NAME = "rule_based_fastapi_scoring"
MODEL_VERSION = "1.0"


def calculate_score(features: LeadScoringRequest) -> LeadScoringResponse:
    score = 0
    explanation: list[ScoreReason] = []

    def add(points: int, code: str, label: str) -> None:
        nonlocal score

        if points <= 0:
            return

        score += points
        explanation.append(
            ScoreReason(
                code=code,
                label=label,
                points=points,
            )
        )

    if features.source == "cart":
        add(25, "source_cart", "Lead was created from cart")
    elif features.source == "product":
        add(18, "source_product", "Lead was created from product page")
    else:
        add(8, "source_contact", "Contact form lead")

    if features.has_profile:
        add(8, "has_profile", "Authenticated customer profile")
    elif features.has_visitor:
        add(3, "has_visitor", "Visitor identifier exists")

    if features.items_count >= 5:
        add(20, "many_items", "Lead contains many items")
    elif features.items_count >= 3:
        add(14, "several_items", "Lead contains several items")
    elif features.items_count >= 1:
        add(7, "single_item", "Lead contains a product")

    if features.total_quantity >= 10:
        add(12, "large_quantity", "Large total quantity")
    elif features.total_quantity >= 5:
        add(8, "medium_quantity", "Medium total quantity")
    elif features.total_quantity >= 2:
        add(4, "small_quantity", "Quantity is greater than one")

    if features.total_amount >= 200000:
        add(18, "high_amount", "High lead amount")
    elif features.total_amount >= 100000:
        add(14, "mid_high_amount", "Significant lead amount")
    elif features.total_amount >= 50000:
        add(10, "medium_amount", "Medium lead amount")
    elif features.total_amount >= 10000:
        add(6, "low_amount", "Lead has measurable amount")

    if features.has_unpriced_items:
        add(5, "unpriced_items", "Lead contains products with price on request")

    if features.is_business_email:
        add(8, "business_email", "Business email domain")

    if features.comment_length >= 150:
        add(10, "long_comment", "Detailed customer comment")
    elif features.comment_length >= 50:
        add(6, "medium_comment", "Meaningful customer comment")
    elif features.comment_length >= 15:
        add(3, "short_comment", "Customer left a comment")

    if features.page_visits_24h >= 8:
        add(10, "active_last_24h", "High activity in the last 24 hours")
    elif features.page_visits_24h >= 3:
        add(5, "some_activity_last_24h", "Some activity in the last 24 hours")

    if features.page_visits_7d >= 15:
        add(8, "many_page_visits", "Many page visits in the last 7 days")
    elif features.page_visits_7d >= 5:
        add(4, "medium_page_visits", "Several page visits in the last 7 days")

    if features.product_views_7d >= 8:
        add(10, "many_product_views", "Many product views")
    elif features.product_views_7d >= 3:
        add(5, "medium_product_views", "Some product interest")

    if features.cart_adds_7d >= 3:
        add(12, "many_cart_adds", "Several cart additions")
    elif features.cart_adds_7d >= 1:
        add(6, "cart_adds", "Product was added to cart")

    if features.favorite_adds_7d >= 3:
        add(6, "many_favorite_adds", "Several favorite additions")
    elif features.favorite_adds_7d >= 1:
        add(3, "favorite_adds", "Product was added to favorites")

    if features.viewed_requested_products_7d >= 3:
        add(
            9,
            "viewed_requested_products_many",
            "Customer viewed requested products several times",
        )
    elif features.viewed_requested_products_7d >= 1:
        add(
            4,
            "viewed_requested_products",
            "Customer viewed requested products before lead creation",
        )

    if features.previous_leads_90d >= 3:
        add(7, "repeat_leads_many", "Multiple previous leads")
    elif features.previous_leads_90d >= 1:
        add(4, "repeat_leads", "Customer has previous leads")

    if features.has_utm:
        add(2, "has_utm", "Marketing attribution data exists")

    score = max(0, min(score, 100))

    if score >= 70:
        priority = "high"
    elif score >= 40:
        priority = "medium"
    else:
        priority = "low"

    return LeadScoringResponse(
        score=round(float(score), 2),
        priority=priority,
        model_name=MODEL_NAME,
        model_version=MODEL_VERSION,
        explanation=explanation,
    )
