"""GovernmentKnowledgeService: sourced guide facts by business_id and topic."""

from __future__ import annotations

from collections.abc import Sequence
from enum import StrEnum

from pydantic import BaseModel, ConfigDict

from gov_service_agent.business_data.models import VerificationStatus
from gov_service_agent.business_data.repository import JsonBusinessRepository
from gov_service_agent.guide_knowledge.models import GuideDocument, KnowledgeItem

_PUBLIC = frozenset(
    {
        VerificationStatus.SOURCE_EXPLICIT,
        VerificationStatus.VERIFIED,
    }
)


class KnowledgeQueryStatus(StrEnum):
    FOUND = "FOUND"
    NOT_FOUND = "NOT_FOUND"
    NOT_VERIFIED = "NOT_VERIFIED"


class KnowledgeFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    item_id: str
    topic: str
    subtopic: str | None
    text: str
    source_id: str
    source_title: str
    source_file: str | None
    source_section: str
    excerpt: str


class KnowledgeQueryResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: KnowledgeQueryStatus
    business_id: str
    topic: str
    facts: list[KnowledgeFact]


class GovernmentKnowledgeService:
    """Exact topic lookup. Semantic hits are not accepted as verified facts."""

    def __init__(
        self,
        documents: dict[str, GuideDocument],
        *,
        business_repository: JsonBusinessRepository | None = None,
    ) -> None:
        self._documents = dict(documents)
        self._repository = business_repository

    def source_title(self, business_id: str) -> str | None:
        document = self._documents.get(business_id)
        if document is None:
            return None
        title = document.source.source_title.strip()
        return title or None

    def query(
        self,
        business_id: str,
        topic: str,
        subtopic: str | None = None,
        *,
        overview_only: bool = False,
    ) -> KnowledgeQueryResult:
        normalized_topic = topic.strip()
        normalized_subtopic = subtopic.strip() if isinstance(subtopic, str) else None
        if self._repository is not None and not self._repository.has_business(business_id):
            return KnowledgeQueryResult(
                status=KnowledgeQueryStatus.NOT_FOUND,
                business_id=business_id,
                topic=normalized_topic,
                facts=[],
            )
        document = self._documents.get(business_id)
        if document is None or not normalized_topic:
            return KnowledgeQueryResult(
                status=KnowledgeQueryStatus.NOT_FOUND,
                business_id=business_id,
                topic=normalized_topic,
                facts=[],
            )
        matched = [
            item
            for item in document.knowledge_items
            if item.topic == normalized_topic
            and (
                normalized_subtopic is None
                or item.subtopic == normalized_subtopic
            )
            and (
                not overview_only
                or normalized_subtopic is not None
                or item.subtopic is None
            )
        ]
        if not matched:
            return KnowledgeQueryResult(
                status=KnowledgeQueryStatus.NOT_FOUND,
                business_id=business_id,
                topic=normalized_topic,
                facts=[],
            )
        public = [item for item in matched if item.verification_status in _PUBLIC]
        if not public:
            return KnowledgeQueryResult(
                status=KnowledgeQueryStatus.NOT_VERIFIED,
                business_id=business_id,
                topic=normalized_topic,
                facts=[],
            )
        return KnowledgeQueryResult(
            status=KnowledgeQueryStatus.FOUND,
            business_id=business_id,
            topic=normalized_topic,
            facts=[_to_fact(document, item) for item in public],
        )

    def query_many(
        self,
        business_id: str,
        lookups: Sequence[tuple[str, str | None]],
    ) -> KnowledgeQueryResult:
        """Union verified facts for several topic lookups. Does not invent matches."""
        facts: list[KnowledgeFact] = []
        seen: set[str] = set()
        unverified = False
        primary = lookups[0][0] if lookups else ""
        for topic, subtopic in lookups:
            result = self.query(
                business_id,
                topic,
                subtopic,
                overview_only=subtopic is None,
            )
            if result.status is KnowledgeQueryStatus.NOT_VERIFIED:
                unverified = True
                continue
            for fact in result.facts:
                if fact.item_id in seen:
                    continue
                seen.add(fact.item_id)
                facts.append(fact)
        if facts:
            return KnowledgeQueryResult(
                status=KnowledgeQueryStatus.FOUND,
                business_id=business_id,
                topic=primary,
                facts=facts,
            )
        if unverified:
            return KnowledgeQueryResult(
                status=KnowledgeQueryStatus.NOT_VERIFIED,
                business_id=business_id,
                topic=primary,
                facts=[],
            )
        return KnowledgeQueryResult(
            status=KnowledgeQueryStatus.NOT_FOUND,
            business_id=business_id,
            topic=primary,
            facts=[],
        )


def _to_fact(document: GuideDocument, item: KnowledgeItem) -> KnowledgeFact:
    section = next(
        section for section in document.source_sections if section.section_id == item.section_id
    )
    assert item.excerpt is not None
    return KnowledgeFact(
        item_id=item.item_id,
        topic=item.topic,
        subtopic=item.subtopic,
        text="\n".join(item.value.render_lines()),
        source_id=item.source_id,
        source_title=document.source.source_title,
        source_file=document.source.source_file,
        source_section=section.title,
        excerpt=item.excerpt,
    )
