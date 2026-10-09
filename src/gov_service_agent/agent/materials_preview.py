"""Post-confirmation materials preview. Display only; F12 remains the authority."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from dataclasses import replace

from gov_service_agent.agent.state import AgentState
from gov_service_agent.agent.terminal import read_f10
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.session.models import AgentTurnResult
from gov_service_agent.session.service import AgentTurnProcessor

logger = logging.getLogger("gov_service_agent")

_BUSINESS_LABEL = "办理事项："
_MATERIALS_LABEL = "需要准备的材料："
_EMPTY_MATERIALS = "当前暂无可展示的办理材料信息。"


class ConfirmedBusinessMaterialsPreviewProcessor:
    """Read-only display wrapper around an existing turn processor."""

    def __init__(
        self,
        *,
        base_processor: AgentTurnProcessor,
        business_repository: JsonBusinessRepository,
    ) -> None:
        self._base_processor = base_processor
        self._business_repository = business_repository

    def process_turn(
        self,
        *,
        session_id: str,
        request_id: str,
        input_text: str,
        restored_state: AgentState | None,
    ) -> AgentTurnResult:
        before_confirmed_id = _read_confirmed_id(restored_state)
        base_result = self._base_processor.process_turn(
            session_id=session_id,
            request_id=request_id,
            input_text=input_text,
            restored_state=restored_state,
        )
        after_confirmed_id = _read_confirmed_id(base_result.state)
        if not _is_first_confirmation(before_confirmed_id, after_confirmed_id):
            return base_result
        try:
            section = _build_preview_section(
                self._business_repository,
                after_confirmed_id,
            )
            return replace(
                base_result,
                response_text=_append_preview(
                    base_result.response_text,
                    section,
                ),
            )
        except Exception as exc:
            logger.warning(
                "message=materials_preview_failed business_id=%s error_type=%s",
                after_confirmed_id,
                type(exc).__name__,
            )
            return base_result


def _read_confirmed_id(state: AgentState | None) -> str | None:
    if state is None:
        return None
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, Mapping):
        return None
    value = read_f10(artifacts).get("confirmed_business_id")
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip()


def _is_first_confirmation(
    before_confirmed_id: str | None,
    after_confirmed_id: str | None,
) -> bool:
    return before_confirmed_id is None and after_confirmed_id is not None


def _build_preview_section(
    repository: JsonBusinessRepository,
    confirmed_business_id: str,
) -> str:
    business = repository.get_business(confirmed_business_id)
    materials = repository.get_materials(confirmed_business_id)
    return _render_materials_preview(business.canonical_name, materials)


def _render_materials_preview(
    canonical_name: str,
    materials: Sequence[object],
) -> str:
    if not isinstance(canonical_name, str) or not canonical_name.strip():
        raise ValueError("canonical_name is missing")
    lines = [f"{_BUSINESS_LABEL}{canonical_name}"]
    if len(materials) == 0:
        lines.append(_EMPTY_MATERIALS)
        return "\n".join(lines)
    lines.append(_MATERIALS_LABEL)
    for index, material in enumerate(materials, start=1):
        source_text = getattr(material, "source_text", None)
        if not isinstance(source_text, str) or not source_text.strip():
            raise ValueError("material source_text is missing")
        lines.append(f"{index}. {source_text}")
    return "\n".join(lines)


def _append_preview(original_response: str, preview_section: str) -> str:
    if original_response:
        return f"{original_response}\n\n{preview_section}"
    return preview_section
