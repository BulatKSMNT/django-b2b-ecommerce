from typing import Literal

from pydantic import BaseModel, Field


LeadSource = Literal["contact", "product", "cart"]
Priority = Literal["low", "medium", "high"]


class LeadScoringRequest(BaseModel):
    source: LeadSource = Field(default="contact")
    status: str = Field(default="new")

    has_profile: bool = Field(default=False)
    has_visitor: bool = Field(default=False)

    has_items: bool = Field(default=False)
    items_count: int = Field(default=0, ge=0)
    total_quantity: int = Field(default=0, ge=0)
    total_amount: float = Field(default=0.0, ge=0)
    has_unpriced_items: bool = Field(default=False)

    comment_length: int = Field(default=0, ge=0)
    is_business_email: bool = Field(default=False)
    email_domain: str = Field(default="")

    page_visits_24h: int = Field(default=0, ge=0)
    page_visits_7d: int = Field(default=0, ge=0)
    product_views_7d: int = Field(default=0, ge=0)
    cart_adds_7d: int = Field(default=0, ge=0)
    favorite_adds_7d: int = Field(default=0, ge=0)
    viewed_requested_products_7d: int = Field(default=0, ge=0)

    previous_leads_30d: int = Field(default=0, ge=0)
    previous_leads_90d: int = Field(default=0, ge=0)

    has_utm: bool = Field(default=False)
    requested_product_ids_count: int = Field(default=0, ge=0)


class ScoreReason(BaseModel):
    code: str
    label: str
    points: int


class LeadScoringResponse(BaseModel):
    score: float
    priority: Priority
    model_name: str
    model_version: str
    explanation: list[ScoreReason]


class HealthResponse(BaseModel):
    status: str
    service: str
