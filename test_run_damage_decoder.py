from __future__ import annotations

from pathlib import Path

import pytest

import battle_event_decoder
import run_damage_decoder
from run_damage_decoder import (
    FIXED_POINT_32_SCALE,
    build_manual_result_metrics_dataset,
    build_skill_training_view,
    compare_battle_results_skill_blocks,
    decode_metric_high32,
    detect_battle_id_from_meta_payload,
    extract_damage_summary,
    extract_member_result_rows,
    filter_skill_block_comparison_report,
    inspect_battle_results_payload,
    index_rich_battle_result_assets,
    latest_rich_battle_result_paths,
    parse_manual_battle_damage_notes,
    pearson_correlation,
    rank_member_composite_metric_candidates,
    rank_member_metric_candidates,
    summarize_battle_event_log,
    summarize_member_skill_blocks,
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


def test_extract_damage_summary_reads_demon_lord_total_damage_candidate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        run_damage_decoder,
        "decode_battle_results_root",
        lambda path: {
            "p": {"i": "4019021", "z": "battle-1", "f": {"h": [{}]}},
            "s": {
                "a": {"dt": 45_621_541 * FIXED_POINT_32_SCALE},
                "f": {
                    "h": [
                        {"i": 0, "t": 3666, "dt": 119_943 * FIXED_POINT_32_SCALE, "ad": {"2004": 1_441_193 * (2**29)}},
                        {"i": 1, "t": 2166, "dt": 176_992 * FIXED_POINT_32_SCALE, "r": {"m": 3_607_101 * (2**10)}},
                        {"i": 2, "t": 6206, "dt": 117_565 * FIXED_POINT_32_SCALE, "w": {"bf": {"d": 19_660_800 * (2**17)}}},
                        {"i": 3, "t": 5836, "dt": 161_248 * FIXED_POINT_32_SCALE, "w": {"bf": {"a": 12_288_000 * (2**18)}}},
                        {"i": 4, "t": 4496, "dt": 178_375 * FIXED_POINT_32_SCALE, "r": {"m": 5_934_940 * (2**11)}},
                    ]
                },
            },
        },
    )

    summary = extract_damage_summary(tmp_path / "sample.bin")

    assert summary["battle_id"] == "battle-1"
    assert summary["total_damage"] == 45_621_541
    assert summary["total_damage_status"] == "candidate_demon_lord_s_a_dt_high32"
    assert summary["member_damage_status"] == "candidate_demon_lord_manual_fit_normalized_total"
    assert summary["damage_trusted"] is False
    assert summary["damage_taken_trusted"] is False
    assert summary["members"][2]["damage_taken"] == 117_565
    assert summary["members"][2]["damage_taken_status"] == "candidate_member_dt_high32_clan_boss"
    assert summary["members"][2]["damage_done"] > 19_000_000
    assert sum(int(member["damage_done"] or 0) for member in summary["members"]) == 45_621_541


def test_extract_damage_summary_keeps_non_clan_boss_damage_taken_trusted(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        run_damage_decoder,
        "decode_battle_results_root",
        lambda path: {
            "p": {
                "i": "2062010",
                "z": "battle-2",
                "f": {"h": [{}]},
            },
            "s": {
                "f": {
                    "h": [
                        {"i": 0, "t": 6206, "dt": 58_334 * FIXED_POINT_32_SCALE},
                    ]
                }
            },
        }
    )

    summary = extract_damage_summary(tmp_path / "sample.bin")

    assert summary["damage_taken_trusted"] is True
    assert summary["damage_taken_status"] == "trusted_member_dt_high32"
    assert summary["members"][0]["damage_taken_status"] == "trusted_member_dt_high32"


def test_summarize_battle_event_log_counts_parties_and_non_null_blocks(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        run_damage_decoder,
        "decode_battle_results_root",
        lambda path: {
            "r": {
                "v": 12345,
                "r": 7,
                "c": [
                    {"t": 0, "s": {"p": {"p": 10}, "t": {"p": -1}}, "c": None, "f": None},
                    {"t": 1, "s": {"p": {"p": -1}, "t": {"p": 10}}, "c": {"delta": 1}, "f": None},
                    {"t": 1, "s": {"p": {"p": 10}, "t": {"p": 10}}, "c": None, "f": {"flag": True}},
                ]
            }
        },
    )

    summary = summarize_battle_event_log(tmp_path / "sample.bin")

    assert summary["event_count"] == 3
    assert summary["event_type_counts"] == {0: 1, 1: 2}
    assert summary["source_party_counts"] == {-1: 1, 10: 2}
    assert summary["target_party_counts"] == {-1: 1, 10: 2}
    assert summary["non_null_c_count"] == 1
    assert summary["non_null_f_count"] == 1
    assert summary["raw_r_v"] == 12345
    assert summary["raw_r_r"] == 7


def test_summarize_member_skill_blocks_merges_event_usage_counts() -> None:
    member_row = {
        "champion_type_id": 6206,
        "member_payload": {
            "k": [
                {"t": 62001, "l": True, "c": 1, "m": 2, "x": 3, "r": 4, "a": 5, "h": 6, "s": 7, "ir": 8, "y": 9, "i": False, "d": False},
                {"t": 3000012, "l": False, "c": 0, "m": 0, "x": 0, "r": 0, "a": 0, "h": 0, "s": 0, "ir": 0, "y": 1, "i": False, "d": False},
            ]
        },
    }

    rows = summarize_member_skill_blocks(member_row, event_skill_usage_counts={"A1": 4})

    assert rows[0]["skill_slot"] == "A1"
    assert rows[0]["event_usage_count"] == 4
    assert rows[0]["x"] == 3
    assert rows[1]["skill_slot"] == ""
    assert rows[1]["skill_order"] is None


def test_pearson_correlation_returns_none_for_flat_series() -> None:
    assert pearson_correlation([1, 1, 1], [2, 3, 4]) is None
    assert pearson_correlation([1], [1]) is None
    assert pearson_correlation([1, 2, 3], [2, 4, 6]) == pytest.approx(1.0)


def test_compare_battle_results_skill_blocks_groups_skill_rows(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    reports = {
        str(tmp_path / "input" / "client_probe" / "session-a" / "snapshots" / "battle_results" / "a.bin"): {
            "battle_id": "battle-a",
            "stage_id": "4019021",
            "duration_seconds_candidate": 120.0,
            "event_log": {"event_count": 10},
            "members": [
                {
                    "member_order": 1,
                    "champion_type_id": 6206,
                    "slot_index": 0,
                    "damage_taken": 100,
                    "damage_taken_status": "candidate",
                    "incoming_target_events": 5,
                    "incoming_boss_target_events": 4,
                    "skill_blocks": [
                        {"skill_code": 62001, "skill_order": 1, "skill_slot": "A1", "enabled": True, "internal_i": False, "internal_d": False, "event_usage_count": 7, "c": 1, "m": 0, "x": 11, "r": 0, "a": 0, "h": 0, "s": 0, "ir": 0, "y": 0}
                    ],
                }
            ],
        },
        str(tmp_path / "input" / "client_probe" / "session-b" / "snapshots" / "battle_results" / "b.bin"): {
            "battle_id": "battle-b",
            "stage_id": "4019021",
            "duration_seconds_candidate": 130.0,
            "event_log": {"event_count": 12},
            "members": [
                {
                    "member_order": 1,
                    "champion_type_id": 6206,
                    "slot_index": 0,
                    "damage_taken": 120,
                    "damage_taken_status": "candidate",
                    "incoming_target_events": 6,
                    "incoming_boss_target_events": 5,
                    "skill_blocks": [
                        {"skill_code": 62001, "skill_order": 1, "skill_slot": "A1", "enabled": True, "internal_i": False, "internal_d": False, "event_usage_count": 9, "c": 2, "m": 0, "x": 15, "r": 0, "a": 0, "h": 0, "s": 0, "ir": 0, "y": 0}
                    ],
                }
            ],
        },
    }

    monkeypatch.setattr(
        run_damage_decoder,
        "inspect_battle_results_payload",
        lambda path: reports[str(path)],
    )

    comparison = compare_battle_results_skill_blocks([Path(path) for path in reports])

    assert comparison["run_count"] == 2
    assert comparison["skill_sample_count"] == 2
    assert len(comparison["skill_groups"]) == 1
    assert comparison["skill_groups"][0]["champion_type_id"] == 6206
    assert comparison["skill_groups"][0]["skill_code"] == 62001
    assert comparison["skill_groups"][0]["event_usage_correlations"]["x"] == pytest.approx(1.0)
    assert comparison["skill_groups"][0]["best_event_usage_abs_correlation"] == pytest.approx(1.0)
    assert comparison["skill_groups"][0]["samples"][0]["session_slug"] == "session-a"


def test_latest_rich_battle_result_paths_skips_placeholder_files(tmp_path: Path) -> None:
    session_root = tmp_path / "input" / "client_probe" / "session-1" / "snapshots" / "battle_results"
    session_root.mkdir(parents=True)
    rich_meta = session_root / "rich.json"
    rich_bin = session_root / "rich.bin"
    rich_bin.write_bytes(b"rich")
    rich_meta.write_text('{"marker": {"size": 100}}', encoding="utf-8")

    placeholder_meta = session_root / "placeholder.json"
    placeholder_bin = session_root / "placeholder.bin"
    placeholder_bin.write_bytes(b"placeholder")
    placeholder_meta.write_text('{"marker": {"size": 11}}', encoding="utf-8")

    latest = latest_rich_battle_result_paths(tmp_path / "input" / "client_probe", limit=5)

    assert latest == [rich_bin]


def test_filter_skill_block_comparison_report_applies_cli_style_filters() -> None:
    report = {
        "skill_groups": [
            {"skill_slot": "A1", "sample_count": 3, "samples": [{"a": 1}]},
            {"skill_slot": "A4", "sample_count": 2, "samples": [{"a": 2}]},
            {"skill_slot": "A2", "sample_count": 1, "samples": [{"a": 3}]},
        ]
    }

    filtered = filter_skill_block_comparison_report(
        report,
        min_samples=2,
        skill_slots=["A1", "A2", "A3"],
        max_groups=1,
        include_samples=False,
    )

    assert filtered["filtered_skill_group_count"] == 1
    assert filtered["skill_groups"] == [{"skill_slot": "A1", "sample_count": 3}]
    assert filtered["filter"] == {
        "min_samples": 2,
        "skill_slots": ["A1", "A2", "A3"],
        "max_groups": 1,
        "include_samples": False,
    }


def test_build_skill_training_view_ranks_features_and_emits_rows() -> None:
    report = {
        "skill_groups": [
            {
                "champion_type_id": 6206,
                "skill_code": 62002,
                "skill_slot": "A2",
                "skill_order": 2,
                "sample_count": 3,
                "field_ranges": {
                    "x": {"distinct_values": [11, 21, 27]},
                    "c": {"distinct_values": [1, 3]},
                    "m": {"distinct_values": [3]},
                    "r": {"distinct_values": [1]},
                    "a": {"distinct_values": [1]},
                    "h": {"distinct_values": [0]},
                    "s": {"distinct_values": [0]},
                    "ir": {"distinct_values": [0]},
                    "y": {"distinct_values": [6]},
                    "damage_taken": {"distinct_values": [52096, 94439, 223896]},
                    "incoming_target_events": {"distinct_values": [0]},
                    "incoming_boss_target_events": {"distinct_values": [0]},
                },
                "event_usage_correlations": {
                    "x": 0.96,
                    "c": 0.91,
                    "m": None,
                    "r": None,
                    "a": None,
                    "h": None,
                    "s": None,
                    "ir": None,
                    "y": None,
                    "damage_taken": 0.98,
                    "incoming_target_events": None,
                    "incoming_boss_target_events": None,
                },
                "samples": [
                    {"battle_id": "b1", "stage_id": "4019024", "session_slug": "s1", "source_path": "p1", "member_order": 1, "event_usage_count": 7, "x": 11, "c": 1, "m": 3, "r": 1, "a": 1, "h": 0, "s": 0, "ir": 0, "y": 6, "damage_taken": 52096, "incoming_target_events": 0, "incoming_boss_target_events": 0},
                    {"battle_id": "b2", "stage_id": "4019024", "session_slug": "s2", "source_path": "p2", "member_order": 1, "event_usage_count": 9, "x": 21, "c": 1, "m": 3, "r": 1, "a": 1, "h": 0, "s": 0, "ir": 0, "y": 6, "damage_taken": 94439, "incoming_target_events": 0, "incoming_boss_target_events": 0},
                    {"battle_id": "b3", "stage_id": "4019024", "session_slug": "s3", "source_path": "p3", "member_order": 1, "event_usage_count": 12, "x": 27, "c": 3, "m": 3, "r": 1, "a": 1, "h": 0, "s": 0, "ir": 0, "y": 6, "damage_taken": 223896, "incoming_target_events": 0, "incoming_boss_target_events": 0},
                ],
            }
        ]
    }

    training_view = build_skill_training_view(report, include_rows=True, max_features_per_skill=3)

    assert training_view["target_label"] == "event_usage_count"
    assert training_view["sample_unit"] == "champion_skill_run"
    assert training_view["group_count"] == 1
    assert training_view["groups"][0]["recommended_primary_feature"] == "damage_taken"
    assert training_view["groups"][0]["recommended_feature_candidates"][1]["field"] == "x"
    assert "m" in training_view["groups"][0]["non_informative_fields"]
    assert training_view["row_count"] == 3
    assert training_view["rows"][0]["target_event_usage_count"] == 7
    assert training_view["rows"][0]["features"]["x"] == 11


def test_build_skill_training_view_uses_field_ranges_when_samples_are_omitted() -> None:
    report = {
        "skill_groups": [
            {
                "champion_type_id": 6206,
                "skill_code": 62002,
                "skill_slot": "A2",
                "skill_order": 2,
                "sample_count": 2,
                "field_ranges": {
                    "x": {"distinct_values": [21, 27]},
                    "c": {"distinct_values": [1, 3]},
                    "m": {"distinct_values": [3]},
                    "r": {"distinct_values": [1]},
                    "a": {"distinct_values": [1]},
                    "h": {"distinct_values": [0]},
                    "s": {"distinct_values": [0]},
                    "ir": {"distinct_values": [0]},
                    "y": {"distinct_values": [6]},
                    "damage_taken": {"distinct_values": [94439, 223896]},
                    "incoming_target_events": {"distinct_values": [0]},
                    "incoming_boss_target_events": {"distinct_values": [0]},
                },
                "event_usage_correlations": {
                    "x": 1.0,
                    "c": 1.0,
                    "m": None,
                    "r": None,
                    "a": None,
                    "h": None,
                    "s": None,
                    "ir": None,
                    "y": None,
                    "damage_taken": 1.0,
                    "incoming_target_events": None,
                    "incoming_boss_target_events": None,
                },
            }
        ]
    }

    training_view = build_skill_training_view(report, include_rows=False, max_features_per_skill=2)

    assert training_view["groups"][0]["recommended_primary_feature"] == "c"
    assert training_view["groups"][0]["recommended_feature_candidates"][1]["field"] == "damage_taken"


def test_inspect_battle_results_payload_merges_member_usage_and_incoming_counts(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        run_damage_decoder,
        "decode_battle_results_root",
        lambda path: {
            "p": {"z": "battle-42", "i": "2062010"},
            "r": {"v": 4500, "r": 3, "c": [{"t": 0, "s": {"p": {"p": 1}, "t": {"p": -1}}, "c": None, "f": None}]},
        },
    )
    monkeypatch.setattr(
        run_damage_decoder,
        "extract_member_result_rows",
        lambda path: [
            {
                "member_order": 1,
                "champion_type_id": 6206,
                "slot_index": 0,
                "damage_taken": 123,
                "member_payload": {"k": [{"t": 62001, "l": True, "c": 0, "m": 0, "x": 9, "r": 0, "a": 0, "h": 0, "s": 0, "ir": 0, "y": 5, "i": False, "d": False}]},
            }
        ],
    )
    monkeypatch.setattr(
        run_damage_decoder,
        "extract_damage_summary",
        lambda path: {
            "members": [{"member_order": 1, "damage_taken_status": "trusted_member_dt_high32"}],
            "damage_taken_trusted": True,
        },
    )
    monkeypatch.setattr(
        battle_event_decoder,
        "extract_skill_usage_counts",
        lambda path: [{"member_order": 1, "skill_usage_counts": {"A1": 4}, "raw_skill_codes": {"62001": 4}}],
    )
    monkeypatch.setattr(
        battle_event_decoder,
        "extract_incoming_target_counts",
        lambda path: [{"member_order": 1, "incoming_target_events": 7, "incoming_boss_target_events": 3, "incoming_boss_skill_codes": {"35001": 3}}],
    )

    report = inspect_battle_results_payload(tmp_path / "sample.bin")

    assert report["battle_id"] == "battle-42"
    assert report["stage_id"] == "2062010"
    assert report["duration_seconds_candidate"] == 4.5
    assert report["event_log"]["event_count"] == 1
    assert report["members"][0]["skill_usage_counts"] == {"A1": 4}
    assert report["members"][0]["incoming_boss_target_events"] == 3
    assert report["members"][0]["skill_blocks"][0]["event_usage_count"] == 4
