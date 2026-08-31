"""F02 Business Data Contract tests (written in Code; executed in Test stage)."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest
from pydantic import ValidationError

from gov_service_agent.business_data import (
    BusinessSnapshot,
    ConditionExecutable,
    VerificationStatus,
    load_snapshot,
    snapshot_from_dict,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEMO_SS_001_PATH = REPO_ROOT / "data" / "demo" / "demo_ss_001.json"


def _demo_dict() -> dict:
    return BusinessSnapshot.model_validate_json(
        DEMO_SS_001_PATH.read_text(encoding="utf-8")
    ).model_dump(mode="json")


def test_demo_ss_001_snapshot_loads() -> None:
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    assert snapshot.schema_version == "1"
    assert snapshot.business.business_id == "DEMO_SS_001"
    assert snapshot.business.data_scope.value == "DEMO"
    assert snapshot.business.data_version == 1


def test_demo_ss_001_canonical_name() -> None:
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    assert snapshot.business.canonical_name == "灵活就业人员社会保险费申报缴费"


def test_demo_ss_001_has_id_card_material() -> None:
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    texts = [m.source_text for m in snapshot.materials]
    assert "身份证" in texts
    material = next(m for m in snapshot.materials if m.source_text == "身份证")
    assert material.source_status == VerificationStatus.SOURCE_EXPLICIT
    assert material.requirement_level.value == "REQUIRED"
    assert material.requirement_level_status == VerificationStatus.SYSTEM_DERIVED
    assert material.evidence.source_section == "申请材料"


def test_demo_ss_001_handling_location() -> None:
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    assert len(snapshot.handling_locations) == 1
    loc = snapshot.handling_locations[0]
    assert loc.name == "国家税务总局杭州市上城区税务局建国南路办公区"
    assert loc.address == "杭州市上城区小营街道建国南路42号"
    assert loc.floor is None
    assert loc.window is None


def test_source_explicit_requires_evidence() -> None:
    data = _demo_dict()
    data["conditions"][0]["evidence"] = None
    with pytest.raises(ValidationError):
        snapshot_from_dict(data)


def test_system_derived_requires_lineage() -> None:
    data = _demo_dict()
    data["materials"][0]["derivation_note"] = None
    with pytest.raises(ValidationError):
        snapshot_from_dict(data)


def test_to_confirm_cannot_be_executable() -> None:
    data = _demo_dict()
    tc = next(
        c for c in data["conditions"] if c["source_status"] == "TO_CONFIRM"
    )
    tc["executable"] = {
        "operator": "eq",
        "verification_status": "VERIFIED",
        "usable_by_rule_engine": True,
    }
    with pytest.raises(ValidationError):
        snapshot_from_dict(data)


def test_verified_executable_passes_validation() -> None:
    """Pure fixture: does not claim DEMO_SS_001 has VERIFIED rules."""
    executable = ConditionExecutable(
        operator="in",
        verification_status=VerificationStatus.VERIFIED,
        usable_by_rule_engine=True,
    )
    assert executable.usable_by_rule_engine is True

    data = _demo_dict()
    cond = deepcopy(data["conditions"][0])
    cond["condition_id"] = "cond-fixture-verified"
    cond["executable"] = {
        "operator": "in",
        "verification_status": "VERIFIED",
        "usable_by_rule_engine": True,
    }
    data["conditions"].append(cond)
    snapshot = snapshot_from_dict(data)
    verified = next(
        c for c in snapshot.conditions if c.condition_id == "cond-fixture-verified"
    )
    assert verified.executable is not None
    assert verified.executable.verification_status == VerificationStatus.VERIFIED


def test_location_floor_window_null_allowed() -> None:
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    loc = snapshot.handling_locations[0]
    assert loc.floor is None
    assert loc.window is None
    assert loc.location_detail_status.value == "UNKNOWN_DETAIL"


def test_no_unconfirmed_service_center_address() -> None:
    raw = DEMO_SS_001_PATH.read_text(encoding="utf-8")
    assert "政务服务中心" not in raw
    assert "1F" not in raw
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    for loc in snapshot.handling_locations:
        assert "政务服务中心" not in loc.name
        assert "政务服务中心" not in loc.address


def test_demo_ss_001_condition_counts() -> None:
    snapshot = load_snapshot(DEMO_SS_001_PATH)
    source_explicit = [
        c
        for c in snapshot.conditions
        if c.source_status == VerificationStatus.SOURCE_EXPLICIT
    ]
    to_confirm = [
        c
        for c in snapshot.conditions
        if c.source_status == VerificationStatus.TO_CONFIRM
    ]
    executable = [c for c in snapshot.conditions if c.executable is not None]
    assert len(source_explicit) == 3
    assert len(to_confirm) == 4
    assert len(executable) == 0


def test_unknown_source_id_fails() -> None:
    data = _demo_dict()
    data["materials"][0]["evidence"]["source_id"] = "src-does-not-exist"
    with pytest.raises(ValidationError):
        snapshot_from_dict(data)


def test_unknown_field_is_forbidden() -> None:
    data = _demo_dict()
    data["business"]["canonical_nam"] = "typo-field-should-fail"
    with pytest.raises(ValidationError) as exc_info:
        snapshot_from_dict(data)
    assert "canonical_nam" in str(exc_info.value)


def test_duplicate_channel_id_fails() -> None:
    data = _demo_dict()
    duplicate = deepcopy(data["channels"][0])
    data["channels"].append(duplicate)
    with pytest.raises(ValidationError) as exc_info:
        snapshot_from_dict(data)
    assert "duplicate channel_id" in str(exc_info.value)


def test_non_verified_executable_fails() -> None:
    """Pure fixture: non-VERIFIED executable must fail Contract validation."""
    with pytest.raises(ValidationError):
        ConditionExecutable(
            operator="eq",
            verification_status=VerificationStatus.SOURCE_EXPLICIT,
            usable_by_rule_engine=True,
        )

    data = _demo_dict()
    cond = deepcopy(data["conditions"][0])
    cond["condition_id"] = "cond-fixture-non-verified"
    cond["executable"] = {
        "operator": "eq",
        "verification_status": "SOURCE_EXPLICIT",
        "usable_by_rule_engine": True,
    }
    data["conditions"].append(cond)
    with pytest.raises(ValidationError):
        snapshot_from_dict(data)
