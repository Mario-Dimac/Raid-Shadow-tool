from __future__ import annotations

import sys
from pathlib import Path


LEGACY_DIR = Path(__file__).resolve().parent / "old" / "legacy_20260318"
if str(LEGACY_DIR) not in sys.path:
    sys.path.insert(0, str(LEGACY_DIR))

from cbforge_extractor.hellhades_bridge import convert_artifact  # type: ignore  # noqa: E402


def test_convert_artifact_maps_kind_8_to_amulet_and_accessory_bonus_types() -> None:
    artifact = convert_artifact(
        {
            "Id": 25944,
            "Kind": 8,
            "RequiredFraction": 5,
            "Set": 0,
            "Rank": 6,
            "Rarity": 5,
            "Level": 16,
            "PrimaryBonus": {"Kind": 8, "IsAbsolute": False, "Value": 0.4},
            "SecondaryBonuses": [
                {"Kind": 2, "IsAbsolute": True, "Value": 19, "Level": 0},
                {"Kind": 3, "IsAbsolute": True, "Value": 81, "Level": 3},
                {"Kind": 6, "IsAbsolute": True, "Value": 21, "Level": 1},
                {"Kind": 1, "IsAbsolute": True, "Value": 522, "Level": 0},
            ],
        },
        artifact_owner_map={"25944": "9170"},
    )

    assert artifact["slot"] == "amulet"
    assert artifact["main_stat"] == {"type": "crit_dmg", "value": 40.0}
    assert [sub["type"] for sub in artifact["substats"]] == ["atk", "def", "acc", "hp"]
    assert artifact["substats"][2]["value"] == 21.0


def test_convert_artifact_maps_kind_9_to_banner_and_accessory_bonus_types() -> None:
    artifact = convert_artifact(
        {
            "Id": 27391,
            "Kind": 9,
            "RequiredFraction": 5,
            "Set": 0,
            "Rank": 6,
            "Rarity": 4,
            "Level": 16,
            "PrimaryBonus": {"Kind": 6, "IsAbsolute": True, "Value": 96},
            "SecondaryBonuses": [
                {"Kind": 1, "IsAbsolute": False, "Value": 0.06, "Level": 0},
                {"Kind": 3, "IsAbsolute": True, "Value": 40, "Level": 1},
                {"Kind": 4, "IsAbsolute": True, "Value": 16, "Level": 2},
                {"Kind": 2, "IsAbsolute": False, "Value": 0.07, "Level": 0},
            ],
        },
        artifact_owner_map={},
    )

    assert artifact["slot"] == "banner"
    assert artifact["main_stat"] == {"type": "acc", "value": 96.0}
    assert [sub["type"] for sub in artifact["substats"]] == ["hp_pct", "def", "spd", "atk_pct"]
