"""Online retrieval admission policy + corpus helpers (F06)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from gov_service_agent.business_data.models import (
    BusinessSnapshot,
    DataScope,
    LifecycleStatus,
)
from gov_service_agent.business_data.repository import (
    BusinessNotFoundError,
    JsonBusinessRepository,
)
from gov_service_agent.retrieval.types import (
    ARTIFACT_SCHEMA_VERSION,
    POLICY_VERSION,
    PROJECTION_VERSION,
)


class AdmissionPolicyError(ValueError):
    """Eligibility artifact is invalid or unusable."""


@dataclass(frozen=True, slots=True)
class AdmissionEntry:
    business_id: str
    decision: str
    reason: str


@dataclass(frozen=True, slots=True)
class AdmissionPolicy:
    schema_version: int
    policy_version: str
    entries: tuple[AdmissionEntry, ...]

    def allow_ids(self) -> frozenset[str]:
        return frozenset(
            e.business_id for e in self.entries if e.decision == "ALLOW"
        )


@dataclass(frozen=True, slots=True)
class RetrievalDocumentDraft:
    business_id: str
    display_name: str
    direction: str
    retrieval_text: str
    source_data_version: int
    source_fingerprint: str


def load_admission_policy(path: Path | str) -> AdmissionPolicy:
    file_path = Path(path)
    try:
        raw = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdmissionPolicyError("eligibility artifact cannot be parsed") from exc
    return parse_admission_policy(raw)


def parse_admission_policy(raw: Any) -> AdmissionPolicy:
    if not isinstance(raw, dict):
        raise AdmissionPolicyError("eligibility artifact must be an object")

    schema_version = raw.get("schema_version")
    if schema_version != ARTIFACT_SCHEMA_VERSION:
        raise AdmissionPolicyError("unsupported eligibility artifact schema_version")

    policy_version = raw.get("policy_version")
    if not isinstance(policy_version, str) or not policy_version.strip():
        raise AdmissionPolicyError("eligibility artifact policy_version is required")
    policy_version = policy_version.strip()

    entries_raw = raw.get("entries")
    if not isinstance(entries_raw, list):
        raise AdmissionPolicyError("eligibility artifact entries must be a list")

    seen: set[str] = set()
    entries: list[AdmissionEntry] = []
    for item in entries_raw:
        if not isinstance(item, dict):
            raise AdmissionPolicyError("eligibility entry must be an object")
        business_id = item.get("business_id")
        decision = item.get("decision")
        reason = item.get("reason")
        if not isinstance(business_id, str) or not business_id.strip():
            raise AdmissionPolicyError("eligibility entry business_id is required")
        business_id = business_id.strip()
        if business_id in seen:
            raise AdmissionPolicyError(
                "duplicate business_id in eligibility artifact"
            )
        seen.add(business_id)
        if decision != "ALLOW":
            raise AdmissionPolicyError(
                "eligibility entry decision must be ALLOW for F06"
            )
        if not isinstance(reason, str) or not reason.strip():
            raise AdmissionPolicyError("eligibility entry reason must be non-empty")
        entries.append(
            AdmissionEntry(
                business_id=business_id,
                decision="ALLOW",
                reason=reason.strip(),
            )
        )

    return AdmissionPolicy(
        schema_version=int(schema_version),
        policy_version=policy_version,
        entries=tuple(entries),
    )


def is_online_retrieval_eligible(
    snapshot: BusinessSnapshot,
    *,
    policy: AdmissionPolicy,
) -> bool:
    """Deterministic ONLINE predicate (admission safety; not VERIFIED)."""
    business = snapshot.business
    if business.business_id not in policy.allow_ids():
        return False
    if business.status != LifecycleStatus.ACTIVE:
        return False
    if business.data_scope == DataScope.TEST:
        return False
    source_ids = {s.source_id for s in snapshot.sources}
    if business.primary_source_id not in source_ids:
        return False
    return True


def build_retrieval_text(snapshot: BusinessSnapshot) -> str:
    category = snapshot.business.category.strip()
    name = snapshot.business.canonical_name.strip()
    if not category or not name:
        raise ValueError("category and canonical_name must be non-empty")
    return f"{category}\n{name}"


def source_fingerprint(
    snapshot: BusinessSnapshot,
    *,
    retrieval_text: str,
    projection_version: str = PROJECTION_VERSION,
    policy_version: str = POLICY_VERSION,
) -> str:
    business = snapshot.business
    payload = (
        f"{business.business_id}|{business.data_version}|"
        f"{business.category.strip()}|{business.canonical_name.strip()}|"
        f"{projection_version}|{policy_version}|{retrieval_text}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_projection_key(
    *,
    provider_name: str,
    model_id: str,
    dimension: int,
    projection_version: str = PROJECTION_VERSION,
    policy_version: str = POLICY_VERSION,
) -> str:
    parts = [
        provider_name.strip(),
        model_id.strip(),
        str(int(dimension)),
        projection_version.strip(),
        policy_version.strip(),
    ]
    canonical = "\0".join(parts)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def draft_online_documents(
    repository: JsonBusinessRepository,
    policy: AdmissionPolicy,
) -> list[RetrievalDocumentDraft]:
    """
    Build ONLINE drafts for all ALLOW entries.

    Unknown business_id in policy → fail closed (entire rebuild).
    """
    if policy.policy_version != POLICY_VERSION:
        # Compared again by builder/service against expected constant.
        pass

    drafts: list[RetrievalDocumentDraft] = []
    for entry in policy.entries:
        if entry.decision != "ALLOW":
            continue
        try:
            snapshot = repository.get_snapshot(entry.business_id)
        except BusinessNotFoundError as exc:
            raise AdmissionPolicyError(
                f"eligibility ALLOW references unknown business_id: "
                f"{entry.business_id}"
            ) from exc
        if not is_online_retrieval_eligible(snapshot, policy=policy):
            raise AdmissionPolicyError(
                f"eligibility ALLOW entry fails ONLINE predicate: "
                f"{entry.business_id}"
            )
        text = build_retrieval_text(snapshot)
        drafts.append(
            RetrievalDocumentDraft(
                business_id=snapshot.business.business_id,
                display_name=snapshot.business.canonical_name,
                direction=snapshot.business.category,
                retrieval_text=text,
                source_data_version=snapshot.business.data_version,
                source_fingerprint=source_fingerprint(
                    snapshot,
                    retrieval_text=text,
                    policy_version=policy.policy_version,
                ),
            )
        )
    return drafts
