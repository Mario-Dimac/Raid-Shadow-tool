from __future__ import annotations

from pathlib import Path

import pytest

import run_damage_decoder
from run_damage_decoder import (
    FIXED_POINT_32_SCALE,
    build_manual_result_metrics_dataset,
    decode_metric_high32,
    detect_battle_id_from_meta_payload,
    extract_member_result_rows,
    index_rich_battle_result_assets,
    parse_manual_battle_damage_notes,
    rank_member_composite_metric_candidates,
    rank_member_metric_candidates,
)


def test_decode_metric_high32_extracts_blue_line_style_metric() -> None:
    raw_value = 58_334 * FIXED_POINT_32_SCALE + 123
    assert decode_metric_high32(raw_value) == 58_334


def test_parse_manual_battle_damage_notes_reads_sections_and_rows(tmp_path: Path) -> None:
    notes_path = tmp_path / "manual.md"
    notes_path.write_text(
        "\n".join(
            [
                "# Manual Battle Damage Notes",
                "",
                "## Battaglia `battle-1`",
                "",
                "Sessione probe: `session-1`.",
                "",
                "Stage ID probe: `2062010`.",
                "",
                "Encounter ricostruito dal recorder: `Dragon` (`void`).",
                "",
                "Contenuto osservato a schermo: `Dragon's Lair. Stage 10`.",
                "",
                "Nella battaglia `battle-1`, `Ninja` ha fatto `7,101,899` danni.",
                "Nella battaglia `battle-1`, `Valkyrie` ha fatto `895,599` danni.",
            ]
        ),
        encoding="utf-8",
    )

    notes = parse_manual_battle_damage_notes(notes_path)

    assert len(notes) == 1
    assert notes[0]["battle_id"] == "battle-1"
    assert notes[0]["session_slug"] == "session-1"
    assert notes[0]["stage_id"] == "2062010"
    assert notes[0]["encounter_name"] == "Dragon"
    assert notes[0]["encounter_affinity"] == "void"
    assert notes[0]["content_label"] == "Dragon's Lair. Stage 10"
    assert notes[0]["member_damage"] == [
        {"battle_id": "battle-1", "champion_name": "Ninja", "damage_done": 7_101_899},
        {"battle_id": "battle-1", "champion_name": "Valkyrie", "damage_done": 895_599},
    ]


def test_rank_member_metric_candidates_prefers_exact_high32_match() -> None:
    samples = [
        ({"dt": 10 * FIXED_POINT_32_SCALE + 11, "noise": 999}, 10),
        ({"dt": 25 * FIXED_POINT_32_SCALE + 77, "noise": 999}, 25),
        ({"dt": 7 * FIXED_POINT_32_SCALE + 3, "noise": 999}, 7),
    ]

    ranked = rank_member_metric_candidates(samples, tolerance_ratio=0.0)

    assert ranked[0]["path"] == "dt"
    assert ranked[0]["transform"] == "high32"
    assert ranked[0]["matches"] == 3


def test_rank_member_composite_metric_candidates_prefers_exact_sum_match() -> None:
    samples = [
        ({"w": {"f": {"a": 100, "d": 250, "noise": 7}}}, 350),
        ({"w": {"f": {"a": 200, "d": 50, "noise": 9}}}, 250),
        ({"w": {"f": {"a": 120, "d": 180, "noise": 11}}}, 300),
    ]

    ranked = rank_member_composite_metric_candidates(samples, tolerance_ratio=0.0)

    assert ranked[0]["path"] == "w.f[a+d]"
    assert ranked[0]["transform"] == "raw"
    assert ranked[0]["matches"] == 3


def test_detect_battle_id_from_meta_payload_prefers_reason_when_context_is_stale(tmp_path: Path) -> None:
    meta_payload = {
        "battle_context": {"battle_id": "wrong-battle-id"},
        "reason": "BattleResult added: [Id=correct-battle-id] TotalCount=1",
    }

    detected = detect_battle_id_from_meta_payload(meta_payload, meta_path=tmp_path / "snapshot.json")

    assert detected == "correct-battle-id"


def test_build_manual_result_metrics_dataset_uses_json_metrics_and_assets(tmp_path: Path) -> None:
    client_probe_root = tmp_path / "input" / "client_probe" / "session-1" / "snapshots" / "battle_results"
    client_probe_root.mkdir(parents=True)

    meta_path = client_probe_root / "sample.json"
    bin_path = client_probe_root / "sample.bin"
    bin_path.write_bytes(b"not-used-here")
    meta_path.write_text(
        """
        {
          "marker": {"size": 100},
          "battle_context": {"battle_id": "battle-1"},
          "reason": "BattleResult added: [Id=battle-1] TotalCount=1"
        }
        """,
        encoding="utf-8",
    )

    metrics_path = tmp_path / "metrics.json"
    metrics_path.write_text(
        """
        {
          "battles": [
            {
              "battle_id": "battle-1",
              "session_slug": "session-1",
              "members": []
            }
          ]
        }
        """,
        encoding="utf-8",
    )

    dataset = build_manual_result_metrics_dataset(metrics_path=metrics_path, client_probe_root=tmp_path / "input" / "client_probe")

    assert len(dataset) == 1
    assert dataset[0]["battle_id"] == "battle-1"
    assert dataset[0]["member_rows"] == []
    assert dataset[0]["manual_rows"] == []


def test_extract_member_result_rows_preserves_zero_slot_index(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        run_damage_decoder,
        "decode_battle_results_root",
        lambda path: {
            "s": {"f": {"h": [{"i": 0, "t": 6206, "dt": 3 * FIXED_POINT_32_SCALE}]}},
            "p": {"f": {"h": [{}]}},
        },
    )

    rows = extract_member_result_rows(tmp_path / "sample.bin")

    assert rows[0]["slot_index"] == 0
    assert rows[0]["damage_taken"] == 3
