from __future__ import annotations

import json
from pathlib import Path

from game_data_probe import build_game_data_probe


def test_game_data_probe_summarizes_local_build_and_registry(tmp_path: Path) -> None:
    build_dir = tmp_path / "build"
    asset_bundles = build_dir / "Raid_Data" / "StreamingAssets" / "AssetBundles"
    asset_bundles.mkdir(parents=True)
    for name in ("HeroesInfoDialog", "SkillIcons_1500", "ArtifactsLocal", "BattleHUD"):
        (asset_bundles / name).mkdir()

    manifest_payload = {
        "options": {"buildId": "raid-build-123"},
        "chunks": [{"path": "AssetBundles/HeroesInfoDialog/11.20.0/file.unity3d"}],
    }
    (build_dir / "manifest.json").write_text(json.dumps(manifest_payload), encoding="utf-8")

    local_registry_path = tmp_path / "local_skill_registry.json"
    local_registry_path.write_text(
        json.dumps(
            {
                "version": 1,
                "champions": [
                    {
                        "champion_name": "Geomancer",
                        "skills": [
                            {
                                "skill_id": "geo_a1",
                                "cooldown": 0,
                                "booked_cooldown": 0,
                                "description_clean": "Attack one enemy.",
                                "type": "Basic",
                                "effects": [],
                            },
                            {
                                "skill_id": "geo_a2",
                                "cooldown": 3,
                                "booked_cooldown": 2,
                                "description_clean": "Places HP Burn.",
                                "type": "Active",
                                "effects": [{"effect_type": "hp_burn"}],
                            },
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    probe = build_game_data_probe(
        build_dir=build_dir,
        local_registry_path=local_registry_path,
        db_path=tmp_path / "missing.sqlite3",
    )

    assert probe["raid_build_exists"] is True
    assert probe["manifest"]["build_id"] == "raid-build-123"
    assert probe["manifest"]["content_version"] == "11.20.0"
    assert probe["asset_bundles"]["bundle_dir_count"] == 4
    assert "HeroesInfoDialog" in probe["asset_bundles"]["interesting_bundle_names"]
    assert "SkillIcons_1500" in probe["asset_bundles"]["skill_related_bundle_names"]
    assert "ArtifactsLocal" in probe["asset_bundles"]["local_bundle_names"]
    assert probe["local_skill_registry"]["champion_count"] == 1
    assert probe["local_skill_registry"]["skill_count"] == 2
    assert probe["local_skill_registry"]["skills_with_cooldown"] == 2
    assert probe["local_skill_registry"]["skills_with_booked_cooldown"] == 2
    assert probe["local_skill_registry"]["skills_with_description"] == 2
    assert probe["local_skill_registry"]["skills_with_type"] == 2
    assert probe["local_skill_registry"]["skills_with_effects"] == 1
    assert probe["db_report"] is None
