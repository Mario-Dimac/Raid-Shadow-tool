from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Mapping


CORE_STATS = ("hp", "atk", "def", "spd", "acc", "res", "crit_rate", "crit_dmg")


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
    affinity: str = "",
) -> StatComputationResult:
    equipped_items = list(equipped_items)
    bonuses = list(bonuses)
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
            affinity=affinity,
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
    affinity: str = "",
) -> Dict[str, float]:
    base_totals = materialize_base_totals(base_stats)
    flat_totals = {stat_name: 0.0 for stat_name in CORE_STATS}
    percent_totals = {"hp": 0.0, "atk": 0.0, "def": 0.0, "spd": 0.0}

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
        completed_sets = int_value(applied_set.get("completed_sets"))
        for stat_type, stat_value in list_value(rule.get("stats")):
            amount = float_value(stat_value) * completed_sets
            apply_stat_value(flat_totals, percent_totals, stat_type, amount)

    champion_affinity = string_value(affinity).strip().lower() or "void"
    for bonus in bonuses:
        if not bool_value(bonus.get("active"), True):
            continue
        target = string_value(bonus.get("target")).strip().lower() or "all"
        if target not in {"all", champion_affinity}:
            continue
        apply_stat_value(flat_totals, percent_totals, bonus.get("stat"), bonus.get("value"))

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
    counts: Dict[str, int] = {}
    for item in equipped_items:
        set_name = string_value(item.get("set_name")).strip()
        if not set_name:
            continue
        counts[set_name] = counts.get(set_name, 0) + 1

    applied_sets: List[Dict[str, Any]] = []
    unsupported_sets: List[str] = []
    for set_name in sorted(counts):
        rule = mapping_value(set_rules.get(set_name))
        if not rule:
            unsupported_sets.append(set_name)
            continue
        pieces_required = int_value(first_non_empty(rule.get("pieces_required"), rule.get("pieces")))
        if pieces_required <= 0:
            unsupported_sets.append(set_name)
            continue
        completed_sets = counts[set_name] // pieces_required
        if completed_sets <= 0:
            continue
        applied_sets.append(
            {
                "set_name": set_name,
                "pieces_required": pieces_required,
                "pieces_equipped": counts[set_name],
                "completed_sets": completed_sets,
            }
        )
    return applied_sets, unsupported_sets


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
