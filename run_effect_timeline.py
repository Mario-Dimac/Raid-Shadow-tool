from __future__ import annotations

import argparse
import bisect
import json
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Sequence

import providers.ayumilove_provider  # noqa: F401
import providers.local_registry_provider  # noqa: F401
from battle_event_decoder import decode_skill_order_from_event_code
from enrichment_sources import get_skill_enrichment_provider
from hellhades_enrich import extract_effect_rows, html_to_text, infer_booked_cooldown, normalize_explicit_effect_rows
from run_damage_decoder import decode_battle_results_root, dict_value, extract_member_result_rows, int_value, list_value, string_value
from run_mapper import HH_HERO_TYPES_PATH, load_enemy_type_map


DEFAULT_PROVIDER_ORDER = ("local_registry", "ayumilove")
BUFF_EFFECT_TYPES = {
    "ally_protection",
    "block_damage",
    "block_debuffs",
    "block_revive",
    "counterattack",
    "continuous_heal",
    "increase_acc",
    "increase_atk",
    "increase_c_rate",
    "increase_c_dmg",
    "increase_def",
    "increase_res",
    "increase_spd",
    "intercept",
    "perfect_veil",
    "shield",
    "strengthen",
    "unkillable",
    "veil",
}
DEBUFF_EFFECT_TYPES = {
    "bomb",
    "decrease_acc",
    "decrease_atk",
    "decrease_c_dmg",
    "decrease_c_rate",
    "decrease_def",
    "decrease_res",
    "decrease_spd",
    "fear",
    "freeze",
    "heal_reduction",
    "hex",
    "hp_burn",
    "leech",
    "poison",
    "provoke",
    "sleep",
    "stun",
    "true_fear",
    "weaken",
}
UTILITY_EFFECT_TYPES = {
    "cooldown_increase",
    "cooldown_reduce",
    "cooldown_reset",
    "extra_turn",
    "remove_buffs",
    "revive",
    "steal_buffs",
    "turn_meter_fill",
    "turn_meter_fill_scaled",
    "turn_meter_reduce",
    "turn_meter_steal",
}
ACTION_BY_EFFECT_TYPE = {
    "cooldown_increase": "increase_cooldown",
    "cooldown_reduce": "reduce_cooldown",
    "cooldown_reset": "reset_cooldown",
    "extra_turn": "grant_extra_turn",
    "remove_buffs": "remove",
    "revive": "revive",
    "steal_buffs": "steal",
    "turn_meter_fill": "turn_meter_fill",
    "turn_meter_fill_scaled": "turn_meter_fill",
    "turn_meter_reduce": "turn_meter_reduce",
    "turn_meter_steal": "turn_meter_steal",
}


def nullable_int(value: Any) -> int | None:
    parsed = int_value(value)
    return parsed if parsed > 0 else None


def effect_category(effect_type: str, target: str) -> str:
    normalized = string_value(effect_type).strip().lower()
    target_text = string_value(target).strip().lower()
    if normalized in BUFF_EFFECT_TYPES:
        return "buff"
    if normalized in DEBUFF_EFFECT_TYPES:
        return "debuff"
    if normalized in UTILITY_EFFECT_TYPES:
        return "utility"
    if target_text in {"self", "ally", "all_allies"}:
        return "buff"
    if target_text in {"enemy", "all_enemies"}:
        return "debuff"
    return "utility"


def effect_action(effect_type: str, category: str) -> str:
    normalized = string_value(effect_type).strip().lower()
    if normalized in ACTION_BY_EFFECT_TYPE:
        return ACTION_BY_EFFECT_TYPE[normalized]
    if category in {"buff", "debuff"}:
        return "place"
    return "trigger"


def load_hero_name_map(hero_types_path: Path = HH_HERO_TYPES_PATH) -> Dict[int, str]:
    return {type_id: string_value(payload.get("name")) for type_id, payload in load_enemy_type_map(hero_types_path).items()}


def build_enemy_context_by_slot(root: Dict[str, Any], hero_types_path: Path = HH_HERO_TYPES_PATH) -> Dict[int, Dict[str, Any]]:
    hero_names = load_hero_name_map(hero_types_path)
    enemy_party = dict_value(dict_value(root.get("s")).get("s"))
    enemy_party_id = int_value(enemy_party.get("i"))
    members: Dict[int, Dict[str, Any]] = {}
    for row in list_value(enemy_party.get("h")):
        enemy = dict_value(row)
        slot_index = int_value(enemy.get("i"))
        champion_type_id = int_value(enemy.get("t"))
        members[slot_index] = {
            "member_order": slot_index + 1 if slot_index >= 0 else 0,
            "slot_index": slot_index,
            "champion_type_id": champion_type_id,
            "champion_name": hero_names.get(champion_type_id) or f"type_{champion_type_id}",
            "party_id": enemy_party_id,
            "party_role": "enemy",
        }
    return members


def build_party_context_by_party(path: Path, hero_types_path: Path = HH_HERO_TYPES_PATH) -> Dict[int, Dict[int, Dict[str, Any]]]:
    root = decode_battle_results_root(path)
    player_party_id = int_value(dict_value(dict_value(root.get("s")).get("f")).get("i"))
    members_by_slot = build_member_context_by_slot(path, hero_types_path=hero_types_path)
    party_context: Dict[int, Dict[int, Dict[str, Any]]] = {}

    if player_party_id != 0:
        party_context[player_party_id] = {
            slot_index: {
                **dict_value(member),
                "party_id": player_party_id,
                "party_role": "player",
            }
            for slot_index, member in members_by_slot.items()
        }

    enemy_context_by_slot = build_enemy_context_by_slot(root, hero_types_path=hero_types_path)
    if enemy_context_by_slot:
        enemy_party_id = int_value(next(iter(enemy_context_by_slot.values())).get("party_id"))
        if enemy_party_id != 0:
            party_context[enemy_party_id] = enemy_context_by_slot

    return party_context


def normalize_skill_row(skill: Dict[str, Any], provider_name: str, default_skill_order: int | None = None) -> Dict[str, Any]:
    description = string_value(skill.get("description_clean")).strip()
    if not description:
        description = html_to_text(skill.get("description"))
    books = list_value(skill.get("books"))
    cooldown = nullable_int(skill.get("cooldown"))
    booked_cooldown = nullable_int(skill.get("booked_cooldown"))
    if booked_cooldown is None:
        booked_cooldown = infer_booked_cooldown(cooldown, books, None)
    skill_order = int_value(skill.get("skill_order")) or nullable_int(string_value(skill.get("slot")).strip().removeprefix("A")) or int_value(default_skill_order)
    slot = string_value(skill.get("slot")).strip()
    if not slot and skill_order > 0:
        slot = f"A{skill_order}"

    effects = normalize_explicit_effect_rows(skill.get("effects"))
    if not effects:
        effects = extract_effect_rows(description)

    return {
        "slot": slot,
        "skill_order": skill_order,
        "skill_id": string_value(skill.get("skill_id")).strip(),
        "skill_name": string_value(skill.get("name") or skill.get("skill_name")).strip(),
        "skill_type": string_value(skill.get("type") or skill.get("skill_type")).strip(),
        "cooldown": cooldown,
        "booked_cooldown": booked_cooldown,
        "description_clean": description,
        "provider": provider_name,
        "effects": effects,
    }


@lru_cache(maxsize=512)
def _resolve_skill_catalog_for_champion_cached(
    champion_name: str,
    provider_order_key: tuple[str, ...],
) -> Dict[int, Dict[str, Any]]:
    name = string_value(champion_name).strip()
    if not name:
        return {}

    for provider_name in provider_order_key:
        provider = get_skill_enrichment_provider(provider_name)
        match = provider.resolve_champion_match(name)
        if match is None:
            continue
        skills = provider.fetch_champion_skills(match)
        normalized_rows = [
            normalize_skill_row(dict_value(skill), provider_name=provider_name, default_skill_order=index)
            for index, skill in enumerate(skills, start=1)
        ]
        catalog = {
            int_value(row.get("skill_order")): row
            for row in normalized_rows
            if int_value(row.get("skill_order")) > 0
        }
        if catalog and any(dict_value(row).get("effects") or string_value(dict_value(row).get("description_clean")).strip() for row in catalog.values()):
            return catalog
    return {}


def resolve_skill_catalog_for_champion(
    champion_name: str,
    provider_order: Sequence[str] = DEFAULT_PROVIDER_ORDER,
) -> Dict[int, Dict[str, Any]]:
    provider_order_key = tuple(string_value(item).strip() for item in provider_order if string_value(item).strip())
    return _resolve_skill_catalog_for_champion_cached(string_value(champion_name), provider_order_key)


def build_member_context_by_slot(path: Path, hero_types_path: Path = HH_HERO_TYPES_PATH) -> Dict[int, Dict[str, Any]]:
    hero_names = load_hero_name_map(hero_types_path)
    members: Dict[int, Dict[str, Any]] = {}
    for row in extract_member_result_rows(path):
        member = dict(row)
        slot_index = member.get("slot_index")
        resolved_slot = int_value(slot_index) if slot_index is not None else max(int_value(member.get("member_order")) - 1, 0)
        champion_type_id = int_value(member.get("champion_type_id"))
        members[resolved_slot] = {
            "member_order": int_value(member.get("member_order")),
            "slot_index": resolved_slot,
            "champion_type_id": champion_type_id,
            "champion_name": hero_names.get(champion_type_id) or f"type_{champion_type_id}",
        }
    return members


def resolve_skill_catalog_by_slot(
    member_context_by_slot: Dict[int, Dict[str, Any]],
    provider_order: Sequence[str] = DEFAULT_PROVIDER_ORDER,
) -> tuple[Dict[int, Dict[int, Dict[str, Any]]], Dict[str, str]]:
    catalog_by_slot: Dict[int, Dict[int, Dict[str, Any]]] = {}
    provider_by_champion: Dict[str, str] = {}
    for slot_index, member in member_context_by_slot.items():
        champion_name = string_value(member.get("champion_name")).strip()
        catalog = resolve_skill_catalog_for_champion(champion_name, provider_order=provider_order)
        if catalog:
            catalog_by_slot[slot_index] = catalog
            provider_by_champion[champion_name] = string_value(next(iter(catalog.values())).get("provider")).strip()
    return catalog_by_slot, provider_by_champion


def member_target_ref(member: Dict[str, Any]) -> Dict[str, Any]:
    slot_index = int_value(member.get("slot_index"))
    member_order = nullable_int(member.get("member_order"))
    if member_order is None and slot_index >= 0:
        member_order = slot_index + 1
    return {
        "party_id": int_value(member.get("party_id")),
        "party_role": string_value(member.get("party_role")).strip(),
        "slot_index": slot_index,
        "member_order": member_order,
        "champion_type_id": int_value(member.get("champion_type_id")),
        "champion_name": string_value(member.get("champion_name")).strip(),
    }


def list_party_member_refs(party_context_by_party: Dict[int, Dict[int, Dict[str, Any]]], party_id: int) -> List[Dict[str, Any]]:
    members = dict_value(party_context_by_party.get(party_id))
    return [member_target_ref(dict_value(members[key])) for key in sorted(members)]


def resolve_effect_candidate_targets(
    effect: Dict[str, Any],
    source_member: Dict[str, Any],
    event_target_party_id: int,
    event_target_slot: int,
    party_context_by_party: Dict[int, Dict[int, Dict[str, Any]]],
) -> tuple[str, str, List[Dict[str, Any]]]:
    normalized_target = string_value(effect.get("target")).strip().lower()
    source_party_id = int_value(source_member.get("party_id"))
    source_ref = member_target_ref(source_member)
    event_target_member = dict_value(dict_value(party_context_by_party.get(event_target_party_id)).get(event_target_slot))

    if normalized_target == "self":
        return "self", "resolved_from_effect_target_self", [source_ref]
    if normalized_target == "all_allies":
        refs = list_party_member_refs(party_context_by_party, source_party_id)
        return "all_allies", "resolved_from_source_party_scan", refs
    if normalized_target == "ally":
        if event_target_party_id == source_party_id and event_target_member:
            return "single_ally", "resolved_from_event_target", [member_target_ref(event_target_member)]
        return "single_ally", "fallback_to_self_source", [source_ref]
    if normalized_target == "all_enemies":
        target_party_id = event_target_party_id if event_target_party_id != source_party_id else next(
            (party_id for party_id in party_context_by_party.keys() if party_id != source_party_id),
            0,
        )
        refs = list_party_member_refs(party_context_by_party, target_party_id)
        return "all_enemies", "resolved_from_target_party_scan", refs
    if normalized_target == "enemy":
        if event_target_member:
            return "single_enemy", "resolved_from_event_target", [member_target_ref(event_target_member)]
        return "single_enemy", "unresolved_enemy_target", []
    if event_target_member:
        return "event_target_fallback", "resolved_from_event_target_fallback", [member_target_ref(event_target_member)]
    return "unresolved", "unresolved_no_target_context", []


def normalize_status_effects(skill_row: Dict[str, Any]) -> List[Dict[str, Any]]:
    payload: List[Dict[str, Any]] = []
    for raw_effect in list_value(skill_row.get("effects")):
        effect = dict_value(raw_effect)
        effect_type = string_value(effect.get("effect_type")).strip().lower()
        if not effect_type:
            continue
        target = string_value(effect.get("target")).strip().lower()
        category = effect_category(effect_type, target)
        payload.append(
            {
                "effect_type": effect_type,
                "category": category,
                "action": effect_action(effect_type, category),
                "target": target,
                "duration": nullable_int(effect.get("duration")),
                "chance": effect.get("chance"),
                "effect_value": effect.get("effect_value"),
                "condition_text": string_value(effect.get("condition_text")).strip(),
                "resolution": "candidate_from_skill_metadata",
            }
        )
    return payload


def build_timeline_row(
    *,
    event_index: int,
    source_party_id: int,
    source_slot: int,
    source_member: Dict[str, Any],
    target_party_id: int,
    target_slot: int,
    raw_skill_code: Any,
    skill_order: int | None,
    skill_row: Dict[str, Any],
    status_effects: List[Dict[str, Any]],
) -> Dict[str, Any]:
    skill_code = str(int_value(raw_skill_code)) if int_value(raw_skill_code) > 0 else string_value(raw_skill_code).strip()
    source_role = string_value(source_member.get("party_role")).strip() or "unknown"
    timeline_kind = "player_skill_cast" if source_role == "player" else "enemy_skill_cast"
    if status_effects:
        timeline_kind = "effect_candidate_cast"
    action_result = "raw_skill_cast"
    if source_role == "player" and skill_order is not None:
        action_result = "cast_skill_no_effect_candidates"
    if status_effects:
        action_result = "cast_skill_with_effect_candidates"
    skill_slot = string_value(skill_row.get("slot")).strip()
    if not skill_slot and skill_order is not None and skill_order > 0:
        skill_slot = f"A{skill_order}"
    skill_name = string_value(skill_row.get("skill_name")).strip()
    if not skill_name:
        skill_name = skill_code or "unknown_skill"
    return {
        "event_index": event_index,
        "turn_event": True,
        "timeline_kind": timeline_kind,
        "action_result": action_result,
        "source_party_id": source_party_id,
        "source_party_role": source_role,
        "source_slot": source_slot,
        "source_name": string_value(source_member.get("champion_name")),
        "source_type_id": int_value(source_member.get("champion_type_id")),
        "target_party_id": target_party_id,
        "target_slot": target_slot,
        "skill_code": skill_code,
        "skill_order": skill_order,
        "skill_slot": skill_slot,
        "skill_name": skill_name,
        "skill_type": string_value(skill_row.get("skill_type")),
        "skill_provider": string_value(skill_row.get("provider")),
        "description_clean": string_value(skill_row.get("description_clean")),
        "status_effects": status_effects,
    }


def annotate_turn_context(timeline: List[Dict[str, Any]]) -> None:
    source_turn_counts: Counter[tuple[int, int]] = Counter()
    party_turn_counts: Counter[int] = Counter()
    enemy_positions: List[int] = []

    for position, row in enumerate(timeline, start=1):
        source_key = (int_value(row.get("source_party_id")), int_value(row.get("source_slot")))
        source_turn_counts[source_key] += 1
        party_id = int_value(row.get("source_party_id"))
        party_turn_counts[party_id] += 1
        row["timeline_index"] = position
        row["source_turn_index"] = source_turn_counts[source_key]
        row["source_party_turn_index"] = party_turn_counts[party_id]
        row["turn_timeline_status"] = "turn_based_skill_cast_sequence_no_skip_resolution"
        if string_value(row.get("source_party_role")) == "enemy":
            enemy_positions.append(position)

    for position, row in enumerate(timeline, start=1):
        insert_at = bisect.bisect_left(enemy_positions, position)
        previous_enemy_pos = enemy_positions[insert_at - 1] if insert_at > 0 else None
        upcoming_enemy_pos = None
        if insert_at < len(enemy_positions):
            upcoming_enemy_pos = enemy_positions[insert_at]
        previous_enemy_turn_index = insert_at
        upcoming_enemy_turn_index = insert_at + 1 if upcoming_enemy_pos is not None else None

        row["previous_enemy_turn_index"] = previous_enemy_turn_index
        row["upcoming_enemy_turn_index"] = upcoming_enemy_turn_index
        row["actions_since_previous_enemy_turn"] = position - previous_enemy_pos - 1 if previous_enemy_pos is not None else position - 1
        row["actions_until_upcoming_enemy_turn"] = upcoming_enemy_pos - position if upcoming_enemy_pos is not None else None
        row["turn_window_index"] = previous_enemy_turn_index + 1
        row["is_enemy_turn"] = string_value(row.get("source_party_role")) == "enemy"
        if row["is_enemy_turn"]:
            row["enemy_turn_index"] = upcoming_enemy_turn_index
            row["boss_turn_anchor"] = f"enemy_turn_{upcoming_enemy_turn_index}"
        else:
            row["enemy_turn_index"] = None
            row["boss_turn_anchor"] = f"before_enemy_turn_{upcoming_enemy_turn_index}" if upcoming_enemy_turn_index is not None else "after_last_enemy_turn"


def extract_effect_timeline(
    path: Path,
    hero_types_path: Path = HH_HERO_TYPES_PATH,
    provider_order: Sequence[str] = DEFAULT_PROVIDER_ORDER,
) -> Dict[str, Any]:
    root = decode_battle_results_root(path)
    player_party_id = int_value(dict_value(dict_value(root.get("s")).get("f")).get("i"))
    members_by_slot = build_member_context_by_slot(path, hero_types_path=hero_types_path)
    party_context_by_party = build_party_context_by_party(path, hero_types_path=hero_types_path)
    skill_catalog_by_slot, provider_by_champion = resolve_skill_catalog_by_slot(members_by_slot, provider_order=provider_order)

    timeline: List[Dict[str, Any]] = []
    all_events = list_value(dict_value(root.get("r")).get("c"))
    for event_index, raw_event in enumerate(all_events):
        event = dict_value(raw_event)
        state = dict_value(event.get("s"))
        source = dict_value(state.get("p"))
        target = dict_value(state.get("t"))
        source_party_id = int_value(source.get("p"))
        source_slot = int_value(source.get("h"))
        member = dict_value(dict_value(party_context_by_party.get(source_party_id)).get(source_slot))
        if not member:
            continue

        skill_order = decode_skill_order_from_event_code(state.get("s"), member.get("champion_type_id"))
        target_party_id = int_value(target.get("p"))
        target_slot = int_value(target.get("h"))
        skill_row: Dict[str, Any] = {}
        if source_party_id == player_party_id and skill_order is not None:
            skill_row = dict_value(dict_value(skill_catalog_by_slot.get(source_slot)).get(skill_order))

        status_effects = normalize_status_effects(skill_row) if skill_row else []
        resolved_status_effects: List[Dict[str, Any]] = []
        for effect in status_effects:
            effect_scope, target_resolution, candidate_targets = resolve_effect_candidate_targets(
                effect,
                source_member=member,
                event_target_party_id=target_party_id,
                event_target_slot=target_slot,
                party_context_by_party=party_context_by_party,
            )
            resolved_status_effects.append(
                {
                    **effect,
                    "target_scope": effect_scope,
                    "target_resolution": target_resolution,
                    "candidate_target_count": len(candidate_targets),
                    "candidate_targets": candidate_targets,
                }
            )

        if skill_order is None and int_value(state.get("s")) <= 0:
            continue

        timeline.append(
            build_timeline_row(
                event_index=event_index,
                source_party_id=source_party_id,
                source_slot=source_slot,
                source_member=member,
                target_party_id=target_party_id,
                target_slot=target_slot,
                raw_skill_code=state.get("s"),
                skill_order=skill_order,
                skill_row=skill_row,
                status_effects=resolved_status_effects,
            )
        )

    annotate_turn_context(timeline)

    effect_totals = Counter()
    status_timeline_count = 0
    enemy_skill_event_count = 0
    for row in timeline:
        if string_value(row.get("source_party_role")) == "enemy":
            enemy_skill_event_count += 1
        if list_value(row.get("status_effects")):
            status_timeline_count += 1
        for effect in list_value(row.get("status_effects")):
            effect_totals[string_value(dict_value(effect).get("effect_type"))] += 1

    return {
        "battle_id": string_value(dict_value(root.get("p")).get("z")).strip(),
        "source_path": str(path),
        "player_party_id": player_party_id,
        "event_count": len(all_events),
        "timeline_count": len(timeline),
        "status_timeline_count": status_timeline_count,
        "enemy_skill_event_count": enemy_skill_event_count,
        "status_timeline_status": "candidate_from_cast_order_plus_skill_metadata",
        "provider_order": list(provider_order),
        "provider_by_champion": provider_by_champion,
        "members": [members_by_slot[key] for key in sorted(members_by_slot)],
        "effect_totals": dict(sorted(effect_totals.items())),
        "timeline": timeline,
    }


def main(argv: Iterable[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Estrae una timeline buff/debuff candidate da battleResults.")
    parser.add_argument("--raw", required=True, help="Path al file battleResults .bin")
    parser.add_argument(
        "--providers",
        default=",".join(DEFAULT_PROVIDER_ORDER),
        help="Ordine provider separato da virgole. Default: local_registry,ayumilove",
    )
    parser.add_argument(
        "--hero-types",
        default=str(HH_HERO_TYPES_PATH),
        help="Path a hh_hero_types.json per risolvere i type_id in nomi campione.",
    )
    args = parser.parse_args(list(argv) if argv is not None else None)

    provider_order = [item.strip() for item in string_value(args.providers).split(",") if item.strip()]
    payload = extract_effect_timeline(
        Path(args.raw),
        hero_types_path=Path(args.hero_types),
        provider_order=provider_order or list(DEFAULT_PROVIDER_ORDER),
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
