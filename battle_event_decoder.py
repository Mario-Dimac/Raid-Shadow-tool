from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from run_damage_decoder import decode_battle_results_root, dict_value, extract_member_result_rows, int_value, list_value


def decode_skill_order_from_event_code(raw_code: Any, champion_type_id: Any) -> int | None:
    code = int_value(raw_code)
    type_id = int_value(champion_type_id)
    if code <= 0 or type_id <= 0:
        return None
    if code // 100 != type_id // 10:
        return None
    skill_order = code % 100
    return skill_order if skill_order > 0 else None


def extract_skill_usage_counts(path: Path) -> List[Dict[str, Any]]:
    root = decode_battle_results_root(path)
    member_rows = extract_member_result_rows(path)
    player_party_id = int_value(dict_value(dict_value(root.get("s")).get("f")).get("i"))
    slot_to_member: Dict[int, Dict[str, Any]] = {}
    for row in member_rows:
        member = dict(row)
        resolved_slot = member.get("slot_index")
        if resolved_slot is None:
            resolved_slot = int_value(member.get("member_order")) - 1
        member["resolved_slot_index"] = resolved_slot
        member["skill_usage_counts"] = {}
        member["raw_skill_codes"] = {}
        slot_to_member[int_value(resolved_slot)] = member

    event_rows = list_value(dict_value(root.get("r")).get("c"))
    for event in event_rows:
        state = dict_value(dict_value(event).get("s"))
        source = dict_value(state.get("p"))
        if int_value(source.get("p")) != player_party_id:
            continue
        source_slot = int_value(source.get("h"))
        member = slot_to_member.get(source_slot)
        if not member:
            continue
        skill_order = decode_skill_order_from_event_code(state.get("s"), member.get("champion_type_id"))
        if skill_order is None:
            continue
        skill_key = f"A{skill_order}"
        member["skill_usage_counts"][skill_key] = int_value(member["skill_usage_counts"].get(skill_key)) + 1
        raw_code_key = str(int_value(state.get("s")))
        member["raw_skill_codes"][raw_code_key] = int_value(member["raw_skill_codes"].get(raw_code_key)) + 1

    return sorted(slot_to_member.values(), key=lambda row: int_value(row.get("member_order")))


def extract_incoming_target_counts(path: Path) -> List[Dict[str, Any]]:
    root = decode_battle_results_root(path)
    member_rows = extract_member_result_rows(path)
    player_party_id = int_value(dict_value(dict_value(root.get("s")).get("f")).get("i"))
    enemy_rows = list_value(dict_value(dict_value(root.get("s")).get("s")).get("h"))

    slot_to_member: Dict[int, Dict[str, Any]] = {}
    for row in member_rows:
        member = dict(row)
        resolved_slot = member.get("slot_index")
        if resolved_slot is None:
            resolved_slot = int_value(member.get("member_order")) - 1
        member["resolved_slot_index"] = resolved_slot
        member["incoming_target_events"] = 0
        member["incoming_boss_target_events"] = 0
        member["incoming_enemy_skill_codes"] = {}
        member["incoming_boss_skill_codes"] = {}
        slot_to_member[int_value(resolved_slot)] = member

    enemy_slot_to_row: Dict[int, Dict[str, Any]] = {}
    primary_enemy_slot: int | None = None
    for row in enemy_rows:
        enemy = dict_value(row)
        slot_index = int_value(enemy.get("i"))
        enemy_slot_to_row[slot_index] = enemy
        if primary_enemy_slot is None:
            primary_enemy_slot = slot_index

    event_rows = list_value(dict_value(root.get("r")).get("c"))
    for event in event_rows:
        state = dict_value(dict_value(event).get("s"))
        source = dict_value(state.get("p"))
        target = dict_value(state.get("t"))
        if int_value(target.get("p")) != player_party_id:
            continue
        if int_value(source.get("p")) == player_party_id:
            continue
        target_slot = int_value(target.get("h"))
        member = slot_to_member.get(target_slot)
        if not member:
            continue

        member["incoming_target_events"] = int_value(member.get("incoming_target_events")) + 1
        raw_code_key = str(int_value(state.get("s")))
        member["incoming_enemy_skill_codes"][raw_code_key] = int_value(member["incoming_enemy_skill_codes"].get(raw_code_key)) + 1

        source_slot = int_value(source.get("h"))
        if primary_enemy_slot is not None and source_slot == primary_enemy_slot:
            member["incoming_boss_target_events"] = int_value(member.get("incoming_boss_target_events")) + 1
            member["incoming_boss_skill_codes"][raw_code_key] = int_value(member["incoming_boss_skill_codes"].get(raw_code_key)) + 1

    return sorted(slot_to_member.values(), key=lambda row: int_value(row.get("member_order")))
