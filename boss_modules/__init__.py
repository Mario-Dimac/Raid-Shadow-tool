from __future__ import annotations

from copy import deepcopy
from typing import Any, Dict, List

from .demon_lord import DEMON_LORD_BOSS_MODULE
from .hydra import HYDRA_BOSS_MODULE
from .iron_twins import IRON_TWINS_BOSS_MODULE


BOSS_MODULES: Dict[str, Dict[str, Any]] = {
    "demon_lord": DEMON_LORD_BOSS_MODULE,
    "hydra": HYDRA_BOSS_MODULE,
    "iron_twins": IRON_TWINS_BOSS_MODULE,
}

PLANNED_BOSS_MODULES: List[Dict[str, Any]] = [
    {
        "boss_key": "spider",
        "label": "Spider",
        "category": "Dungeon / Boss PvE",
        "status": "pending",
        "note": "Da portare dentro con logica HP Burn, TM control e differenza early / late game.",
    },
    {
        "boss_key": "sand_devil",
        "label": "Sand Devil",
        "category": "Dungeon / Boss PvE",
        "status": "pending",
        "note": "Da modellare con sleep windows, revive on death e turn order dedicato.",
    },
    {
        "boss_key": "fire_knight",
        "label": "Fire Knight",
        "category": "Dungeon / Boss PvE",
        "status": "pending",
        "note": "Da aggiungere con multi-hit, TM control e gestione shield.",
    },
    {
        "boss_key": "dragon",
        "label": "Dragon",
        "category": "Dungeon / Boss PvE",
        "status": "pending",
        "note": "Da costruire con priorita su wave control, poison e tenuta.",
    },
    {
        "boss_key": "ice_golem",
        "label": "Ice Golem",
        "category": "Dungeon / Boss PvE",
        "status": "pending",
        "note": "Da trattare con attenzione ai trigger punitivi e al danno burst.",
    },
    {
        "boss_key": "phantom_shogun",
        "label": "Phantom Shogun",
        "category": "Dungeon / Boss PvE",
        "status": "pending",
        "note": "Da supportare con set-up molto guidati e controllo delle meccaniche speciali.",
    },
]


def list_boss_modules() -> List[Dict[str, Any]]:
    entries: List[Dict[str, Any]] = []
    for key in sorted(BOSS_MODULES):
        module = BOSS_MODULES[key]
        entries.append(
            {
                "boss_key": key,
                "label": str(module.get("label") or key),
                "category": str(module.get("category") or ""),
                "optimizer_status": str(module.get("optimizer_status") or "knowledge_only"),
                "implemented_in_optimizer": bool(module.get("implemented_in_optimizer")),
                "team_size": int(module.get("team_size") or 0),
                "source_count": len(list(module.get("sources") or [])),
            }
        )
    return entries


def build_boss_intel(
    boss_key: str,
    level_key: str = "",
    affinity: str = "",
) -> Dict[str, Any]:
    normalized_key = str(boss_key or "").strip().lower()
    module = deepcopy(BOSS_MODULES.get(normalized_key) or BOSS_MODULES["demon_lord"])

    levels = list(module.get("levels") or [])
    affinities = list(module.get("affinities") or [])

    selected_level = str(level_key or module.get("default_level") or "").strip().lower()
    selected_affinity = str(affinity or module.get("default_affinity") or "").strip().lower()

    level_lookup = {str(item.get("key") or "").strip().lower(): item for item in levels if isinstance(item, dict)}
    affinity_lookup = {str(item.get("key") or "").strip().lower(): item for item in affinities if isinstance(item, dict)}

    if selected_level not in level_lookup and levels:
        selected_level = str(module.get("default_level") or levels[0].get("key") or "").strip().lower()
    if selected_affinity not in affinity_lookup and affinities:
        selected_affinity = str(module.get("default_affinity") or affinities[0].get("key") or "").strip().lower()

    selected_level_entry = deepcopy(level_lookup.get(selected_level) or {})
    selected_affinity_entry = deepcopy(affinity_lookup.get(selected_affinity) or {})

    module["selected_level_key"] = selected_level
    module["selected_level_label"] = str(selected_level_entry.get("label") or selected_level or "")
    module["selected_level_targets"] = list(selected_level_entry.get("stat_targets") or [])
    module["selected_level_notes"] = list(selected_level_entry.get("notes") or [])
    module["selected_affinity_key"] = selected_affinity
    module["selected_affinity_label"] = str(selected_affinity_entry.get("label") or selected_affinity or "")
    rotations = module.get("rotations") or {}
    if isinstance(rotations, dict):
        module["selected_rotation"] = deepcopy(rotations.get(selected_affinity) or {})
    module["catalog"] = list_boss_modules()
    module["planned_modules"] = deepcopy(PLANNED_BOSS_MODULES)
    return module
