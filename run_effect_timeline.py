from __future__ import annotations

import argparse
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


def extract_effect_timeline(
    path: Path,
    hero_types_path: Path = HH_HERO_TYPES_PATH,
    provider_order: Sequence[str] = DEFAULT_PROVIDER_ORDER,
) -> Dict[str, Any]:
    root = decode_battle_results_root(path)
    player_party_id = int_value(dict_value(dict_value(root.get("s")).get("f")).get("i"))
    members_by_slot = build_member_context_by_slot(path, hero_types_path=hero_types_path)
    skill_catalog_by_slot, provider_by_champion = resolve_skill_catalog_by_slot(members_by_slot, provider_order=provider_order)

    timeline: List[Dict[str, Any]] = []
    all_events = list_value(dict_value(root.get("r")).get("c"))
    for event_index, raw_event in enumerate(all_events):
        event = dict_value(raw_event)
        state = dict_value(event.get("s"))
        source = dict_value(state.get("p"))
        target = dict_value(state.get("t"))
        if int_value(source.get("p")) != player_party_id:
            continue

        source_slot = int_value(source.get("h"))
        member = dict_value(members_by_slot.get(source_slot))
        if not member:
            continue

        skill_order = decode_skill_order_from_event_code(state.get("s"), member.get("champion_type_id"))
        if skill_order is None:
            continue

        skill_row = dict_value(dict_value(skill_catalog_by_slot.get(source_slot)).get(skill_order))
        status_effects = normalize_status_effects(skill_row)
        if not status_effects:
            continue

        timeline.append(
            {
                "event_index": event_index,
                "source_party_id": int_value(source.get("p")),
                "source_slot": source_slot,
                "source_name": string_value(member.get("champion_name")),
                "source_type_id": int_value(member.get("champion_type_id")),
                "target_party_id": int_value(target.get("p")),
                "target_slot": int_value(target.get("h")),
                "skill_code": str(int_value(state.get("s"))),
                "skill_order": skill_order,
                "skill_slot": string_value(skill_row.get("slot")) or f"A{skill_order}",
                "skill_name": string_value(skill_row.get("skill_name")) or str(int_value(state.get("s"))),
                "skill_type": string_value(skill_row.get("skill_type")),
                "skill_provider": string_value(skill_row.get("provider")),
                "description_clean": string_value(skill_row.get("description_clean")),
                "status_effects": status_effects,
            }
        )

    effect_totals = Counter()
    for row in timeline:
        for effect in list_value(row.get("status_effects")):
            effect_totals[string_value(dict_value(effect).get("effect_type"))] += 1

    return {
        "battle_id": string_value(dict_value(root.get("p")).get("z")).strip(),
        "source_path": str(path),
        "player_party_id": player_party_id,
        "event_count": len(all_events),
        "status_timeline_count": len(timeline),
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
