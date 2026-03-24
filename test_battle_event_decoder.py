from __future__ import annotations

from pathlib import Path

import pytest

import battle_event_decoder
from battle_event_decoder import decode_skill_order_from_event_code, extract_incoming_target_counts, extract_skill_usage_counts


def test_decode_skill_order_from_event_code_requires_matching_champion_type() -> None:
    assert decode_skill_order_from_event_code(62003, 6206) == 3
    assert decode_skill_order_from_event_code(62000, 6206) is None
    assert decode_skill_order_from_event_code(69003, 6206) is None


def test_extract_skill_usage_counts_groups_events_by_member_slot(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = {
        "s": {"f": {"i": 83832666}},
        "r": {
            "c": [
                {"s": {"p": {"p": 83832666, "h": 0}, "s": 62001}},
                {"s": {"p": {"p": 83832666, "h": 0}, "s": 62001}},
                {"s": {"p": {"p": 83832666, "h": 0}, "s": 62003}},
                {"s": {"p": {"p": 83832666, "h": 1}, "s": 69002}},
                {"s": {"p": {"p": -1, "h": 8}, "s": 99999}},
                {"s": {"p": {"p": 83832666, "h": 1}, "s": 62001}},
            ]
        },
    }
    member_rows = [
        {"member_order": 1, "champion_type_id": 6206, "slot_index": 0},
        {"member_order": 2, "champion_type_id": 6906, "slot_index": 1},
    ]

    monkeypatch.setattr(battle_event_decoder, "decode_battle_results_root", lambda path: root)
    monkeypatch.setattr(battle_event_decoder, "extract_member_result_rows", lambda path: member_rows)

    rows = extract_skill_usage_counts(tmp_path / "sample.bin")

    assert rows[0]["skill_usage_counts"] == {"A1": 2, "A3": 1}
    assert rows[0]["raw_skill_codes"] == {"62001": 2, "62003": 1}
    assert rows[1]["skill_usage_counts"] == {"A2": 1}
    assert rows[1]["raw_skill_codes"] == {"69002": 1}


def test_extract_incoming_target_counts_groups_enemy_targets_by_member_slot(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = {
        "s": {
            "f": {"i": 83832666},
            "s": {
                "h": [
                    {"i": 15, "t": 26486},
                    {"i": 5, "t": 3500},
                ]
            },
        },
        "r": {
            "c": [
                {"s": {"p": {"p": -1, "h": 15}, "t": {"p": 83832666, "h": 0}, "s": 264801}},
                {"s": {"p": {"p": -1, "h": 15}, "t": {"p": 83832666, "h": 0}, "s": 264802}},
                {"s": {"p": {"p": -1, "h": 5}, "t": {"p": 83832666, "h": 1}, "s": 35001}},
                {"s": {"p": {"p": 83832666, "h": 0}, "t": {"p": -1, "h": 15}, "s": 62001}},
            ]
        },
    }
    member_rows = [
        {"member_order": 1, "champion_type_id": 6206, "slot_index": 0},
        {"member_order": 2, "champion_type_id": 6906, "slot_index": 1},
    ]

    monkeypatch.setattr(battle_event_decoder, "decode_battle_results_root", lambda path: root)
    monkeypatch.setattr(battle_event_decoder, "extract_member_result_rows", lambda path: member_rows)

    rows = extract_incoming_target_counts(tmp_path / "sample.bin")

    assert rows[0]["incoming_target_events"] == 2
    assert rows[0]["incoming_boss_target_events"] == 2
    assert rows[0]["incoming_enemy_skill_codes"] == {"264801": 1, "264802": 1}
    assert rows[0]["incoming_boss_skill_codes"] == {"264801": 1, "264802": 1}
    assert rows[1]["incoming_target_events"] == 1
    assert rows[1]["incoming_boss_target_events"] == 0
    assert rows[1]["incoming_enemy_skill_codes"] == {"35001": 1}
