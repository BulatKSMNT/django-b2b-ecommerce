from fastapi import FastAPI

from app.schemas import HealthResponse, LeadScoringRequest, LeadScoringResponse
from app.scoring import calculate_score


app = FastAPI(
    title="Lead Scoring API",
    description="FastAPI service for rule-based B2B lead scoring.",
    version="1.0.0",
)


@app.get("/health", response_model=HealthResponse, tags=["health"])
async def health_check() -> HealthResponse:
    return HealthResponse(
        status="ok",
        service="lead_scoring_api",
    )


@app.post("/api/v1/score", response_model=LeadScoringResponse, tags=["scoring"])
async def score_lead(payload: LeadScoringRequest) -> LeadScoringResponse:
    return calculate_score(payload)
