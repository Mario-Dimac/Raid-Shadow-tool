from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol


@dataclass(frozen=True)
class ChampionSkillMatch:
    source_name: str
    source_ref: str
    title: str
    url: str


class SkillEnrichmentProvider(Protocol):
    source_name: str

    def resolve_champion_match(self, champion_name: str) -> Optional[ChampionSkillMatch]:
        ...

    def fetch_champion_skills(self, match: ChampionSkillMatch) -> List[Dict[str, Any]]:
        ...


_PROVIDERS: Dict[str, SkillEnrichmentProvider] = {}


def register_skill_enrichment_provider(provider: SkillEnrichmentProvider) -> None:
    _PROVIDERS[str(provider.source_name).strip().lower()] = provider


def get_skill_enrichment_provider(name: str) -> SkillEnrichmentProvider:
    normalized_name = str(name or "").strip().lower()
    if not normalized_name:
        raise KeyError("provider name mancante")
    provider = _PROVIDERS.get(normalized_name)
    if provider is None:
        raise KeyError(f"provider non registrato: {name}")
    return provider


def list_skill_enrichment_providers() -> List[str]:
    return sorted(_PROVIDERS)
