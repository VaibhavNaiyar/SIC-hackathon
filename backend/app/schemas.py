"""Pydantic v2 request / response schemas.

All validation lives here — route handlers stay thin.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


# ── User ───────────────────────────────────────────────────────────────────────

class UserCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    age: int = Field(..., ge=13, le=120)
    city: str = Field(..., min_length=1, max_length=100)
    interests: list[str] = Field(default_factory=list)

    @field_validator("name", "city", mode="before")
    @classmethod
    def strip_whitespace(cls, v: str) -> str:
        return v.strip()

    @field_validator("interests", mode="before")
    @classmethod
    def normalise_interests(cls, v: list[str]) -> list[str]:
        return [i.lower().strip() for i in v if i.strip()]


class UserResponse(BaseModel):
    user_id: str
    name: str
    age: int
    city: str
    interests: list[str]
    degree: int = 0

    model_config = {"from_attributes": True}


# ── Friend Requests ────────────────────────────────────────────────────────────

class SendRequestBody(BaseModel):
    from_id: str = Field(..., min_length=1)
    to_id: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def no_self_request(self) -> "SendRequestBody":
        if self.from_id == self.to_id:
            raise ValueError("Cannot send a friend request to yourself.")
        return self


class RequestResponse(BaseModel):
    from_id: str
    to_id: str
    status: str


# ── Path / connection ──────────────────────────────────────────────────────────

class PathResponse(BaseModel):
    path: list[str] | None
    hops: int
    degrees: str
    connected: bool


class AllPathsResponse(BaseModel):
    paths: list[list[str]]
    count: int


# ── Mutual friends ─────────────────────────────────────────────────────────────

class MutualFriendsResponse(BaseModel):
    user_a: str
    user_b: str
    mutual_friends: list[str]
    count: int
    jaccard_similarity: float


# ── Recommendations ────────────────────────────────────────────────────────────

class RecommendationWhyResponse(BaseModel):
    mutuals: list[str]
    shared_interests: list[str]
    same_city: bool
    score: float


class RecommendationResponse(BaseModel):
    candidate_id: str
    candidate_name: str
    why: RecommendationWhyResponse


# ── Analytics ──────────────────────────────────────────────────────────────────

class AnalyticsSummaryResponse(BaseModel):
    total_users: int
    total_edges: int
    density: float
    num_components: int
    largest_component_size: int
    diameter: float
    average_separation: float
    degree_stats: dict[str, Any]


class InfluencerResponse(BaseModel):
    user_id: str
    name: str
    degree: int
    betweenness_approx: float


# ── Graph (force-graph payload) ────────────────────────────────────────────────

class GraphNode(BaseModel):
    id: str
    name: str
    age: int
    city: str
    interests: list[str]
    degree: int
    community: int = 0


class GraphEdge(BaseModel):
    source: str
    target: str


class GraphResponse(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


# ── Generic error ──────────────────────────────────────────────────────────────

class ErrorResponse(BaseModel):
    error: str
    detail: str
