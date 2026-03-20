from __future__ import annotations

from cb_teams import (
    TeamMemberPlan,
    TeamRecommendation,
    assign_gear,
    available_bosses,
    build_assisted_swap_plan,
    build_recommendations,
    load_account,
    reconcile_loaded_account_ownership,
    serialize_team,
)


def test_available_bosses_exposes_main_targets() -> None:
    bosses = {boss["key"] for boss in available_bosses()}
    assert "demon_lord_unm" in bosses
    assert "hydra_normal" in bosses
    assert "dragon_hard" in bosses


def test_demon_lord_recommendations_include_detected_meta_core() -> None:
    account = load_account()
    options = build_recommendations(account, "demon_lord_unm")

    assert options
    best = options[0]
    best_names = {member.name for member in best.members}

    assert "Maneater" in best_names
    assert "Pain Keeper" in best_names
    assert len(best.members) == 5
    assert all(member.gear_plan for member in best.members)
    assert all(len(member.gear_plan) == 9 for member in best.members)
    assert any("equipped_by_name" in item for member in best.members for item in member.gear_plan)


def test_build_recommendations_deduplicates_same_member_set() -> None:
    account = load_account()
    options = build_recommendations(account, "demon_lord_unm")

    signatures = [tuple(sorted(member.champ_id for member in option.members)) for option in options]

    assert len(signatures) == len(set(signatures))


def test_demon_lord_recommendations_consider_supported_legendary_specialists() -> None:
    account = load_account()
    options = build_recommendations(account, "demon_lord_unm")

    recommended_names = {member.name for option in options for member in option.members}

    assert {"Teodor the Savant", "Valkyrie", "Jintoro"} & recommended_names


def test_build_assisted_swap_plan_counts_ready_free_and_swap_actions() -> None:
    member = TeamMemberPlan(
        champ_id="target-1",
        name="Ninja",
        build_key="clan_boss_dps",
        reason="Test plan",
        score=10.0,
        current_gear_count=9,
        gear_plan=[
            {"item_id": "100", "slot": "weapon", "set_name": "Attack Speed", "equipped_by": "target-1", "equipped_by_name": "Ninja", "why": "utility"},
            {"item_id": "101", "slot": "helmet", "set_name": "Accuracy And Speed", "equipped_by": None, "equipped_by_name": "", "why": "utility"},
            {"item_id": "102", "slot": "boots", "set_name": "Attack Speed", "equipped_by": "source-1", "equipped_by_name": "Geomancer", "needs_swap": True, "why": "damage / utility"},
        ],
    )
    team = TeamRecommendation(
        boss_key="demon_lord_unm",
        boss_label="Clan Boss",
        team_name="Test Assisted Swap",
        score=99.0,
        summary="Test",
        warnings=[],
        members=[member],
    )

    plan = build_assisted_swap_plan(team)

    assert plan["total_items"] == 3
    assert plan["ready_count"] == 1
    assert plan["action_count"] == 2
    assert plan["free_equip_count"] == 1
    assert plan["swap_count"] == 1
    assert plan["source_owners"] == ["Geomancer"]
    assert [step["action"] for step in plan["steps"]] == ["equip_free", "swap"]
    assert plan["member_blocks"][0]["action_count"] == 2


def test_serialize_team_includes_assisted_swap_plan() -> None:
    member = TeamMemberPlan(
        champ_id="target-1",
        name="Ninja",
        build_key="clan_boss_dps",
        reason="Test plan",
        score=10.0,
        current_gear_count=9,
        gear_plan=[
            {"item_id": "102", "slot": "boots", "set_name": "Attack Speed", "equipped_by": "source-1", "equipped_by_name": "Geomancer", "needs_swap": True, "why": "damage / utility"},
        ],
    )
    team = TeamRecommendation(
        boss_key="demon_lord_unm",
        boss_label="Clan Boss",
        team_name="Test Assisted Swap",
        score=99.0,
        summary="Test",
        warnings=[],
        members=[member],
    )

    payload = serialize_team(team)

    assert payload["swap_count"] == 1
    assert payload["swap_plan"]["swap_count"] == 1
    assert payload["swap_plan"]["steps"][0]["member_name"] == "Ninja"


def test_assign_gear_skips_accessories_from_wrong_faction() -> None:
    member = TeamMemberPlan(
        champ_id="target-1",
        name="Faction Target",
        build_key="clan_boss_dps",
        reason="Test plan",
        score=10.0,
        current_gear_count=0,
        faction="Orcs",
    )
    team = TeamRecommendation(
        boss_key="demon_lord_unm",
        boss_label="Clan Boss",
        team_name="Faction Safe Team",
        score=50.0,
        summary="Test",
        warnings=[],
        members=[member],
    )
    gear = [
        {
            "item_id": "wrong-ring",
            "slot": "ring",
            "item_class": "accessory",
            "set_name": "",
            "main_stat": {"type": "atk", "value": 500},
            "substats": [],
            "required_faction": "High Elves",
            "level": 16,
            "rank": 6,
        },
        {
            "item_id": "right-ring",
            "slot": "ring",
            "item_class": "accessory",
            "set_name": "",
            "main_stat": {"type": "atk", "value": 450},
            "substats": [],
            "required_faction": "Orcs",
            "level": 16,
            "rank": 6,
        },
        {
            "item_id": "unknown-banner",
            "slot": "banner",
            "item_class": "accessory",
            "set_name": "",
            "main_stat": {"type": "acc", "value": 96},
            "substats": [],
            "level": 16,
            "rank": 6,
        },
    ]

    assign_gear(team, gear, owner_names={}, owner_factions={})

    picked_ids = {item["item_id"] for item in member.gear_plan}
    assert "right-ring" in picked_ids
    assert "wrong-ring" not in picked_ids
    assert "unknown-banner" not in picked_ids


def test_assign_gear_can_infer_accessory_faction_from_current_owner() -> None:
    member = TeamMemberPlan(
        champ_id="target-1",
        name="Faction Target",
        build_key="clan_boss_dps",
        reason="Test plan",
        score=10.0,
        current_gear_count=0,
        faction="Orcs",
    )
    team = TeamRecommendation(
        boss_key="demon_lord_unm",
        boss_label="Clan Boss",
        team_name="Faction Safe Team",
        score=50.0,
        summary="Test",
        warnings=[],
        members=[member],
    )
    gear = [
        {
            "item_id": "owner-ring",
            "slot": "ring",
            "item_class": "accessory",
            "set_name": "",
            "main_stat": {"type": "atk", "value": 500},
            "substats": [],
            "equipped_by": "source-1",
            "level": 16,
            "rank": 6,
        },
    ]

    assign_gear(team, gear, owner_names={"source-1": "Old Owner"}, owner_factions={"source-1": "Orcs"})

    assert member.gear_plan[0]["item_id"] == "owner-ring"
    assert member.gear_plan[0]["required_faction"] == "Orcs"


def test_reconcile_loaded_account_ownership_repairs_missing_equipped_by() -> None:
    account = {
        "champions": [
            {
                "champ_id": "10578",
                "name": "Frozen Banshee",
                "equipped_item_ids": ["36281"],
            }
        ],
        "gear": [
            {
                "item_id": "36281",
                "slot": "weapon",
                "equipped_by": None,
            }
        ],
    }

    reconcile_loaded_account_ownership(account)

    assert account["gear"][0]["equipped_by"] == "10578"
