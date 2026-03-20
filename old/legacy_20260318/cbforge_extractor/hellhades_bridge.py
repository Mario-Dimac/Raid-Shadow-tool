from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from .paths import BASE_DIR, INPUT_DIR


HH_BRIDGE_OUTPUT = INPUT_DIR / "hh_account_dump.json"
HH_HERO_TYPES_PATH = INPUT_DIR / "hh_hero_types.json"
HH_HERO_TYPES_URL = "https://raidoptimiser.hellhades.com/api/StaticData/hero_types"

RARITY_MAP = {
    1: "common",
    2: "uncommon",
    3: "rare",
    4: "epic",
    5: "legendary",
    6: "mythical",
}

AFFINITY_MAP = {
    1: "magic",
    2: "force",
    3: "spirit",
    4: "void",
}

SLOT_MAP = {
    1: ("artifact", "helmet"),
    2: ("artifact", "chest"),
    3: ("artifact", "gloves"),
    4: ("artifact", "boots"),
    5: ("artifact", "weapon"),
    6: ("artifact", "shield"),
    7: ("accessory", "ring"),
    8: ("accessory", "amulet"),
    9: ("accessory", "banner"),
}

PERCENT_STATS = {"hp", "atk", "def"}

FACTION_MAP = {
    0: "",
    1: "Banner Lords",
    2: "High Elves",
    3: "Sacred Order",
    4: "Coven of Magi",
    5: "Ogryn Tribes",
    6: "Lizardmen",
    7: "Skinwalkers",
    8: "Orcs",
    9: "Demonspawn",
    10: "Undead Hordes",
    11: "Dark Elves",
    12: "Knights Revenant",
    13: "Barbarians",
    14: "Sylvan Watchers",
    15: "Shadowkin",
    16: "Dwarves",
    17: "Argonites",
}

ROLE_MAP = {
    0: "attack",
    1: "defense",
    2: "health",
    3: "support",
    4: "evolve",
    5: "xp",
}

ARTIFACT_SET_ENUM_MAP = {
    0: "None",
    1: "Hp",
    2: "AttackPower",
    3: "Defense",
    4: "AttackSpeed",
    5: "CriticalChance",
    6: "CriticalDamage",
    7: "Accuracy",
    8: "Resistance",
    9: "LifeDrain",
    10: "DamageIncreaseOnHpDecrease",
    11: "SleepChance",
    12: "BlockHealChance",
    13: "FreezeRateOnDamageReceived",
    14: "Stamina",
    15: "Heal",
    16: "BlockDebuff",
    17: "Shield",
    18: "GetExtraTurn",
    19: "IgnoreDefense",
    20: "DecreaseMaxHp",
    21: "StunChance",
    22: "DotRate",
    23: "ProvokeChance",
    24: "Counterattack",
    25: "CounterattackOnCrit",
    26: "AoeDamageDecrease",
    27: "CooldownReductionChance",
    28: "CriticalHealMultiplier",
    29: "AttackPowerAndIgnoreDefense",
    30: "HpAndHeal",
    31: "ShieldAndAttackPower",
    32: "ShieldAndCriticalChance",
    33: "ShieldAndHp",
    34: "ShieldAndSpeed",
    35: "UnkillableAndSpdAndCrDmg",
    36: "BlockReflectDebuffAndHpAndDef",
    37: "HpAndDefence",
    38: "AccuracyAndSpeed",
    39: "CritDmgAndTransformWeekIntoCritHit",
    40: "ResistanceAndBlockDebuff",
    41: "AttackAndCritRate",
    42: "FreezeResistAndRate",
    43: "CritRateAndLifeDrain",
    44: "PassiveShareDamageAndHeal",
    45: "ResistAndDef",
    46: "CritRateAndIgnoreDefMultiplier",
    47: "Protection",
    48: "StoneSkin",
    49: "Killstroke",
    50: "Instinct",
    51: "Bolster",
    52: "Defiant",
    53: "Impulse",
    54: "Zeal",
    55: "IncreaseStaminaAndSpdAndAcc",
    56: "CritDmgAndIgnoreDefAndCdReductionChance",
    57: "Righteous",
    58: "Supersonic",
    59: "Merciless",
    60: "MonsterHunter",
    61: "Feral",
    62: "Pinpoint",
    63: "Stonecleaver",
    64: "Rebirth",
    65: "Chronophage",
    66: "Mercurial",
    1000: "IgnoreCooldown",
    1001: "RemoveDebuff",
    1002: "ShieldAccessory",
    1003: "ChangeHitType",
    1004: "CounterattackAccessory",
}

GREAT_HALL_STAT_MAP = {
    1: "atk_pct",
    2: "hp_pct",
    3: "def_pct",
    5: "res",
    6: "acc",
    8: "crit_dmg",
}


def extract_account_snapshot() -> Dict[str, Any]:
    bridge_payload = run_bridge()
    hero_types = load_hero_types()

    raw_data = mapping_value(bridge_payload.get("data"))
    raw_heroes = list_value(raw_data.get("heroes"))
    raw_artifacts = list_value(raw_data.get("artifacts"))
    raw_great_hall = list_value(raw_data.get("great_hall"))

    artifact_owner_map = build_artifact_owner_map(raw_heroes)
    champions = [convert_hero(hero, hero_types) for hero in raw_heroes]
    inventory = [convert_artifact(item, artifact_owner_map) for item in raw_artifacts]
    reconcile_inventory_ownership(champions, inventory)
    bonuses = convert_great_hall(raw_great_hall)

    summary = mapping_value(bridge_payload.get("summary"))
    return {
        "summary": summary,
        "bonuses": bonuses,
        "roster": champions,
        "inventory": inventory,
        "hero_types_cached": len(hero_types),
        "bridge_output_path": str(HH_BRIDGE_OUTPUT),
    }


def reconcile_inventory_ownership(champions: List[Dict[str, Any]], inventory: List[Dict[str, Any]]) -> None:
    owner_by_item_id: Dict[str, str] = {}
    for champion in champions:
        champ_id = string_value(champion.get("champ_id"))
        for item_id in list_value(champion.get("equipped_item_ids")):
            normalized_item_id = string_value(item_id)
            if normalized_item_id:
                owner_by_item_id[normalized_item_id] = champ_id

    for item in inventory:
        item_id = string_value(item.get("item_id") or item.get("id"))
        if not item_id:
            continue
        owner_id = owner_by_item_id.get(item_id)
        if owner_id:
            item["equipped_by"] = owner_id


def run_bridge() -> Dict[str, Any]:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    command = ["dotnet", "run", "--project", str(BASE_DIR / "hh_reader_bridge" / "hh_reader_bridge.csproj")]
    completed = subprocess.run(
        command,
        capture_output=True,
        text=True,
        cwd=BASE_DIR,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "hh_reader_bridge failed")

    stdout = completed.stdout
    json_start = stdout.find("{")
    if json_start < 0:
        raise RuntimeError("hh_reader_bridge did not emit JSON")

    payload = json.loads(stdout[json_start:])
    HH_BRIDGE_OUTPUT.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    if payload.get("load_account_data") != "ok":
        raise RuntimeError(str(payload.get("error") or "hh_reader_bridge did not load account data"))
    return payload


def load_hero_types() -> Dict[int, Dict[str, Any]]:
    if not HH_HERO_TYPES_PATH.exists():
        request = urllib.request.Request(
            HH_HERO_TYPES_URL,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "application/json, text/plain, */*",
                "Referer": "https://raidoptimiser.hellhades.com/",
                "Origin": "https://raidoptimiser.hellhades.com",
            },
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            HH_HERO_TYPES_PATH.write_bytes(response.read())

    hero_types_raw = json.loads(HH_HERO_TYPES_PATH.read_text(encoding="utf-8-sig"))
    return {
        int(item["id"]): item
        for item in hero_types_raw
        if isinstance(item, dict) and "id" in item
    }


def build_artifact_owner_map(raw_heroes: List[Any]) -> Dict[str, str]:
    owners: Dict[str, str] = {}
    for hero in raw_heroes:
        hero_map = mapping_value(hero)
        hero_id = str(hero_map.get("Id", ""))
        for artifact_id in list_value(hero_map.get("Artifacts")):
            owners[str(artifact_id)] = hero_id
    return owners


def convert_hero(raw_hero: Any, hero_types: Dict[int, Dict[str, Any]]) -> Dict[str, Any]:
    hero = mapping_value(raw_hero)
    hero_type = hero_types.get(int_value(hero.get("TypeId"), 0), {})
    form = first_form(hero_type)
    base_stats = mapping_value(form.get("baseStats"))

    return {
        "champ_id": str(hero.get("Id", "")),
        "hero_id": str(hero.get("Id", "")),
        "type_id": int_value(hero.get("TypeId"), 0),
        "name": string_value(hero_type.get("name"), f"Hero {hero.get('TypeId', '')}"),
        "rarity": RARITY_MAP.get(int_value(hero_type.get("rarity"), 0), ""),
        "affinity": AFFINITY_MAP.get(int_value(form.get("element"), 0), ""),
        "faction": FACTION_MAP.get(int_value(hero_type.get("fraction"), 0), ""),
        "level": int_value(hero.get("Level"), 1),
        "rank": int_value(hero.get("Grade"), 1),
        "awakening_level": int_value(hero.get("AwakenedGrade"), 0),
        "empowerment_level": int_value(hero.get("EmpowerLevel"), 0),
        "locked": bool_value(hero.get("Locked"), False),
        "in_vault": bool_value(hero.get("InStorage"), False),
        "equipped_item_ids": [str(item) for item in list_value(hero.get("Artifacts"))],
        "masteries": [
            {"mastery_id": str(item), "name": str(item), "tree": "", "active": True}
            for item in list_value(hero.get("Masteries"))
        ],
        "blessing": {
            "name": str(hero.get("BlessingId", "")) if hero.get("BlessingId") is not None else "",
            "level": int_value(hero.get("AwakenedGrade"), 0),
        },
        "skills": [
            {
                "skill_id": str(mapping_value(skill).get("Key", "")),
                "name": str(mapping_value(skill).get("Key", "")),
                "slot": skill_slot_name(index),
                "booked": int_value(mapping_value(skill).get("Value"), 0) > 1,
            }
            for index, skill in enumerate(list_value(hero.get("SkillLevels")), start=1)
        ],
        "base_stats": {
            "hp": float_value(base_stats.get("health"), 0.0),
            "atk": float_value(base_stats.get("attack"), 0.0),
            "def": float_value(base_stats.get("defence"), 0.0),
            "spd": float_value(base_stats.get("speed"), 0.0),
            "crit_rate": float_value(base_stats.get("criticalChance"), 0.0),
            "crit_dmg": float_value(base_stats.get("criticalDamage"), 0.0),
            "res": float_value(base_stats.get("resistance"), 0.0),
            "acc": float_value(base_stats.get("accuracy"), 0.0),
        },
        "total_stats": {},
        "role_tags": [ROLE_MAP.get(int_value(form.get("role"), -1), str(form.get("role", "")))] if form else [],
    }


def convert_artifact(raw_artifact: Any, artifact_owner_map: Dict[str, str]) -> Dict[str, Any]:
    artifact = mapping_value(raw_artifact)
    kind = int_value(artifact.get("Kind"), 0)
    item_class, slot = SLOT_MAP.get(kind, ("artifact", f"slot_{kind}"))
    required_faction_id = int_value(artifact.get("RequiredFraction"), 0)

    return {
        "item_id": str(artifact.get("Id", "")),
        "id": str(artifact.get("Id", "")),
        "item_class": item_class,
        "slot": slot,
        "set_name": artifact_set_name(int_value(artifact.get("Set"), 0)),
        "rarity": RARITY_MAP.get(int_value(artifact.get("Rarity"), 0), ""),
        "rank": int_value(artifact.get("Rank"), 0),
        "level": int_value(artifact.get("Level"), 0),
        "ascension_level": int_value(artifact.get("AscendLevel"), 0),
        "main_stat": bonus_to_stat(mapping_value(artifact.get("PrimaryBonus"))),
        "substats": [
            bonus_to_substat(mapping_value(stat))
            for stat in list_value(artifact.get("SecondaryBonuses"))
        ],
        "required_faction": FACTION_MAP.get(required_faction_id, ""),
        "required_faction_id": required_faction_id,
        "equipped_by": artifact_owner_map.get(str(artifact.get("Id", ""))),
        "locked": bool_value(artifact.get("Locked"), False),
        "kind": kind,
    }


def convert_great_hall(raw_great_hall: List[Any]) -> List[Dict[str, Any]]:
    bonuses: List[Dict[str, Any]] = []
    for affinity_entry in raw_great_hall:
        entry = mapping_value(affinity_entry)
        affinity_id = int_value(entry.get("Key"), 0)
        affinity = AFFINITY_MAP.get(affinity_id, f"affinity_{affinity_id}")
        for stat_entry in list_value(entry.get("Value")):
            stat_map = mapping_value(stat_entry)
            stat_id = int_value(stat_map.get("Key"), 0)
            stat_name = GREAT_HALL_STAT_MAP.get(stat_id, f"stat_{stat_id}")
            value = float_value(stat_map.get("Value"), 0.0)
            bonuses.append(
                {
                    "bonus_id": f"great_hall_{affinity}_{stat_name}",
                    "source": "great_hall",
                    "scope": "global",
                    "target": affinity,
                    "stat": stat_name,
                    "value": value,
                    "active": value > 0,
                }
            )
    return bonuses


def bonus_to_stat(bonus: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not bonus:
        return None
    return {
        "type": bonus_type_name(
            int_value(bonus.get("Kind"), 0),
            bool_value(bonus.get("IsAbsolute"), True),
        ),
        "value": float_value(bonus.get("Value"), 0.0),
    }


def bonus_to_substat(bonus: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "type": bonus_type_name(
            int_value(bonus.get("Kind"), 0),
            bool_value(bonus.get("IsAbsolute"), True),
        ),
        "value": float_value(bonus.get("Value"), 0.0),
        "rolls": int_value(bonus.get("Level"), 0),
        "glyph_value": float_value(bonus.get("RarityBasedPowerUpValue"), 0.0),
    }


def bonus_type_name(kind: int, is_absolute: bool = True) -> str:
    mapping = {
        1: "hp",
        2: "atk",
        3: "def",
        4: "spd",
        5: "crit_rate",
        6: "crit_dmg",
        7: "res",
        8: "acc",
    }
    stat_name = mapping.get(kind, f"stat_{kind}")
    if not is_absolute and stat_name in PERCENT_STATS:
        return f"{stat_name}_pct"
    return stat_name


def artifact_set_name(set_id: int) -> str:
    raw_name = ARTIFACT_SET_ENUM_MAP.get(set_id, "")
    if not raw_name or raw_name == "None":
        return ""
    return humanize_identifier(raw_name)


def skill_slot_name(index: int) -> str:
    if index <= 4:
        return f"A{index}"
    return f"Skill{index}"


def humanize_identifier(value: str) -> str:
    words = re.sub(r"(?<!^)([A-Z])", r" \1", value.replace("_", " ")).split()
    acronyms = {
        "Hp": "HP",
        "Spd": "SPD",
        "Cr": "CR",
        "Cd": "CD",
        "Dmg": "Damage",
        "Def": "DEF",
        "Crit": "Crit",
        "Aoe": "AoE",
    }
    normalized = [acronyms.get(word, word) for word in words]
    return " ".join(normalized)


def first_form(hero_type: Dict[str, Any]) -> Dict[str, Any]:
    forms = list_value(hero_type.get("forms"))
    if forms:
        return mapping_value(forms[0])
    return {}


def mapping_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def string_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)
