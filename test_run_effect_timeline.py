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
    monkeypatch.setattr(
        run_effect_timeline,
        "resolve_skill_catalog_by_slot",
        lambda member_context_by_slot, provider_order: (catalog_by_slot, {"Ninja": "ayumilove", "Stag Knight": "ayumilove"}),
    )

    payload = run_effect_timeline.extract_effect_timeline(tmp_path / "sample.bin")

    assert payload["battle_id"] == "battle-123"
    assert payload["status_timeline_count"] == 2
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
    assert [effect["category"] for effect in ninja_event["status_effects"]] == ["debuff", "buff"]
    assert [effect["action"] for effect in ninja_event["status_effects"]] == ["place", "place"]

    stag_event = payload["timeline"][1]
    assert stag_event["source_name"] == "Stag Knight"
    assert stag_event["skill_name"] == "Huntmaster"
    assert {effect["effect_type"] for effect in stag_event["status_effects"]} == {"decrease_def", "decrease_atk"}
