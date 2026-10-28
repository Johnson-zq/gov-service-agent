"""Multi-matter registration: business_id → Business Data + Decision Graph."""

from gov_service_agent.matters.registry import (
    MatterRegistration,
    MatterRegistry,
    MatterRegistryError,
    load_matter_registry,
)

__all__ = [
    "MatterRegistration",
    "MatterRegistry",
    "MatterRegistryError",
    "load_matter_registry",
]
