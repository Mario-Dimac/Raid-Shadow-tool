from __future__ import annotations

from typing import Any, Dict, Iterable, List


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def build_team_equip_plan(team_loadout: Dict[str, Any]) -> Dict[str, Any]:
    payload = dict_value(team_loadout)
    team_rows = list_value(payload.get("team"))
    conflicts = list_value(payload.get("conflicts"))

    member_blocks: List[Dict[str, Any]] = []
    steps: List[Dict[str, Any]] = []
    source_owner_names: set[str] = set()
    ready_count = 0
    free_equip_count = 0
    swap_count = 0
    step_number = 1

    for member in team_rows:
        member_map = dict_value(member)
        member_name = string_value(member_map.get("champion_name")).strip()
        build_label = string_value(member_map.get("build_label") or member_map.get("default_build")).strip()
        block_steps: List[Dict[str, Any]] = []
        member_ready_count = 0
        member_swap_count = 0
        member_free_equip_count = 0

        for item in list_value(member_map.get("items")):
            item_map = dict_value(item)
            source_kind = string_value(item_map.get("source_kind")).strip().lower()
            if source_kind == "current":
                ready_count += 1
                member_ready_count += 1
                continue

            action = "swap" if source_kind == "borrowed" else "equip_free"
            source_name = string_value(item_map.get("owner_name") or item_map.get("equipped_by")).strip()
            if action == "swap":
                swap_count += 1
                member_swap_count += 1
                if source_name:
                    source_owner_names.add(source_name)
            else:
                free_equip_count += 1
                member_free_equip_count += 1

            step = {
                "step": step_number,
                "action": action,
                "member_name": member_name,
                "build_label": build_label,
                "slot": string_value(item_map.get("slot")),
                "item_id": string_value(item_map.get("item_id")),
                "set_name": string_value(item_map.get("set_name")),
                "rarity": string_value(item_map.get("rarity")),
                "rank": int_value(item_map.get("rank")),
                "level": int_value(item_map.get("level")),
                "source_name": source_name,
                "main_stat_type": string_value(item_map.get("main_stat_type")),
                "main_stat_value": item_map.get("main_stat_value"),
                "why": string_value(item_map.get("source_label")),
            }
            steps.append(step)
            block_steps.append(step)
            step_number += 1

        member_blocks.append(
            {
                "member_name": member_name,
                "build_label": build_label,
                "ready_count": member_ready_count,
                "free_equip_count": member_free_equip_count,
                "swap_count": member_swap_count,
                "action_count": len(block_steps),
                "steps": block_steps,
            }
        )

    action_count = len(steps)
    notes: List[str] = []
    if action_count == 0:
        notes.append("Team gia pronto: i pezzi consigliati risultano gia indossati dai campioni target.")
    else:
        notes.append(
            f"{action_count} azioni manuali: {swap_count} swap da altri campioni e {free_equip_count} pezzi liberi da montare."
        )
        if source_owner_names:
            notes.append(f"Campioni toccati dagli swap: {', '.join(sorted(source_owner_names))}.")
    if conflicts:
        notes.append("Conflitti presenti nel planner: alcuni pezzi sono richiesti da piu campioni del team.")

    return {
        "provider": "local_manual",
        "total_items": sum(len(list_value(dict_value(member).get("items"))) for member in team_rows),
        "ready_count": ready_count,
        "action_count": action_count,
        "free_equip_count": free_equip_count,
        "swap_count": swap_count,
        "source_owners": sorted(source_owner_names),
        "notes": notes,
        "member_blocks": member_blocks,
        "steps": steps,
        "conflicts": conflicts,
    }


def build_team_equip_plan_from_members(members: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    return build_team_equip_plan({"team": list(members), "conflicts": []})
