from __future__ import annotations

from typing import Any, Dict, Iterable, List, Mapping, Tuple


PREMIUM_STATS = {"spd", "crit_rate", "crit_dmg", "acc"}
GOOD_STATS = PREMIUM_STATS | {"hp_pct", "def_pct", "atk_pct", "res"}
FLAT_STATS = {"hp", "atk", "def"}
STRONG_MAIN = "strong"
MEDIUM_MAIN = "medium"
WEAK_MAIN = "weak"

RARITY_SCORES = {
    "mythical": 14,
    "legendary": 11,
    "epic": 6,
    "rare": -2,
    "uncommon": -8,
    "common": -12,
}

SET_SCORES = {
    "Accuracy": 8,
    "Accuracy And Speed": 12,
    "Attack Speed": 10,
    "Attack Power And Ignore Defense": 8,
    "Feral": 7,
    "HP And Defence": 8,
    "HP And Heal": 8,
    "Life Drain": 4,
    "Merciless": 8,
    "Mercurial": 6,
    "Protection": 7,
    "Shield And Attack Power": 6,
    "Shield And Critical Chance": 6,
    "Shield And HP": 6,
    "Shield And Speed": 9,
    "Stone Skin": 7,
    "Supersonic": 8,
}

MAIN_STAT_SCORES = {
    "weapon": {"atk": 18},
    "helmet": {"hp": 18},
    "shield": {"def": 18},
    "boots": {"spd": 24, "hp_pct": 18, "def_pct": 18, "atk_pct": 15, "acc": 12, "res": 12, "hp": 5, "atk": 5, "def": 5},
    "chest": {"hp_pct": 20, "def_pct": 20, "atk_pct": 16, "acc": 15, "res": 15, "crit_rate": 13, "crit_dmg": 13, "hp": 5, "atk": 5, "def": 5},
    "gloves": {"crit_rate": 22, "crit_dmg": 22, "hp_pct": 18, "def_pct": 18, "atk_pct": 16, "acc": 13, "res": 13, "hp": 5, "atk": 5, "def": 5},
    "ring": {"hp": 12, "def": 12, "atk": 10},
    "amulet": {"acc": 15, "res": 14, "crit_dmg": 14, "hp": 11, "def": 11, "atk": 10},
    "banner": {"acc": 18, "res": 16, "hp": 13, "def": 13, "atk": 11, "crit_rate": 10, "crit_dmg": 10},
}

STAT_SCORES = {
    "spd": 10,
    "crit_rate": 9,
    "crit_dmg": 8,
    "acc": 8,
    "hp_pct": 7,
    "def_pct": 7,
    "atk_pct": 6,
    "res": 5,
    "hp": 2,
    "def": 2,
    "atk": 1,
}

STARTING_SUBSTAT_SCORES = {
    4: 6,
    3: 2,
    2: -4,
    1: -8,
    0: -12,
}


def evaluate_gear_item(item: Mapping[str, Any], substats: Iterable[Mapping[str, Any]]) -> Dict[str, Any]:
    slot = normalize_key(item.get("slot"))
    main_stat_type = normalize_key(item.get("main_stat_type"))
    rarity = normalize_key(item.get("rarity"))
    set_name = string_value(item.get("set_name")).strip()
    level = int_value(item.get("level"))
    rank = int_value(item.get("rank"))
    equipped = bool(item.get("equipped"))

    substat_rows = [dict(substat) for substat in substats]
    main_tier, desired_core, desired_support, dead_substats = desired_profile(slot, main_stat_type)
    good_substats = [normalize_key(row.get("stat_type")) for row in substat_rows if stat_score(row.get("stat_type")) >= 5]
    premium_substats = [normalize_key(row.get("stat_type")) for row in substat_rows if normalize_key(row.get("stat_type")) in PREMIUM_STATS]
    premium_rolls = sum(int_value(row.get("rolls")) for row in substat_rows if normalize_key(row.get("stat_type")) in PREMIUM_STATS)
    good_rolls = sum(int_value(row.get("rolls")) for row in substat_rows if stat_score(row.get("stat_type")) >= 5)
    substat_count = len(substat_rows)
    starting_rolls = sum(max(int_value(row.get("rolls")), 0) for row in substat_rows)
    desired_core_count, desired_support_count, dead_count = desired_substat_counts(
        substat_rows,
        desired_core,
        desired_support,
        dead_substats,
    )
    desired_rolls = desired_roll_count(substat_rows, desired_core, desired_support)

    main_score = MAIN_STAT_SCORES.get(slot, {}).get(main_stat_type, 8 if main_stat_type in GOOD_STATS else 4)
    set_score = SET_SCORES.get(set_name, 4 if set_name else 0)
    rank_score = 14 if rank >= 6 else 8 if rank == 5 else 0
    rarity_score = RARITY_SCORES.get(rarity, 0)

    base_substat_score = sum(max(stat_score(row.get("stat_type")), 0) for row in substat_rows)
    realized_roll_score = sum(realized_substat_score(row) for row in substat_rows)
    starting_quality_score = STARTING_SUBSTAT_SCORES.get(substat_count, -12) + min(starting_rolls, 2) * 4

    pre12_score = main_score + set_score + rank_score + rarity_score + base_substat_score + starting_quality_score
    realized_score = main_score + set_score + rank_score + rarity_score + realized_roll_score + starting_quality_score

    reasons: List[str] = []
    if main_tier == STRONG_MAIN:
        reasons.append(f"main stat forte: {main_stat_type}")
    elif main_tier == MEDIUM_MAIN:
        reasons.append(f"main stat situazionale: {main_stat_type}")
    else:
        reasons.append(f"main stat debole per slot: {main_stat_type}")
    reasons.append(rarity_reason(rarity))

    if desired_core_count > 0:
        reasons.append(f"sub core: {desired_core_count}")
    if desired_support_count > 0:
        reasons.append(f"sub support: {desired_support_count}")
    reasons.append(f"partenza: {substat_count} sub aperte")
    if starting_rolls > 0:
        reasons.append(f"partenza: {starting_rolls} roll gia presenti")
    if premium_substats:
        reasons.append(f"sub premium: {', '.join(sorted(set(premium_substats)))}")
    elif good_substats:
        reasons.append(f"sub utili: {', '.join(sorted(set(good_substats)))}")
    else:
        reasons.append("substat poco utili")
    if dead_count > 0:
        reasons.append(f"sub morte: {dead_count}")

    if level < 12:
        can_push_12 = should_push_12(
            main_tier=main_tier,
            pre12_score=pre12_score,
            desired_core_count=desired_core_count,
            desired_support_count=desired_support_count,
            desired_rolls=desired_rolls,
            dead_count=dead_count,
            rank=rank,
            rarity=rarity,
            set_score=set_score,
        )
        verdict = evaluate_pre12(level=level, can_push_12=can_push_12)
        verdict = apply_accessory_pre12_policy(
            verdict=verdict,
            level=level,
            slot=slot,
            rarity=rarity,
            main_tier=main_tier,
            pre12_score=pre12_score,
            desired_core_count=desired_core_count,
            desired_support_count=desired_support_count,
            dead_count=dead_count,
        )
    elif level < 16:
        verdict = evaluate_plus_12(
            main_tier=main_tier,
            realized_score=realized_score,
            premium_rolls=premium_rolls,
            good_rolls=good_rolls,
            desired_core_count=desired_core_count,
            desired_support_count=desired_support_count,
            desired_rolls=desired_rolls,
            dead_count=dead_count,
        )
        verdict = apply_accessory_plus_12_policy(
            verdict=verdict,
            slot=slot,
            main_tier=main_tier,
            realized_score=realized_score,
            premium_rolls=premium_rolls,
            desired_core_count=desired_core_count,
            desired_support_count=desired_support_count,
            desired_rolls=desired_rolls,
            dead_count=dead_count,
        )
    else:
        verdict = evaluate_plus_16(
            main_tier=main_tier,
            realized_score=realized_score,
            desired_core_count=desired_core_count,
            desired_support_count=desired_support_count,
            premium_rolls=premium_rolls,
            dead_count=dead_count,
        )

    verdict = apply_rarity_policy(verdict=verdict, rarity=rarity, level=level)

    if equipped and verdict in {"sell_now", "sell_after_12", "review_pre12"}:
        verdict = "review_equipped"
        reasons.append(f"attualmente addosso a {string_value(item.get('owner_name')) or 'un campione'}")

    if premium_rolls > 0:
        reasons.append(f"roll premium: {premium_rolls}")
    elif good_rolls > 0:
        reasons.append(f"roll utili: {good_rolls}")

    return {
        "verdict": verdict,
        "pre12_score": pre12_score,
        "realized_score": realized_score,
        "main_score": main_score,
        "set_score": set_score,
        "premium_rolls": premium_rolls,
        "good_rolls": good_rolls,
        "desired_core_count": desired_core_count,
        "desired_support_count": desired_support_count,
        "desired_rolls": desired_rolls,
        "dead_count": dead_count,
        "main_tier": main_tier,
        "good_substats": sorted(set(filter(None, good_substats))),
        "premium_substats": sorted(set(filter(None, premium_substats))),
        "reasons": reasons,
    }


def summarize_gear_verdicts(items: Iterable[Mapping[str, Any]]) -> Dict[str, int]:
    counts: Dict[str, int] = {}
    for item in items:
        verdict = string_value(item.get("advice_verdict"))
        if not verdict:
            continue
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def should_push_12(
    main_tier: str,
    pre12_score: float,
    desired_core_count: int,
    desired_support_count: int,
    desired_rolls: int,
    dead_count: int,
    rank: int,
    rarity: str,
    set_score: int,
) -> bool:
    if rank < 5:
        return False
    if rarity not in {"epic", "legendary", "mythical"}:
        return False
    if main_tier == WEAK_MAIN:
        return False
    if main_tier == STRONG_MAIN:
        return (
            pre12_score >= 54
            and desired_core_count >= 1
            and desired_core_count + desired_support_count >= 2
            and dead_count <= 2
        )
    return (
        pre12_score >= 62
        and desired_core_count >= 2
        and desired_rolls >= 1
        and dead_count <= 1
        and set_score >= 4
    )


def evaluate_pre12(level: int, can_push_12: bool) -> str:
    if can_push_12:
        return "push_12"
    if level < 8:
        return "sell_now"
    return "review_pre12"


def apply_rarity_policy(verdict: str, rarity: str, level: int) -> str:
    rarity = normalize_key(rarity)
    if rarity in {"mythical", "legendary"}:
        return verdict
    if rarity == "epic":
        if verdict == "keep_16" and level >= 16:
            return verdict
        return verdict
    if rarity == "rare":
        if level < 12:
            return "review_pre12" if level >= 8 else "sell_now"
        if level < 16:
            return "sell_after_12"
        return "review_16"
    if rarity in {"uncommon", "common"}:
        if level < 12:
            return "review_pre12" if level >= 8 else "sell_now"
        if level < 16:
            return "sell_after_12"
        return "review_16"
    return verdict


def apply_accessory_pre12_policy(
    verdict: str,
    level: int,
    slot: str,
    rarity: str,
    main_tier: str,
    pre12_score: float,
    desired_core_count: int,
    desired_support_count: int,
    dead_count: int,
) -> str:
    if verdict != "sell_now":
        return verdict
    if level >= 8:
        return verdict
    if slot not in {"ring", "amulet", "banner"}:
        return verdict
    if rarity not in {"epic", "legendary", "mythical"}:
        return verdict

    total_useful_subs = desired_core_count + desired_support_count
    if main_tier == STRONG_MAIN:
        if pre12_score >= 50 and total_useful_subs >= 2 and dead_count <= 2:
            return "review_pre12"
        return verdict
    if main_tier == MEDIUM_MAIN:
        if pre12_score >= 44 and desired_core_count >= 1 and dead_count <= 1:
            return "review_pre12"
    return verdict


def evaluate_plus_12(
    main_tier: str,
    realized_score: float,
    premium_rolls: int,
    good_rolls: int,
    desired_core_count: int,
    desired_support_count: int,
    desired_rolls: int,
    dead_count: int,
) -> str:
    if main_tier != WEAK_MAIN and realized_score >= 82 and desired_rolls >= 3 and premium_rolls >= 1 and dead_count <= 1:
        return "push_16"
    if main_tier == STRONG_MAIN and realized_score >= 70 and desired_rolls >= 2 and desired_core_count + desired_support_count >= 2:
        return "keep_after_12"
    if main_tier == MEDIUM_MAIN and realized_score >= 76 and desired_core_count >= 2 and desired_rolls >= 2 and dead_count == 0:
        return "keep_after_12"
    return "sell_after_12"


def evaluate_plus_16(
    main_tier: str,
    realized_score: float,
    desired_core_count: int,
    desired_support_count: int,
    premium_rolls: int,
    dead_count: int,
) -> str:
    if main_tier == WEAK_MAIN:
        return "review_16"
    if realized_score >= 74 and desired_core_count + desired_support_count >= 2 and premium_rolls >= 1 and dead_count <= 2:
        return "keep_16"
    return "review_16"


def apply_accessory_plus_12_policy(
    verdict: str,
    slot: str,
    main_tier: str,
    realized_score: float,
    premium_rolls: int,
    desired_core_count: int,
    desired_support_count: int,
    desired_rolls: int,
    dead_count: int,
) -> str:
    if verdict != "sell_after_12":
        return verdict
    if slot not in {"ring", "amulet", "banner"}:
        return verdict
    if main_tier == STRONG_MAIN:
        if realized_score >= 68 and desired_rolls >= 2 and desired_core_count + desired_support_count >= 2 and dead_count <= 2:
            return "keep_after_12"
        return verdict
    if main_tier == MEDIUM_MAIN:
        if realized_score >= 74 and desired_rolls >= 2 and desired_core_count + desired_support_count >= 2 and dead_count <= 1:
            return "keep_after_12"
    return verdict


def desired_profile(slot: str, main_stat_type: str) -> Tuple[str, set[str], set[str], set[str]]:
    if slot in {"weapon", "helmet", "shield"}:
        return STRONG_MAIN, {"spd", "crit_rate", "crit_dmg", "acc"}, {"hp_pct", "def_pct", "atk_pct", "res"}, FLAT_STATS

    if slot == "boots":
        if main_stat_type == "spd":
            return STRONG_MAIN, {"acc", "res", "crit_rate", "crit_dmg"}, {"hp_pct", "def_pct", "atk_pct"}, FLAT_STATS
        if main_stat_type in {"hp_pct", "def_pct"}:
            return STRONG_MAIN, {"spd", "acc", "res"}, {"crit_rate", "crit_dmg", "hp_pct", "def_pct"}, FLAT_STATS
        if main_stat_type == "atk_pct":
            return MEDIUM_MAIN, {"spd", "crit_rate", "crit_dmg"}, {"atk_pct", "acc"}, FLAT_STATS
        return WEAK_MAIN, {"spd"}, {"acc"}, FLAT_STATS

    if slot == "gloves":
        if main_stat_type in {"crit_rate", "crit_dmg"}:
            return STRONG_MAIN, {"spd", "crit_rate", "crit_dmg", "atk_pct"}, {"acc", "hp_pct", "def_pct"}, FLAT_STATS
        if main_stat_type in {"hp_pct", "def_pct"}:
            return STRONG_MAIN, {"spd", "acc", "res"}, {"hp_pct", "def_pct", "crit_rate"}, FLAT_STATS
        if main_stat_type in {"atk_pct", "acc", "res"}:
            return MEDIUM_MAIN, {"spd", "crit_rate", "crit_dmg", "acc"}, {"atk_pct", "hp_pct", "def_pct"}, FLAT_STATS
        return WEAK_MAIN, {"spd"}, {"acc"}, FLAT_STATS

    if slot == "chest":
        if main_stat_type in {"hp_pct", "def_pct", "acc", "res"}:
            return STRONG_MAIN, {"spd", "acc", "res"}, {"hp_pct", "def_pct", "crit_rate"}, FLAT_STATS
        if main_stat_type in {"atk_pct", "crit_rate", "crit_dmg"}:
            return MEDIUM_MAIN, {"spd", "crit_rate", "crit_dmg"}, {"atk_pct", "acc"}, FLAT_STATS
        return WEAK_MAIN, {"spd"}, {"acc"}, FLAT_STATS

    if slot == "ring":
        if main_stat_type == "hp":
            return MEDIUM_MAIN, {"hp_pct", "spd"}, {"def_pct", "acc", "res", "crit_rate"}, {"atk", "def"}
        if main_stat_type == "def":
            return MEDIUM_MAIN, {"def_pct", "spd"}, {"hp_pct", "acc", "res", "crit_rate"}, {"atk", "hp"}
        if main_stat_type == "atk":
            return MEDIUM_MAIN, {"atk_pct", "spd", "crit_rate", "crit_dmg"}, {"acc"}, {"hp", "def"}
        return WEAK_MAIN, {"spd"}, {"acc"}, FLAT_STATS

    if slot == "amulet":
        if main_stat_type in {"crit_dmg", "acc", "res"}:
            return STRONG_MAIN, {"spd", "crit_rate", "acc", "res"}, {"hp_pct", "def_pct", "atk_pct"}, FLAT_STATS
        if main_stat_type == "atk":
            return MEDIUM_MAIN, {"spd", "crit_rate", "crit_dmg", "atk_pct"}, {"acc"}, {"hp", "def"}
        if main_stat_type in {"hp", "def"}:
            return MEDIUM_MAIN, {"spd", "acc", "res"}, {"hp_pct", "def_pct", "crit_rate"}, {"atk"}
        return WEAK_MAIN, {"spd"}, {"acc"}, FLAT_STATS

    if slot == "banner":
        if main_stat_type in {"acc", "res"}:
            return STRONG_MAIN, {"spd", "hp_pct", "def_pct"}, {"acc", "res", "crit_rate"}, FLAT_STATS
        if main_stat_type == "def":
            return MEDIUM_MAIN, {"spd", "def_pct", "acc", "res"}, {"hp_pct", "crit_rate"}, {"atk", "hp"}
        if main_stat_type == "hp":
            return MEDIUM_MAIN, {"spd", "hp_pct", "acc", "res"}, {"def_pct", "crit_rate"}, {"atk", "def"}
        if main_stat_type == "atk":
            return MEDIUM_MAIN, {"spd", "atk_pct", "crit_rate", "crit_dmg"}, {"acc"}, {"hp", "def"}
        if main_stat_type in {"crit_rate", "crit_dmg"}:
            return MEDIUM_MAIN, {"spd", "atk_pct", "crit_rate", "crit_dmg"}, {"hp_pct", "def_pct", "acc"}, FLAT_STATS
        return WEAK_MAIN, {"spd"}, {"acc"}, FLAT_STATS

    return MEDIUM_MAIN, {"spd", "acc"}, {"hp_pct", "def_pct", "atk_pct", "res"}, FLAT_STATS


def desired_substat_counts(
    substats: Iterable[Mapping[str, Any]],
    desired_core: set[str],
    desired_support: set[str],
    dead_substats: set[str],
) -> Tuple[int, int, int]:
    core_count = 0
    support_count = 0
    dead_count = 0
    for substat in substats:
        stat_type = normalize_key(substat.get("stat_type"))
        if stat_type in desired_core:
            core_count += 1
        elif stat_type in desired_support:
            support_count += 1
        elif stat_type in dead_substats:
            dead_count += 1
    return core_count, support_count, dead_count


def desired_roll_count(
    substats: Iterable[Mapping[str, Any]],
    desired_core: set[str],
    desired_support: set[str],
) -> int:
    rolls = 0
    for substat in substats:
        stat_type = normalize_key(substat.get("stat_type"))
        stat_rolls = int_value(substat.get("rolls"))
        if stat_type in desired_core:
            rolls += max(stat_rolls, 0) + 1
        elif stat_type in desired_support:
            rolls += max(stat_rolls, 0)
    return rolls


def realized_substat_score(substat: Mapping[str, Any]) -> float:
    base = max(stat_score(substat.get("stat_type")), 0)
    rolls = int_value(substat.get("rolls"))
    glyph_value = float_value(substat.get("glyph_value"))
    glyph_bonus = min(glyph_value / 5.0, 2.0)
    return base * (1.0 + 0.7 * rolls + 0.15 * glyph_bonus)


def stat_score(stat_type: Any) -> int:
    return STAT_SCORES.get(normalize_key(stat_type), 0)


def normalize_key(value: Any) -> str:
    aliases = {
        "def_": "def",
    }
    normalized = string_value(value).strip().lower()
    return aliases.get(normalized, normalized)


def rarity_reason(rarity: str) -> str:
    rarity = normalize_key(rarity)
    if rarity == "mythical":
        return "rarita top: rosso"
    if rarity == "legendary":
        return "rarita top: arancione"
    if rarity == "epic":
        return "rarita buona: viola"
    if rarity == "rare":
        return "rarita bassa: azzurro"
    if rarity == "uncommon":
        return "rarita scarsa: verde"
    if rarity == "common":
        return "rarita scarsa: grigio"
    return f"rarita: {rarity or 'n/d'}"


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
