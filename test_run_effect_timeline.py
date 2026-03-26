from __future__ import annotations

from pathlib import Path

import run_effect_timeline


def test_normalize_skill_row_extracts_effects_from_description() -> None:
    row = run_effect_timeline.normalize_skill_row(
        {
            "slot": "A2",
            "skill_order": 2,
            "name": "Stand Firm",
            "type": "Active",
            "cooldown": 4,
            "description": "Places a [Shield] buff on all allies for 3 turns and a [Counterattack] buff on all allies for 2 turns.",
            "books": ["Level 7: Cooldown -1"],
            "effects": [],
        },
        provider_name="ayumilove",
    )

    assert row["booked_cooldown"] == 3
    assert [effect["effect_type"] for effect in row["effects"]] == ["shield", "counterattack"]


def test_extract_effect_timeline_builds_candidate_status_rows(monkeypatch, tmp_path: Path) -> None:
    root = {
        "p": {"z": "battle-123"},
        "s": {"f": {"i": 83832666}},
        "r": {
            "c": [
                {"s": {"p": {"p": 83832666, "h": 0}, "t": {"p": -1, "h": 5}, "s": 62002}},
                {"s": {"p": {"p": 83832666, "h": 1}, "t": {"p": -1, "h": 5}, "s": 44902}},
                {"s": {"p": {"p": 83832666, "h": 0}, "t": {"p": -1, "h": 5}, "s": 62001}},
                {"s": {"p": {"p": -1, "h": 5}, "t": {"p": 83832666, "h": 0}, "s": 222603}},
            ]
        },
    }
    members_by_slot = {
        0: {"member_order": 1, "slot_index": 0, "champion_type_id": 6206, "champion_name": "Ninja"},
        1: {"member_order": 2, "slot_index": 1, "champion_type_id": 4496, "champion_name": "Stag Knight"},
    }
    party_context_by_party = {
        83832666: {
            0: {"member_order": 1, "slot_index": 0, "champion_type_id": 6206, "champion_name": "Ninja", "party_id": 83832666, "party_role": "player"},
            1: {"member_order": 2, "slot_index": 1, "champion_type_id": 4496, "champion_name": "Stag Knight", "party_id": 83832666, "party_role": "player"},
        },
        -1: {
            5: {"member_order": 6, "slot_index": 5, "champion_type_id": 22286, "champion_name": "Demon Lord", "party_id": -1, "party_role": "enemy"},
        },
    }
    catalog_by_slot = {
        0: {
            1: {
                "slot": "A1",
                "skill_order": 1,
                "skill_name": "Shatterbolt",
                "skill_type": "Basic",
                "provider": "ayumilove",
                "description_clean": "Attacks 1 enemy.",
                "effects": [],
            },
            2: {
                "slot": "A2",
                "skill_order": 2,
                "skill_name": "Hailburn",
                "skill_type": "Active",
                "provider": "ayumilove",
                "description_clean": "Places [HP Burn] and [Perfect Veil].",
                "effects": [
                    {"effect_type": "hp_burn", "target": "enemy", "duration": 3, "chance": 1.0, "effect_value": None},
                    {"effect_type": "perfect_veil", "target": "self", "duration": 2, "chance": None, "effect_value": None},
                ],
            },
        },
        1: {
            2: {
                "slot": "A2",
                "skill_order": 2,
                "skill_name": "Huntmaster",
                "skill_type": "Active",
                "provider": "ayumilove",
                "description_clean": "Places [Decrease DEF] and [Decrease ATK].",
                "effects": [
                    {"effect_type": "decrease_def", "target": "all_enemies", "duration": 2, "chance": 0.7, "effect_value": 60.0},
                    {"effect_type": "decrease_atk", "target": "all_enemies", "duration": 2, "chance": 0.7, "effect_value": 50.0},
                ],
            }
        },
    }

    monkeypatch.setattr(run_effect_timeline, "decode_battle_results_root", lambda path: root)
    monkeypatch.setattr(run_effect_timeline, "build_member_context_by_slot", lambda path, hero_types_path: members_by_slot)
    monkeypatch.setattr(run_effect_timeline, "build_party_context_by_party", lambda path, hero_types_path: party_context_by_party)
    monkeypatch.setattr(
        run_effect_timeline,
        "resolve_skill_catalog_by_slot",
        lambda member_context_by_slot, provider_order: (catalog_by_slot, {"Ninja": "ayumilove", "Stag Knight": "ayumilove"}),
    )

    payload = run_effect_timeline.extract_effect_timeline(tmp_path / "sample.bin")

    assert payload["battle_id"] == "battle-123"
    assert payload["timeline_count"] == 4
    assert payload["status_timeline_count"] == 2
    assert payload["enemy_skill_event_count"] == 1
    assert payload["provider_by_champion"] == {"Ninja": "ayumilove", "Stag Knight": "ayumilove"}
    assert payload["effect_totals"] == {
        "decrease_atk": 1,
        "decrease_def": 1,
        "hp_burn": 1,
        "perfect_veil": 1,
    }

    ninja_event = payload["timeline"][0]
    assert ninja_event["source_name"] == "Ninja"
    assert ninja_event["skill_name"] == "Hailburn"
    assert ninja_event["timeline_index"] == 1
    assert ninja_event["source_turn_index"] == 1
    assert ninja_event["upcoming_enemy_turn_index"] == 1
    assert ninja_event["actions_until_upcoming_enemy_turn"] == 3
    assert [effect["category"] for effect in ninja_event["status_effects"]] == ["debuff", "buff"]
    assert [effect["action"] for effect in ninja_event["status_effects"]] == ["place", "place"]
    assert ninja_event["status_effects"][0]["target_scope"] == "single_enemy"
    assert ninja_event["status_effects"][0]["candidate_targets"] == [
        {"party_id": -1, "party_role": "enemy", "slot_index": 5, "member_order": 6, "champion_type_id": 22286, "champion_name": "Demon Lord"}
    ]
    assert ninja_event["status_effects"][1]["target_scope"] == "self"
    assert ninja_event["status_effects"][1]["candidate_targets"] == [
        {"party_id": 83832666, "party_role": "player", "slot_index": 0, "member_order": 1, "champion_type_id": 6206, "champion_name": "Ninja"}
    ]

    stag_event = payload["timeline"][1]
    assert stag_event["source_name"] == "Stag Knight"
    assert stag_event["skill_name"] == "Huntmaster"
    assert stag_event["turn_window_index"] == 1
    assert {effect["effect_type"] for effect in stag_event["status_effects"]} == {"decrease_def", "decrease_atk"}
    assert {effect["target_scope"] for effect in stag_event["status_effects"]} == {"all_enemies"}
    assert all(effect["candidate_target_count"] == 1 for effect in stag_event["status_effects"])

    filler_event = payload["timeline"][2]
    assert filler_event["source_name"] == "Ninja"
    assert filler_event["timeline_kind"] == "player_skill_cast"
    assert filler_event["action_result"] == "cast_skill_no_effect_candidates"
    assert filler_event["skill_slot"] == "A1"
    assert filler_event["skill_name"] == "Shatterbolt"
    assert filler_event["status_effects"] == []

    boss_event = payload["timeline"][3]
    assert boss_event["source_name"] == "Demon Lord"
    assert boss_event["source_party_role"] == "enemy"
    assert boss_event["timeline_kind"] == "enemy_skill_cast"
    assert boss_event["action_result"] == "raw_skill_cast"
    assert boss_event["enemy_turn_index"] == 1
    assert boss_event["actions_until_upcoming_enemy_turn"] == 0
    assert boss_event["skill_code"] == "222603"
    assert boss_event["status_effects"] == []
