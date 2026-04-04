from __future__ import annotations

from local_game_bridge import build_team_equip_plan


def test_build_team_equip_plan_counts_ready_swaps_and_inventory() -> None:
    payload = {
        "team": [
            {
                "champion_name": "Ninja",
                "build_label": "CB DPS",
                "items": [
                    {"item_id": "n-weapon", "slot": "weapon", "source_kind": "current", "source_label": "Gia su Ninja"},
                    {"item_id": "shared-boots", "slot": "boots", "source_kind": "borrowed", "owner_name": "Jintoro", "source_label": "Da Jintoro"},
                    {"item_id": "free-helmet", "slot": "helmet", "source_kind": "inventory", "source_label": "Magazzino"},
                ],
            }
        ],
        "conflicts": [],
    }

    plan = build_team_equip_plan(payload)

    assert plan["provider"] == "local_manual"
    assert plan["ready_count"] == 1
    assert plan["swap_count"] == 1
    assert plan["free_equip_count"] == 1
    assert plan["action_count"] == 2
    assert plan["source_owners"] == ["Jintoro"]
    assert plan["member_blocks"][0]["action_count"] == 2
    assert plan["steps"][0]["action"] == "swap"
    assert plan["steps"][1]["action"] == "equip_free"
