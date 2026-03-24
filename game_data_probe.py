from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from providers.local_registry_provider import LOCAL_SKILL_REGISTRY_PATH, load_local_skill_registry
from registry_report import build_registry_report


DEFAULT_RAID_BUILD_DIR = Path.home() / "AppData" / "Local" / "PlariumPlay" / "StandAloneApps" / "raid-shadow-legends" / "build"
DEFAULT_DB_PATH = Path(__file__).resolve().parent / "data" / "cbforge.sqlite3"
INTERESTING_BUNDLE_PATTERNS = ("hero", "skill", "leader", "info", "local", "string", "text", "lang")


def detect_content_version(manifest: Dict[str, Any]) -> Optional[str]:
    version_pattern = re.compile(r"/(\d+\.\d+\.\d+)/")
    for chunk in manifest.get("chunks", []):
        path = str(chunk.get("path", ""))
        match = version_pattern.search(path)
        if match:
            return match.group(1)
    return None


def load_manifest_summary(build_dir: Path) -> Dict[str, Any]:
    manifest_path = build_dir / "manifest.json"
    summary: Dict[str, Any] = {
        "path": str(manifest_path),
        "exists": manifest_path.exists(),
        "build_id": None,
        "content_version": None,
    }
    if not manifest_path.exists():
        return summary
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    summary["build_id"] = manifest.get("options", {}).get("buildId")
    summary["content_version"] = detect_content_version(manifest)
    return summary


def summarize_asset_bundles(build_dir: Path) -> Dict[str, Any]:
    bundle_root = build_dir / "Raid_Data" / "StreamingAssets" / "AssetBundles"
    summary: Dict[str, Any] = {
        "path": str(bundle_root),
        "exists": bundle_root.exists(),
        "bundle_dir_count": 0,
        "interesting_bundle_names": [],
        "skill_related_bundle_names": [],
        "local_bundle_names": [],
    }
    if not bundle_root.exists():
        return summary

    bundle_names = sorted(path.name for path in bundle_root.iterdir() if path.is_dir())
    summary["bundle_dir_count"] = len(bundle_names)
    summary["interesting_bundle_names"] = [
        name for name in bundle_names if any(pattern in name.lower() for pattern in INTERESTING_BUNDLE_PATTERNS)
    ][:40]
    summary["skill_related_bundle_names"] = [name for name in bundle_names if "skill" in name.lower()][:25]
    summary["local_bundle_names"] = [name for name in bundle_names if "local" in name.lower()][:25]
    return summary


def summarize_local_skill_registry(path: Path = LOCAL_SKILL_REGISTRY_PATH) -> Dict[str, Any]:
    payload = load_local_skill_registry(path)
    champions = [entry for entry in payload.get("champions", []) if isinstance(entry, dict)]
    skills = [
        skill
        for champion in champions
        for skill in champion.get("skills", [])
        if isinstance(skill, dict)
    ]

    return {
        "path": str(path),
        "exists": path.exists(),
        "champion_count": len(champions),
        "skill_count": len(skills),
        "skills_with_cooldown": sum(1 for skill in skills if skill.get("cooldown") is not None),
        "skills_with_booked_cooldown": sum(1 for skill in skills if skill.get("booked_cooldown") is not None),
        "skills_with_description": sum(1 for skill in skills if str(skill.get("description_clean") or skill.get("description") or "").strip()),
        "skills_with_type": sum(1 for skill in skills if str(skill.get("type") or skill.get("skill_type") or "").strip()),
        "skills_with_effects": sum(1 for skill in skills if list(skill.get("effects") or [])),
    }


def build_game_data_probe(
    build_dir: Path = DEFAULT_RAID_BUILD_DIR,
    local_registry_path: Path = LOCAL_SKILL_REGISTRY_PATH,
    db_path: Path = DEFAULT_DB_PATH,
) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "raid_build_dir": str(build_dir),
        "raid_build_exists": build_dir.exists(),
        "manifest": load_manifest_summary(build_dir),
        "asset_bundles": summarize_asset_bundles(build_dir),
        "local_skill_registry": summarize_local_skill_registry(local_registry_path),
        "db_report": None,
    }
    if db_path.exists():
        report = build_registry_report(db_path)
        summary["db_report"] = {
            "path": str(db_path),
            "registry_targets": report.get("registry_targets", 0),
            "registry_targets_ready": report.get("registry_targets_ready", 0),
            "registry_targets_with_effect_data": report.get("registry_targets_with_effect_data", 0),
            "registry_targets_ready_from_local_registry": report.get("registry_targets_ready_from_local_registry", 0),
            "registry_targets_ready_from_hellhades": report.get("registry_targets_ready_from_hellhades", 0),
            "skill_rows_from_local_registry": report.get("skill_rows_from_local_registry", 0),
            "skill_rows_from_hellhades": report.get("skill_rows_from_hellhades", 0),
            "targets_needing_data_count": len(report.get("targets_needing_data", [])),
            "targets_needing_effects_count": len(report.get("targets_needing_effects", [])),
            "last_sync_provider_hits": report.get("skill_registry_last_sync_provider_hits", {}),
        }
    return summary


def main() -> None:
    print(json.dumps(build_game_data_probe(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
