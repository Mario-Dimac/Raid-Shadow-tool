from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode, urlparse

from enrichment_sources import ChampionSkillMatch, register_skill_enrichment_provider


HH_SEARCH_URL = "https://hellhades.com/wp-json/wp/v2/search"
HH_SKILLS_URL_TEMPLATE = "https://hellhades.com/wp-json/hh-api/v3/raid/skills/{post_id}"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://hellhades.com/",
    "Origin": "https://hellhades.com",
}


@dataclass(frozen=True)
class HellHadesChampionMatch(ChampionSkillMatch):
    post_id: int

    def __init__(self, post_id: int, title: str, url: str) -> None:
        object.__setattr__(self, "source_name", "hellhades")
        object.__setattr__(self, "source_ref", str(int(post_id)))
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "post_id", int(post_id))


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def normalize_lookup_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def slug_from_url(value: str) -> str:
    path = urlparse(value).path.strip("/")
    if not path:
        return ""
    return path.split("/")[-1]


class HellHadesSkillEnrichmentProvider:
    source_name = "hellhades"

    def resolve_champion_match(self, champion_name: str) -> Optional[HellHadesChampionMatch]:
        query = urlencode({"search": champion_name, "subtype": "champions", "per_page": "20"})
        payload = fetch_json(f"{HH_SEARCH_URL}?{query}")
        if not isinstance(payload, list):
            return None

        normalized_name = normalize_lookup_text(champion_name)
        best_candidate: Optional[Tuple[int, int, HellHadesChampionMatch]] = None

        for item in payload:
            if not isinstance(item, dict):
                continue
            post_id = int(item.get("id") or 0)
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if not post_id or not title or not url:
                continue

            title_norm = normalize_lookup_text(title)
            slug_norm = normalize_lookup_text(slug_from_url(url))
            score = 0
            if title_norm == normalized_name:
                score += 1000
            if slug_norm == normalized_name:
                score += 900
            if normalized_name and normalized_name in title_norm:
                score += 300
            if normalized_name and normalized_name in slug_norm:
                score += 250

            token_overlap = len(set(re.findall(r"[a-z0-9]+", champion_name.lower())) & set(re.findall(r"[a-z0-9]+", title.lower())))
            score += token_overlap * 10
            length_delta = abs(len(title_norm) - len(normalized_name))

            match = HellHadesChampionMatch(post_id=post_id, title=title, url=url)
            candidate = (score, -length_delta, match)
            if best_candidate is None or candidate > best_candidate:
                best_candidate = candidate

        if best_candidate is None or best_candidate[0] <= 0:
            return None
        return best_candidate[2]

    def fetch_champion_skills(self, match: ChampionSkillMatch) -> List[Dict[str, Any]]:
        post_id = int(str(match.source_ref or "0"))
        payload = fetch_json(HH_SKILLS_URL_TEMPLATE.format(post_id=post_id))
        if isinstance(payload, list) and payload and isinstance(payload[0], list):
            return [item for item in payload[0] if isinstance(item, dict)]
        return []


register_skill_enrichment_provider(HellHadesSkillEnrichmentProvider())
