"""Sidecar guide knowledge. Does not alter the F02 BusinessSnapshot contract."""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from gov_service_agent.business_data.models import SourceRecord, VerificationStatus


class GuideValueKind(StrEnum):
    TEXT = "text"
    LIST = "list"


class GuideValue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: GuideValueKind
    text: str | None = None
    items: list[str] | None = None

    @model_validator(mode="after")
    def _shape(self) -> GuideValue:
        if self.kind is GuideValueKind.TEXT:
            if not isinstance(self.text, str) or not self.text.strip():
                raise ValueError("text value must be nonblank")
            if self.items is not None:
                raise ValueError("text value forbids items")
            return self
        if not self.items:
            raise ValueError("list value requires items")
        if any(not isinstance(item, str) or not item.strip() for item in self.items):
            raise ValueError("list items must be nonblank str")
        if self.text is not None:
            raise ValueError("list value forbids text")
        return self

    def render_lines(self) -> list[str]:
        if self.kind is GuideValueKind.TEXT:
            assert self.text is not None
            return [self.text.strip()]
        assert self.items is not None
        return [f"{index}. {item.strip()}" for index, item in enumerate(self.items, start=1)]


class SourceSection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    title: str
    text: str

    @field_validator("section_id", "title", "text")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("section fields must be nonblank")
        return value.strip()


class KnowledgeItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    topic: str
    subtopic: str | None = None
    value: GuideValue
    verification_status: VerificationStatus
    source_id: str
    section_id: str
    excerpt: str | None = None

    @field_validator("item_id", "topic", "source_id", "section_id")
    @classmethod
    def _nonblank(cls, value: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("knowledge item ids must be nonblank")
        return value.strip()

    @field_validator("subtopic")
    @classmethod
    def _subtopic(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            raise ValueError("subtopic must be nonblank when set")
        return stripped

    @model_validator(mode="after")
    def _public_excerpt(self) -> KnowledgeItem:
        if self.verification_status in (
            VerificationStatus.SOURCE_EXPLICIT,
            VerificationStatus.VERIFIED,
        ):
            if not isinstance(self.excerpt, str) or not self.excerpt.strip():
                raise ValueError("public knowledge item requires excerpt")
            self.excerpt = self.excerpt.strip()
        return self


class GuideDocument(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(min_length=1)
    business_id: str = Field(min_length=1)
    source: SourceRecord
    source_sections: list[SourceSection]
    knowledge_items: list[KnowledgeItem]

    @model_validator(mode="after")
    def _links(self) -> GuideDocument:
        section_ids = [section.section_id for section in self.source_sections]
        if len(section_ids) != len(set(section_ids)):
            raise ValueError("duplicate section_id")
        item_ids = [item.item_id for item in self.knowledge_items]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("duplicate item_id")
        known = set(section_ids)
        for item in self.knowledge_items:
            if item.source_id != self.source.source_id:
                raise ValueError("knowledge item source_id must match guide source")
            if item.section_id not in known:
                raise ValueError("knowledge item section_id is unknown")
        return self


def load_guide_document(path: Path | str) -> GuideDocument:
    file_path = Path(path)
    return GuideDocument.model_validate_json(file_path.read_text(encoding="utf-8"))


def guide_document_from_dict(data: dict[str, Any]) -> GuideDocument:
    return GuideDocument.model_validate(data)
