from __future__ import annotations

from pathlib import Path

import cb_battle_results

from cb_battle_results import extract_damage_summary, read_battle_result_payload


def test_extract_damage_summary_prefers_named_champion_rows() -> None:
    decoded = {
        "results": [
            {"name": "Coldheart", "damageDone": 1234567},
            {"name": "Heiress", "damageDone": 765432},
        ],
        "totalDamage": 1999999,
    }

    summary = extract_damage_summary(decoded, ["Coldheart", "Heiress"])

    assert summary["total_damage"] == 1999999.0
    assert summary["damage_by_champion"] == [
        {"path": "$.results[0]", "name": "Coldheart", "damage": 1234567.0},
        {"path": "$.results[1]", "name": "Heiress", "damage": 765432.0},
    ]


def test_extract_damage_summary_prefers_uncompressed_structured_payload() -> None:
    decoded = {
        "decoded": [{"binary_length": 11}],
        "decoded_uncompressed": {
            "decode_offset": 1,
            "remaining_bytes": 0,
            "decoded": {
                "p": {
                    "f": {
                        "h": [
                            {"i": 4786, "h": 10771},
                            {"i": 5836, "h": 13041},
                            {"i": 6206, "h": 5996},
                        ]
                    }
                },
                "s": {
                    "f": {
                        "h": [
                            {"t": 4786, "u": 10771, "ad": {"2004": 42949672960}},
                            {"t": 5836, "u": 13041, "ad": {}},
                            {"t": 6206, "u": 5996, "ad": {"2004": 21474836480}},
                        ]
                    }
                },
            },
        },
    }

    summary = extract_damage_summary(decoded, ["Coldheart", "Heiress", "Ninja"])

    assert summary["total_damage"] == 15.0
    assert summary["source"] == "structured_battle_result"
    assert summary["damage_by_champion"] == [
        {
            "path": "$.s.f.h[0].ad.2004",
            "name": "Coldheart",
            "damage": 10.0,
            "raw_value": 42949672960,
            "source_field": "ad.2004",
            "confidence": "medium",
        },
        {
            "path": "$.s.f.h[1].ad.2004",
            "name": "Heiress",
            "damage": 0.0,
            "raw_value": 0,
            "source_field": "ad.2004",
            "confidence": "medium",
        },
        {
            "path": "$.s.f.h[2].ad.2004",
            "name": "Ninja",
            "damage": 5.0,
            "raw_value": 21474836480,
            "source_field": "ad.2004",
            "confidence": "medium",
        },
    ]


def test_extract_damage_summary_falls_back_to_h_when_ad_missing() -> None:
    decoded = {
        "decoded_uncompressed": {
            "decoded": {
                "p": {
                    "f": {
                        "h": [
                            {"i": 4786, "h": 10771},
                            {"i": 5836, "h": 13041},
                        ]
                    }
                },
                "s": {
                    "f": {
                        "h": [
                            {"t": 4786, "u": 10771, "h": 42949672960, "dt": 21474836480},
                            {"t": 5836, "u": 13041, "h": 21474836480, "dt": 42949672960},
                        ]
                    }
                },
            }
        }
    }

    summary = extract_damage_summary(decoded, ["Coldheart", "Heiress"])

    assert summary["total_damage"] == 15.0
    assert summary["confidence"] == "heuristic"
    assert summary["damage_by_champion"] == [
        {
            "path": "$.s.f.h[0].h",
            "name": "Coldheart",
            "damage": 10.0,
            "raw_value": 42949672960,
            "source_field": "h",
            "confidence": "heuristic",
        },
        {
            "path": "$.s.f.h[1].h",
            "name": "Heiress",
            "damage": 5.0,
            "raw_value": 21474836480,
            "source_field": "h",
            "confidence": "heuristic",
        },
    ]


def test_extract_damage_summary_uses_type_name_map_when_preferred_names_missing(monkeypatch) -> None:
    decoded = {
        "decoded_uncompressed": {
            "decoded": {
                "p": {
                    "f": {
                        "h": [
                            {"i": 4786, "h": 10771},
                            {"i": 5836, "h": 13041},
                        ]
                    }
                },
                "s": {
                    "f": {
                        "h": [
                            {"t": 4786, "u": 10771, "h": 42949672960},
                            {"t": 5836, "u": 13041, "h": 21474836480},
                        ]
                    }
                },
            }
        }
    }
    monkeypatch.setattr(
        cb_battle_results,
        "load_champion_type_name_map",
        lambda path=cb_battle_results.RAW_ACCOUNT_PATH: {4786: "Coldheart", 5836: "Heiress"},
    )

    summary = extract_damage_summary(decoded, [])

    assert summary["damage_by_champion"] == [
        {
            "path": "$.s.f.h[0].h",
            "name": "Coldheart",
            "damage": 10.0,
            "raw_value": 42949672960,
            "source_field": "h",
            "confidence": "heuristic",
        },
        {
            "path": "$.s.f.h[1].h",
            "name": "Heiress",
            "damage": 5.0,
            "raw_value": 21474836480,
            "source_field": "h",
            "confidence": "heuristic",
        },
    ]


def test_read_battle_result_payload_skips_payload_by_default(tmp_path: Path) -> None:
    path = tmp_path / "battleResults"
    path.write_bytes(b"abc123")

    payload = read_battle_result_payload(path)

    assert payload["exists"] is True
    assert payload["size"] == 6
    assert payload["payload"] is None


def test_read_battle_result_payload_can_include_payload(tmp_path: Path) -> None:
    path = tmp_path / "battleResults"
    path.write_bytes(b"abc123")

    payload = read_battle_result_payload(path, include_payload=True)

    assert payload["payload"] == b"abc123"
