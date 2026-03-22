from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping


CORE_STATS = ("hp", "atk", "def", "spd", "acc", "res", "crit_rate", "crit_dmg")
BASIC_ARTIFACT_SET_NAMES = {
    "HP",
    "Attack Power",
    "Defense",
    "Attack Speed",
    "Critical Chance",
    "Critical Heal Multiplier",
    "Accuracy",
    "Resistance",
}
STATIC_MASTERY_BONUSES = {
    "500112": [("atk", 75.0)],
    "500113": [("crit_rate", 5.0)],
    "500122": [("crit_dmg", 10.0)],
    "500164": [("crit_dmg", 20.0)],
    "500212": [("def", 75.0)],
    "500213": [("res", 10.0)],
    "500261": [("def", 200.0)],
    "500264": [("res", 50.0)],
    "500312": [("hp", 810.0)],
    "500313": [("acc", 10.0)],
    "500361": [("hp", 3000.0)],
    "500364": [("acc", 50.0)],
}
LORE_OF_STEEL_ID = "500343"
AWAKENING_BONUSES_BY_RARITY = {
    "rare": {
        1: [("hp", 2250.0)],
        2: [("atk", 450.0)],
        3: [("def", 300.0)],
        4: [("hp", 1000.0), ("crit_dmg", 23.0)],
        5: [("acc", 40.0), ("res", 40.0)],
        6: [("spd", 7.0)],
    },
    "epic": {
        1: [("hp", 4500.0)],
        2: [("atk", 600.0)],
        3: [("def", 450.0)],
        4: [("hp", 1000.0), ("crit_dmg", 30.0)],
        5: [("acc", 60.0), ("res", 60.0)],
        6: [("spd", 10.0)],
    },
    "legendary": {
        1: [("hp", 7500.0)],
        2: [("atk", 750.0)],
        3: [("def", 600.0)],
        4: [("hp", 1000.0), ("crit_dmg", 38.0)],
        5: [("acc", 75.0), ("res", 75.0)],
        6: [("spd", 15.0)],
    },
    "mythical": {
        1: [("hp", 10500.0)],
        2: [("atk", 900.0)],
        3: [("def", 750.0)],
        4: [("hp", 1000.0), ("crit_dmg", 45.0)],
        5: [("acc", 90.0), ("res", 90.0)],
        6: [("spd", 20.0)],
    },
}
EMPOWERMENT_BONUSES_BY_RARITY = {
    "epic": {
        1: [("hp_pct", 10.0), ("atk_pct", 10.0), ("def_pct", 10.0), ("acc", 10.0), ("res", 10.0)],
        2: [("hp_pct", 20.0), ("atk_pct", 20.0), ("def_pct", 20.0), ("acc", 20.0), ("res", 20.0), ("spd", 5.0), ("crit_dmg", 5.0)],
        3: [("hp_pct", 30.0), ("atk_pct", 30.0), ("def_pct", 30.0), ("acc", 30.0), ("res", 30.0), ("spd", 5.0)],
        4: [("hp_pct", 40.0), ("atk_pct", 40.0), ("def_pct", 40.0), ("acc", 40.0), ("res", 40.0), ("spd", 10.0), ("crit_dmg", 15.0), ("crit_rate", 5.0)],
    },
    "legendary": {
        1: [("hp_pct", 10.0), ("atk_pct", 10.0), ("def_pct", 10.0), ("acc", 15.0), ("res", 15.0)],
        2: [("hp_pct", 20.0), ("atk_pct", 20.0), ("def_pct", 20.0), ("acc", 25.0), ("res", 25.0), ("spd", 10.0)],
        3: [("hp_pct", 30.0), ("atk_pct", 30.0), ("def_pct", 30.0), ("acc", 45.0), ("res", 45.0), ("spd", 10.0)],
        4: [("hp_pct", 40.0), ("atk_pct", 40.0), ("def_pct", 40.0), ("acc", 55.0), ("res", 55.0), ("spd", 15.0), ("crit_dmg", 30.0), ("crit_rate", 10.0)],
    },
    "mythical": {
        1: [("hp_pct", 10.0), ("atk_pct", 10.0), ("def_pct", 10.0), ("acc", 15.0), ("res", 15.0)],
        2: [("hp_pct", 20.0), ("atk_pct", 20.0), ("def_pct", 20.0), ("acc", 25.0), ("res", 25.0), ("spd", 10.0)],
        3: [("hp_pct", 30.0), ("atk_pct", 30.0), ("def_pct", 30.0), ("acc", 45.0), ("res", 45.0), ("spd", 10.0)],
        4: [("hp_pct", 40.0), ("atk_pct", 40.0), ("def_pct", 40.0), ("acc", 55.0), ("res", 55.0), ("spd", 15.0), ("crit_dmg", 30.0), ("crit_rate", 10.0)],
    },
}


@dataclass
class StatComputationResult:
    total_stats: Dict[str, float]
    base_totals: Dict[str, float]
    source: str
    completeness: str
    unsupported_sets: List[str] = field(default_factory=list)
    applied_sets: List[Dict[str, Any]] = field(default_factory=list)


def build_stat_computation(
    base_stats: Mapping[str, Any],
    raw_total_stats: Mapping[str, Any],
    equipped_items: Iterable[Mapping[str, Any]],
    bonuses: Iterable[Mapping[str, Any]],
    set_rules: Mapping[str, Mapping[str, Any]],
    masteries: Iterable[Mapping[str, Any]] | None = None,
    affinity: str = "",
    rarity: str = "",
    awakening_level: int = 0,
    empowerment_level: int = 0,
    area_region: str = "",
) -> StatComputationResult:
    equipped_items = list(equipped_items)
    bonuses = list(bonuses)
    masteries = list(masteries or [])
    base_totals = materialize_base_totals(base_stats)
    applied_sets, unsupported_sets = summarize_sets(equipped_items, set_rules)

    if has_meaningful_total_stats(raw_total_stats):
        return StatComputationResult(
            total_stats=normalize_total_stats(raw_total_stats),
            base_totals=base_totals,
            source="raw",
            completeness="raw",
            unsupported_sets=unsupported_sets,
            applied_sets=applied_sets,
        )

    if has_meaningful_base_stats(base_stats) or equipped_items or bonuses or applied_sets or unsupported_sets:
        total_stats = derive_total_stats(
            base_stats=base_stats,
            equipped_items=equipped_items,
            bonuses=bonuses,
            set_rules=set_rules,
            masteries=masteries,
            affinity=affinity,
            rarity=rarity,
            awakening_level=awakening_level,
            empowerment_level=empowerment_level,
            area_region=area_region,
        )
        completeness = "partial" if unsupported_sets else "derived"
        return StatComputationResult(
            total_stats=total_stats,
            base_totals=base_totals,
            source="derived",
            completeness=completeness,
            unsupported_sets=unsupported_sets,
            applied_sets=applied_sets,
        )

    return StatComputationResult(
        total_stats={},
        base_totals=base_totals,
        source="missing",
        completeness="missing",
        unsupported_sets=unsupported_sets,
        applied_sets=applied_sets,
    )


def materialize_base_totals(base_stats: Mapping[str, Any]) -> Dict[str, float]:
    hp_raw = float_value(base_stats.get("hp"))
    atk_raw = float_value(base_stats.get("atk"))
    def_raw = float_value(base_stats.get("def"))
    spd_raw = float_value(base_stats.get("spd"))
    crit_rate_raw = float_value(base_stats.get("crit_rate"))
    crit_dmg_raw = float_value(base_stats.get("crit_dmg"))
    acc_raw = float_value(base_stats.get("acc"))
    res_raw = float_value(base_stats.get("res"))

    return {
        "hp": hp_raw * 240.0 if 0 < hp_raw <= 500.0 else hp_raw,
        "atk": atk_raw * 9.0 if 0 < atk_raw <= 500.0 else atk_raw,
        "def": def_raw * 8.0 if 0 < def_raw <= 500.0 else def_raw,
        "spd": spd_raw or 100.0,
        "acc": acc_raw,
        "res": res_raw if res_raw else 30.0,
        "crit_rate": crit_rate_raw or 15.0,
        "crit_dmg": crit_dmg_raw or 50.0,
    }


def derive_total_stats(
    base_stats: Mapping[str, Any],
    equipped_items: Iterable[Mapping[str, Any]],
    bonuses: Iterable[Mapping[str, Any]],
    set_rules: Mapping[str, Mapping[str, Any]],
    masteries: Iterable[Mapping[str, Any]] | None = None,
    affinity: str = "",
    rarity: str = "",
    awakening_level: int = 0,
    empowerment_level: int = 0,
    area_region: str = "",
) -> Dict[str, float]:
    base_totals = materialize_base_totals(base_stats)
    flat_totals = {stat_name: 0.0 for stat_name in CORE_STATS}
    percent_totals = {"hp": 0.0, "atk": 0.0, "def": 0.0, "spd": 0.0}
    mastery_ids = active_mastery_ids(masteries or [])
    lore_of_steel_active = LORE_OF_STEEL_ID in mastery_ids

    for mastery_id in mastery_ids:
        for stat_type, stat_value in STATIC_MASTERY_BONUSES.get(mastery_id, []):
            apply_stat_value(flat_totals, percent_totals, stat_type, stat_value)

    for stat_type, stat_value in awakening_bonus_stats(rarity, awakening_level):
        apply_stat_value(flat_totals, percent_totals, stat_type, stat_value)

    for item in equipped_items:
        main_stat = mapping_value(item.get("main_stat"))
        apply_stat_value(flat_totals, percent_totals, main_stat.get("type"), main_stat.get("value"))
        for substat in list_value(item.get("substats")):
            glyph_value = float_value(substat.get("glyph_value"))
            total_value = float_value(substat.get("value")) + glyph_value
            apply_stat_value(flat_totals, percent_totals, substat.get("type"), total_value)

    applied_sets, _unsupported_sets = summarize_sets(equipped_items, set_rules)
    for applied_set in applied_sets:
        rule = mapping_value(set_rules.get(str(applied_set.get("set_name"))))
        set_kind = string_value(first_non_empty(applied_set.get("set_kind"), rule.get("set_kind"))).strip().lower() or "fixed"
        if set_kind in {"variable", "accessory"}:
            pieces_equipped = int_value(applied_set.get("pieces_equipped"))
            for piece_bonus in list_value(rule.get("piece_bonuses")):
                if pieces_equipped < int_value(piece_bonus.get("pieces_required")):
                    continue
                for stat_type, stat_value in list_value(piece_bonus.get("stats")):
                    apply_stat_value(flat_totals, percent_totals, stat_type, stat_value)
            continue

        completed_sets = int_value(applied_set.get("completed_sets"))
        for stat_type, stat_value in list_value(rule.get("stats")):
            amount = float_value(stat_value) * completed_sets
            if lore_of_steel_active and set_name_uses_basic_artifact_bonus(str(applied_set.get("set_name") or "")):
                amount *= 1.15
            apply_stat_value(flat_totals, percent_totals, stat_type, amount)

    champion_affinity = string_value(affinity).strip().lower() or "void"
    normalized_area_region = string_value(area_region).strip().lower()
    for bonus in bonuses:
        if not bool_value(bonus.get("active"), True):
            continue
        scope = string_value(bonus.get("scope")).strip().lower() or "global"
        target = string_value(bonus.get("target")).strip().lower() or "all"
        if scope == "area":
            if not normalized_area_region or target not in {"all", normalized_area_region}:
                continue
        elif target not in {"all", champion_affinity}:
            continue
        apply_stat_value(flat_totals, percent_totals, bonus.get("stat"), bonus.get("value"))

    for stat_type, stat_value in empowerment_bonus_stats(rarity, empowerment_level):
        apply_stat_value(flat_totals, percent_totals, stat_type, stat_value)

    totals = {
        "hp": base_totals["hp"] * (1.0 + percent_totals["hp"] / 100.0) + flat_totals["hp"],
        "atk": base_totals["atk"] * (1.0 + percent_totals["atk"] / 100.0) + flat_totals["atk"],
        "def": base_totals["def"] * (1.0 + percent_totals["def"] / 100.0) + flat_totals["def"],
        "spd": base_totals["spd"] * (1.0 + percent_totals["spd"] / 100.0) + flat_totals["spd"],
        "acc": base_totals["acc"] + flat_totals["acc"],
        "res": base_totals["res"] + flat_totals["res"],
        "crit_rate": base_totals["crit_rate"] + flat_totals["crit_rate"],
        "crit_dmg": base_totals["crit_dmg"] + flat_totals["crit_dmg"],
    }
    totals["spd"] = max(totals["spd"], 90.0)
    totals["crit_rate"] = min(max(totals["crit_rate"], 15.0), 100.0)
    totals["crit_dmg"] = max(totals["crit_dmg"], 50.0)
    return {stat_name: round(stat_value, 2) for stat_name, stat_value in totals.items()}


def summarize_sets(
    equipped_items: Iterable[Mapping[str, Any]],
    set_rules: Mapping[str, Mapping[str, Any]],
) -> tuple[List[Dict[str, Any]], List[str]]:
    counts: Dict[str, Dict[str, int]] = {}
    for item in equipped_items:
        set_name = string_value(item.get("set_name")).strip()
        if not set_name:
            continue
        bucket = counts.setdefault(set_name, {"all": 0, "artifact": 0, "accessory": 0})
        bucket["all"] += 1
        item_class = string_value(item.get("item_class")).strip().lower()
        if item_class == "accessory":
            bucket["accessory"] += 1
        else:
            bucket["artifact"] += 1

    applied_sets: List[Dict[str, Any]] = []
    unsupported_sets: List[str] = []
    for set_name in sorted(counts):
        rule = mapping_value(set_rules.get(set_name))
        if not rule:
            unsupported_sets.append(set_name)
            continue
        set_kind = string_value(rule.get("set_kind")).strip().lower() or "fixed"
        counts_accessories = bool_value(rule.get("counts_accessories"))
        pieces_equipped = counts[set_name]["all"] if counts_accessories else counts[set_name]["artifact"]
        if pieces_equipped <= 0:
            continue

        if set_kind in {"variable", "accessory"}:
            active_effects = [
                string_value(piece_bonus.get("effect_text")).strip()
                for piece_bonus in list_value(rule.get("piece_bonuses"))
                if pieces_equipped >= int_value(piece_bonus.get("pieces_required"))
                and string_value(piece_bonus.get("effect_text")).strip()
            ]
            if active_effects:
                unsupported_sets.append(set_name)
            applied_sets.append(
                {
                    "set_name": set_name,
                    "set_kind": set_kind,
                    "pieces_required": 1,
                    "pieces_equipped": pieces_equipped,
                    "completed_sets": 1,
                    "max_pieces": int_value(first_non_empty(rule.get("max_pieces"), 9 if set_kind == "variable" else 3)),
                    "active_bonus_count": sum(
                        1
                        for piece_bonus in list_value(rule.get("piece_bonuses"))
                        if pieces_equipped >= int_value(piece_bonus.get("pieces_required"))
                    ),
                }
            )
            continue

        pieces_required = int_value(first_non_empty(rule.get("pieces_required"), rule.get("pieces")))
        if pieces_required <= 0:
            unsupported_sets.append(set_name)
            continue
        completed_sets = pieces_equipped // pieces_required
        if completed_sets <= 0:
            continue
        applied_sets.append(
            {
                "set_name": set_name,
                "set_kind": "fixed",
                "pieces_required": pieces_required,
                "pieces_equipped": pieces_equipped,
                "completed_sets": completed_sets,
                "max_pieces": int_value(first_non_empty(rule.get("max_pieces"), pieces_required)),
            }
        )
    return applied_sets, sorted(set(unsupported_sets))


def apply_stat_value(
    flat_totals: Dict[str, float],
    percent_totals: Dict[str, float],
    stat_type: Any,
    raw_value: Any,
) -> None:
    normalized_key = normalize_stat_key(stat_type)
    if not normalized_key:
        return
    value = normalize_stat_amount(normalized_key, float_value(raw_value))
    if value == 0:
        return
    if normalized_key == "hp":
        flat_totals["hp"] += value
    elif normalized_key == "atk":
        flat_totals["atk"] += value
    elif normalized_key == "def":
        flat_totals["def"] += value
    elif normalized_key == "spd":
        flat_totals["spd"] += value
    elif normalized_key == "acc":
        flat_totals["acc"] += value
    elif normalized_key == "res":
        flat_totals["res"] += value
    elif normalized_key == "crit_rate":
        flat_totals["crit_rate"] += value
    elif normalized_key == "crit_dmg":
        flat_totals["crit_dmg"] += value
    elif normalized_key == "hp_pct":
        percent_totals["hp"] += value
    elif normalized_key == "atk_pct":
        percent_totals["atk"] += value
    elif normalized_key == "def_pct":
        percent_totals["def"] += value
    elif normalized_key == "spd_pct":
        percent_totals["spd"] += value


def has_meaningful_total_stats(total_stats: Mapping[str, Any]) -> bool:
    return any(abs(float_value(value)) > 0.001 for value in total_stats.values())


def has_meaningful_base_stats(base_stats: Mapping[str, Any]) -> bool:
    return any(abs(float_value(value)) > 0.001 for value in base_stats.values())


def normalize_total_stats(total_stats: Mapping[str, Any]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    for stat_name, stat_value in total_stats.items():
        normalized_name = normalize_stat_key(stat_name)
        if not normalized_name:
            continue
        normalized[normalized_name] = round(float_value(stat_value), 2)
    return normalized


def normalize_stat_key(value: Any) -> str:
    aliases = {
        "def_": "def",
        "critical_rate": "crit_rate",
        "critical_damage": "crit_dmg",
    }
    normalized = string_value(value).strip().lower()
    return aliases.get(normalized, normalized)


def normalize_stat_amount(stat_type: str, value: float) -> float:
    if 0 < abs(value) <= 1.0 and stat_type in {"hp_pct", "atk_pct", "def_pct", "spd_pct", "acc", "res"}:
        return value * 100.0
    return value


def first_non_empty(*values: Any) -> Any:
    for value in values:
        if value is None:
            continue
        if isinstance(value, str) and not value.strip():
            continue
        return value
    return None


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def mapping_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)


def active_mastery_ids(masteries: Iterable[Mapping[str, Any]]) -> set[str]:
    return {
        string_value(mastery.get("mastery_id")).strip()
        for mastery in masteries
        if bool_value(mastery.get("active"), True) and string_value(mastery.get("mastery_id")).strip()
    }


def set_name_uses_basic_artifact_bonus(set_name: str) -> bool:
    return string_value(set_name).strip() in BASIC_ARTIFACT_SET_NAMES


def awakening_bonus_stats(rarity: Any, awakening_level: Any) -> List[tuple[str, float]]:
    rarity_key = string_value(rarity).strip().lower()
    grade = max(0, min(int_value(awakening_level), 6))
    bonuses: List[tuple[str, float]] = []
    for current_grade in range(1, grade + 1):
        bonuses.extend(AWAKENING_BONUSES_BY_RARITY.get(rarity_key, {}).get(current_grade, []))
    return bonuses


def empowerment_bonus_stats(rarity: Any, empowerment_level: Any) -> List[tuple[str, float]]:
    rarity_key = string_value(rarity).strip().lower()
    level = max(0, min(int_value(empowerment_level), 4))
    return list(EMPOWERMENT_BONUSES_BY_RARITY.get(rarity_key, {}).get(level, []))
