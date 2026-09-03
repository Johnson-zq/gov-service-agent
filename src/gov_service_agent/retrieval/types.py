"""Retrieval result types and constants (F06)."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


EXPECTED_EMBEDDING_DIMENSION = 768
PROJECTION_VERSION = "business-intent-v1"
POLICY_VERSION = "f06-online-v1"
ARTIFACT_SCHEMA_VERSION = 1
INDEX_NAME = "business_intent"
ELIGIBILITY_SCOPE_ONLINE = "ONLINE"
DEFAULT_TOP_K = 5
DEFAULT_MIN_SCORE = 0.50


class RetrievalStatus(str, Enum):
    INVALID_QUERY = "INVALID_QUERY"
    UNAVAILABLE = "UNAVAILABLE"
    NOT_READY = "NOT_READY"
    NO_USABLE_CANDIDATE = "NO_USABLE_CANDIDATE"
    CANDIDATES = "CANDIDATES"


class NotReadyReason(str, Enum):
    PROVIDER_NOT_CONFIGURED = "PROVIDER_NOT_CONFIGURED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"
    MODEL_NOT_AVAILABLE = "MODEL_NOT_AVAILABLE"
    DEVICE_UNAVAILABLE = "DEVICE_UNAVAILABLE"
    INDEX_MISSING = "INDEX_MISSING"
    MODEL_MISMATCH = "MODEL_MISMATCH"
    DIMENSION_MISMATCH = "DIMENSION_MISMATCH"
    PROJECTION_VERSION_MISMATCH = "PROJECTION_VERSION_MISMATCH"
    POLICY_VERSION_MISMATCH = "POLICY_VERSION_MISMATCH"
    POLICY_INVALID = "POLICY_INVALID"


class RetrievalCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    business_id: str
    display_name: str
    score: float
    rank: int = Field(ge=1)
    direction: str
    eligibility_scope: str = ELIGIBILITY_SCOPE_ONLINE


class RetrievalResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: RetrievalStatus
    query: str
    reason: NotReadyReason | None = None
    direction: str | None = None
    candidates: list[RetrievalCandidate] = Field(default_factory=list)
    provider_name: str | None = None
    model_id: str | None = None
    projection_version: str | None = None
    policy_version: str | None = None
    projection_key: str | None = None
    top_k: int | None = None
    min_score: float | None = None
