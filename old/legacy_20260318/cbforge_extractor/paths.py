from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / "input"
RAW_PATH = INPUT_DIR / "raw_account.json"

RAID_LOCALLOW = Path.home() / "AppData" / "LocalLow" / "Plarium" / "Raid_ Shadow Legends"
PLARIUM_LOCAL = Path.home() / "AppData" / "Local" / "PlariumPlay"
RAID_BUILD_DIR = PLARIUM_LOCAL / "StandAloneApps" / "raid-shadow-legends" / "build"
RAID_BUILD_LOG = RAID_BUILD_DIR / "log.txt"
RAID_MANIFEST = RAID_BUILD_DIR / "manifest.json"
RAID_EXECUTABLE = RAID_BUILD_DIR / "Raid.exe"

HELLHADES_INSTALL = Path.home() / "AppData" / "Roaming" / "HellHades Artifact Extractor"
HELLHADES_REFERENCE_DIR = BASE_DIR / "vendor" / "hellhades_reference"
