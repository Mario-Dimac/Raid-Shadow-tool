from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from enrichment_sources import ChampionSkillMatch, register_skill_enrichment_provider
from forge_db import DB_PATH


BASE_DIR = Path(__file__).resolve().parent.parent
LOCAL_SKILL_REGISTRY_PATH = BASE_DIR / "data_sources" / "local_skill_registry.json"


def normalize_lookup_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


@dataclass(frozen=True)
class LocalRegistryChampionMatch(ChampionSkillMatch):
    registry_key: str

    def __init__(self, registry_key: str, title: str, url: str = "") -> None:
        normalized_key = str(registry_key or "").strip()
        object.__setattr__(self, "source_name", "local_registry")
        object.__setattr__(self, "source_ref", normalized_key)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "registry_key", normalized_key)


def load_local_skill_registry(path: Path = LOCAL_SKILL_REGISTRY_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {"version": 1, "champions": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"version": 1, "champions": []}
    champions = payload.get("champions")
    if not isinstance(champions, list):
        payload["champions"] = []
    return payload


def _registry_entries(path: Path = LOCAL_SKILL_REGISTRY_PATH) -> List[Dict[str, Any]]:
    payload = load_local_skill_registry(path)
    entries = payload.get("champions") or []
    return [entry for entry in entries if isinstance(entry, dict)]


class LocalRegistrySkillEnrichmentProvider:
    source_name = "local_registry"

    def __init__(self, registry_path: Path = LOCAL_SKILL_REGISTRY_PATH) -> None:
        self.registry_path = registry_path

    def resolve_champion_match(self, champion_name: str) -> Optional[LocalRegistryChampionMatch]:
        normalized_name = normalize_lookup_text(champion_name)
        best_entry: Optional[Dict[str, Any]] = None
        best_score = -1
        for entry in _registry_entries(self.registry_path):
            entry_name = str(entry.get("champion_name") or "").strip()
            if not entry_name:
                continue
            candidates = [entry_name] + [str(alias).strip() for alias in entry.get("aliases") or [] if str(alias).strip()]
            score = 0
            for candidate in candidates:
                normalized_candidate = normalize_lookup_text(candidate)
                if not normalized_candidate:
                    continue
                if normalized_candidate == normalized_name:
                    score = max(score, 1000)
                elif normalized_name and normalized_name in normalized_candidate:
                    score = max(score, 300)
            if score > best_score:
                best_score = score
                best_entry = entry

        if best_entry is None or best_score <= 0:
            return None

        registry_key = str(best_entry.get("registry_key") or best_entry.get("champion_name") or "").strip()
        return LocalRegistryChampionMatch(
            registry_key=registry_key,
            title=str(best_entry.get("champion_name") or registry_key),
            url=str(best_entry.get("source_url") or ""),
        )

    def fetch_champion_skills(self, match: ChampionSkillMatch) -> List[Dict[str, Any]]:
        registry_key = str(match.source_ref or "").strip()
        if not registry_key:
            return []
        for entry in _registry_entries(self.registry_path):
            candidate_key = str(entry.get("registry_key") or entry.get("champion_name") or "").strip()
            if candidate_key != registry_key:
                continue
            skills = entry.get("skills") or []
            return [skill for skill in skills if isinstance(skill, dict)]
        return []


def export_local_skill_registry(
    db_path: Path = DB_PATH,
    output_path: Path = LOCAL_SKILL_REGISTRY_PATH,
    champion_names: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    selected_names = {str(name).strip() for name in (champion_names or []) if str(name).strip()}
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        champion_rows = conn.execute(
            """
            SELECT DISTINCT cs.champion_name, cc.hellhades_url, cc.last_enriched_at
            FROM champion_skills cs
            LEFT JOIN champion_catalog cc
                ON cc.champion_name = cs.champion_name
            ORDER BY cs.champion_name ASC
            """
        ).fetchall()

        entries: List[Dict[str, Any]] = []
        for champion_row in champion_rows:
            champion_name = str(champion_row["champion_name"] or "").strip()
            if not champion_name:
                continue
            if selected_names and champion_name not in selected_names:
                continue

            skill_rows = conn.execute(
                """
                SELECT slot, skill_order, skill_id, skill_name, cooldown, booked_cooldown,
                       description, skill_type, description_clean, source
                FROM champion_skills
                WHERE champion_name = ?
                ORDER BY skill_order ASC
                """,
                (champion_name,),
            ).fetchall()
            if not skill_rows:
                continue

            skills: List[Dict[str, Any]] = []
            for skill_row in skill_rows:
                effect_rows = conn.execute(
                    """
                    SELECT effect_order, effect_type, target, effect_value, duration, chance, condition_text
                    FROM champion_skill_effects
                    WHERE champion_name = ? AND slot = ?
                    ORDER BY effect_order ASC
                    """,
                    (champion_name, skill_row["slot"]),
                ).fetchall()
                skills.append(
                    {
                        "slot": str(skill_row["slot"] or ""),
                        "skill_order": int(skill_row["skill_order"] or 0),
                        "skill_id": str(skill_row["skill_id"] or ""),
                        "name": str(skill_row["skill_name"] or ""),
                        "type": str(skill_row["skill_type"] or ""),
                        "cooldown": skill_row["cooldown"],
                        "booked_cooldown": skill_row["booked_cooldown"],
                        "description": str(skill_row["description"] or ""),
                        "description_clean": str(skill_row["description_clean"] or ""),
                        "source": str(skill_row["source"] or ""),
                        "effects": [
                            {
                                "effect_order": int(effect_row["effect_order"] or 0),
                                "effect_type": str(effect_row["effect_type"] or ""),
                                "target": str(effect_row["target"] or ""),
                                "effect_value": effect_row["effect_value"],
                                "duration": effect_row["duration"],
                                "chance": effect_row["chance"],
                                "condition_text": str(effect_row["condition_text"] or ""),
                            }
                            for effect_row in effect_rows
                        ],
                    }
                )

            entries.append(
                {
                    "registry_key": champion_name,
                    "champion_name": champion_name,
                    "aliases": [],
                    "source_url": str(champion_row["hellhades_url"] or ""),
                    "last_synced_at": str(champion_row["last_enriched_at"] or ""),
                    "skills": skills,
                }
            )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "generated_from_db": str(db_path),
        "champions": entries,
    }
    output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "output_path": str(output_path),
        "champion_count": len(entries),
        "skill_count": sum(len(entry.get("skills") or []) for entry in entries),
    }


register_skill_enrichment_provider(LocalRegistrySkillEnrichmentProvider())
