from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from account_stats import (
    build_stat_computation,
    has_meaningful_total_stats,
    materialize_base_totals,
    normalize_stat_amount,
    normalize_stat_key,
)
from forge_db import DB_PATH, DEFAULT_SET_RULES, ensure_schema, load_account_bonuses, load_set_rules


BUILD_SLOT_ORDER = (
    "weapon",
    "helmet",
    "shield",
    "gloves",
    "chest",
    "boots",
    "ring",
    "amulet",
    "banner",
)

STAT_NORMALIZERS = {
    "hp": 1000.0,
    "atk": 100.0,
    "def": 100.0,
    "spd": 1.0,
    "acc": 1.0,
    "res": 1.0,
    "crit_rate": 1.0,
    "crit_dmg": 1.0,
}

BUILD_PROFILES: Dict[str, Dict[str, Any]] = {
    "arena_speed_lead": {
        "label": "Arena Speed Lead",
        "description": "Massimizza la speed reale del campione, con tie-break su HP, DEF e RES.",
        "weights": {"spd": 16.0, "hp": 1.1, "def": 0.8, "res": 0.22, "acc": 0.04},
        "set_bias": {"Attack Speed": 18.0, "Accuracy And Speed": 18.0, "Shield And Speed": 15.0, "Accuracy": 4.0},
        "highlights": ["spd", "hp", "def", "res"],
    },
    "debuffer_acc_spd": {
        "label": "Debuffer ACC / SPD",
        "description": "Cerca speed e accuracy, senza buttare via tutta la sopravvivenza.",
        "weights": {"spd": 11.0, "acc": 8.0, "hp": 0.9, "def": 0.8, "res": 0.18},
        "set_bias": {"Accuracy And Speed": 15.0, "Accuracy": 11.0, "Attack Speed": 10.0, "Shield And Speed": 8.0},
        "highlights": ["spd", "acc", "hp", "def"],
    },
    "support_tank": {
        "label": "Support / Tank",
        "description": "Bilancia tankiness e turn cycle per reviver, cleanser e support generici.",
        "weights": {"hp": 1.8, "def": 1.4, "spd": 6.0, "res": 0.42, "acc": 0.7},
        "set_bias": {"HP And Defence": 16.0, "HP And Heal": 13.0, "Shield And HP": 11.0, "Shield And Speed": 8.0},
        "highlights": ["hp", "def", "spd", "res"],
    },
    "arena_nuker": {
        "label": "Arena Nuker",
        "description": "Spinge danno e stats critiche, con un minimo di speed per non diventare piantato.",
        "weights": {"atk": 5.6, "crit_rate": 7.0, "crit_dmg": 6.6, "spd": 2.4, "hp": 0.2, "def": 0.15},
        "set_bias": {"Attack Power And Ignore Defense": 10.0, "Shield And Critical Chance": 9.0, "Attack Speed": 4.0},
        "highlights": ["atk", "crit_rate", "crit_dmg", "spd"],
    },
}

BUILD_SCOPE_OPTIONS = (
    {
        "key": "inventory_only",
        "label": "Magazzino + attuale",
        "description": "Usa solo pezzi liberi in magazzino o già addosso al campione.",
        "allow_borrowed": False,
        "candidate_limit": 7,
        "beam_width": 48,
        "borrow_penalty": 0.0,
    },
    {
        "key": "overall",
        "label": "Spinta massima",
        "description": "Può anche prendere pezzi da altri campioni per massimizzare il profilo.",
        "allow_borrowed": True,
        "candidate_limit": 8,
        "beam_width": 60,
        "borrow_penalty": 0.0,
    },
)


def list_build_profiles() -> List[Dict[str, Any]]:
    return [
        {
            "key": key,
            "label": profile["label"],
            "description": profile["description"],
            "highlights": list(profile.get("highlights") or []),
        }
        for key, profile in BUILD_PROFILES.items()
    ]


def build_champion_plan(
    champion_name: str,
    profile_key: str = "arena_speed_lead",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    profile = BUILD_PROFILES.get(profile_key)
    if profile is None:
        raise KeyError(f"Profilo build non trovato: {profile_key}")

    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        champion = load_champion_account(conn, champion_name)
        base_stats = load_base_stats(conn, champion["champion_name"])
        raw_total_stats = load_total_stats(conn, champion["champ_id"])
        bonuses = load_account_bonuses(conn)
        set_rules = dict(DEFAULT_SET_RULES)
        set_rules.update(load_set_rules(conn))
        all_items = load_all_gear(conn)

    eligible_items = [
        item
        for item in all_items
        if item.get("slot") in BUILD_SLOT_ORDER and item_matches_faction(item, champion["faction"])
    ]
    current_items = [item for item in eligible_items if item.get("equipped_by") == champion["champ_id"]]
    current_by_slot = {str(item["slot"]): item for item in current_items}
    base_totals = materialize_base_totals(base_stats)

    current_model = build_stat_computation(
        base_stats=base_stats,
        raw_total_stats=raw_total_stats,
        equipped_items=current_items,
        bonuses=bonuses,
        set_rules=set_rules,
        affinity=champion["affinity"],
    )
    current_compare_stats = (
        current_model.total_stats
        if has_meaningful_total_stats(current_model.total_stats)
        else derive_stats(base_stats, current_items, bonuses, set_rules, champion["affinity"])
    )
    current_build = summarize_build(
        scope_key="current",
        scope_label="Build attuale",
        scope_description="Pezzi attualmente equipaggiati su questo campione.",
        items=current_items,
        champion=champion,
        base_stats=base_stats,
        bonuses=bonuses,
        set_rules=set_rules,
        profile=profile,
        compare_stats=current_compare_stats,
        current_champion_name=champion["champion_name"],
        current_champ_id=champion["champ_id"],
        source_override=current_model.source,
        completeness_override=current_model.completeness,
        unsupported_override=current_model.unsupported_sets,
        applied_sets_override=current_model.applied_sets,
    )

    proposals: List[Dict[str, Any]] = []
    for scope in BUILD_SCOPE_OPTIONS:
        slot_candidates = collect_slot_candidates(
            eligible_items=eligible_items,
            current_by_slot=current_by_slot,
            champion=champion,
            base_totals=base_totals,
            profile=profile,
            set_rules=set_rules,
            scope=scope,
        )
        items = solve_build_with_beam_search(
            slot_candidates=slot_candidates,
            base_stats=base_stats,
            bonuses=bonuses,
            set_rules=set_rules,
            profile=profile,
            affinity=champion["affinity"],
            current_champ_id=champion["champ_id"],
            beam_width=int(scope["beam_width"]),
            borrow_penalty=float(scope["borrow_penalty"]),
        )
        proposals.append(
            summarize_build(
                scope_key=str(scope["key"]),
                scope_label=str(scope["label"]),
                scope_description=str(scope["description"]),
                items=items,
                champion=champion,
                base_stats=base_stats,
                bonuses=bonuses,
                set_rules=set_rules,
                profile=profile,
                compare_stats=current_compare_stats,
                current_champion_name=champion["champion_name"],
                current_champ_id=champion["champ_id"],
            )
        )

    return {
        "champion": champion,
        "profile": {
            "key": profile_key,
            "label": profile["label"],
            "description": profile["description"],
            "highlights": list(profile.get("highlights") or []),
        },
        "profiles": list_build_profiles(),
        "current_build": current_build,
        "proposals": proposals,
    }


def load_champion_account(conn: sqlite3.Connection, champion_name: str) -> Dict[str, Any]:
    row = conn.execute(
        """
        SELECT champ_id, champion_name, rarity, affinity, faction, level, rank, awakening_level, empowerment_level, booked
        FROM account_champions
        WHERE champion_name = ?
        ORDER BY level DESC, rank DESC, awakening_level DESC, empowerment_level DESC
        LIMIT 1
        """,
        (champion_name,),
    ).fetchone()
    if row is None:
        raise KeyError(f"Campione non trovato: {champion_name}")
    return {
        "champ_id": str(row["champ_id"]),
        "champion_name": str(row["champion_name"]),
        "rarity": str(row["rarity"] or ""),
        "affinity": str(row["affinity"] or ""),
        "faction": str(row["faction"] or ""),
        "level": int(row["level"] or 0),
        "rank": int(row["rank"] or 0),
        "awakening_level": int(row["awakening_level"] or 0),
        "empowerment_level": int(row["empowerment_level"] or 0),
        "booked": bool(row["booked"]),
    }


def load_base_stats(conn: sqlite3.Connection, champion_name: str) -> Dict[str, float]:
    rows = conn.execute(
        """
        SELECT stat_name, stat_value
        FROM champion_base_stats
        WHERE champion_name = ?
        ORDER BY stat_name ASC
        """,
        (champion_name,),
    ).fetchall()
    return {str(row["stat_name"]): float(row["stat_value"] or 0.0) for row in rows}


def load_total_stats(conn: sqlite3.Connection, champ_id: str) -> Dict[str, float]:
    rows = conn.execute(
        """
        SELECT stat_name, stat_value
        FROM account_champion_total_stats
        WHERE champ_id = ?
        ORDER BY stat_name ASC
        """,
        (champ_id,),
    ).fetchall()
    return {str(row["stat_name"]): float(row["stat_value"] or 0.0) for row in rows}


def load_all_gear(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    substat_rows = conn.execute(
        """
        SELECT item_id, substat_order, stat_type, stat_value, rolls, glyph_value
        FROM gear_substats
        ORDER BY item_id ASC, substat_order ASC
        """
    ).fetchall()
    substats_by_item: Dict[str, List[Dict[str, Any]]] = {}
    for row in substat_rows:
        substats_by_item.setdefault(str(row["item_id"]), []).append(
            {
                "substat_order": int(row["substat_order"] or 0),
                "type": str(row["stat_type"] or ""),
                "value": float(row["stat_value"] or 0.0),
                "rolls": int(row["rolls"] or 0),
                "glyph_value": float(row["glyph_value"] or 0.0),
            }
        )

    item_rows = conn.execute(
        """
        SELECT
            gi.item_id,
            gi.item_class,
            gi.slot,
            gi.set_name,
            gi.rarity,
            gi.rank,
            gi.level,
            gi.ascension_level,
            gi.required_faction,
            gi.required_faction_id,
            gi.equipped_by,
            gi.locked,
            gi.main_stat_type,
            gi.main_stat_value,
            ac.champion_name AS owner_name
        FROM gear_items gi
        LEFT JOIN account_champions ac
            ON ac.champ_id = gi.equipped_by
        ORDER BY gi.item_id ASC
        """
    ).fetchall()

    return [
        {
            "item_id": str(row["item_id"]),
            "item_class": str(row["item_class"] or ""),
            "slot": str(row["slot"] or ""),
            "set_name": str(row["set_name"] or ""),
            "rarity": str(row["rarity"] or ""),
            "rank": int(row["rank"] or 0),
            "level": int(row["level"] or 0),
            "ascension_level": int(row["ascension_level"] or 0),
            "required_faction": str(row["required_faction"] or ""),
            "required_faction_id": int(row["required_faction_id"] or 0),
            "equipped_by": str(row["equipped_by"] or ""),
            "owner_name": str(row["owner_name"] or ""),
            "locked": bool(row["locked"]),
            "main_stat": {
                "type": str(row["main_stat_type"] or ""),
                "value": float(row["main_stat_value"] or 0.0),
            },
            "substats": substats_by_item.get(str(row["item_id"]), []),
        }
        for row in item_rows
    ]


def item_matches_faction(item: Mapping[str, Any], champion_faction: str) -> bool:
    required = str(item.get("required_faction") or "").strip().lower()
    if not required:
        return True
    return required == str(champion_faction or "").strip().lower()


def collect_slot_candidates(
    eligible_items: Iterable[Dict[str, Any]],
    current_by_slot: Mapping[str, Dict[str, Any]],
    champion: Mapping[str, Any],
    base_totals: Mapping[str, float],
    profile: Mapping[str, Any],
    set_rules: Mapping[str, Mapping[str, Any]],
    scope: Mapping[str, Any],
) -> Dict[str, List[Dict[str, Any]]]:
    candidate_limit = int(scope.get("candidate_limit") or 6)
    allow_borrowed = bool(scope.get("allow_borrowed"))
    current_champ_id = str(champion.get("champ_id") or "")

    by_slot: Dict[str, List[Dict[str, Any]]] = {slot: [] for slot in BUILD_SLOT_ORDER}
    for item in eligible_items:
        equipped_by = str(item.get("equipped_by") or "")
        if not allow_borrowed and equipped_by and equipped_by != current_champ_id:
            continue
        slot = str(item.get("slot") or "")
        if slot in by_slot:
            by_slot[slot].append(item)

    slot_candidates: Dict[str, List[Dict[str, Any]]] = {}
    for slot in BUILD_SLOT_ORDER:
        seen_ids = set()
        candidates: List[Dict[str, Any]] = []
        current_item = current_by_slot.get(slot)
        if current_item is not None:
            seen_ids.add(str(current_item["item_id"]))
            candidates.append(current_item)

        ranked = sorted(
            by_slot.get(slot, []),
            key=lambda item: (
                -estimate_item_score(item, base_totals, profile, set_rules),
                -int(item.get("level") or 0),
                -int(item.get("rank") or 0),
                str(item.get("item_id") or ""),
            ),
        )
        for item in ranked:
            item_id = str(item.get("item_id") or "")
            if item_id in seen_ids:
                continue
            seen_ids.add(item_id)
            candidates.append(item)
            if len(candidates) >= candidate_limit:
                break

        if not candidates and current_item is not None:
            candidates = [current_item]
        slot_candidates[slot] = candidates
    return slot_candidates


def solve_build_with_beam_search(
    slot_candidates: Mapping[str, List[Dict[str, Any]]],
    base_stats: Mapping[str, Any],
    bonuses: Iterable[Mapping[str, Any]],
    set_rules: Mapping[str, Mapping[str, Any]],
    profile: Mapping[str, Any],
    affinity: str,
    current_champ_id: str,
    beam_width: int,
    borrow_penalty: float,
) -> List[Dict[str, Any]]:
    states: List[Dict[str, Any]] = [{"items": [], "score": float("-inf"), "signature": ""}]
    for slot in BUILD_SLOT_ORDER:
        options = list(slot_candidates.get(slot) or [])
        if not options:
            continue
        next_states: List[Dict[str, Any]] = []
        seen_signatures = set()
        for state in states:
            existing_items = list(state["items"])
            for item in options:
                new_items = existing_items + [item]
                signature = "|".join(sorted(str(selected["item_id"]) for selected in new_items))
                if signature in seen_signatures:
                    continue
                totals = derive_stats(base_stats, new_items, bonuses, set_rules, affinity)
                score = score_profile_totals(totals, profile) - build_borrow_penalty(new_items, current_champ_id, borrow_penalty)
                next_states.append({"items": new_items, "score": score, "signature": signature})
                seen_signatures.add(signature)
        next_states.sort(key=lambda state: (-float(state["score"]), len(state["items"]), str(state["signature"])))
        states = next_states[:beam_width] or states

    if not states:
        return []
    states.sort(key=lambda state: (-float(state["score"]), str(state["signature"])))
    return list(states[0]["items"])


def derive_stats(
    base_stats: Mapping[str, Any],
    items: Iterable[Mapping[str, Any]],
    bonuses: Iterable[Mapping[str, Any]],
    set_rules: Mapping[str, Mapping[str, Any]],
    affinity: str,
) -> Dict[str, float]:
    result = build_stat_computation(
        base_stats=base_stats,
        raw_total_stats={},
        equipped_items=items,
        bonuses=bonuses,
        set_rules=set_rules,
        affinity=affinity,
    )
    return result.total_stats


def build_borrow_penalty(items: Iterable[Mapping[str, Any]], current_champ_id: str, penalty_per_item: float) -> float:
    if penalty_per_item <= 0:
        return 0.0
    borrowed = 0
    for item in items:
        equipped_by = str(item.get("equipped_by") or "")
        if equipped_by and equipped_by != current_champ_id:
            borrowed += 1
    return borrowed * penalty_per_item


def summarize_build(
    scope_key: str,
    scope_label: str,
    scope_description: str,
    items: Iterable[Mapping[str, Any]],
    champion: Mapping[str, Any],
    base_stats: Mapping[str, Any],
    bonuses: Iterable[Mapping[str, Any]],
    set_rules: Mapping[str, Mapping[str, Any]],
    profile: Mapping[str, Any],
    compare_stats: Mapping[str, Any],
    current_champion_name: str,
    current_champ_id: str,
    source_override: str | None = None,
    completeness_override: str | None = None,
    unsupported_override: List[str] | None = None,
    applied_sets_override: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    item_list = sorted(list(items), key=lambda item: BUILD_SLOT_ORDER.index(str(item.get("slot") or "")))
    stat_result = build_stat_computation(
        base_stats=base_stats,
        raw_total_stats={} if source_override is None else compare_stats if scope_key == "current" else {},
        equipped_items=item_list,
        bonuses=bonuses,
        set_rules=set_rules,
        affinity=str(champion.get("affinity") or ""),
    )
    totals = stat_result.total_stats
    score = round(score_profile_totals(totals, profile), 2)
    compare_totals = normalize_total_map(compare_stats)
    deltas = {
        stat_name: round(float(totals.get(stat_name, 0.0)) - float(compare_totals.get(stat_name, 0.0)), 2)
        for stat_name in STAT_NORMALIZERS
    }
    slot_map = {str(item.get("slot") or ""): item for item in item_list}
    missing_slots = [slot for slot in BUILD_SLOT_ORDER if slot not in slot_map]
    inventory_count = 0
    borrowed_count = 0
    same_owner_count = 0
    normalized_items: List[Dict[str, Any]] = []
    for item in item_list:
        equipped_by = str(item.get("equipped_by") or "")
        owner_name = str(item.get("owner_name") or "")
        if not equipped_by:
            source_label = "Magazzino"
            source_kind = "inventory"
            inventory_count += 1
        elif equipped_by == current_champ_id:
            source_label = f"Gia su {current_champion_name}"
            source_kind = "current"
            same_owner_count += 1
        else:
            source_label = f"Da {owner_name or equipped_by}"
            source_kind = "borrowed"
            borrowed_count += 1
        normalized_items.append(
            {
                "item_id": str(item.get("item_id") or ""),
                "item_class": str(item.get("item_class") or ""),
                "slot": str(item.get("slot") or ""),
                "set_name": str(item.get("set_name") or ""),
                "rarity": str(item.get("rarity") or ""),
                "rank": int(item.get("rank") or 0),
                "level": int(item.get("level") or 0),
                "ascension_level": int(item.get("ascension_level") or 0),
                "main_stat_type": str(mapping_value(item.get("main_stat")).get("type") or ""),
                "main_stat_value": float(mapping_value(item.get("main_stat")).get("value") or 0.0),
                "substats": [
                    {
                        "stat_type": str(substat.get("type") or ""),
                        "stat_value": round(float_value(substat.get("value")) + float_value(substat.get("glyph_value")), 2),
                        "rolls": int(substat.get("rolls") or 0),
                        "glyph_value": float_value(substat.get("glyph_value")),
                    }
                    for substat in list_value(item.get("substats"))
                ],
                "owner_name": owner_name,
                "equipped_by": equipped_by,
                "source_label": source_label,
                "source_kind": source_kind,
                "locked": bool(item.get("locked")),
            }
        )

    applied_sets = applied_sets_override if applied_sets_override is not None else stat_result.applied_sets
    unsupported_sets = unsupported_override if unsupported_override is not None else stat_result.unsupported_sets
    notes = build_notes(
        deltas=deltas,
        inventory_count=inventory_count,
        borrowed_count=borrowed_count,
        applied_sets=applied_sets,
    )
    return {
        "key": scope_key,
        "label": scope_label,
        "description": scope_description,
        "score": score,
        "stats": normalize_total_map(totals),
        "deltas": deltas,
        "items": normalized_items,
        "inventory_items": inventory_count,
        "borrowed_items": borrowed_count,
        "same_owner_items": same_owner_count,
        "swap_count": inventory_count + borrowed_count,
        "missing_slots": missing_slots,
        "notes": notes,
        "source": source_override or stat_result.source,
        "completeness": completeness_override or stat_result.completeness,
        "applied_sets": applied_sets,
        "unsupported_sets": unsupported_sets,
    }


def build_notes(
    deltas: Mapping[str, float],
    inventory_count: int,
    borrowed_count: int,
    applied_sets: Iterable[Mapping[str, Any]],
) -> List[str]:
    notes: List[str] = []
    for stat_name in ("spd", "acc", "hp", "def", "res", "crit_rate", "crit_dmg", "atk"):
        delta = float(deltas.get(stat_name) or 0.0)
        if abs(delta) < 0.01:
            continue
        label = stat_name.upper() if stat_name not in {"crit_rate", "crit_dmg"} else {"crit_rate": "C.RATE", "crit_dmg": "C.DMG"}[stat_name]
        prefix = "+" if delta > 0 else ""
        notes.append(f"{prefix}{format_delta(delta)} {label}")
        if len(notes) >= 3:
            break
    if inventory_count:
        notes.append(f"{inventory_count} pezzi dal magazzino")
    if borrowed_count:
        notes.append(f"{borrowed_count} pezzi presi da altri campioni")
    set_labels = [f"{row.get('set_name')} x{row.get('completed_sets')}" for row in applied_sets]
    if set_labels:
        notes.append("Set: " + ", ".join(set_labels[:2]))
    return notes[:5]


def estimate_item_score(
    item: Mapping[str, Any],
    base_totals: Mapping[str, float],
    profile: Mapping[str, Any],
    set_rules: Mapping[str, Mapping[str, Any]],
) -> float:
    score = 0.0
    weights = mapping_value(profile.get("weights"))
    score += estimate_stat_line_score(
        stat_type=mapping_value(item.get("main_stat")).get("type"),
        raw_value=mapping_value(item.get("main_stat")).get("value"),
        base_totals=base_totals,
        weights=weights,
    )
    for substat in list_value(item.get("substats")):
        raw_total = float_value(substat.get("value")) + float_value(substat.get("glyph_value"))
        score += estimate_stat_line_score(
            stat_type=substat.get("type"),
            raw_value=raw_total,
            base_totals=base_totals,
            weights=weights,
        )

    set_name = str(item.get("set_name") or "")
    pieces_required = int(mapping_value(set_rules.get(set_name)).get("pieces_required") or 0)
    set_bias = float(mapping_value(profile.get("set_bias")).get(set_name) or 0.0)
    if pieces_required > 0 and set_bias:
        score += set_bias / pieces_required
    return round(score, 4)


def estimate_stat_line_score(
    stat_type: Any,
    raw_value: Any,
    base_totals: Mapping[str, float],
    weights: Mapping[str, Any],
) -> float:
    normalized = normalize_stat_key(stat_type)
    amount = normalize_stat_amount(normalized, float_value(raw_value))
    if not normalized or amount == 0:
        return 0.0
    if normalized == "hp":
        return score_stat_delta("hp", amount, weights)
    if normalized == "atk":
        return score_stat_delta("atk", amount, weights)
    if normalized == "def":
        return score_stat_delta("def", amount, weights)
    if normalized == "spd":
        return score_stat_delta("spd", amount, weights)
    if normalized == "acc":
        return score_stat_delta("acc", amount, weights)
    if normalized == "res":
        return score_stat_delta("res", amount, weights)
    if normalized == "crit_rate":
        return score_stat_delta("crit_rate", amount, weights)
    if normalized == "crit_dmg":
        return score_stat_delta("crit_dmg", amount, weights)
    if normalized == "hp_pct":
        return score_stat_delta("hp", float(base_totals.get("hp") or 0.0) * amount / 100.0, weights)
    if normalized == "atk_pct":
        return score_stat_delta("atk", float(base_totals.get("atk") or 0.0) * amount / 100.0, weights)
    if normalized == "def_pct":
        return score_stat_delta("def", float(base_totals.get("def") or 0.0) * amount / 100.0, weights)
    if normalized == "spd_pct":
        return score_stat_delta("spd", float(base_totals.get("spd") or 0.0) * amount / 100.0, weights)
    return 0.0


def score_profile_totals(total_stats: Mapping[str, Any], profile: Mapping[str, Any]) -> float:
    weights = mapping_value(profile.get("weights"))
    score = 0.0
    for stat_name, weight in weights.items():
        score += score_stat_delta(str(stat_name), float_value(total_stats.get(stat_name)), weights)
    return round(score, 4)


def score_stat_delta(stat_name: str, value: float, weights: Mapping[str, Any]) -> float:
    normalized = normalize_stat_key(stat_name)
    if not normalized:
        return 0.0
    normalizer = float(STAT_NORMALIZERS.get(normalized, 1.0))
    weight = float(weights.get(normalized) or 0.0)
    return (float(value) / normalizer) * weight


def normalize_total_map(values: Mapping[str, Any]) -> Dict[str, float]:
    normalized: Dict[str, float] = {}
    for stat_name in STAT_NORMALIZERS:
        normalized[stat_name] = round(float_value(values.get(stat_name)), 2)
    return normalized


def format_delta(value: float) -> str:
    if abs(value - round(value)) < 0.05:
        return str(int(round(value)))
    return f"{value:.1f}"


def mapping_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
