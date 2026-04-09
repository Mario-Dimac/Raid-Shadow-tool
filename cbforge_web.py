from __future__ import annotations

import argparse
import copy
from concurrent.futures import ThreadPoolExecutor
import itertools
import json
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional
from urllib.parse import parse_qs, unquote, urlparse

from account_stats import materialize_base_totals
from battle_event_decoder import extract_incoming_target_counts
from boss_modules import build_boss_intel
from build_planner import build_champion_plan, list_area_bonus_regions, list_build_profiles
from clan_boss_simulator import AFFINITY_OPTIONS as CLAN_BOSS_SIM_AFFINITY_OPTIONS, BOSS_DIFFICULTIES as CLAN_BOSS_SIM_DIFFICULTIES, DEFAULT_TEAM_PRESETS as CLAN_BOSS_SIM_PRESETS, EFFECT_LIBRARY as CLAN_BOSS_SIM_EFFECT_LIBRARY, default_member_row as default_clan_boss_member_row, simulate_clan_boss_battle
import deep_battle_probe
from forge_db import DB_PATH, NORMALIZED_SOURCE_PATH, bootstrap_database, cleanup_duplicate_run_history_runs, ensure_schema, load_app_state, refresh_account_stats_from_source, save_app_state
from gear_advisor import evaluate_gear_item, summarize_gear_verdicts
from hellhades_enrich import enrich_registry_from_source
from local_game_bridge import build_team_equip_plan
from registry_report import build_registry_report
from run_mapper import HH_HERO_TYPES_PATH, derive_run_mapping
from run_damage_decoder import extract_damage_summary, extract_member_result_rows
from run_effect_timeline import extract_effect_timeline
from run_history_importer import LIVE_STORAGE_ROOT, import_probe_session, import_probe_sessions
from set_curation import load_local_set_entries, save_local_set_entry
from team_optimizer import build_candidate_clan_boss_member_row, build_team_optimizer_report, list_team_optimizer_targets, optimizer_area_region_for_boss, simulate_candidate_team

try:
    import winsound
except ImportError:  # pragma: no cover - non-Windows fallback
    winsound = None


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
MODEL_DIR = BASE_DIR / "models"
LEGACY_DIR = BASE_DIR / "old" / "legacy_20260318"
LEGACY_INPUT_DIR = LEGACY_DIR / "input"
LOCAL_HH_BRIDGE_PROJECT = BASE_DIR / "tools" / "hh_local_bridge" / "hh_local_bridge.csproj"
LOCAL_HH_BRIDGE_DLL = BASE_DIR / "tools" / "hh_local_bridge" / "bin" / "Release" / "net9.0" / "hh_local_bridge.dll"
LOCAL_HH_BRIDGE_SOURCES = [
    LOCAL_HH_BRIDGE_PROJECT,
    BASE_DIR / "tools" / "hh_local_bridge" / "Program.cs",
]
TEAM_OPTIMIZER_SNAPSHOT_SCOPE = "team_optimizer"
TEAM_OPTIMIZER_LAST_RESTORE_KEY = "team_optimizer:last_restore"
TEAM_OPTIMIZER_CACHE_TTL_SECONDS = 12.0
TEAM_OPTIMIZER_CACHE_LOCK = threading.Lock()
TEAM_OPTIMIZER_REPORT_CACHE: Dict[tuple[str, str, str, str, str, int], Dict[str, Any]] = {}
TEAM_OPTIMIZER_LOADOUT_CACHE: Dict[tuple[str, str, str, str, str, int], Dict[str, Any]] = {}
GEAR_SLOT_ORDER = {
    "weapon": 1,
    "helmet": 2,
    "shield": 3,
    "gloves": 4,
    "chest": 5,
    "boots": 6,
    "ring": 7,
    "amulet": 8,
    "banner": 9,
}
SELL_QUEUE_PAGES = {
    "artifact": {"item_class": "artifact", "label": "Artifact (6 slot)"},
    "accessory": {"item_class": "accessory", "label": "Accessori (ring, amulet, banner)"},
}
SELL_QUEUE_VERDICTS = {"sell_now", "sell_after_12"}
SELL_QUEUE_MAIN_TIER_ORDER = {"weak": 0, "medium": 1, "strong": 2}
SELL_QUEUE_LOCAL_STATE_KEY = "gear:sell_queue_local"
SET_DISPLAY_NAMES = {
    "Attack Speed": "Speed",
    "Accuracy And Speed": "Perception",
    "HP And Heal": "Immortal",
    "HP And Defence": "Resilience",
    "Shield And HP": "Divine Life",
    "Shield And Speed": "Divine Speed",
    "Shield And Attack Power": "Divine Offense",
    "Shield And Critical Chance": "Divine Crit Rate",
    "Attack Power And Ignore Defense": "Cruel",
    "Life Drain": "Lifesteal",
    "Counterattack On Crit": "Avenging",
    "Dot Rate": "Toxic",
    "Freeze Rate On Damage Received": "Frost",
    "AoE Damage Decrease": "Stalwart",
    "Ignore Defense": "Savage",
    "Sleep Chance": "Daze",
    "Decrease Max HP": "Destroy",
    "Attack Power": "Offense",
    "Cooldown Reduction Chance": "Reflex",
    "Critical Heal Multiplier": "Critical Damage",
    "Unkillable And SPD And CR Damage": "Swift Parry",
    "Attack And Crit Rate": "Fatal",
    "Block Debuff": "Immunity",
    "Crit Rate And Ignore DEF Multiplier": "Lethal",
    "Damage Increase On HP Decrease": "Fury",
    "Get Extra Turn": "Relentless",
    "HP": "Life",
    "Stun Chance": "Stun",
    "Crit Damage And Transform Week Into Crit Hit": "Affinitybreaker",
    "Crit Rate And Life Drain": "Bloodthirst",
    "Resistance": "Resistance",
    "Critical Chance": "Critical Rate",
    "Defense": "Defense",
    "Shield": "Shield",
    "Counterattack": "Retaliation",
    "Passive Share Damage And Heal": "Guardian",
    "Provoke Chance": "Taunting",
    "Change Hit Type": "Reaction Accessory",
    "Counterattack Accessory": "Revenge Accessory",
    "Shield Accessory": "Bloodshield Accessory",
}
RUN_CATEGORY_LABELS = {
    "clan_boss": "Clan Boss",
    "dungeon_boss": "Dungeon / Boss PvE",
    "special_pve_unmapped": "PvE Speciale / Non Mappato",
    "stage_pve": "Stage / Campagna / Altra PvE",
    "raw_unmapped": "Tipo grezzo / non mappato",
    "other": "Altro",
}
DUNGEON_BOSS_KEYWORDS = (
    "dragon",
    "dragon's lair",
    "ice golem",
    "spider",
    "fire knight",
    "sand devil",
    "al-naemeh",
    "phantom shogun",
    "minotaur",
    "iron twins",
    "amius",
    "scarab",
    "nether spider",
    "griffin",
    "bommal",
)
SPECIAL_PVE_STAGE_PREFIXES = ("15019",)


def is_client_disconnect_error(exc: BaseException) -> bool:
    if isinstance(exc, (BrokenPipeError, ConnectionAbortedError, ConnectionResetError)):
        return True
    if not isinstance(exc, OSError):
        return False
    if getattr(exc, "winerror", None) in {10053, 10054}:
        return True
    return getattr(exc, "errno", None) in {32, 104}


def choose_set_display_name(set_name: str, curated_entry: Dict[str, Any] | None = None) -> str:
    curated_entry = curated_entry or {}
    raw_name = str(set_name or "").strip()
    canonical_name = str(curated_entry.get("canonical_name") or "").strip()
    display_name = str(curated_entry.get("display_name") or "").strip()
    if canonical_name and (not display_name or display_name == raw_name):
        return canonical_name
    return display_name or canonical_name or SET_DISPLAY_NAMES.get(raw_name, raw_name)


def categorize_run(
    *,
    encounter_name: str = "",
    boss_name: str = "",
    encounter_key: str = "",
    stage_id: str = "",
    game_mode: str = "",
    area_region: str = "",
) -> Dict[str, str]:
    normalized_encounter = str(encounter_name or "").strip()
    normalized_boss = str(boss_name or "").strip()
    normalized_key = str(encounter_key or "").strip().lower()
    normalized_stage = str(stage_id or "").strip()
    normalized_game_mode = str(game_mode or "").strip().lower()
    normalized_area = str(area_region or "").strip().lower()
    combined = " ".join(
        part.lower()
        for part in (normalized_encounter, normalized_boss, normalized_key)
        if part
    )

    category_key = "other"
    if (
        normalized_game_mode == "clan_boss"
        or normalized_area == "clan_boss"
        or normalized_key.startswith("demon_lord")
        or "demon lord" in combined
        or normalized_stage.startswith("4019")
    ):
        category_key = "clan_boss"
    elif any(keyword in combined for keyword in DUNGEON_BOSS_KEYWORDS):
        category_key = "dungeon_boss"
    elif any(normalized_stage.startswith(prefix) for prefix in SPECIAL_PVE_STAGE_PREFIXES):
        category_key = "special_pve_unmapped"
    elif normalized_encounter.lower().startswith("type ") or normalized_boss.lower().startswith("type "):
        category_key = "raw_unmapped"
    elif normalized_stage:
        category_key = "stage_pve"

    return {
        "category_key": category_key,
        "category_label": RUN_CATEGORY_LABELS.get(category_key, RUN_CATEGORY_LABELS["other"]),
    }


def open_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    ensure_schema(db_path)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def build_web_summary(db_path: Path = DB_PATH) -> Dict[str, Any]:
    report = build_registry_report(db_path)
    with open_db(db_path) as conn:
        owned_row = conn.execute("SELECT COUNT(*) FROM account_champions").fetchone()
        report["owned_champions"] = int(owned_row[0] if owned_row else 0)
    return report


def clear_team_optimizer_caches() -> None:
    with TEAM_OPTIMIZER_CACHE_LOCK:
        TEAM_OPTIMIZER_REPORT_CACHE.clear()
        TEAM_OPTIMIZER_LOADOUT_CACHE.clear()


def refresh_gear_from_game(
    db_path: Path = DB_PATH,
    source_path: Path = NORMALIZED_SOURCE_PATH,
    mode: str = "legacy_bridge",
) -> Dict[str, Any]:
    normalized_mode = str(mode or "").strip().lower() or "legacy_bridge"

    if normalized_mode in {"local_only", "local_source", "rebuild_local"}:
        rebuild_summary = bootstrap_database(
            source_path=source_path,
            db_path=db_path,
            rebuild=False,
        )
        clear_team_optimizer_caches()
        clear_local_sell_queue_state(db_path)
        return {
            "ok": True,
            "mode": "local_only",
            "results": [],
            "copied_files": [],
            "summary": rebuild_summary,
            "output": "",
            "message": "Database ricaricato dal dump locale esistente senza usare HellHades.",
        }

    if not LEGACY_DIR.exists():
        raise FileNotFoundError(f"Pipeline legacy non trovata: {LEGACY_DIR}")

    python_executable = sys.executable or "python"
    commands = [
        [python_executable, "extract_local.py"],
        [python_executable, "normalize.py"],
    ]
    results: List[Dict[str, Any]] = []
    combined_output: List[str] = []
    for command in commands:
        completed = subprocess.run(
            command,
            cwd=LEGACY_DIR,
            capture_output=True,
            text=True,
            check=False,
        )
        output = (completed.stdout + completed.stderr).strip()
        results.append(
            {
                "command": command,
                "returncode": completed.returncode,
                "output": output,
            }
        )
        if output:
            combined_output.append(output)
        if completed.returncode != 0:
            raise RuntimeError(output or f"Command failed: {' '.join(command)}")

    raw_payload = load_json_file(LEGACY_INPUT_DIR / "raw_account.json")
    normalized_payload = load_json_file(LEGACY_INPUT_DIR / "normalized_account.json")
    validate_legacy_refresh_outputs(raw_payload, normalized_payload)

    copied_files: List[str] = []
    for file_name in ("raw_account.json", "normalized_account.json"):
        legacy_path = LEGACY_INPUT_DIR / file_name
        target_path = BASE_DIR / "input" / file_name
        if not legacy_path.exists():
            raise FileNotFoundError(f"Output pipeline mancante: {legacy_path}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(legacy_path, target_path)
        copied_files.append(str(target_path))

    rebuild_summary = bootstrap_database(
        source_path=source_path,
        db_path=db_path,
        rebuild=False,
    )
    clear_team_optimizer_caches()
    clear_local_sell_queue_state(db_path)
    return {
        "ok": True,
        "mode": "legacy_bridge",
        "results": results,
        "copied_files": copied_files,
        "summary": rebuild_summary,
        "output": "\n\n".join(chunk for chunk in combined_output if chunk),
    }


def load_json_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File JSON mancante: {path}")
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"Payload JSON non valido in {path}")
    return payload


def extract_legacy_bridge_error(raw_payload: Dict[str, Any]) -> str:
    local_client = raw_payload.get("local_client")
    if isinstance(local_client, dict):
        bridge_payload = local_client.get("hellhades_bridge")
        if isinstance(bridge_payload, dict):
            for candidate in (
                bridge_payload.get("error"),
                (bridge_payload.get("summary") or {}).get("error") if isinstance(bridge_payload.get("summary"), dict) else "",
            ):
                message = str(candidate or "").strip()
                if message:
                    return message
    return str(raw_payload.get("error") or "").strip()


def validate_legacy_refresh_outputs(raw_payload: Dict[str, Any], normalized_payload: Dict[str, Any]) -> None:
    bridge_error = extract_legacy_bridge_error(raw_payload)
    if not bridge_error:
        return

    champion_count = len(normalized_payload.get("champions") or [])
    gear_count = len(normalized_payload.get("gear") or [])
    if champion_count > 0 or gear_count > 0:
        return

    first_line = bridge_error.splitlines()[0].strip() or bridge_error
    if "ExtractorOutdatedException" in bridge_error:
        raise RuntimeError(
            "Refresh equip fallito: il bridge HellHades usa un reader non compatibile con la build attuale di RAID. "
            f"Dettaglio: {first_line}"
        )
    raise RuntimeError(f"Refresh equip fallito: {first_line}")


def build_gear_summary(db_path: Path = DB_PATH) -> Dict[str, Any]:
    with open_db(db_path) as conn:
        total_items = int(conn.execute("SELECT COUNT(*) FROM gear_items").fetchone()[0])
        equipped_items = int(
            conn.execute(
                "SELECT COUNT(*) FROM gear_items WHERE equipped_by IS NOT NULL AND equipped_by != ''"
            ).fetchone()[0]
        )
        locked_items = int(conn.execute("SELECT COUNT(*) FROM gear_items WHERE locked = 1").fetchone()[0])
        unique_sets = int(
            conn.execute(
                "SELECT COUNT(DISTINCT set_name) FROM gear_items WHERE set_name IS NOT NULL AND set_name != ''"
            ).fetchone()[0]
        )
        top_sets = [
            {"set_name": str(row["set_name"] or "(none)"), "count": int(row["item_count"] or 0)}
            for row in conn.execute(
                """
                SELECT set_name, COUNT(*) AS item_count
                FROM gear_items
                GROUP BY set_name
                ORDER BY item_count DESC, set_name ASC
                LIMIT 8
                """
            ).fetchall()
        ]
        slots = [
            {"slot": str(row["slot"] or ""), "count": int(row["item_count"] or 0)}
            for row in conn.execute(
                """
                SELECT slot, COUNT(*) AS item_count
                FROM gear_items
                GROUP BY slot
                ORDER BY item_count DESC, slot ASC
                """
            ).fetchall()
        ]
        item_rows = conn.execute(
            """
            SELECT
                gi.item_id,
                gi.slot,
                gi.set_name,
                gi.rarity,
                gi.rank,
                gi.level,
                gi.main_stat_type,
                gi.equipped_by,
                ac.champion_name AS owner_name
            FROM gear_items gi
            LEFT JOIN account_champions ac
                ON ac.champ_id = gi.equipped_by
            """
        ).fetchall()
        substats_by_item = load_gear_substats_map(conn)

    evaluated_items: List[Dict[str, Any]] = []
    for row in item_rows:
        item = {
            "item_id": str(row["item_id"]),
            "slot": str(row["slot"] or ""),
            "set_name": str(row["set_name"] or ""),
            "rarity": str(row["rarity"] or ""),
            "rank": int(row["rank"] or 0),
            "level": int(row["level"] or 0),
            "main_stat_type": str(row["main_stat_type"] or ""),
            "equipped": bool(row["equipped_by"]),
            "owner_name": str(row["owner_name"] or ""),
        }
        item["advice_verdict"] = evaluate_gear_item(item, substats_by_item.get(item["item_id"], []))["verdict"]
        evaluated_items.append(item)

    return {
        "total_items": total_items,
        "equipped_items": equipped_items,
        "inventory_items": total_items - equipped_items,
        "locked_items": locked_items,
        "unique_sets": unique_sets,
        "verdict_counts": summarize_gear_verdicts(evaluated_items),
        "top_sets": top_sets,
        "slots": slots,
    }


def build_set_registry(db_path: Path = DB_PATH) -> Dict[str, Any]:
    curated_entries = {
        str(entry.get("set_name") or "").strip(): entry
        for entry in load_local_set_entries()
        if str(entry.get("set_name") or "").strip()
    }
    with open_db(db_path) as conn:
        definition_rows = conn.execute(
            """
            SELECT set_name, pieces_required, heal_each_turn_pct, set_kind, counts_accessories, max_pieces, source
            FROM set_definitions
            ORDER BY set_name ASC
            """
        ).fetchall()
        stat_rows = conn.execute(
            """
            SELECT set_name, stat_order, stat_type, stat_value
            FROM set_definition_stats
            ORDER BY set_name ASC, stat_order ASC
            """
        ).fetchall()
        piece_bonus_rows = conn.execute(
            """
            SELECT set_name, bonus_order, pieces_required, stat_type, stat_value, effect_text
            FROM set_definition_piece_bonuses
            ORDER BY set_name ASC, bonus_order ASC
            """
        ).fetchall()
        inventory_rows = conn.execute(
            """
            SELECT
                set_name,
                COUNT(*) AS total_items,
                SUM(CASE WHEN item_class = 'artifact' THEN 1 ELSE 0 END) AS artifact_items,
                SUM(CASE WHEN item_class = 'accessory' THEN 1 ELSE 0 END) AS accessory_items,
                SUM(CASE WHEN equipped_by IS NOT NULL AND equipped_by != '' THEN 1 ELSE 0 END) AS equipped_items,
                SUM(CASE WHEN item_class = 'artifact' AND (equipped_by IS NULL OR equipped_by = '') THEN 1 ELSE 0 END) AS inventory_artifact_items,
                SUM(CASE WHEN item_class = 'accessory' AND (equipped_by IS NULL OR equipped_by = '') THEN 1 ELSE 0 END) AS inventory_accessory_items,
                COUNT(DISTINCT CASE WHEN equipped_by IS NOT NULL AND equipped_by != '' THEN equipped_by END) AS equipped_owners
            FROM gear_items
            WHERE set_name IS NOT NULL AND set_name != ''
            GROUP BY set_name
            ORDER BY set_name ASC
            """
        ).fetchall()

    sets_by_name: Dict[str, Dict[str, Any]] = {}
    for row in definition_rows:
        set_name = str(row["set_name"] or "")
        curated_entry = curated_entries.get(set_name) or {}
        sets_by_name[set_name] = {
            "set_name": set_name,
            "canonical_name": str(curated_entry.get("canonical_name") or "").strip(),
            "display_name": choose_set_display_name(set_name, curated_entry),
            "set_kind": str(row["set_kind"] or "unknown"),
            "pieces_required": int(row["pieces_required"] or 0),
            "max_pieces": int(row["max_pieces"] or 0),
            "counts_accessories": bool(row["counts_accessories"]),
            "heal_each_turn_pct": float(row["heal_each_turn_pct"] or 0.0),
            "source": str(row["source"] or ""),
            "stats": [],
            "piece_bonuses": [],
            "inventory": {
                "total_items": 0,
                "artifact_items": 0,
                "accessory_items": 0,
                "equipped_items": 0,
                "inventory_items": 0,
                "inventory_artifact_items": 0,
                "inventory_accessory_items": 0,
                "equipped_owners": 0,
            },
            "progress": {},
        }

    for row in stat_rows:
        set_name = str(row["set_name"] or "")
        set_row = sets_by_name.setdefault(
            set_name,
            {
                "set_name": set_name,
                "canonical_name": "",
                "display_name": choose_set_display_name(set_name),
                "set_kind": "unknown",
                "pieces_required": 0,
                "max_pieces": 0,
                "counts_accessories": False,
                "heal_each_turn_pct": 0.0,
                "source": "unknown",
                "stats": [],
                "piece_bonuses": [],
                "inventory": {
                    "total_items": 0,
                    "artifact_items": 0,
                    "accessory_items": 0,
                    "equipped_items": 0,
                    "inventory_items": 0,
                    "inventory_artifact_items": 0,
                    "inventory_accessory_items": 0,
                    "equipped_owners": 0,
                },
                "progress": {},
            },
        )
        set_row["stats"].append(
            {
                "stat_type": str(row["stat_type"] or ""),
                "stat_value": float(row["stat_value"] or 0.0),
            }
        )

    piece_bonus_map: Dict[tuple[str, int], Dict[str, Any]] = {}
    for row in piece_bonus_rows:
        set_name = str(row["set_name"] or "")
        pieces_required = int(row["pieces_required"] or 0)
        bonus_key = (set_name, pieces_required)
        piece_bonus = piece_bonus_map.get(bonus_key)
        if piece_bonus is None:
            piece_bonus = {
                "pieces_required": pieces_required,
                "stats": [],
                "effects": [],
            }
            piece_bonus_map[bonus_key] = piece_bonus
            sets_by_name.setdefault(
                set_name,
                {
                    "set_name": set_name,
                    "canonical_name": "",
                    "display_name": choose_set_display_name(set_name),
                    "set_kind": "unknown",
                    "pieces_required": 0,
                    "max_pieces": 0,
                    "counts_accessories": False,
                    "heal_each_turn_pct": 0.0,
                    "source": "unknown",
                    "stats": [],
                    "piece_bonuses": [],
                    "inventory": {
                        "total_items": 0,
                        "artifact_items": 0,
                        "accessory_items": 0,
                        "equipped_items": 0,
                        "inventory_items": 0,
                        "inventory_artifact_items": 0,
                        "inventory_accessory_items": 0,
                        "equipped_owners": 0,
                    },
                    "progress": {},
                },
            )["piece_bonuses"].append(piece_bonus)
        if row["stat_type"] is not None:
            piece_bonus["stats"].append(
                {
                    "stat_type": str(row["stat_type"] or ""),
                    "stat_value": float(row["stat_value"] or 0.0),
                }
            )
        effect_text = str(row["effect_text"] or "").strip()
        if effect_text:
            piece_bonus["effects"].append(effect_text)

    for row in inventory_rows:
        set_name = str(row["set_name"] or "")
        set_row = sets_by_name.setdefault(
            set_name,
            {
                "set_name": set_name,
                "canonical_name": "",
                "display_name": choose_set_display_name(set_name),
                "set_kind": "unknown",
                "pieces_required": 0,
                "max_pieces": 0,
                "counts_accessories": False,
                "heal_each_turn_pct": 0.0,
                "source": "observed_gear",
                "stats": [],
                "piece_bonuses": [],
                    "inventory": {
                        "total_items": 0,
                        "artifact_items": 0,
                        "accessory_items": 0,
                        "equipped_items": 0,
                        "inventory_items": 0,
                        "inventory_artifact_items": 0,
                        "inventory_accessory_items": 0,
                        "equipped_owners": 0,
                    },
                    "progress": {},
                },
            )
        total_items = int(row["total_items"] or 0)
        equipped_items = int(row["equipped_items"] or 0)
        set_row["inventory"] = {
            "total_items": total_items,
            "artifact_items": int(row["artifact_items"] or 0),
            "accessory_items": int(row["accessory_items"] or 0),
            "equipped_items": equipped_items,
            "inventory_items": total_items - equipped_items,
            "inventory_artifact_items": int(row["inventory_artifact_items"] or 0),
            "inventory_accessory_items": int(row["inventory_accessory_items"] or 0),
            "equipped_owners": int(row["equipped_owners"] or 0),
        }
        infer_accessory_only_set(set_row)

    items = sorted(
        sets_by_name.values(),
        key=lambda row: (
            0 if row["inventory"]["total_items"] > 0 else 1,
            row["display_name"].lower(),
            row["set_name"].lower(),
        ),
    )
    for item in items:
        item["piece_bonuses"].sort(key=lambda row: int(row["pieces_required"] or 0))
        item["progress"] = build_set_progress(item)
        item["summary"] = summarize_set_rule(item)

    total_sets = len(items)
    observed_sets = sum(1 for item in items if int(item["inventory"]["total_items"]) > 0)
    variable_sets = sum(1 for item in items if str(item["set_kind"]).lower() == "variable")
    fixed_sets = sum(1 for item in items if str(item["set_kind"]).lower() == "fixed")
    accessory_sets = sum(1 for item in items if bool(item["counts_accessories"]))
    completable_fixed_sets = sum(1 for item in items if int(item["progress"].get("complete_sets_total") or 0) > 0)
    inventory_ready_fixed_sets = sum(1 for item in items if int(item["progress"].get("complete_sets_inventory") or 0) > 0)
    return {
        "summary": {
            "total_sets": total_sets,
            "observed_sets": observed_sets,
            "fixed_sets": fixed_sets,
            "variable_sets": variable_sets,
            "accessory_sets": accessory_sets,
            "completable_fixed_sets": completable_fixed_sets,
            "inventory_ready_fixed_sets": inventory_ready_fixed_sets,
        },
        "sets": items,
    }


def build_set_curation_payload(db_path: Path = DB_PATH) -> Dict[str, Any]:
    registry = build_set_registry(db_path)
    curated_entries = {str(entry.get("set_name") or "").strip(): entry for entry in load_local_set_entries() if str(entry.get("set_name") or "").strip()}
    samples_by_set = load_set_curation_samples(db_path)
    items: List[Dict[str, Any]] = []
    for set_row in registry["sets"]:
        set_name = str(set_row.get("set_name") or "").strip()
        curated = curated_entries.get(set_name)
        item = {
            "set_name": set_name,
            "display_name": str(set_row.get("display_name") or ""),
            "summary": str(set_row.get("summary") or ""),
            "set_kind": str(set_row.get("set_kind") or ""),
            "counts_accessories": bool(set_row.get("counts_accessories")),
            "pieces_required": int(set_row.get("pieces_required") or 0),
            "max_pieces": int(set_row.get("max_pieces") or 0),
            "inventory": dict(set_row.get("inventory") or {}),
            "progress": dict(set_row.get("progress") or {}),
            "source": str(set_row.get("source") or ""),
            "observed_samples": dict(samples_by_set.get(set_name) or default_set_curation_samples()),
            "curated": bool(curated),
            "curation": curated or {
                "set_name": set_name,
                "canonical_name": "",
                "display_name": str(set_row.get("display_name") or ""),
                "set_kind": infer_curation_kind(set_row),
                "counts_accessories": bool(set_row.get("counts_accessories")),
                "pieces_required": default_curation_pieces_required(set_row),
                "max_pieces": default_curation_max_pieces(set_row),
                "base_bonus_text": "",
                "thresholds_text": "",
            },
        }
        items.append(item)
    items.sort(
        key=lambda row: (
            0 if int(dict(row.get("inventory") or {}).get("total_items") or 0) > 0 else 1,
            0 if not bool(row.get("curated")) else 1,
            row["display_name"].lower(),
            row["set_name"].lower(),
        )
    )
    return {
        "summary": registry["summary"],
        "items": items,
    }


def default_set_curation_samples() -> Dict[str, Any]:
    return {
        "slot_counts": [],
        "owner_counts": [],
        "sample_items": [],
    }


def load_set_curation_samples(db_path: Path = DB_PATH, limit_per_set: int = 12) -> Dict[str, Dict[str, Any]]:
    with open_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                gi.set_name,
                gi.item_id,
                gi.item_class,
                gi.slot,
                gi.rarity,
                gi.rank,
                gi.level,
                gi.main_stat_type,
                gi.main_stat_value,
                gi.equipped_by,
                ac.champion_name AS owner_name
            FROM gear_items gi
            LEFT JOIN account_champions ac
                ON ac.champ_id = gi.equipped_by
            WHERE gi.set_name IS NOT NULL AND gi.set_name != ''
            ORDER BY
                gi.set_name ASC,
                CASE WHEN gi.equipped_by IS NOT NULL AND gi.equipped_by != '' THEN 0 ELSE 1 END ASC,
                gi.rank DESC,
                gi.level DESC,
                gi.slot ASC,
                gi.item_id ASC
            """
        ).fetchall()

    slot_counters: Dict[str, Counter[str]] = {}
    owner_counters: Dict[str, Counter[str]] = {}
    samples_by_set: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        set_name = str(row["set_name"] or "").strip()
        if not set_name:
            continue
        slot = str(row["slot"] or "").strip()
        owner_name = str(row["owner_name"] or "").strip()
        slot_counters.setdefault(set_name, Counter())
        owner_counters.setdefault(set_name, Counter())
        if slot:
            slot_counters[set_name][slot] += 1
        if owner_name:
            owner_counters[set_name][owner_name] += 1
        bucket = samples_by_set.setdefault(set_name, default_set_curation_samples())
        if len(bucket["sample_items"]) >= limit_per_set:
            continue
        bucket["sample_items"].append(
            {
                "item_id": str(row["item_id"] or ""),
                "item_class": str(row["item_class"] or ""),
                "slot": slot,
                "rarity": str(row["rarity"] or ""),
                "rank": int(row["rank"] or 0),
                "level": int(row["level"] or 0),
                "main_stat_type": str(row["main_stat_type"] or ""),
                "main_stat_value": row["main_stat_value"],
                "equipped": bool(row["equipped_by"]),
                "owner_name": owner_name,
            }
        )

    for set_name, payload in samples_by_set.items():
        payload["slot_counts"] = [
            {"slot": slot, "count": count}
            for slot, count in sorted(slot_counters.get(set_name, Counter()).items(), key=lambda item: (gear_slot_sort_key(item[0]), item[0].lower()))
        ]
        payload["owner_counts"] = [
            {"owner_name": owner_name, "count": count}
            for owner_name, count in owner_counters.get(set_name, Counter()).most_common(8)
        ]
    return samples_by_set


def infer_curation_kind(set_row: Dict[str, Any]) -> str:
    current = str(set_row.get("set_kind") or "").strip().lower()
    if current in {"fixed", "variable", "accessory"}:
        return current
    inventory = dict(set_row.get("inventory") or {})
    if int(inventory.get("artifact_items") or 0) == 0 and int(inventory.get("accessory_items") or 0) > 0:
        return "accessory"
    return "fixed"


def default_curation_pieces_required(set_row: Dict[str, Any]) -> int:
    set_kind = infer_curation_kind(set_row)
    if set_kind in {"variable", "accessory"}:
        return 1
    return max(int(set_row.get("pieces_required") or 0), 2)


def default_curation_max_pieces(set_row: Dict[str, Any]) -> int:
    set_kind = infer_curation_kind(set_row)
    current = int(set_row.get("max_pieces") or 0)
    if current > 0:
        return current
    if set_kind == "variable":
        return 9
    if set_kind == "accessory":
        return 3
    return 6


def build_set_progress(set_row: Dict[str, Any]) -> Dict[str, Any]:
    inventory = dict(set_row.get("inventory") or {})
    counts_accessories = bool(set_row.get("counts_accessories"))
    set_kind = str(set_row.get("set_kind") or "unknown").strip().lower()
    relevant_total_items = int(inventory.get("total_items") or 0) if counts_accessories else int(inventory.get("artifact_items") or 0)
    relevant_inventory_items = (
        int(inventory.get("inventory_items") or 0)
        if counts_accessories
        else int(inventory.get("inventory_artifact_items") or 0)
    )
    relevant_equipped_items = max(relevant_total_items - relevant_inventory_items, 0)

    progress = {
        "relevant_total_items": relevant_total_items,
        "relevant_inventory_items": relevant_inventory_items,
        "relevant_equipped_items": relevant_equipped_items,
        "complete_sets_total": 0,
        "complete_sets_inventory": 0,
        "highest_bonus_threshold_total": 0,
        "highest_bonus_threshold_inventory": 0,
        "next_threshold_total": 0,
        "next_threshold_inventory": 0,
        "missing_for_next_total": 0,
        "missing_for_next_inventory": 0,
    }

    if set_kind in {"variable", "accessory"}:
        thresholds = sorted(
            {
                int(row.get("pieces_required") or 0)
                for row in list(set_row.get("piece_bonuses") or [])
                if int(row.get("pieces_required") or 0) > 0
            }
        )
        progress["highest_bonus_threshold_total"] = highest_reached_threshold(relevant_total_items, thresholds)
        progress["highest_bonus_threshold_inventory"] = highest_reached_threshold(relevant_inventory_items, thresholds)
        progress["next_threshold_total"] = next_threshold_after(progress["highest_bonus_threshold_total"], thresholds)
        progress["next_threshold_inventory"] = next_threshold_after(progress["highest_bonus_threshold_inventory"], thresholds)
        if progress["next_threshold_total"] > 0:
            progress["missing_for_next_total"] = max(progress["next_threshold_total"] - relevant_total_items, 0)
        if progress["next_threshold_inventory"] > 0:
            progress["missing_for_next_inventory"] = max(progress["next_threshold_inventory"] - relevant_inventory_items, 0)
        return progress

    pieces_required = int(set_row.get("pieces_required") or 0)
    if pieces_required > 0:
        progress["complete_sets_total"] = relevant_total_items // pieces_required
        progress["complete_sets_inventory"] = relevant_inventory_items // pieces_required
        progress["next_threshold_total"] = pieces_required if relevant_total_items % pieces_required else 0
        progress["next_threshold_inventory"] = pieces_required if relevant_inventory_items % pieces_required else 0
        if progress["next_threshold_total"] > 0:
            progress["missing_for_next_total"] = pieces_required - (relevant_total_items % pieces_required)
        if progress["next_threshold_inventory"] > 0:
            progress["missing_for_next_inventory"] = pieces_required - (relevant_inventory_items % pieces_required)
    return progress


def highest_reached_threshold(pieces: int, thresholds: List[int]) -> int:
    reached = 0
    for threshold in thresholds:
        if pieces < threshold:
            break
        reached = threshold
    return reached


def next_threshold_after(current: int, thresholds: List[int]) -> int:
    for threshold in thresholds:
        if threshold > current:
            return threshold
    return 0


def summarize_set_rule(set_row: Dict[str, Any]) -> str:
    set_kind = str(set_row.get("set_kind") or "unknown").strip().lower()
    counts_accessories = bool(set_row.get("counts_accessories"))
    if set_kind == "accessory":
        max_pieces = int(set_row.get("max_pieces") or 0)
        highest = int(dict(set_row.get("progress") or {}).get("highest_bonus_threshold_total") or 0)
        return f"Accessory set 1/2/3 ({'solo accessori' if counts_accessories else 'misto'}) · soglia attiva {highest}/{max_pieces}"
    if set_kind == "variable":
        max_pieces = int(set_row.get("max_pieces") or 0)
        scope = "artifact + accessori" if counts_accessories else "solo artifact"
        highest = int(dict(set_row.get("progress") or {}).get("highest_bonus_threshold_total") or 0)
        return (
            f"Variabile fino a {max_pieces} pezzi ({scope}) · soglia attiva {highest}/{max_pieces}"
            if max_pieces
            else f"Variable set ({scope})"
        )
    pieces_required = int(set_row.get("pieces_required") or 0)
    if pieces_required > 0:
        scope = "solo artifact" if not counts_accessories else "artifact + accessori"
        complete_sets_total = int(dict(set_row.get("progress") or {}).get("complete_sets_total") or 0)
        return f"{pieces_required} pezzi ({scope}) · chiudibili {complete_sets_total}"
    return "Regola non classificata"


def infer_accessory_only_set(set_row: Dict[str, Any]) -> None:
    inventory = dict(set_row.get("inventory") or {})
    if str(set_row.get("set_kind") or "").strip().lower() != "unknown":
        return
    if int(inventory.get("artifact_items") or 0) != 0:
        return
    if int(inventory.get("accessory_items") or 0) <= 0:
        return
    if not str(set_row.get("set_name") or "").strip().lower().endswith("accessory"):
        return
    set_row["set_kind"] = "accessory"
    set_row["pieces_required"] = 1
    set_row["max_pieces"] = 3
    set_row["counts_accessories"] = True
    if not str(set_row.get("source") or "").strip():
        set_row["source"] = "inferred_accessory_set"


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def emit_attention_beep(frequency_hz: int = 950, duration_ms: int = 120) -> None:
    if winsound is None:
        return
    try:
        winsound.Beep(max(37, int(frequency_hz)), max(50, int(duration_ms)))
    except RuntimeError:
        return


def parse_float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def percent_share(value: Any, total: Any) -> float:
    numerator = parse_float_value(value)
    denominator = parse_float_value(total)
    if numerator <= 0 or denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def parse_json_text(raw: str, default: Any) -> Any:
    text = str(raw or "").strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def read_json_file(path: Path, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    payload = parse_json_text(path.read_text(encoding="utf-8"), default or {}) if path.exists() else (default or {})
    return payload if isinstance(payload, dict) else (default or {})


def read_jsonl_rows(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        payload = parse_json_text(line, {})
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def extract_probe_battle(event: Dict[str, Any]) -> Dict[str, Any]:
    battle = event.get("battle")
    if isinstance(battle, dict) and battle:
        return battle
    battle_context = event.get("battle_context")
    if isinstance(battle_context, dict) and battle_context:
        return battle_context
    saved = event.get("saved")
    if isinstance(saved, dict):
        nested = saved.get("battle_context")
        if isinstance(nested, dict) and nested:
            return nested
    return {}


def probe_event_battle_id(event: Dict[str, Any], current_battle_id: str = "") -> str:
    line = str(event.get("line") or "").strip()
    if line:
        match = PROBE_BATTLE_ID_RE.search(line)
        if match:
            return str(match.group("id") or "").strip()
    reason = str(event.get("reason") or "").strip()
    if reason:
        match = PROBE_BATTLE_ID_RE.search(reason)
        if match:
            return str(match.group("id") or "").strip()
    event_type = str(event.get("event_type") or "").strip()
    if current_battle_id and event_type in {"file_snapshot", "forced_file_snapshot"}:
        return current_battle_id.strip()
    battle = extract_probe_battle(event)
    battle_id = str(battle.get("battle_id") or "").strip()
    if battle_id:
        return battle_id
    return current_battle_id.strip()


def count_snapshot_files(session_dir: Path) -> Dict[str, int]:
    snapshots_dir = session_dir / "snapshots"
    counts = {"total": 0, "bin": 0, "json": 0}
    if not snapshots_dir.exists():
        return counts
    for path in snapshots_dir.rglob("*"):
        if not path.is_file():
            continue
        counts["total"] += 1
        if path.suffix.lower() == ".bin":
            counts["bin"] += 1
        elif path.suffix.lower() == ".json":
            counts["json"] += 1
    return counts


def collect_session_snapshot_rows(session_dir: Path, limit: int = 20) -> List[Dict[str, Any]]:
    snapshots_dir = session_dir / "snapshots"
    if not snapshots_dir.exists():
        return []
    rows: List[Dict[str, Any]] = []
    for path in snapshots_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(session_dir).as_posix()
        root_name = relative.split("/", 2)[1] if relative.startswith("snapshots/") and "/" in relative else "snapshots"
        rows.append(
            {
                "file_name": path.name,
                "path": str(path),
                "relative_path": relative,
                "root_name": root_name,
                "size_bytes": path.stat().st_size,
                "modified_at": datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat(),
            }
        )
    rows.sort(key=lambda row: (row["modified_at"], row["relative_path"]), reverse=True)
    return rows[:limit]


def summarize_probe_runs(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    runs_by_id: Dict[str, Dict[str, Any]] = {}
    run_order: List[str] = []
    current_battle_id = ""

    for event in events:
        battle = extract_probe_battle(event)
        battle_id = probe_event_battle_id(event, current_battle_id=current_battle_id)
        if not battle_id:
            continue
        current_battle_id = battle_id

        run = runs_by_id.get(battle_id)
        if run is None:
            run = {
                "battle_id": battle_id,
                "stage_id": "",
                "formation_index": None,
                "team_members": [],
                "enemy_names": [],
                "first_seen_at": "",
                "started_at": "",
                "result_detected_at": "",
                "finished_at": "",
                "last_event_at": "",
                "event_count": 0,
                "battle_results_snapshot_count": 0,
                "rich_battle_results_count": 0,
                "best_battle_results_size": 0,
                "best_battle_results_path": "",
                "has_rich_battle_results": False,
                "result_source": "",
                "completed": False,
                "total_damage": None,
                "member_damage": [],
                "boss_name": "",
                "boss_affinity": "",
                "encounter_name": "",
                "damage_trusted": False,
                "damage_note": "battleResults catturato, ma decoder danno non ancora trusted",
                "total_damage_status": "not_available",
                "member_damage_status": "not_available",
            }
            runs_by_id[battle_id] = run
            run_order.append(battle_id)

        captured_at = str(event.get("captured_at") or "")
        if captured_at:
            if not run["first_seen_at"]:
                run["first_seen_at"] = captured_at
            run["last_event_at"] = captured_at
        run["event_count"] += 1

        if battle:
            stage_id = str(battle.get("stage_id") or "").strip()
            if stage_id:
                run["stage_id"] = stage_id
            if battle.get("formation_index") is not None:
                run["formation_index"] = battle.get("formation_index")
            members = list(battle.get("player_members") or [])
            if members:
                run["team_members"] = members
            enemy_rows = battle.get("enemy_rows") or []
            enemy_names = [str(row.get("name") or "").strip() for row in enemy_rows if isinstance(row, dict) and str(row.get("name") or "").strip()]
            if enemy_names:
                run["enemy_names"] = enemy_names
            mapping = derive_run_mapping(battle, hero_types_path=HH_HERO_TYPES_PATH)
            run["boss_name"] = str(mapping.get("enemy_name") or mapping.get("encounter_name") or run.get("boss_name") or "")
            run["boss_affinity"] = str(mapping.get("boss_affinity") or run.get("boss_affinity") or "")
            run["encounter_name"] = str(mapping.get("encounter_name") or run.get("encounter_name") or "")

        event_type = str(event.get("event_type") or "").strip()
        line = str(event.get("line") or "").strip()
        lowered = line.lower()
        if event_type == "log_line":
            if (
                "change battle state [loading -> started]" in lowered
                or "change battle state [startcmdsucceed -> started]" in lowered
            ) and not run["started_at"]:
                run["started_at"] = captured_at
            if "battleresult added:" in lowered and not run["result_detected_at"]:
                run["result_detected_at"] = captured_at
                run["result_source"] = "log_line"
            if "change battle state [started -> finished]" in lowered:
                run["finished_at"] = captured_at
                run["completed"] = True

        saved = event.get("saved")
        if isinstance(saved, dict):
            marker = saved.get("marker")
            size_bytes = int(marker.get("size") or 0) if isinstance(marker, dict) else 0
            if str(event.get("source_name") or "") == "battle_results":
                run["battle_results_snapshot_count"] += 1
                run["best_battle_results_size"] = max(int(run["best_battle_results_size"] or 0), size_bytes)
                if size_bytes > 11:
                    run["rich_battle_results_count"] += 1
                    run["has_rich_battle_results"] = True
                    raw_path = str(saved.get("raw_path") or "").strip()
                    if raw_path and size_bytes >= int(run["best_battle_results_size"] or 0):
                        run["best_battle_results_path"] = raw_path
                    if not run["result_detected_at"]:
                        run["result_detected_at"] = captured_at
                        run["result_source"] = "battle_results_snapshot"

        if not run["completed"] and run["finished_at"]:
            run["completed"] = True

        run.update(
            categorize_run(
                encounter_name=str(run.get("encounter_name") or ""),
                boss_name=str(run.get("boss_name") or ""),
                stage_id=str(run.get("stage_id") or ""),
            )
        )

    runs = [runs_by_id[battle_id] for battle_id in run_order]
    for run in runs:
        raw_path = Path(str(run.get("best_battle_results_path") or "").strip())
        if not raw_path.exists() or not raw_path.is_file():
            continue
        try:
            damage_summary = dict_value(extract_damage_summary(raw_path))
        except Exception:
            continue
        total_damage = parse_float_value(damage_summary.get("total_damage"))
        meaningful_member_damage = [
            dict_value(row)
            for row in list_value(damage_summary.get("members"))
            if dict_value(row).get("damage_done") is not None
        ]
        if total_damage > 0:
            run["total_damage"] = total_damage
        run["member_damage"] = meaningful_member_damage
        run["damage_trusted"] = bool(damage_summary.get("damage_trusted"))
        run["total_damage_status"] = str(damage_summary.get("total_damage_status") or "not_available")
        run["member_damage_status"] = str(damage_summary.get("member_damage_status") or "not_available")
        if run["damage_trusted"] and total_damage > 0:
            run["damage_note"] = "Danno team disponibile dal raw battleResults."
        elif total_damage > 0 and meaningful_member_damage:
            run["damage_note"] = "Total damage disponibile; danno per campione ancora candidato dal raw battleResults."
        elif total_damage > 0:
            run["damage_note"] = "Total damage disponibile dal raw battleResults come candidato forte."
        elif meaningful_member_damage:
            run["damage_note"] = "Danno per campione disponibile solo come candidato dal raw battleResults."
    runs.sort(key=lambda row: (str(row.get("first_seen_at") or ""), str(row.get("battle_id") or "")), reverse=True)
    return runs


def summarize_run_recorder_session(
    session_dir: Path,
    recorder_status: Optional[Dict[str, Any]] = None,
    include_recent: bool = False,
) -> Dict[str, Any]:
    metadata = read_json_file(session_dir / "session.json", {})
    events = read_jsonl_rows(session_dir / "events.jsonl")
    event_type_counts = Counter(str(event.get("event_type") or "").strip() for event in events if str(event.get("event_type") or "").strip())
    recent_events = events[-12:] if include_recent else []
    recent_log_lines = [
        str(event.get("line") or "").strip()
        for event in events
        if str(event.get("event_type") or "") == "log_line" and str(event.get("line") or "").strip()
    ][-12:]

    latest_battle: Dict[str, Any] = {}
    for event in reversed(events):
        latest_battle = extract_probe_battle(event)
        if latest_battle:
            break

    latest_event_at = ""
    if events:
        latest_event_at = str(events[-1].get("captured_at") or "")
    elif metadata:
        latest_event_at = str(metadata.get("created_at") or "")

    snapshot_counts = count_snapshot_files(session_dir)
    runs = summarize_probe_runs(events)
    latest_run = runs[0] if runs else {}
    running = False
    if recorder_status:
        running = bool(recorder_status.get("running")) and str(recorder_status.get("session_slug") or "") == session_dir.name

    payload = {
        "session_slug": session_dir.name,
        "session_dir": str(session_dir),
        "created_at": str(metadata.get("created_at") or ""),
        "last_event_at": latest_event_at,
        "running": running,
        "event_count": len(events),
        "event_type_counts": dict(event_type_counts),
        "snapshot_count": snapshot_counts["total"],
        "snapshot_bin_count": snapshot_counts["bin"],
        "snapshot_meta_count": snapshot_counts["json"],
        "run_count": len(runs),
        "latest_run": latest_run,
        "latest_battle": {
            "battle_id": str(latest_battle.get("battle_id") or ""),
            "stage_id": str(latest_battle.get("stage_id") or ""),
            "formation_index": latest_battle.get("formation_index"),
            "team_members": list(latest_battle.get("player_members") or []),
        },
    }
    if include_recent:
        payload["metadata"] = metadata
        payload["paths"] = {
            "session_json": str(session_dir / "session.json"),
            "events_jsonl": str(session_dir / "events.jsonl"),
            "log_capture": str(session_dir / "interesting_log_lines.txt"),
        }
        payload["recent_log_lines"] = recent_log_lines
        payload["recent_events"] = recent_events
        payload["snapshots"] = collect_session_snapshot_rows(session_dir)
        payload["runs"] = runs
    return payload


class RunRecorderController:
    def __init__(
        self,
        base_dir: Path = BASE_DIR,
        script_path: Path = BASE_DIR / "deep_battle_probe.py",
        output_root: Path = deep_battle_probe.OUTPUT_ROOT,
        python_executable: Optional[str] = None,
    ) -> None:
        self.base_dir = base_dir
        self.script_path = script_path
        self.output_root = output_root
        self.python_executable = python_executable or sys.executable
        self._lock = threading.Lock()
        self._process: Optional[subprocess.Popen[str]] = None
        self._stdout_handle: Any = None
        self._session_slug = ""
        self._session_dir = Path()
        self._started_at = ""
        self._interval_seconds = 0.35
        self._duration_seconds = 0.0
        self._last_exit_code: Optional[int] = None

    def _refresh_locked(self) -> None:
        if self._process is None:
            return
        exit_code = self._process.poll()
        if exit_code is None:
            return
        self._last_exit_code = exit_code
        if self._stdout_handle is not None:
            self._stdout_handle.close()
            self._stdout_handle = None
        self._process = None

    def _status_locked(self) -> Dict[str, Any]:
        running = self._process is not None
        return {
            "running": running,
            "pid": self._process.pid if self._process is not None else None,
            "started_at": self._started_at,
            "session_slug": self._session_slug,
            "session_dir": str(self._session_dir) if self._session_slug else "",
            "interval_seconds": self._interval_seconds,
            "duration_seconds": self._duration_seconds,
            "script_path": str(self.script_path),
            "output_root": str(self.output_root),
            "last_exit_code": self._last_exit_code,
        }

    def _next_session_slug_locked(self) -> str:
        base_slug = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        slug = base_slug
        counter = 1
        while (self.output_root / slug).exists():
            counter += 1
            slug = f"{base_slug}_{counter}"
        return slug

    def status(self) -> Dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            return self._status_locked()

    def start(self, interval_seconds: float = 0.35, duration_seconds: float = 0.0) -> Dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            if self._process is not None:
                raise RuntimeError("Il registratore delle run e' gia' attivo.")

            session_slug = self._next_session_slug_locked()
            session_dir = self.output_root / session_slug
            session_dir.mkdir(parents=True, exist_ok=True)
            stdout_path = session_dir / "stdout.log"
            stdout_handle = stdout_path.open("a", encoding="utf-8")
            interval = max(parse_float_value(interval_seconds, 0.35), 0.1)
            duration = max(parse_float_value(duration_seconds, 0.0), 0.0)
            command = [
                self.python_executable,
                str(self.script_path),
                "--interval",
                str(interval),
                "--duration",
                str(duration),
                "--session-slug",
                session_slug,
            ]
            try:
                process = subprocess.Popen(
                    command,
                    cwd=self.base_dir,
                    stdout=stdout_handle,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
            except Exception:
                stdout_handle.close()
                raise
            self._process = process
            self._stdout_handle = stdout_handle
            self._session_slug = session_slug
            self._session_dir = session_dir
            self._started_at = utc_now_iso()
            self._interval_seconds = interval
            self._duration_seconds = duration
            self._last_exit_code = None
            return self._status_locked()

    def stop(self) -> Dict[str, Any]:
        with self._lock:
            self._refresh_locked()
            if self._process is None:
                return self._status_locked()
            process = self._process
            process.terminate()
            try:
                process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5.0)
            self._refresh_locked()
            return self._status_locked()


RUN_RECORDER = RunRecorderController()
PROBE_BATTLE_ID_RE = re.compile(
    r"(?:Id=|battleId - |Battle \[|Created setup for battle Id -\s*|BattleSetup cached:\s*\[\s*Id\s*=\s*|Created battle processor for battleId -\s*)(?P<id>[0-9a-fA-F-]{8,})",
    re.IGNORECASE,
)


def build_run_recorder_status(recorder: RunRecorderController = RUN_RECORDER) -> Dict[str, Any]:
    return recorder.status()


def default_run_recorder_db_import(run_count: int = 0) -> Dict[str, Any]:
    return {
        "imported": False,
        "imported_runs": 0,
        "completed_runs": 0,
        "successful_runs": 0,
        "latest_saved_at": "",
        "latest_run_id": None,
        "pending_runs_estimate": max(int(run_count or 0), 0),
    }


def build_run_recorder_db_import_index(db_path: Path = DB_PATH) -> Dict[str, Any]:
    with open_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                probe_session_slug,
                COUNT(*) AS imported_runs,
                SUM(CASE WHEN completed = 1 THEN 1 ELSE 0 END) AS completed_runs,
                SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) AS successful_runs,
                MAX(saved_at) AS latest_saved_at,
                MAX(run_id) AS latest_run_id
            FROM run_history_runs
            WHERE source = 'probe_import'
              AND NULLIF(TRIM(COALESCE(probe_session_slug, '')), '') IS NOT NULL
            GROUP BY probe_session_slug
            """
        ).fetchall()
        totals = conn.execute(
            """
            SELECT COUNT(*) AS imported_runs, COUNT(DISTINCT probe_session_slug) AS imported_sessions
            FROM run_history_runs
            WHERE source = 'probe_import'
              AND NULLIF(TRIM(COALESCE(probe_session_slug, '')), '') IS NOT NULL
            """
        ).fetchone()

    by_session: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        session_slug = str(row["probe_session_slug"] or "").strip()
        if not session_slug:
            continue
        by_session[session_slug] = {
            "imported": int(row["imported_runs"] or 0) > 0,
            "imported_runs": int(row["imported_runs"] or 0),
            "completed_runs": int(row["completed_runs"] or 0),
            "successful_runs": int(row["successful_runs"] or 0),
            "latest_saved_at": str(row["latest_saved_at"] or ""),
            "latest_run_id": int(row["latest_run_id"]) if row["latest_run_id"] is not None else None,
        }

    return {
        "runs": int(totals["imported_runs"] or 0) if totals else 0,
        "sessions": int(totals["imported_sessions"] or 0) if totals else 0,
        "by_session": by_session,
    }


def list_run_history_runs_for_session(session_slug: str, db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    clean_slug = str(session_slug or "").strip()
    if not clean_slug:
        return []
    with open_db(db_path) as conn:
        run_rows = conn.execute(
            """
            SELECT
                r.run_id,
                r.battle_id,
                r.saved_at,
                r.encounter_key,
                r.encounter_name,
                r.area_region,
                r.game_mode,
                r.stage_id,
                r.stage_label,
                r.success,
                r.elapsed_seconds,
                r.total_damage,
                COUNT(DISTINCT m.member_order) AS members,
                COUNT(DISTINCT su.member_order || ':' || su.skill_order) AS skill_usages
            FROM run_history_runs r
            LEFT JOIN run_history_members m
              ON m.run_id = r.run_id
            LEFT JOIN run_history_member_skill_usage su
              ON su.run_id = r.run_id
            WHERE r.source = 'probe_import'
              AND r.probe_session_slug = ?
            GROUP BY
                r.run_id,
                r.battle_id,
                r.saved_at,
                r.encounter_key,
                r.encounter_name,
                r.area_region,
                r.game_mode,
                r.stage_id,
                r.stage_label,
                r.success,
                r.elapsed_seconds,
                r.total_damage
            ORDER BY r.run_id DESC
            """,
            (clean_slug,),
        ).fetchall()
    return [
        {
            "run_id": int(row["run_id"]),
            "battle_id": str(row["battle_id"] or ""),
            "saved_at": str(row["saved_at"] or ""),
            "encounter_key": str(row["encounter_key"] or ""),
            "encounter_name": str(row["encounter_name"] or ""),
            "stage_id": str(row["stage_id"] or ""),
            "stage_label": str(row["stage_label"] or ""),
            "success": bool(row["success"]),
            "elapsed_seconds": parse_float_value(row["elapsed_seconds"]),
            "total_damage": parse_float_value(row["total_damage"]),
            "members": int(row["members"] or 0),
            "skill_usages": int(row["skill_usages"] or 0),
            **categorize_run(
                encounter_name=str(row["encounter_name"] or ""),
                encounter_key=str(row["encounter_key"] or ""),
                stage_id=str(row["stage_id"] or ""),
                game_mode=str(row["game_mode"] or ""),
                area_region=str(row["area_region"] or ""),
            ),
        }
        for row in run_rows
    ]


def run_history_run_detail(run_id: int, db_path: Path = DB_PATH) -> Dict[str, Any]:
    with open_db(db_path) as conn:
        run_row = conn.execute(
            """
            SELECT
                run_id,
                saved_at,
                source,
                source_run_uid,
                battle_id,
                probe_session_slug,
                encounter_key,
                encounter_name,
                area_region,
                game_mode,
                stage_id,
                stage_label,
                success,
                completed,
                elapsed_seconds,
                total_damage,
                labels_json,
                context_json
            FROM run_history_runs
            WHERE run_id = ?
            """,
            (run_id,),
        ).fetchone()
        if run_row is None:
            raise KeyError(f"Run non trovata: {run_id}")

        member_rows = conn.execute(
            """
            SELECT
                member_order,
                champ_id,
                champion_name,
                champion_type_id,
                level,
                rank,
                awakening_level,
                empowerment_level,
                booked,
                build_fingerprint,
                set_summary_json,
                tags_json
            FROM run_history_members
            WHERE run_id = ?
            ORDER BY member_order ASC
            """,
            (run_id,),
        ).fetchall()
        stat_rows = conn.execute(
            """
            SELECT member_order, stat_name, stat_value, stat_source
            FROM run_history_member_stats
            WHERE run_id = ?
            ORDER BY member_order ASC, stat_name ASC
            """,
            (run_id,),
        ).fetchall()
        metric_rows = conn.execute(
            """
            SELECT member_order, damage_done, damage_taken, healing_done, shields_done,
                   buffs_applied, debuffs_applied, deaths, revives, alive_at_end, metric_payload_json
            FROM run_history_member_metrics
            WHERE run_id = ?
            ORDER BY member_order ASC
            """,
            (run_id,),
        ).fetchall()
        skill_usage_rows = conn.execute(
            """
            SELECT member_order, skill_order, skill_slot, skill_code, usage_count, usage_payload_json
            FROM run_history_member_skill_usage
            WHERE run_id = ?
            ORDER BY member_order ASC, skill_order ASC
            """,
            (run_id,),
        ).fetchall()
        asset_rows = conn.execute(
            """
            SELECT asset_order, asset_kind, asset_path, sha256, size_bytes, captured_at, metadata_json
            FROM run_history_assets
            WHERE run_id = ?
            ORDER BY asset_order ASC
            """,
            (run_id,),
        ).fetchall()

    stats_by_member: Dict[int, Dict[str, Any]] = {}
    for row in stat_rows:
        member_order = int(row["member_order"] or 0)
        stats_by_member.setdefault(member_order, {})[str(row["stat_name"] or "")] = row["stat_value"]

    metrics_by_member: Dict[int, Dict[str, Any]] = {}
    for row in metric_rows:
        member_order = int(row["member_order"] or 0)
        payload = parse_json_text(str(row["metric_payload_json"] or ""), {})
        metrics_by_member[member_order] = {
            "damage_done": parse_float_value(row["damage_done"]),
            "damage_taken": parse_float_value(row["damage_taken"]),
            "healing_done": parse_float_value(row["healing_done"]),
            "shields_done": parse_float_value(row["shields_done"]),
            "buffs_applied": int(row["buffs_applied"] or 0),
            "debuffs_applied": int(row["debuffs_applied"] or 0),
            "deaths": int(row["deaths"] or 0),
            "revives": int(row["revives"] or 0),
            "alive_at_end": row["alive_at_end"],
            "damage_done_status": str(payload.get("damage_done_status") or ""),
            "damage_done_weight": parse_float_value(payload.get("damage_done_weight")),
            "damage_taken_trusted": bool(payload.get("damage_taken_trusted")),
            "damage_taken_status": str(payload.get("damage_taken_status") or ""),
            "payload": payload,
        }

    skill_usage_by_member: Dict[int, List[Dict[str, Any]]] = {}
    for row in skill_usage_rows:
        member_order = int(row["member_order"] or 0)
        skill_usage_by_member.setdefault(member_order, []).append(
            {
                "skill_order": int(row["skill_order"] or 0),
                "skill_slot": str(row["skill_slot"] or ""),
                "skill_code": str(row["skill_code"] or ""),
                "usage_count": int(row["usage_count"] or 0),
                "payload": parse_json_text(str(row["usage_payload_json"] or ""), {}),
            }
        )

    assets = [
        {
            "asset_order": int(row["asset_order"] or 0),
            "asset_kind": str(row["asset_kind"] or ""),
            "asset_path": str(row["asset_path"] or ""),
            "sha256": str(row["sha256"] or ""),
            "size_bytes": int(row["size_bytes"] or 0),
            "captured_at": str(row["captured_at"] or ""),
            "metadata": parse_json_text(str(row["metadata_json"] or ""), {}),
        }
        for row in asset_rows
    ]

    raw_member_rows_by_order: Dict[int, Dict[str, Any]] = {}
    incoming_rows_by_order: Dict[int, Dict[str, Any]] = {}
    effect_timeline: Dict[str, Any] = {}
    raw_asset_path = next(
        (
            Path(str(asset.get("asset_path") or ""))
            for asset in assets
            if str(asset.get("asset_kind") or "") == "client_probe_battle_results_bin"
            and str(asset.get("asset_path") or "").strip()
        ),
        None,
    )
    if raw_asset_path and raw_asset_path.exists() and raw_asset_path.is_file():
        try:
            for raw_member_row in extract_member_result_rows(raw_asset_path):
                raw_member_rows_by_order[int(raw_member_row.get("member_order") or 0)] = {
                    "member_order": int(raw_member_row.get("member_order") or 0),
                    "champion_type_id": raw_member_row.get("champion_type_id"),
                    "slot_index": raw_member_row.get("slot_index"),
                    "damage_taken": raw_member_row.get("damage_taken"),
                    "raw_damage_taken": raw_member_row.get("raw_damage_taken"),
                    "member_payload": dict_value(raw_member_row.get("member_payload")),
                    "profile_payload": dict_value(raw_member_row.get("profile_payload")),
                }
        except Exception:
            raw_member_rows_by_order = {}
        try:
            for incoming_row in extract_incoming_target_counts(raw_asset_path):
                incoming_rows_by_order[int(incoming_row.get("member_order") or 0)] = {
                    "incoming_target_events": int(incoming_row.get("incoming_target_events") or 0),
                    "incoming_boss_target_events": int(incoming_row.get("incoming_boss_target_events") or 0),
                    "incoming_enemy_skill_codes": dict_value(incoming_row.get("incoming_enemy_skill_codes")),
                    "incoming_boss_skill_codes": dict_value(incoming_row.get("incoming_boss_skill_codes")),
                }
        except Exception:
            incoming_rows_by_order = {}
        try:
            effect_timeline = dict_value(extract_effect_timeline(raw_asset_path))
        except Exception:
            effect_timeline = {}

    members = []
    for row in member_rows:
        member_order = int(row["member_order"] or 0)
        metrics = metrics_by_member.get(member_order, {})
        raw_row = raw_member_rows_by_order.get(member_order, {})
        incoming = incoming_rows_by_order.get(member_order, {})
        effective_damage_taken = parse_float_value(metrics.get("damage_taken")) or parse_float_value(raw_row.get("damage_taken"))
        members.append(
            {
                "member_order": member_order,
                "champ_id": str(row["champ_id"] or ""),
                "champion_name": str(row["champion_name"] or ""),
                "champion_type_id": int(row["champion_type_id"] or 0),
                "level": int(row["level"] or 0),
                "rank": int(row["rank"] or 0),
                "awakening_level": int(row["awakening_level"] or 0),
                "empowerment_level": int(row["empowerment_level"] or 0),
                "booked": bool(row["booked"]),
                "build_fingerprint": str(row["build_fingerprint"] or ""),
                "set_summary": parse_json_text(str(row["set_summary_json"] or ""), []),
                "tags": parse_json_text(str(row["tags_json"] or ""), []),
                "stats": stats_by_member.get(member_order, {}),
                "metrics": metrics,
                "pressure": {
                    "incoming_target_events": int(incoming.get("incoming_target_events") or 0),
                    "incoming_boss_target_events": int(incoming.get("incoming_boss_target_events") or 0),
                    "incoming_enemy_skill_codes": dict_value(incoming.get("incoming_enemy_skill_codes")),
                    "incoming_boss_skill_codes": dict_value(incoming.get("incoming_boss_skill_codes")),
                    "effective_damage_taken": effective_damage_taken,
                },
                "skill_usage": skill_usage_by_member.get(member_order, []),
                "raw": raw_row,
            }
        )

    member_damage_done_total = round(sum(parse_float_value(dict_value(member.get("metrics")).get("damage_done")) for member in members), 2)
    run_total_damage = parse_float_value(run_row["total_damage"])
    effective_damage_done_total = member_damage_done_total if member_damage_done_total > 0 else run_total_damage

    derived_totals = {
        "damage_done": effective_damage_done_total,
        "damage_done_members_total": member_damage_done_total,
        "damage_done_run_total": run_total_damage,
        "damage_taken": round(sum(parse_float_value(dict_value(member.get("pressure")).get("effective_damage_taken")) for member in members), 2),
        "healing_done": round(sum(parse_float_value(dict_value(member.get("metrics")).get("healing_done")) for member in members), 2),
        "incoming_target_events": sum(int(dict_value(member.get("pressure")).get("incoming_target_events") or 0) for member in members),
        "incoming_boss_target_events": sum(int(dict_value(member.get("pressure")).get("incoming_boss_target_events") or 0) for member in members),
        "skill_casts": sum(sum(int(skill.get("usage_count") or 0) for skill in list(member.get("skill_usage") or [])) for member in members),
    }

    for member in members:
        metrics = dict_value(member.get("metrics"))
        pressure = dict_value(member.get("pressure"))
        skill_usage = list(member.get("skill_usage") or [])
        member["derived"] = {
            "damage_done_share_pct": percent_share(metrics.get("damage_done"), derived_totals["damage_done"]),
            "damage_taken_share_pct": percent_share(pressure.get("effective_damage_taken"), derived_totals["damage_taken"]),
            "healing_done_share_pct": percent_share(metrics.get("healing_done"), derived_totals["healing_done"]),
            "incoming_target_share_pct": percent_share(pressure.get("incoming_target_events"), derived_totals["incoming_target_events"]),
            "incoming_boss_target_share_pct": percent_share(pressure.get("incoming_boss_target_events"), derived_totals["incoming_boss_target_events"]),
            "skill_cast_share_pct": percent_share(sum(int(skill.get("usage_count") or 0) for skill in skill_usage), derived_totals["skill_casts"]),
        }

    return {
        "run": {
            "run_id": int(run_row["run_id"]),
            "saved_at": str(run_row["saved_at"] or ""),
            "source": str(run_row["source"] or ""),
            "source_run_uid": str(run_row["source_run_uid"] or ""),
            "battle_id": str(run_row["battle_id"] or ""),
            "probe_session_slug": str(run_row["probe_session_slug"] or ""),
            "encounter_key": str(run_row["encounter_key"] or ""),
            "encounter_name": str(run_row["encounter_name"] or ""),
            "stage_id": str(run_row["stage_id"] or ""),
            "stage_label": str(run_row["stage_label"] or ""),
            "success": bool(run_row["success"]),
            "completed": bool(run_row["completed"]),
            "elapsed_seconds": parse_float_value(run_row["elapsed_seconds"]),
            "total_damage": parse_float_value(run_row["total_damage"]),
            "labels": parse_json_text(str(run_row["labels_json"] or ""), {}),
            "context": parse_json_text(str(run_row["context_json"] or ""), {}),
            **categorize_run(
                encounter_name=str(run_row["encounter_name"] or ""),
                encounter_key=str(run_row["encounter_key"] or ""),
                stage_id=str(run_row["stage_id"] or ""),
                game_mode=str(run_row["game_mode"] or ""),
                area_region=str(run_row["area_region"] or ""),
            ),
        },
        "derived_totals": derived_totals,
        "members": members,
        "assets": assets,
        "raw_asset_path": str(raw_asset_path) if raw_asset_path else "",
        "effect_timeline": effect_timeline,
    }


def list_run_recorder_sessions(
    output_root: Path = deep_battle_probe.OUTPUT_ROOT,
    recorder: RunRecorderController = RUN_RECORDER,
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    recorder_status = recorder.status()
    import_index = build_run_recorder_db_import_index(db_path)
    session_dirs = [path for path in output_root.iterdir() if path.is_dir()] if output_root.exists() else []
    sessions: List[Dict[str, Any]] = []
    for path in sorted(session_dirs, key=lambda item: item.name, reverse=True):
        session_payload = summarize_run_recorder_session(path, recorder_status=recorder_status, include_recent=False)
        db_import = dict(import_index["by_session"].get(path.name, default_run_recorder_db_import(session_payload.get("run_count", 0))))
        db_import["pending_runs_estimate"] = max(int(session_payload.get("run_count") or 0) - int(db_import.get("imported_runs") or 0), 0)
        session_payload["db_import"] = db_import
        sessions.append(session_payload)
    return {
        "status": recorder_status,
        "summary": {
            "sessions": len(sessions),
            "runs": sum(int(item.get("run_count") or 0) for item in sessions),
            "events": sum(int(item.get("event_count") or 0) for item in sessions),
            "snapshots": sum(int(item.get("snapshot_count") or 0) for item in sessions),
            "running": 1 if recorder_status.get("running") else 0,
            "db_runs": int(import_index.get("runs") or 0),
            "db_sessions": int(import_index.get("sessions") or 0),
        },
        "sessions": sessions,
    }


def run_recorder_session_detail(
    session_slug: str,
    output_root: Path = deep_battle_probe.OUTPUT_ROOT,
    recorder: RunRecorderController = RUN_RECORDER,
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    clean_slug = str(session_slug or "").strip()
    if not clean_slug:
        raise KeyError("Sessione recorder mancante.")
    session_dir = output_root / clean_slug
    if not session_dir.exists() or not session_dir.is_dir():
        raise KeyError(f"Sessione recorder non trovata: {clean_slug}")
    recorder_status = recorder.status()
    payload = summarize_run_recorder_session(session_dir, recorder_status=recorder_status, include_recent=True)
    import_index = build_run_recorder_db_import_index(db_path)
    db_import = dict(import_index["by_session"].get(clean_slug, default_run_recorder_db_import(payload.get("run_count", 0))))
    db_import["pending_runs_estimate"] = max(int(payload.get("run_count") or 0) - int(db_import.get("imported_runs") or 0), 0)
    payload["db_import"] = db_import
    payload["db_runs"] = list_run_history_runs_for_session(clean_slug, db_path=db_path)
    return payload


def import_run_recorder_session(
    session_slug: str,
    db_path: Path = DB_PATH,
    client_root: Path = deep_battle_probe.OUTPUT_ROOT,
    live_root: Path = LIVE_STORAGE_ROOT,
    hero_types_path: Path = HH_HERO_TYPES_PATH,
    recorder: RunRecorderController = RUN_RECORDER,
    allow_running: bool = False,
) -> Dict[str, Any]:
    clean_slug = str(session_slug or "").strip()
    if not clean_slug:
        raise KeyError("Sessione recorder mancante.")
    recorder_status = recorder.status()
    if not allow_running and bool(recorder_status.get("running")) and str(recorder_status.get("session_slug") or "") == clean_slug:
        raise RuntimeError("Ferma prima il recorder per importare questa sessione nel DB.")
    summary = import_probe_session(
        session_slug=clean_slug,
        client_root=client_root,
        live_root=live_root,
        db_path=db_path,
        hero_types_path=hero_types_path,
    )
    summary["ok"] = True
    summary["db_import"] = build_run_recorder_db_import_index(db_path)["by_session"].get(clean_slug, default_run_recorder_db_import())
    return summary


def import_all_run_recorder_sessions(
    db_path: Path = DB_PATH,
    output_root: Path = deep_battle_probe.OUTPUT_ROOT,
    live_root: Path = LIVE_STORAGE_ROOT,
    hero_types_path: Path = HH_HERO_TYPES_PATH,
    recorder: RunRecorderController = RUN_RECORDER,
    include_running: bool = False,
) -> Dict[str, Any]:
    recorder_status = recorder.status()
    running_slug = str(recorder_status.get("session_slug") or "").strip()
    selected_slugs: List[str] = []
    skipped_sessions: List[Dict[str, Any]] = []
    if output_root.exists():
        for path in sorted(output_root.iterdir(), key=lambda item: item.name):
            if not path.is_dir():
                continue
            if not include_running and bool(recorder_status.get("running")) and path.name == running_slug:
                skipped_sessions.append({"session_slug": path.name, "reason": "running"})
                continue
            selected_slugs.append(path.name)
    summary = import_probe_sessions(
        session_slugs=selected_slugs,
        client_root=output_root,
        live_root=live_root,
        db_path=db_path,
        hero_types_path=hero_types_path,
    )
    summary["ok"] = True
    summary["selected_sessions"] = len(selected_slugs)
    summary["skipped_sessions"] = skipped_sessions
    summary["db_summary"] = {
        "runs": build_run_recorder_db_import_index(db_path)["runs"],
        "sessions": build_run_recorder_db_import_index(db_path)["sessions"],
    }
    return summary


def delete_run_recorder_session(
    session_slug: str,
    output_root: Path = deep_battle_probe.OUTPUT_ROOT,
    recorder: RunRecorderController = RUN_RECORDER,
) -> Dict[str, Any]:
    clean_slug = str(session_slug or "").strip()
    if not clean_slug:
        raise KeyError("Sessione recorder mancante.")
    recorder_status = recorder.status()
    if bool(recorder_status.get("running")) and str(recorder_status.get("session_slug") or "") == clean_slug:
        raise RuntimeError("Non posso eliminare una sessione recorder mentre e' ancora attiva.")
    session_dir = output_root / clean_slug
    if not session_dir.exists() or not session_dir.is_dir():
        raise KeyError(f"Sessione recorder non trovata: {clean_slug}")
    shutil.rmtree(session_dir)
    return {
        "ok": True,
        "deleted_session_slug": clean_slug,
        "status": recorder_status,
    }


def list_owned_champions(
    db_path: Path = DB_PATH,
    search: str = "",
    scope: str = "all",
    sort: str = "power",
) -> Dict[str, Any]:
    search_text = search.strip().lower()
    with open_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                ac.champ_id,
                ac.champion_name,
                ac.level,
                ac.rank,
                ac.booked,
                ac.rarity,
                ac.affinity,
                ac.faction,
                CASE WHEN rt.champion_name IS NOT NULL THEN 1 ELSE 0 END AS is_registry_target,
                cc.hellhades_post_id,
                COUNT(DISTINCT CASE WHEN cs.slot IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS skill_rows,
                COUNT(DISTINCT CASE WHEN (
                    cs.cooldown IS NOT NULL
                    OR cs.booked_cooldown IS NOT NULL
                    OR NULLIF(TRIM(COALESCE(cs.skill_type, '')), '') IS NOT NULL
                    OR NULLIF(TRIM(COALESCE(cs.description_clean, cs.description, '')), '') IS NOT NULL
                ) THEN cs.slot || ':' || cs.skill_order END) AS skill_rows_with_data,
                COUNT(DISTINCT CASE WHEN cse.effect_order IS NOT NULL THEN cs.slot || ':' || cs.skill_order END) AS skill_rows_with_effects
            FROM account_champions ac
            LEFT JOIN registry_targets rt
                ON rt.champion_name = ac.champion_name
            LEFT JOIN champion_catalog cc
                ON cc.champion_name = ac.champion_name
            LEFT JOIN champion_skills cs
                ON cs.champion_name = ac.champion_name
            LEFT JOIN champion_skill_effects cse
                ON cse.champion_name = cs.champion_name
                AND cse.slot = cs.slot
            GROUP BY
                ac.champ_id,
                ac.champion_name,
                ac.level,
                ac.rank,
                ac.booked,
                ac.rarity,
                ac.affinity,
                ac.faction,
                is_registry_target,
                cc.hellhades_post_id
            """
        ).fetchall()

    champions_by_name: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        champion = {
            "champ_id": str(row["champ_id"]),
            "champion_name": str(row["champion_name"]),
            "level": int(row["level"] or 0),
            "rank": int(row["rank"] or 0),
            "booked": bool(row["booked"]),
            "rarity": str(row["rarity"] or ""),
            "affinity": str(row["affinity"] or ""),
            "faction": str(row["faction"] or ""),
            "is_registry_target": bool(row["is_registry_target"]),
            "hellhades_post_id": row["hellhades_post_id"],
            "skill_rows": int(row["skill_rows"] or 0),
            "skill_rows_with_data": int(row["skill_rows_with_data"] or 0),
            "skill_rows_with_effects": int(row["skill_rows_with_effects"] or 0),
        }
        champion["data_status"] = classify_skill_data_status(
            champion["skill_rows"],
            champion["skill_rows_with_data"],
        )
        champion["enriched"] = champion["data_status"] == "complete"
        if search_text and search_text not in champion["champion_name"].lower():
            continue
        if scope == "target" and not champion["is_registry_target"]:
            continue
        if scope == "missing" and champion["data_status"] == "complete":
            continue
        current = champions_by_name.get(champion["champion_name"])
        if current is None or champion_sort_key(champion) > champion_sort_key(current):
            champions_by_name[champion["champion_name"]] = champion

    champions = list(champions_by_name.values())

    if sort == "name":
        champions.sort(key=lambda item: (item["champion_name"].lower(), -item["level"], -item["rank"]))
    else:
        champions.sort(
            key=lambda item: (
                -item["level"],
                -item["rank"],
                0 if item["is_registry_target"] else 1,
                item["champion_name"].lower(),
            )
        )

    return {"champions": champions}


def list_owned_champions_with_speed(db_path: Path = DB_PATH) -> List[Dict[str, Any]]:
    with open_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                ac.champ_id,
                ac.champion_name,
                ac.level,
                ac.rank,
                COALESCE(MAX(CASE WHEN acts.stat_name = 'spd' THEN acts.stat_value END), 0) AS spd
            FROM account_champions ac
            LEFT JOIN account_champion_total_stats acts
                ON acts.champ_id = ac.champ_id
            GROUP BY ac.champ_id, ac.champion_name, ac.level, ac.rank
            ORDER BY ac.champion_name ASC, ac.level DESC, ac.rank DESC, ac.champ_id ASC
            """
        ).fetchall()

    champions_by_name: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        item = {
            "champ_id": str(row["champ_id"] or ""),
            "champion_name": str(row["champion_name"] or ""),
            "level": int(row["level"] or 0),
            "rank": int(row["rank"] or 0),
            "speed": parse_float_value(row["spd"]),
        }
        current = champions_by_name.get(item["champion_name"])
        if current is None or champion_sort_key(item) > champion_sort_key(current):
            champions_by_name[item["champion_name"]] = item
    return sorted(champions_by_name.values(), key=lambda row: row["champion_name"].lower())


def clan_boss_preset_map() -> Dict[str, Dict[str, Any]]:
    return {str(item.get("key") or ""): dict(item) for item in CLAN_BOSS_SIM_PRESETS}


def clan_boss_ml_encounter_key(difficulty: str) -> str:
    normalized = str(difficulty or "").strip() or "ultra_nightmare"
    if normalized == "ultra_nightmare":
        return "demon_lord_ultra_nightmare"
    if normalized == "nightmare":
        return "demon_lord_nm"
    return f"demon_lord_{normalized}"


def infer_clan_boss_preset_key(candidate: Dict[str, Any]) -> str:
    roles = {str(item).strip() for item in list(candidate.get("roles") or []) if str(item).strip()}
    capability_tags = {str(item).strip() for item in list(candidate.get("capability_tags") or []) if str(item).strip()}
    if "unkillable" in capability_tags:
        return "unkillable_support"
    if "block_debuffs" in capability_tags:
        return "block_debuffs_support"
    if "ally_protect" in capability_tags:
        return "ally_protect_support"
    if "counterattack" in capability_tags:
        return "counterattack_anchor"
    if "decrease_attack" in capability_tags or "decrease_attack" in roles:
        return "decrease_attack_a1"
    if "hp_burn" in capability_tags or "burner" in roles:
        return "burner"
    if "poison" in capability_tags or "poisoner" in roles:
        return "poisoner"
    if "cleanse" in capability_tags or "cleanse" in roles:
        return "cleanser_speed"
    return "blank"


def apply_clan_boss_preset(member_row: Dict[str, Any], preset_key: str) -> Dict[str, Any]:
    preset = clan_boss_preset_map().get(str(preset_key or "").strip()) or {}
    member_row["preset_key"] = str(preset.get("key") or "blank")
    base_skills = list(default_clan_boss_member_row(int(member_row.get("slot_index") or 1)).get("skills") or [])
    member_row["skills"] = base_skills
    for preset_skill in list(preset.get("skills") or []):
        slot = str(dict_value(preset_skill).get("slot") or "").strip()
        if slot not in {"A1", "A2", "A3", "A4"}:
            continue
        slot_index = {"A1": 0, "A2": 1, "A3": 2, "A4": 3}[slot]
        member_row["skills"][slot_index] = dict(preset_skill)
    return member_row


def candidate_to_clan_boss_member_row(candidate: Dict[str, Any], slot_index: int) -> Dict[str, Any]:
    return build_candidate_clan_boss_member_row(candidate, slot_index)


def build_clan_boss_recommendations(
    difficulty: str = "ultra_nightmare",
    affinity: str = "void",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    normalized_difficulty = str(difficulty or "").strip() or "ultra_nightmare"
    normalized_affinity = str(affinity or "").strip() or "void"
    report = build_team_optimizer_report(
        boss_key="demon_lord",
        level_key=normalized_difficulty,
        affinity=normalized_affinity,
        db_path=db_path,
    )
    heuristic_candidates = list(report.get("selected_team") or [])[:5]
    heuristic_team = [
        candidate_to_clan_boss_member_row(candidate, index)
        for index, candidate in enumerate(heuristic_candidates, start=1)
    ]
    heuristic_simulation = simulate_candidate_team(
        heuristic_candidates,
        difficulty=normalized_difficulty,
        affinity=normalized_affinity,
        max_boss_turns=6,
    ) if heuristic_candidates else {}
    response: Dict[str, Any] = {
        "heuristic": {
            "available": bool(heuristic_team),
            "label": "Consiglio CB Forge",
            "source": "team_optimizer",
            "team": heuristic_team,
            "team_names": [str(member.get("champion_name") or "") for member in heuristic_team],
            "warnings": list(report.get("warnings") or []) + list(dict_value(heuristic_simulation.get("summary")).get("warnings") or []),
            "notes": list(report.get("notes") or []),
            "build_requirements": list(dict_value(report.get("team_fit")).get("build_requirements") or []),
            "simulation": heuristic_simulation if heuristic_simulation.get("ok") else {},
        },
        "ai": {
            "available": False,
            "label": "Consiglio AI",
            "source": "ml_team_baseline",
            "team": [],
            "team_names": [],
            "warnings": [],
            "notes": [],
        },
    }

    try:
        from ml_team_baseline import default_model_path, recommend_best_team_from_candidates
    except Exception as exc:
        response["ai"]["warnings"] = [f"Modulo AI non disponibile: {exc}"]
        return response

    ml_encounter_key = clan_boss_ml_encounter_key(normalized_difficulty)
    model_path = MODEL_DIR / default_model_path(ml_encounter_key).name
    if not model_path.exists():
        response["ai"]["warnings"] = [f"Modello AI non trovato: {model_path.name}"]
        return response

    try:
        ai_payload = recommend_best_team_from_candidates(
            candidates=list(report.get("candidates") or []),
            encounter_key=ml_encounter_key,
            difficulty=normalized_difficulty,
            boss_affinity=normalized_affinity,
            model_path=model_path,
        )
    except Exception as exc:
        response["ai"]["warnings"] = [f"AI non disponibile: {exc}"]
        return response

    ai_candidates = list(ai_payload.get("best_team") or [])
    ai_team = [
        candidate_to_clan_boss_member_row(candidate, index)
        for index, candidate in enumerate(ai_candidates, start=1)
    ]
    ai_simulation = simulate_candidate_team(
        ai_candidates,
        difficulty=normalized_difficulty,
        affinity=normalized_affinity,
        max_boss_turns=6,
    ) if ai_candidates else {}
    response["ai"] = {
        "available": bool(ai_team),
        "label": "Consiglio AI",
        "source": "ml_team_baseline",
        "team": ai_team,
        "team_names": [str(member.get("champion_name") or "") for member in ai_team],
        "predicted_total_damage": parse_float_value(ai_payload.get("predicted_total_damage")),
        "predicted_success_probability": ai_payload.get("predicted_success_probability"),
        "evaluated_combinations": int(ai_payload.get("evaluated_combinations") or 0),
        "pool_size": int(ai_payload.get("pool_size") or 0),
        "model_path": str(ai_payload.get("model_path") or ""),
        "warnings": list(dict_value(ai_simulation.get("summary")).get("warnings") or []),
        "notes": [
            f"Combinazioni valutate: {int(ai_payload.get('evaluated_combinations') or 0)}",
            f"Danno previsto: {parse_float_value(ai_payload.get('predicted_total_damage')):.0f}",
        ],
        "simulation": ai_simulation if ai_simulation.get("ok") else {},
    }
    if ai_payload.get("predicted_success_probability") is not None:
        response["ai"]["notes"].append(
            f"Probabilita successo: {parse_float_value(ai_payload.get('predicted_success_probability')) * 100:.1f}%"
        )
    return response


def _run_identity(row: Dict[str, Any] | sqlite3.Row) -> str:
    source_run_uid = str(row["source_run_uid"] or "").strip() if "source_run_uid" in row.keys() else ""
    if source_run_uid:
        return source_run_uid
    battle_id = str(row["battle_id"] or "").strip() if "battle_id" in row.keys() else ""
    if battle_id:
        return battle_id
    return f"run:{int(row['run_id'])}"


def build_ai_training_advisor(
    encounters: List[Dict[str, Any]],
    categories: List[Dict[str, Any]],
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    ensure_schema(db_path)
    duplicate_groups = 0
    duplicate_rows = 0
    unique_damage_runs: List[Dict[str, Any]] = []
    members_by_run_id: Dict[int, List[str]] = {}

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        duplicate_row = conn.execute(
            """
            SELECT
                COUNT(*) AS duplicate_groups,
                COALESCE(SUM(duplicate_count - 1), 0) AS duplicate_rows
            FROM (
                SELECT COUNT(*) AS duplicate_count
                FROM run_history_runs
                WHERE NULLIF(TRIM(COALESCE(source_run_uid, '')), '') IS NOT NULL
                GROUP BY source, source_run_uid
                HAVING COUNT(*) > 1
            )
            """
        ).fetchone()
        if duplicate_row is not None:
            duplicate_groups = int(duplicate_row["duplicate_groups"] or 0)
            duplicate_rows = int(duplicate_row["duplicate_rows"] or 0)

        damage_rows = conn.execute(
            """
            SELECT
                run_id,
                source_run_uid,
                battle_id,
                encounter_key,
                encounter_name,
                stage_id,
                game_mode,
                area_region,
                boss_affinity,
                total_damage,
                saved_at
            FROM run_history_runs
            WHERE total_damage IS NOT NULL
            ORDER BY saved_at ASC, run_id ASC
            """
        ).fetchall()

        seen_identities: set[str] = set()
        unique_run_ids: List[int] = []
        for row in damage_rows:
            identity = _run_identity(row)
            if identity in seen_identities:
                continue
            seen_identities.add(identity)
            unique_damage_runs.append(
                {
                    "run_id": int(row["run_id"]),
                    "encounter_key": str(row["encounter_key"] or ""),
                    "encounter_name": str(row["encounter_name"] or ""),
                    "stage_id": str(row["stage_id"] or ""),
                    "game_mode": str(row["game_mode"] or ""),
                    "area_region": str(row["area_region"] or ""),
                    "boss_affinity": str(row["boss_affinity"] or ""),
                    "total_damage": parse_float_value(row["total_damage"]),
                    "category": categorize_run(
                        encounter_name=str(row["encounter_name"] or ""),
                        encounter_key=str(row["encounter_key"] or ""),
                        stage_id=str(row["stage_id"] or ""),
                        game_mode=str(row["game_mode"] or ""),
                        area_region=str(row["area_region"] or ""),
                    ),
                }
            )
            unique_run_ids.append(int(row["run_id"]))

        if unique_run_ids:
            placeholders = ", ".join("?" for _ in unique_run_ids)
            member_rows = conn.execute(
                f"""
                SELECT run_id, member_order, champion_name
                FROM run_history_members
                WHERE run_id IN ({placeholders})
                ORDER BY run_id ASC, member_order ASC
                """,
                unique_run_ids,
            ).fetchall()
            for member_row in member_rows:
                members_by_run_id.setdefault(int(member_row["run_id"]), []).append(str(member_row["champion_name"] or ""))

    train_ready_encounters = [item for item in encounters if bool(item.get("train_ready"))]
    best_train_ready = (
        sorted(
            train_ready_encounters,
            key=lambda item: (
                int(item.get("runs_with_damage") or 0),
                int(item.get("run_count") or 0),
                str(item.get("encounter_key") or ""),
            ),
            reverse=True,
        )[0]
        if train_ready_encounters
        else {}
    )

    skill_category_keys = {"dungeon_boss", "stage_pve", "special_pve_unmapped"}
    skill_capture_runs = sum(int(item.get("run_count") or 0) for item in categories if str(item.get("category_key") or "") in skill_category_keys)
    clan_boss_runs = [row for row in unique_damage_runs if str(dict_value(row.get("category")).get("category_key")) == "clan_boss"]
    clan_boss_team_counter: Counter[str] = Counter()
    for row in clan_boss_runs:
        team_signature = " / ".join(members_by_run_id.get(int(row["run_id"]), []))
        if team_signature:
            clan_boss_team_counter[team_signature] += 1
    clan_boss_unique_teams = len(clan_boss_team_counter)
    dominant_team_signature = ""
    dominant_team_runs = 0
    if clan_boss_team_counter:
        dominant_team_signature, dominant_team_runs = clan_boss_team_counter.most_common(1)[0]
    dominant_team_share = (dominant_team_runs / len(clan_boss_runs)) if clan_boss_runs else 0.0

    headline = "Dataset ancora in raccolta: conviene usarlo per capire skill e rotazioni, non ancora per fidarsi di un optimizer forte."
    if duplicate_groups > 0:
        headline = "Prima pulisci i duplicati: i conteggi del dataset sono gonfiati e il training rischia di imparare due volte la stessa run."
    elif train_ready_encounters and clan_boss_unique_teams >= 4 and len(clan_boss_runs) >= 12:
        headline = "Hai abbastanza varieta' per iniziare un baseline mirato su target specifici, tenendo il consigliere euristico come rete di sicurezza."
    elif train_ready_encounters:
        headline = "Puoi gia' allenare un baseline leggero su target specifici, ma serve ancora piu' varieta' per consigli affidabili sui team."

    next_actions: List[Dict[str, Any]] = []
    if duplicate_groups > 0:
        next_actions.append(
            {
                "priority": "adesso",
                "title": "Ripulisci i duplicati importati",
                "detail": f"Ho trovato {duplicate_groups} gruppi duplicati per un totale di {duplicate_rows} righe in eccesso. Pulisci prima di leggere i conteggi del dataset o allenare modelli.",
            }
        )
    if skill_capture_runs < 12:
        next_actions.append(
            {
                "priority": "adesso",
                "title": "Raccogli run PvE per capire meglio le skill",
                "detail": f"Hai {skill_capture_runs} run fuori dal Clan Boss nelle categorie piu' utili alla lettura delle skill. Punta a 10-15 run ripetibili tra dungeon boss, wave e contenuti con pattern chiari.",
            }
        )
    if len(clan_boss_runs) > 0 and clan_boss_unique_teams < 4:
        next_actions.append(
            {
                "priority": "adesso",
                "title": "Aumenta la varieta' dei team Clan Boss",
                "detail": f"Le run Clan Boss con damage coprono {clan_boss_unique_teams} team distinti. Prima del training serio prova almeno 4-5 team diversi o varianti con un solo cambio per volta.",
            }
        )
    if dominant_team_share >= 0.65 and dominant_team_signature:
        next_actions.append(
            {
                "priority": "presto",
                "title": "Cambia una sola variabile per serie di test",
                "detail": f"Il team piu' frequente copre il {dominant_team_share * 100:.0f}% delle run Clan Boss con damage. Fai mini-serie cambiando solo 1 membro, 1 set o 1 speed tune per dare segnali piu' utili all'AI.",
            }
        )
    if best_train_ready:
        next_actions.append(
            {
                "priority": "presto",
                "title": "Allena prima il target piu' pronto",
                "detail": f"Il target piu' maturo e' {best_train_ready.get('encounter_name') or best_train_ready.get('encounter_key')} con {int(best_train_ready.get('runs_with_damage') or 0)} run con total_damage.",
            }
        )
    else:
        next_actions.append(
            {
                "priority": "presto",
                "title": "Concentra il farming su un target singolo",
                "detail": "Per partire con il baseline serve almeno un encounter con 3 run o piu' dotate di total_damage e qualche variante di team reale.",
            }
        )

    content_focus: List[Dict[str, Any]] = []
    category_by_key = {str(item.get("category_key") or ""): item for item in categories}
    for category_key, why_now in (
        ("dungeon_boss", "Ideale per leggere rotazioni, opener, buff/debuff e pattern ripetibili."),
        ("stage_pve", "Utile per targeting, AOE opener e velocita' di clear sulle wave."),
        ("clan_boss", "Serve per misurare resa reale, stabilita' lunga, affinita' e speed tune."),
    ):
        category_row = dict(category_by_key.get(category_key) or {})
        content_focus.append(
            {
                "category_key": category_key,
                "category_label": str(category_row.get("category_label") or RUN_CATEGORY_LABELS.get(category_key, category_key)),
                "run_count": int(category_row.get("run_count") or 0),
                "runs_with_damage": int(category_row.get("runs_with_damage") or 0),
                "why_now": why_now,
            }
        )

    recommended_targets = sorted(
        encounters,
        key=lambda item: (
            int(item.get("runs_with_damage") or 0),
            int(item.get("run_count") or 0),
            str(item.get("encounter_key") or ""),
        ),
        reverse=True,
    )[:3]

    return {
        "headline": headline,
        "health": {
            "duplicate_groups": duplicate_groups,
            "duplicate_rows": duplicate_rows,
            "distinct_damage_runs": len(unique_damage_runs),
            "clan_boss_damage_runs": len(clan_boss_runs),
            "clan_boss_unique_teams": clan_boss_unique_teams,
            "skill_capture_runs": skill_capture_runs,
        },
        "next_actions": next_actions[:5],
        "content_focus": content_focus,
        "recommended_targets": [
            {
                "encounter_key": str(item.get("encounter_key") or ""),
                "encounter_name": str(item.get("encounter_name") or item.get("encounter_key") or ""),
                "difficulty": str(item.get("difficulty") or ""),
                "boss_affinity": str(item.get("boss_affinity") or ""),
                "runs_with_damage": int(item.get("runs_with_damage") or 0),
                "run_count": int(item.get("run_count") or 0),
                "train_ready": bool(item.get("train_ready")),
            }
            for item in recommended_targets
        ],
    }


def build_ai_training_overview(db_path: Path = DB_PATH) -> Dict[str, Any]:
    ensure_schema(db_path)
    try:
        from ml_team_baseline import MODEL_VERSION, ai_dependency_status, default_model_path
    except Exception as exc:
        return {
            "ai_available": False,
            "training_available": False,
            "error": str(exc),
            "model_version": "",
            "encounters": [],
            "categories": [],
            "summary": {"encounters": 0, "models_present": 0, "runs": 0, "runs_with_damage": 0},
        }
    dependency_status = ai_dependency_status()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT
                encounter_key,
                encounter_name,
                encounter_family,
                area_region,
                game_mode,
                MIN(NULLIF(TRIM(COALESCE(stage_id, '')), '')) AS sample_stage_id,
                difficulty,
                boss_affinity,
                COUNT(*) AS run_count,
                SUM(CASE WHEN total_damage IS NOT NULL THEN 1 ELSE 0 END) AS runs_with_damage,
                AVG(total_damage) AS avg_total_damage,
                MAX(saved_at) AS last_seen_at
            FROM run_history_runs
            GROUP BY encounter_key, encounter_name, encounter_family, area_region, game_mode, difficulty, boss_affinity
            ORDER BY
                SUM(CASE WHEN total_damage IS NOT NULL THEN 1 ELSE 0 END) DESC,
                COUNT(*) DESC,
                encounter_key ASC
            """
        ).fetchall()

    encounters: List[Dict[str, Any]] = []
    category_rows: Dict[str, Dict[str, Any]] = {}
    models_present = 0
    total_runs = 0
    total_runs_with_damage = 0
    for row in rows:
        encounter_key = str(row["encounter_key"] or "").strip()
        model_path = MODEL_DIR / default_model_path(encounter_key).name
        model_exists = model_path.exists()
        if model_exists:
            models_present += 1
        run_count = int(row["run_count"] or 0)
        runs_with_damage = int(row["runs_with_damage"] or 0)
        total_runs += run_count
        total_runs_with_damage += runs_with_damage
        model_updated_at = ""
        if model_exists:
            model_updated_at = datetime.fromtimestamp(model_path.stat().st_mtime, tz=timezone.utc).replace(microsecond=0).isoformat()
        category_info = categorize_run(
            encounter_name=str(row["encounter_name"] or ""),
            encounter_key=encounter_key,
            stage_id=str(row["sample_stage_id"] or ""),
            game_mode=str(row["game_mode"] or ""),
            area_region=str(row["area_region"] or ""),
        )
        encounters.append(
            {
                "encounter_key": encounter_key,
                "encounter_name": str(row["encounter_name"] or encounter_key),
                "encounter_family": str(row["encounter_family"] or ""),
                "area_region": str(row["area_region"] or ""),
                "game_mode": str(row["game_mode"] or ""),
                "sample_stage_id": str(row["sample_stage_id"] or ""),
                "difficulty": str(row["difficulty"] or ""),
                "boss_affinity": str(row["boss_affinity"] or ""),
                "run_count": run_count,
                "runs_with_damage": runs_with_damage,
                "avg_total_damage": parse_float_value(row["avg_total_damage"]),
                "last_seen_at": str(row["last_seen_at"] or ""),
                "model_path": str(model_path),
                "model_exists": model_exists,
                "model_updated_at": model_updated_at,
                "train_ready": runs_with_damage >= 3,
                **category_info,
            }
        )
        bucket = category_rows.setdefault(
            category_info["category_key"],
            {
                "category_key": category_info["category_key"],
                "category_label": category_info["category_label"],
                "encounter_count": 0,
                "run_count": 0,
                "runs_with_damage": 0,
                "examples": [],
            },
        )
        bucket["encounter_count"] = int(bucket["encounter_count"] or 0) + 1
        bucket["run_count"] = int(bucket["run_count"] or 0) + run_count
        bucket["runs_with_damage"] = int(bucket["runs_with_damage"] or 0) + runs_with_damage
        examples = list(bucket.get("examples") or [])
        encounter_name = str(row["encounter_name"] or encounter_key)
        if encounter_name and encounter_name not in examples:
            examples.append(encounter_name)
        bucket["examples"] = examples[:5]

    categories = sorted(
        category_rows.values(),
        key=lambda item: (-int(item.get("run_count") or 0), str(item.get("category_label") or "")),
    )

    return {
        "ai_available": True,
        "training_available": bool(dependency_status.get("ok")),
        "error": str(dependency_status.get("error") or ""),
        "dependency_detail": str(dependency_status.get("detail") or ""),
        "dependency_runtime": dict(dependency_status.get("runtime") or {}),
        "model_version": MODEL_VERSION,
        "encounters": encounters,
        "categories": categories,
        "summary": {
            "encounters": len(encounters),
            "models_present": models_present,
            "runs": total_runs,
            "runs_with_damage": total_runs_with_damage,
        },
        "advisor": build_ai_training_advisor(
            encounters=encounters,
            categories=categories,
            db_path=db_path,
        ),
    }


def train_ai_baseline_model(
    encounter_key: str,
    db_path: Path = DB_PATH,
    output_path: Path | None = None,
) -> Dict[str, Any]:
    normalized_encounter_key = str(encounter_key or "").strip()
    if not normalized_encounter_key:
        raise ValueError("Encounter mancante per il training AI.")

    from ml_team_baseline import default_model_path, train_from_database

    resolved_output = output_path or (MODEL_DIR / default_model_path(normalized_encounter_key).name)
    summary = train_from_database(
        db_path=db_path,
        encounter_key=normalized_encounter_key,
        output_path=resolved_output,
    )
    return {
        "ok": True,
        "encounter_key": normalized_encounter_key,
        "training": summary,
        "overview": build_ai_training_overview(db_path=db_path),
    }


def cleanup_ai_training_duplicates(
    db_path: Path = DB_PATH,
    source: str = "probe_import",
) -> Dict[str, Any]:
    cleanup = cleanup_duplicate_run_history_runs(db_path=db_path, source=source)
    return {
        "ok": True,
        "cleanup": cleanup,
        "overview": build_ai_training_overview(db_path=db_path),
    }


def build_clan_boss_simulator_bootstrap(db_path: Path = DB_PATH) -> Dict[str, Any]:
    roster = list_owned_champions_with_speed(db_path=db_path)
    roster_speed_by_name = {
        str(item.get("champion_name") or ""): parse_float_value(item.get("speed"), 0.0)
        for item in roster
        if str(item.get("champion_name") or "").strip()
    }
    recommendations = build_clan_boss_recommendations(
        difficulty="ultra_nightmare",
        affinity="void",
        db_path=db_path,
    )
    default_team = list(dict_value(recommendations.get("heuristic")).get("team") or [])[:5]
    for member in default_team:
        champion_name = str(dict_value(member).get("champion_name") or "").strip()
        roster_speed = roster_speed_by_name.get(champion_name)
        if roster_speed:
            member["speed"] = roster_speed
    while len(default_team) < 5:
        default_team.append(default_clan_boss_member_row(len(default_team) + 1))

    return {
        "difficulty_options": [
            {"key": key, "label": str(value.get("label") or key), "boss_speed": parse_float_value(value.get("boss_speed"))}
            for key, value in CLAN_BOSS_SIM_DIFFICULTIES.items()
        ],
        "affinity_options": CLAN_BOSS_SIM_AFFINITY_OPTIONS,
        "effect_library": CLAN_BOSS_SIM_EFFECT_LIBRARY,
        "team_presets": CLAN_BOSS_SIM_PRESETS,
        "champions": roster,
        "default_team": default_team,
        "recommendations": recommendations,
    }


def build_team_optimizer_view(
    boss_key: str = "demon_lord",
    level_key: str = "ultra_nightmare",
    affinity: str = "void",
    recommendation_source: str = "optimizer",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    return {
        "targets": list_team_optimizer_targets(),
        "selection": {
            "boss_key": boss_key,
            "level_key": level_key,
            "affinity": affinity,
            "recommendation_source": recommendation_source,
        },
        "boss_intel": build_boss_intel(
            boss_key=boss_key,
            level_key=level_key,
            affinity=affinity,
        ),
        "training_overview": build_ai_training_overview(db_path=db_path),
        "report": _cached_team_optimizer_report(
            boss_key=boss_key,
            level_key=level_key,
            affinity=affinity,
            recommendation_source=recommendation_source,
            db_path=db_path,
        ),
    }


def _optimizer_cache_key(
    boss_key: str,
    level_key: str,
    affinity: str,
    recommendation_source: str,
    db_path: Path,
) -> tuple[str, str, str, str, str, int]:
    resolved = Path(db_path)
    try:
        mtime_ns = resolved.stat().st_mtime_ns
    except FileNotFoundError:
        mtime_ns = 0
    return (
        str(boss_key or "").strip(),
        str(level_key or "").strip(),
        str(affinity or "").strip(),
        str(recommendation_source or "").strip().lower() or "optimizer",
        str(resolved.resolve()),
        int(mtime_ns),
    )


def _cache_fetch(cache: Dict[tuple[str, str, str, str, str, int], Dict[str, Any]], key: tuple[str, str, str, str, str, int]) -> Optional[Dict[str, Any]]:
    now = time.monotonic()
    with TEAM_OPTIMIZER_CACHE_LOCK:
        cached = cache.get(key)
        if not cached:
            return None
        expires_at = float(cached.get("expires_at") or 0.0)
        if expires_at <= now:
            cache.pop(key, None)
            return None
        return copy.deepcopy(dict(cached.get("payload") or {}))


def _cache_store(
    cache: Dict[tuple[str, str, str, str, str, int], Dict[str, Any]],
    key: tuple[str, str, str, str, str, int],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    now = time.monotonic()
    with TEAM_OPTIMIZER_CACHE_LOCK:
        cache[key] = {
            "expires_at": now + TEAM_OPTIMIZER_CACHE_TTL_SECONDS,
            "payload": copy.deepcopy(payload),
        }
    return copy.deepcopy(payload)


def _cached_team_optimizer_report(
    boss_key: str,
    level_key: str,
    affinity: str,
    recommendation_source: str,
    db_path: Path,
) -> Dict[str, Any]:
    key = _optimizer_cache_key(boss_key, level_key, affinity, recommendation_source, db_path)
    cached = _cache_fetch(TEAM_OPTIMIZER_REPORT_CACHE, key)
    if cached is not None:
        return cached
    payload = build_team_optimizer_report(
        boss_key=boss_key,
        level_key=level_key,
        affinity=affinity,
        recommendation_source=recommendation_source,
        db_path=db_path,
    )
    return _cache_store(TEAM_OPTIMIZER_REPORT_CACHE, key, payload)


def build_team_optimizer_loadout(
    boss_key: str = "demon_lord",
    level_key: str = "ultra_nightmare",
    affinity: str = "void",
    recommendation_source: str = "optimizer",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    cache_key = _optimizer_cache_key(boss_key, level_key, affinity, recommendation_source, db_path)
    cached_loadout = _cache_fetch(TEAM_OPTIMIZER_LOADOUT_CACHE, cache_key)
    if cached_loadout is not None:
        return cached_loadout
    report = _cached_team_optimizer_report(
        boss_key=boss_key,
        level_key=level_key,
        affinity=affinity,
        recommendation_source=recommendation_source,
        db_path=db_path,
    )

    team_loadout: List[Dict[str, Any]] = []
    item_usage: Dict[str, List[Dict[str, Any]]] = {}
    total_swap_count = 0
    total_inventory_items = 0
    total_borrowed_items = 0

    selected_team = list(report.get("selected_team") or [])
    area_region = optimizer_area_region_for_boss(boss_key)

    def _resolve_member_loadout_candidates(member: Dict[str, Any]) -> List[Dict[str, Any]]:
        champion_name = str(member.get("champion_name") or "").strip()
        profile_key = str(member.get("default_build") or "support_general").strip() or "support_general"
        if profile_key == "support_general":
            profile_key = "support_tank"
        if not champion_name:
            return []

        plan = build_champion_plan(
            champion_name,
            profile_key=profile_key,
            area_region=area_region,
            db_path=db_path,
        )
        candidate_builds = [dict(plan.get("current_build") or {})] + [dict(row) for row in list(plan.get("proposals") or [])]
        unique_candidates: List[Dict[str, Any]] = []
        seen_signatures: set[str] = set()
        for build in candidate_builds:
            items = list(build.get("items") or [])
            item_signature = "|".join(sorted(str(item.get("item_id") or "").strip() for item in items if str(item.get("item_id") or "").strip()))
            if item_signature in seen_signatures:
                continue
            seen_signatures.add(item_signature)
            summarized_items: List[Dict[str, Any]] = []
            for item in items:
                item_id = str(item.get("item_id") or "").strip()
                slot_name = str(item.get("slot") or "").strip()
                source_kind = str(item.get("source_kind") or "").strip()
                summarized_items.append(
                    {
                        "item_id": item_id,
                        "slot": slot_name,
                        "set_name": str(item.get("set_name") or ""),
                        "source_kind": source_kind,
                        "source_label": str(item.get("source_label") or ""),
                        "owner_name": str(item.get("owner_name") or ""),
                        "equipped_by": str(item.get("equipped_by") or ""),
                        "main_stat_type": str(item.get("main_stat_type") or ""),
                        "main_stat_value": item.get("main_stat_value"),
                        "rarity": str(item.get("rarity") or ""),
                        "rank": int(item.get("rank") or 0),
                        "level": int(item.get("level") or 0),
                    }
                )
            unique_candidates.append(
                {
                    "champion_name": champion_name,
                    "champ_id": str(member.get("champ_id") or "").strip(),
                    "default_build": profile_key,
                    "optimizer_score": member.get("score"),
                    "build_label": str(build.get("label") or ""),
                    "build_score": float(build.get("score") or 0.0),
                    "swap_count": int(build.get("swap_count") or 0),
                    "inventory_items": int(build.get("inventory_items") or 0),
                    "borrowed_items": int(build.get("borrowed_items") or 0),
                    "scope_label": str(build.get("scope_label") or ""),
                    "set_coherence": dict(build.get("set_coherence") or {}),
                    "items": summarized_items,
                }
            )
        unique_candidates.sort(
            key=lambda row: (
                -float(row.get("build_score") or 0.0),
                int(row.get("swap_count") or 0),
                int(row.get("borrowed_items") or 0),
                str(row.get("build_label") or ""),
            )
        )
        return unique_candidates

    max_workers = min(4, max(1, len(selected_team)))
    if len(selected_team) <= 1:
        resolved_rows = [_resolve_member_loadout_candidates(member) for member in selected_team]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            resolved_rows = list(executor.map(_resolve_member_loadout_candidates, selected_team))

    member_candidate_rows = [rows for rows in resolved_rows if rows]
    chosen_rows: List[Dict[str, Any]] = []
    if member_candidate_rows:
        best_choice: List[Dict[str, Any]] = []
        best_signature: Optional[tuple[int, int, float, int, int]] = None
        for combo in itertools.product(*member_candidate_rows):
            usage_by_item: Dict[str, int] = {}
            for row in combo:
                for item in list(row.get("items") or []):
                    item_id = str(item.get("item_id") or "").strip()
                    if item_id:
                        usage_by_item[item_id] = usage_by_item.get(item_id, 0) + 1
            duplicate_overages = sum(max(0, count - 1) for count in usage_by_item.values())
            duplicate_groups = sum(1 for count in usage_by_item.values() if count > 1)
            total_build_score = round(sum(float(row.get("build_score") or 0.0) for row in combo), 4)
            total_combo_swaps = sum(int(row.get("swap_count") or 0) for row in combo)
            total_combo_borrowed = sum(int(row.get("borrowed_items") or 0) for row in combo)
            signature = (
                duplicate_overages,
                duplicate_groups,
                -total_build_score,
                total_combo_swaps,
                total_combo_borrowed,
            )
            if best_signature is None or signature < best_signature:
                best_signature = signature
                best_choice = [dict(row) for row in combo]
        chosen_rows = best_choice

    for row in chosen_rows:
        total_swap_count += int(row.get("swap_count") or 0)
        total_inventory_items += int(row.get("inventory_items") or 0)
        total_borrowed_items += int(row.get("borrowed_items") or 0)
        for item in list(row.get("items") or []):
            item_id = str(item.get("item_id") or "").strip()
            if item_id:
                item_usage.setdefault(item_id, []).append(
                    {
                        "champion_name": str(row.get("champion_name") or ""),
                        "slot": str(item.get("slot") or ""),
                        "source_kind": str(item.get("source_kind") or ""),
                    }
                )
        team_loadout.append(row)

    conflicts = [
        {
            "item_id": item_id,
            "usage": usage_rows,
        }
        for item_id, usage_rows in sorted(item_usage.items())
        if len(usage_rows) > 1
    ]

    conflict_item_ids = {str(conflict["item_id"]) for conflict in conflicts}
    for row in team_loadout:
        row["conflict_item_ids"] = [
            str(item.get("item_id") or "")
            for item in list(row.get("items") or [])
            if str(item.get("item_id") or "") in conflict_item_ids
        ]

    payload = {
        "target": dict(report.get("target") or {}),
        "team": team_loadout,
        "conflicts": conflicts,
        "summary": {
            "champions": len(team_loadout),
            "total_swap_count": total_swap_count,
            "total_inventory_items": total_inventory_items,
            "total_borrowed_items": total_borrowed_items,
            "conflict_count": len(conflicts),
        },
    }
    return _cache_store(TEAM_OPTIMIZER_LOADOUT_CACHE, cache_key, payload)


def load_primary_champion_ids(champion_names: List[str], db_path: Path = DB_PATH) -> Dict[str, str]:
    normalized_names = sorted({str(name or "").strip() for name in champion_names if str(name or "").strip()})
    if not normalized_names:
        return {}
    ensure_schema(db_path)
    placeholders = ",".join("?" for _ in normalized_names)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT champ_id, champion_name, level, rank, booked
            FROM account_champions
            WHERE champion_name IN ({placeholders})
            ORDER BY champion_name ASC, level DESC, rank DESC, booked DESC, champ_id ASC
            """,
            normalized_names,
        ).fetchall()
    name_to_id: Dict[str, str] = {}
    for row in rows:
        champion_name = str(row["champion_name"] or "").strip()
        champ_id = str(row["champ_id"] or "").strip()
        if champion_name and champ_id and champion_name not in name_to_id:
            name_to_id[champion_name] = champ_id
    return name_to_id


def simulate_team_optimizer_opening_preferences(
    boss_key: str = "demon_lord",
    level_key: str = "ultra_nightmare",
    affinity: str = "void",
    recommendation_source: str = "optimizer",
    opener_preferences: Optional[Mapping[str, Any]] = None,
    max_boss_turns: int = 6,
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    if str(boss_key or "").strip().lower() != "demon_lord":
        raise ValueError("Le preferenze opener del simulatore optimizer sono disponibili solo per Clan Boss.")

    report = _cached_team_optimizer_report(
        boss_key=boss_key,
        level_key=level_key,
        affinity=affinity,
        recommendation_source=recommendation_source,
        db_path=db_path,
    )
    selected_team = [dict(row) for row in list(report.get("selected_team") or [])]
    if not selected_team:
        raise ValueError("Nessun team optimizer disponibile da simulare.")
    valid_names = {str(row.get("champion_name") or "").strip() for row in selected_team if str(row.get("champion_name") or "").strip()}

    normalized_preferences: Dict[str, str] = {}
    for champion_name, raw_slot in dict(opener_preferences or {}).items():
        normalized_name = str(champion_name or "").strip()
        normalized_slot = str(raw_slot or "").strip().upper()
        if not normalized_name or normalized_name not in valid_names or not normalized_slot:
            continue
        if normalized_slot == "AUTO":
            continue
        if normalized_slot not in {"A1", "A2", "A3", "A4", "NONE"}:
            continue
        normalized_preferences[normalized_name] = normalized_slot

    member_rows = [
        build_candidate_clan_boss_member_row(
            candidate,
            index,
            opener_slot=normalized_preferences.get(str(candidate.get("champion_name") or "").strip()),
        )
        for index, candidate in enumerate(selected_team, start=1)
    ]
    simulation = simulate_candidate_team(
        selected_team,
        difficulty=str(level_key or "").strip() or "ultra_nightmare",
        affinity=str(affinity or "").strip() or "void",
        max_boss_turns=max(3, int(max_boss_turns or 6)),
        opener_overrides=normalized_preferences,
    )
    return {
        "ok": bool(simulation.get("ok")),
        "target": dict(report.get("target") or {}),
        "preferences": normalized_preferences,
        "members": member_rows,
        "simulation": simulation,
    }


def ensure_local_hh_bridge_built() -> Path:
    if LOCAL_HH_BRIDGE_DLL.exists():
        dll_mtime = LOCAL_HH_BRIDGE_DLL.stat().st_mtime
        if all(path.exists() and path.stat().st_mtime <= dll_mtime for path in LOCAL_HH_BRIDGE_SOURCES):
            return LOCAL_HH_BRIDGE_DLL
    if not LOCAL_HH_BRIDGE_PROJECT.exists():
        raise FileNotFoundError(f"Bridge locale non trovato: {LOCAL_HH_BRIDGE_PROJECT}")
    subprocess.run(
        ["dotnet", "build", str(LOCAL_HH_BRIDGE_PROJECT), "-c", "Release", "--nologo"],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    if not LOCAL_HH_BRIDGE_DLL.exists():
        raise FileNotFoundError(f"Build bridge locale non riuscita: {LOCAL_HH_BRIDGE_DLL}")
    return LOCAL_HH_BRIDGE_DLL


def invoke_local_hh_bridge(command: str, *arguments: str) -> Dict[str, Any]:
    bridge_dll = ensure_local_hh_bridge_built()
    completed = subprocess.run(
        ["dotnet", str(bridge_dll), str(command), *[str(argument) for argument in arguments]],
        cwd=BASE_DIR,
        capture_output=True,
        text=True,
        check=True,
    )
    stdout = completed.stdout.strip()
    if not stdout:
        raise RuntimeError("Bridge locale senza output.")
    try:
        return json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Output bridge locale non valido: {stdout}") from exc


def ensure_local_hh_bridge_ready() -> Dict[str, Any]:
    status = invoke_local_hh_bridge("status")
    if not bool(status.get("ok")):
        raise RuntimeError("Bridge locale HH non pronto.")
    if not bool(status.get("raid_running")):
        raise RuntimeError("RAID non risulta in esecuzione.")
    if not bool(status.get("helper_capable")):
        raise RuntimeError("Helper HH non compatibile con il processo RAID corrente.")
    if bool(status.get("restart_required")):
        raise RuntimeError("Helper HH richiede riavvio di RAID prima di usare equip/sell.")
    return status


def bridge_result_error_message(result: Dict[str, Any]) -> str:
    payload = dict(result or {})
    if not bool(payload.get("ok")):
        return str(payload.get("error") or "Bridge locale HH ha restituito un errore.").strip()

    published_events = list(payload.get("published_events") or [])
    for event in published_events:
        event_map = dict(event or {})
        if event_map.get("IsSuccess") is False:
            return str(event_map.get("Error") or "Helper HH ha rifiutato l'operazione richiesta.").strip()
    return ""


def assert_local_hh_bridge_command_succeeded(result: Dict[str, Any]) -> Dict[str, Any]:
    message = bridge_result_error_message(result)
    if message:
        raise RuntimeError(message)
    return result


def collect_team_optimizer_touched_champions(loadout: Dict[str, Any]) -> List[Dict[str, str]]:
    touched: Dict[str, Dict[str, str]] = {}

    def _remember(champ_id: str, champion_name: str) -> None:
        normalized_id = str(champ_id or "").strip()
        normalized_name = str(champion_name or "").strip()
        if not normalized_id:
            return
        existing = touched.get(normalized_id)
        if existing:
            if normalized_name and not existing.get("champion_name"):
                existing["champion_name"] = normalized_name
            return
        touched[normalized_id] = {
            "champ_id": normalized_id,
            "champion_name": normalized_name,
        }

    for member in list(loadout.get("team") or []):
        _remember(str(member.get("champ_id") or ""), str(member.get("champion_name") or ""))
        for item in list(member.get("items") or []):
            if str(item.get("source_kind") or "").strip().lower() != "borrowed":
                continue
            _remember(str(item.get("equipped_by") or ""), str(item.get("owner_name") or ""))

    return list(touched.values())


def capture_equipped_items_snapshot(champions: List[Dict[str, str]], db_path: Path = DB_PATH) -> Dict[str, Any]:
    champion_ids = sorted({str(row.get("champ_id") or "").strip() for row in champions if str(row.get("champ_id") or "").strip()})
    if not champion_ids:
        return {"saved_at": utc_now_iso(), "champions": [], "summary": {"champions": 0, "artifacts": 0}}

    placeholders = ",".join("?" for _ in champion_ids)
    champion_name_overrides = {
        str(row.get("champ_id") or "").strip(): str(row.get("champion_name") or "").strip()
        for row in champions
        if str(row.get("champ_id") or "").strip()
    }

    with open_db(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                ac.champ_id,
                ac.champion_name,
                gi.item_id,
                gi.slot
            FROM account_champions ac
            LEFT JOIN gear_items gi
                ON gi.equipped_by = ac.champ_id
            WHERE ac.champ_id IN ({placeholders})
            ORDER BY ac.champ_id ASC, gi.item_id ASC
            """,
            champion_ids,
        ).fetchall()

    champions_by_id: Dict[str, Dict[str, Any]] = {
        champ_id: {
            "champ_id": champ_id,
            "champion_name": champion_name_overrides.get(champ_id, ""),
            "artifact_ids": [],
            "items": [],
        }
        for champ_id in champion_ids
    }
    for row in rows:
        champ_id = str(row["champ_id"] or "").strip()
        if not champ_id:
            continue
        bucket = champions_by_id.setdefault(
            champ_id,
            {"champ_id": champ_id, "champion_name": "", "artifact_ids": [], "items": []},
        )
        champion_name = str(row["champion_name"] or "").strip()
        if champion_name and not bucket.get("champion_name"):
            bucket["champion_name"] = champion_name
        item_id = str(row["item_id"] or "").strip()
        if not item_id:
            continue
        bucket["items"].append(
            {
                "item_id": item_id,
                "slot": str(row["slot"] or "").strip(),
            }
        )

    snapshot_champions: List[Dict[str, Any]] = []
    total_artifacts = 0
    for champ_id in champion_ids:
        bucket = champions_by_id.get(champ_id) or {}
        items = sorted(
            list(bucket.get("items") or []),
            key=lambda row: (gear_slot_sort_key(str(row.get("slot") or "")), str(row.get("item_id") or "")),
        )
        artifact_ids = [str(row.get("item_id") or "") for row in items if str(row.get("item_id") or "").strip()]
        total_artifacts += len(artifact_ids)
        snapshot_champions.append(
            {
                "champ_id": champ_id,
                "champion_name": str(bucket.get("champion_name") or ""),
                "artifact_ids": artifact_ids,
                "artifact_count": len(artifact_ids),
            }
        )

    return {
        "saved_at": utc_now_iso(),
        "champions": snapshot_champions,
        "summary": {
            "champions": len(snapshot_champions),
            "artifacts": total_artifacts,
        },
    }


def build_team_optimizer_snapshot_key(
    boss_key: str,
    level_key: str,
    affinity: str,
    recommendation_source: str = "optimizer",
) -> str:
    normalized_source = str(recommendation_source or "").strip().lower() or "optimizer"
    return f"{TEAM_OPTIMIZER_SNAPSHOT_SCOPE}:{boss_key}:{level_key}:{affinity}:{normalized_source}"


def save_gear_snapshot_record(
    snapshot_key: str,
    label: str,
    scope: str,
    snapshot_kind: str,
    context: Dict[str, Any],
    snapshot: Dict[str, Any],
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    saved_at = str(snapshot.get("saved_at") or utc_now_iso())
    with open_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO gear_snapshots (
                snapshot_key,
                label,
                scope,
                snapshot_kind,
                saved_at,
                updated_at,
                context_json,
                snapshot_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(snapshot_key) DO UPDATE SET
                label = excluded.label,
                scope = excluded.scope,
                snapshot_kind = excluded.snapshot_kind,
                saved_at = excluded.saved_at,
                updated_at = excluded.updated_at,
                context_json = excluded.context_json,
                snapshot_json = excluded.snapshot_json
            """,
            (
                snapshot_key,
                label,
                scope,
                snapshot_kind,
                saved_at,
                saved_at,
                json.dumps(context, ensure_ascii=True),
                json.dumps(snapshot, ensure_ascii=True),
            ),
        )
        conn.commit()
    return load_gear_snapshot_record(snapshot_key, db_path=db_path)


def load_gear_snapshot_record(snapshot_key: str, db_path: Path = DB_PATH) -> Dict[str, Any]:
    with open_db(db_path) as conn:
        row = conn.execute(
            """
            SELECT snapshot_key, label, scope, snapshot_kind, saved_at, updated_at, context_json, snapshot_json
            FROM gear_snapshots
            WHERE snapshot_key = ?
            """,
            (snapshot_key,),
        ).fetchone()
    if not row:
        raise FileNotFoundError("Snapshot equip non trovato.")
    context = json.loads(str(row["context_json"] or "{}"))
    snapshot = json.loads(str(row["snapshot_json"] or "{}"))
    return {
        "snapshot_key": str(row["snapshot_key"] or ""),
        "label": str(row["label"] or ""),
        "scope": str(row["scope"] or ""),
        "snapshot_kind": str(row["snapshot_kind"] or ""),
        "saved_at": str(row["saved_at"] or ""),
        "updated_at": str(row["updated_at"] or ""),
        "context": context,
        "summary": dict(snapshot.get("summary") or {}),
        "champions": list(snapshot.get("champions") or []),
    }


def build_snapshot_status_payload(record: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not record:
        return {
            "available": False,
            "summary": {"champions": 0, "artifacts": 0},
            "champions": [],
        }
    return {
        "available": True,
        "snapshot_key": str(record.get("snapshot_key") or ""),
        "label": str(record.get("label") or ""),
        "snapshot_kind": str(record.get("snapshot_kind") or ""),
        "saved_at": str(record.get("saved_at") or ""),
        "updated_at": str(record.get("updated_at") or ""),
        "context": dict(record.get("context") or {}),
        "summary": dict(record.get("summary") or {}),
        "champions": list(record.get("champions") or []),
    }


def save_team_optimizer_snapshot(
    snapshot_key: str,
    label: str,
    snapshot_kind: str,
    loadout: Dict[str, Any],
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    touched_champions = collect_team_optimizer_touched_champions(loadout)
    snapshot = capture_equipped_items_snapshot(touched_champions, db_path=db_path)
    context = {
        "target": dict(loadout.get("target") or {}),
        "selection": {
            "boss_key": str(dict(loadout.get("target") or {}).get("boss_key") or ""),
            "level_key": str(dict(loadout.get("target") or {}).get("level_key") or ""),
            "affinity": str(dict(loadout.get("target") or {}).get("affinity_key") or ""),
            "recommendation_source": str(dict(loadout.get("target") or {}).get("recommendation_source") or "optimizer"),
        },
    }
    return save_gear_snapshot_record(
        snapshot_key=snapshot_key,
        label=label,
        scope=TEAM_OPTIMIZER_SNAPSHOT_SCOPE,
        snapshot_kind=snapshot_kind,
        context=context,
        snapshot=snapshot,
        db_path=db_path,
    )


def save_team_optimizer_restore_snapshot(loadout: Dict[str, Any], db_path: Path = DB_PATH) -> Dict[str, Any]:
    target = dict(loadout.get("target") or {})
    label = f"Ultimo equip {target.get('boss_label') or 'Team Optimizer'} {target.get('level_label') or ''}".strip()
    return save_team_optimizer_snapshot(
        snapshot_key=TEAM_OPTIMIZER_LAST_RESTORE_KEY,
        label=label,
        snapshot_kind="auto_restore",
        loadout=loadout,
        db_path=db_path,
    )


def save_named_team_optimizer_snapshot(
    boss_key: str = "demon_lord",
    level_key: str = "ultra_nightmare",
    affinity: str = "void",
    recommendation_source: str = "optimizer",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    loadout = build_team_optimizer_loadout(
        boss_key=boss_key,
        level_key=level_key,
        affinity=affinity,
        recommendation_source=recommendation_source,
        db_path=db_path,
    )
    target = dict(loadout.get("target") or {})
    label = f"Snapshot {target.get('boss_label') or boss_key} {target.get('level_label') or level_key} {target.get('affinity_label') or affinity} [{target.get('recommendation_label') or recommendation_source}]".strip()
    return save_team_optimizer_snapshot(
        snapshot_key=build_team_optimizer_snapshot_key(boss_key, level_key, affinity, recommendation_source),
        label=label,
        snapshot_kind="manual_team",
        loadout=loadout,
        db_path=db_path,
    )


def build_team_optimizer_restore_status(
    boss_key: str = "demon_lord",
    level_key: str = "ultra_nightmare",
    affinity: str = "void",
    recommendation_source: str = "optimizer",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    try:
        last_restore = load_gear_snapshot_record(TEAM_OPTIMIZER_LAST_RESTORE_KEY, db_path=db_path)
    except FileNotFoundError:
        last_restore = None
    try:
        team_snapshot = load_gear_snapshot_record(
            build_team_optimizer_snapshot_key(boss_key, level_key, affinity, recommendation_source),
            db_path=db_path,
        )
    except FileNotFoundError:
        team_snapshot = None
    return {
        "last_restore": build_snapshot_status_payload(last_restore),
        "team_snapshot": build_snapshot_status_payload(team_snapshot),
    }


def restore_snapshot_record(record: Dict[str, Any]) -> Dict[str, Any]:
    payload = record
    members = list(payload.get("champions") or [])
    member_results: List[Dict[str, Any]] = []
    started_at = time.perf_counter()
    for member in members:
        champ_id = str(member.get("champ_id") or "").strip()
        champion_name = str(member.get("champion_name") or "").strip()
        artifact_ids = [str(item_id or "").strip() for item_id in list(member.get("artifact_ids") or []) if str(item_id or "").strip()]
        if not champ_id or not artifact_ids:
            continue
        bridge_result = assert_local_hh_bridge_command_succeeded(
            invoke_local_hh_bridge("equip", champ_id, ",".join(artifact_ids))
        )
        member_results.append(
            {
                "champion_name": champion_name,
                "champ_id": champ_id,
                "artifact_ids": artifact_ids,
                "artifact_count": len(artifact_ids),
                "result": bridge_result,
            }
        )

    members_succeeded = sum(1 for row in member_results if bool(dict(row.get("result") or {}).get("ok")))
    members_failed = max(len(member_results) - members_succeeded, 0)
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    return {
        "ok": True,
        "restored_from": str(payload.get("saved_at") or ""),
        "snapshot_key": str(payload.get("snapshot_key") or ""),
        "label": str(payload.get("label") or ""),
        "summary": {
            "members_requested": len(member_results),
            "members_succeeded": members_succeeded,
            "members_failed": members_failed,
            "total_artifacts_requested": sum(int(row.get("artifact_count") or 0) for row in member_results),
            "duration_ms": duration_ms,
        },
        "members": member_results,
    }


def restore_last_team_optimizer_equip(db_path: Path = DB_PATH) -> Dict[str, Any]:
    return restore_snapshot_record(load_gear_snapshot_record(TEAM_OPTIMIZER_LAST_RESTORE_KEY, db_path=db_path))


def restore_named_team_optimizer_snapshot(
    boss_key: str = "demon_lord",
    level_key: str = "ultra_nightmare",
    affinity: str = "void",
    recommendation_source: str = "optimizer",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    snapshot_key = build_team_optimizer_snapshot_key(boss_key, level_key, affinity, recommendation_source)
    return restore_snapshot_record(load_gear_snapshot_record(snapshot_key, db_path=db_path))


def equip_team_optimizer_member_in_game(
    champion_name: str = "",
    champ_id: str = "",
    boss_key: str = "demon_lord",
    level_key: str = "ultra_nightmare",
    affinity: str = "void",
    recommendation_source: str = "optimizer",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    loadout = build_team_optimizer_loadout(
        boss_key=boss_key,
        level_key=level_key,
        affinity=affinity,
        recommendation_source=recommendation_source,
        db_path=db_path,
    )
    member = None
    for row in list(loadout.get("team") or []):
        row_champ_id = str(row.get("champ_id") or "").strip()
        row_name = str(row.get("champion_name") or "").strip()
        if champ_id and row_champ_id == str(champ_id).strip():
            member = row
            break
        if champion_name and row_name == str(champion_name).strip():
            member = row
            break
    if not member:
        raise KeyError("Campione non trovato nel team optimizer corrente.")
    member_conflicts = [str(item_id or "").strip() for item_id in list(member.get("conflict_item_ids") or []) if str(item_id or "").strip()]
    if member_conflicts:
        raise ValueError(
            "Equip singolo bloccato: il campione usa pezzi in conflitto con altri membri del team "
            f"({', '.join(member_conflicts)}). Risolvi prima i conflitti nel loadout."
        )

    actionable_items = [
        item
        for item in list(member.get("items") or [])
        if str(item.get("item_id") or "").strip() and str(item.get("source_kind") or "").strip().lower() != "current"
    ]
    if not actionable_items:
        raise ValueError("Campione gia pronto: nessun pezzo da cambiare in game.")

    single_loadout = {
        "target": dict(loadout.get("target") or {}),
        "team": [dict(member)],
        "conflicts": [],
        "summary": {"champions": 1},
    }
    restore_snapshot = save_team_optimizer_restore_snapshot(single_loadout, db_path=db_path)

    champion_name = str(member.get("champion_name") or "").strip()
    champ_id = str(member.get("champ_id") or "").strip()
    artifact_ids = [
        str(item.get("item_id") or "").strip()
        for item in list(member.get("items") or [])
        if str(item.get("item_id") or "").strip()
    ]
    actionable_artifact_ids = [
        str(item.get("item_id") or "").strip()
        for item in actionable_items
    ]
    if not champion_name or not champ_id or not artifact_ids:
        raise ValueError("Build non equipaggiabile per il campione selezionato.")

    bridge_status = ensure_local_hh_bridge_ready()
    started_at = time.perf_counter()
    bridge_result = assert_local_hh_bridge_command_succeeded(
        invoke_local_hh_bridge("equip", champ_id, ",".join(artifact_ids))
    )
    duration_ms = int((time.perf_counter() - started_at) * 1000)
    member_result = {
        "champion_name": champion_name,
        "champ_id": champ_id,
        "artifact_ids": artifact_ids,
        "artifact_count": len(artifact_ids),
        "result": bridge_result,
    }
    return {
        "ok": True,
        "target": dict(loadout.get("target") or {}),
        "bridge_status": bridge_status,
        "restore_snapshot": restore_snapshot,
        "summary": {
            "members_requested": 1,
            "members_succeeded": 1 if bool(dict(bridge_result).get("ok")) else 0,
            "members_failed": 0 if bool(dict(bridge_result).get("ok")) else 1,
            "total_artifacts_requested": len(artifact_ids),
            "changed_artifacts_requested": len(actionable_artifact_ids),
            "duration_ms": duration_ms,
        },
        "members": [member_result],
    }


def equip_team_optimizer_in_game(
    boss_key: str = "demon_lord",
    level_key: str = "ultra_nightmare",
    affinity: str = "void",
    recommendation_source: str = "optimizer",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    started_at = time.perf_counter()
    loadout = build_team_optimizer_loadout(
        boss_key=boss_key,
        level_key=level_key,
        affinity=affinity,
        recommendation_source=recommendation_source,
        db_path=db_path,
    )
    conflicts = list(loadout.get("conflicts") or [])
    if conflicts:
        raise ValueError("Il team optimizer ha conflitti su pezzi condivisi: risolvili prima di equipaggiare in game.")
    restore_snapshot = save_team_optimizer_restore_snapshot(loadout, db_path=db_path)

    bridge_status = ensure_local_hh_bridge_ready()
    member_results: List[Dict[str, Any]] = []
    for member in list(loadout.get("team") or []):
        champion_name = str(member.get("champion_name") or "").strip()
        champ_id = str(member.get("champ_id") or "").strip()
        artifact_ids = [
            str(item.get("item_id") or "").strip()
            for item in list(member.get("items") or [])
            if str(item.get("item_id") or "").strip()
        ]
        if not champion_name or not champ_id or not artifact_ids:
            continue
        bridge_result = assert_local_hh_bridge_command_succeeded(
            invoke_local_hh_bridge("equip", champ_id, ",".join(artifact_ids))
        )
        member_results.append(
            {
                "champion_name": champion_name,
                "champ_id": champ_id,
                "artifact_ids": artifact_ids,
                "artifact_count": len(artifact_ids),
                "result": bridge_result,
            }
        )

    members_succeeded = sum(1 for row in member_results if bool(dict(row.get("result") or {}).get("ok")))
    members_failed = max(len(member_results) - members_succeeded, 0)
    total_artifacts_requested = sum(int(row.get("artifact_count") or 0) for row in member_results)
    duration_ms = int((time.perf_counter() - started_at) * 1000)

    return {
        "ok": True,
        "target": dict(loadout.get("target") or {}),
        "bridge_status": bridge_status,
        "restore_snapshot": restore_snapshot,
        "summary": {
            "members_requested": len(member_results),
            "members_succeeded": members_succeeded,
            "members_failed": members_failed,
            "total_artifacts_requested": total_artifacts_requested,
            "duration_ms": duration_ms,
        },
        "members": member_results,
    }


def build_team_optimizer_local_bridge_plan(
    boss_key: str = "demon_lord",
    level_key: str = "ultra_nightmare",
    affinity: str = "void",
    recommendation_source: str = "optimizer",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    loadout = build_team_optimizer_loadout(
        boss_key=boss_key,
        level_key=level_key,
        affinity=affinity,
        recommendation_source=recommendation_source,
        db_path=db_path,
    )
    plan = build_team_equip_plan(loadout)
    return {
        "target": dict(loadout.get("target") or {}),
        "summary": dict(loadout.get("summary") or {}),
        "plan": plan,
    }


def champion_sort_key(champion: Dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(champion.get("level") or 0),
        int(champion.get("rank") or 0),
        1 if champion.get("booked") else 0,
        1 if champion.get("enriched") else 0,
    )


def classify_skill_data_status(skill_rows: int, skill_rows_with_data: int) -> str:
    if skill_rows <= 0 or skill_rows_with_data <= 0:
        return "missing"
    if skill_rows_with_data < skill_rows:
        return "partial"
    return "complete"


def list_gear_items(
    db_path: Path = DB_PATH,
    search: str = "",
    ownership: str = "all",
    item_class: str = "",
    slot: str = "",
    set_name: str = "",
    advice: str = "",
    sort: str = "rank",
) -> Dict[str, Any]:
    search_text = search.strip().lower()
    selected_item_class = item_class.strip().lower()
    selected_slot = slot.strip().lower()
    selected_set = set_name.strip().lower()
    with open_db(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                gi.item_id,
                gi.item_class,
                gi.slot,
                gi.set_name,
                gi.rarity,
                gi.rank,
                gi.level,
                gi.ascension_level,
                gi.required_faction,
                gi.equipped_by,
                gi.locked,
                gi.main_stat_type,
                gi.main_stat_value,
                ac.champion_name AS owner_name,
                COUNT(gs.substat_order) AS substat_count,
                COALESCE(SUM(gs.glyph_value), 0) AS glyph_total
            FROM gear_items gi
            LEFT JOIN account_champions ac
                ON ac.champ_id = gi.equipped_by
            LEFT JOIN gear_substats gs
                ON gs.item_id = gi.item_id
            GROUP BY
                gi.item_id,
                gi.item_class,
                gi.slot,
                gi.set_name,
                gi.rarity,
                gi.rank,
                gi.level,
                gi.ascension_level,
                gi.required_faction,
                gi.equipped_by,
                gi.locked,
                gi.main_stat_type,
                gi.main_stat_value,
                owner_name
            """
        ).fetchall()
        substats_by_item = load_gear_substats_map(conn)

    items: List[Dict[str, Any]] = []
    item_classes = sorted({str(row["item_class"] or "") for row in rows if str(row["item_class"] or "")}, key=lambda value: value.lower())
    slots = sorted({str(row["slot"] or "") for row in rows if str(row["slot"] or "")}, key=gear_slot_sort_key)
    sets = sorted({str(row["set_name"] or "") for row in rows if str(row["set_name"] or "")}, key=lambda value: value.lower())
    owners = sorted({str(row["owner_name"] or "") for row in rows if str(row["owner_name"] or "")}, key=lambda value: value.lower())

    for row in rows:
        item = {
            "item_id": str(row["item_id"]),
            "item_class": str(row["item_class"] or ""),
            "slot": str(row["slot"] or ""),
            "set_name": str(row["set_name"] or ""),
            "rarity": str(row["rarity"] or ""),
            "rank": int(row["rank"] or 0),
            "level": int(row["level"] or 0),
            "ascension_level": int(row["ascension_level"] or 0),
            "required_faction": str(row["required_faction"] or ""),
            "equipped_by": str(row["equipped_by"] or ""),
            "owner_name": str(row["owner_name"] or ""),
            "locked": bool(row["locked"]),
            "main_stat_type": str(row["main_stat_type"] or ""),
            "main_stat_value": row["main_stat_value"],
            "substat_count": int(row["substat_count"] or 0),
            "glyph_total": float(row["glyph_total"] or 0.0),
        }
        item["equipped"] = bool(item["equipped_by"])
        advice_payload = evaluate_gear_item(item, substats_by_item.get(item["item_id"], []))
        item["advice_verdict"] = advice_payload["verdict"]
        item["advice_reasons"] = advice_payload["reasons"]
        item["pre12_score"] = advice_payload["pre12_score"]
        item["realized_score"] = advice_payload["realized_score"]
        item["premium_rolls"] = advice_payload["premium_rolls"]
        item["good_rolls"] = advice_payload["good_rolls"]
        item["main_tier"] = advice_payload["main_tier"]
        haystack = " ".join(
            [
                item["item_id"],
                item["slot"],
                item["set_name"],
                SET_DISPLAY_NAMES.get(item["set_name"], ""),
                item["owner_name"],
                item["main_stat_type"],
                item["rarity"],
                item["required_faction"],
                item["advice_verdict"],
                " ".join(item["advice_reasons"]),
            ]
        ).lower()
        if search_text and search_text not in haystack:
            continue
        if ownership == "equipped" and not item["equipped"]:
            continue
        if ownership == "inventory" and item["equipped"]:
            continue
        if selected_item_class and item["item_class"].lower() != selected_item_class:
            continue
        if selected_slot and item["slot"].lower() != selected_slot:
            continue
        if selected_set and item["set_name"].lower() != selected_set:
            continue
        if advice and item["advice_verdict"] != advice:
            continue
        items.append(item)

    if sort == "advice":
        advice_order = {
            "push_16": 0,
            "keep_16": 1,
            "keep_after_12": 2,
            "push_12": 3,
            "review_pre12": 4,
            "review_16": 5,
            "review_equipped": 6,
            "sell_after_12": 7,
            "sell_now": 8,
        }
        items.sort(
            key=lambda item: (
                advice_order.get(item["advice_verdict"], 99),
                -float(item["realized_score"]),
                -float(item["pre12_score"]),
                gear_slot_sort_key(item["slot"]),
                item["item_id"],
            )
        )
    elif sort == "slot":
        items.sort(key=lambda item: (gear_slot_sort_key(item["slot"]), item["set_name"].lower(), -item["rank"], -item["level"], item["item_id"]))
    elif sort == "set":
        items.sort(key=lambda item: (item["set_name"].lower(), gear_slot_sort_key(item["slot"]), -item["rank"], -item["level"], item["item_id"]))
    elif sort == "owner":
        items.sort(key=lambda item: (0 if item["equipped"] else 1, item["owner_name"].lower(), gear_slot_sort_key(item["slot"]), item["set_name"].lower(), item["item_id"]))
    else:
        items.sort(
            key=lambda item: (
                0 if item["equipped"] else 1,
                -item["rank"],
                -item["level"],
                -item["ascension_level"],
                gear_slot_sort_key(item["slot"]),
                item["set_name"].lower(),
                item["item_id"],
            )
        )

    return {
        "items": items,
        "filters": {
            "item_classes": item_classes,
            "slots": slots,
            "sets": sets,
            "owners": owners,
            "advice": sorted({item["advice_verdict"] for item in items}, key=lambda value: value.lower()),
        },
    }


def build_sell_queue_summary(
    db_path: Path = DB_PATH,
    limit_per_page: int = 50,
    exclude_ids: List[str] | None = None,
) -> Dict[str, Any]:
    candidates_by_page = collect_sell_queue_candidates(db_path, exclude_ids=exclude_ids)
    queued_ids = load_local_sell_queue_state(db_path)
    pages_payload: List[Dict[str, Any]] = []
    for page, page_meta in sorted(SELL_QUEUE_PAGES.items()):
        candidates = candidates_by_page[page]
        pages_payload.append(
            {
                "page": page,
                "label": page_meta["label"],
                "item_class": page_meta["item_class"],
                "candidate_count": len(candidates),
                "visible_candidates": candidates[:limit_per_page],
            }
        )
    return {"pages": pages_payload, "queued_ids": queued_ids, "queued_count": len(queued_ids)}


def collect_sell_queue_candidates(
    db_path: Path = DB_PATH,
    exclude_ids: List[str] | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    excluded = {str(item_id).strip() for item_id in (exclude_ids or []) if str(item_id).strip()}
    excluded.update(load_local_sell_queue_state(db_path))
    pages_payload: Dict[str, List[Dict[str, Any]]] = {}
    for page, page_meta in sorted(SELL_QUEUE_PAGES.items()):
        page_items = list_gear_items(
            db_path=db_path,
            ownership="inventory",
            item_class=page_meta["item_class"],
            sort="advice",
        )["items"]
        pages_payload[page] = [
            item
            for item in page_items
            if (
                str(item.get("advice_verdict") or "") in SELL_QUEUE_VERDICTS
                and not bool(item.get("locked"))
                and str(item.get("item_id") or "") not in excluded
            )
        ]
        pages_payload[page].sort(key=sell_queue_sort_key)
    return pages_payload


def load_local_sell_queue_state(db_path: Path = DB_PATH) -> List[str]:
    state = load_app_state(db_path)
    raw_items = state.get(SELL_QUEUE_LOCAL_STATE_KEY)
    if not isinstance(raw_items, list):
        return []
    queued_ids: List[str] = []
    seen: set[str] = set()
    for raw_value in raw_items:
        item_id = str(raw_value or "").strip()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        queued_ids.append(item_id)
    return queued_ids


def save_local_sell_queue_state(item_ids: List[str], db_path: Path = DB_PATH) -> None:
    save_app_state({SELL_QUEUE_LOCAL_STATE_KEY: item_ids}, db_path=db_path)


def clear_local_sell_queue_state(db_path: Path = DB_PATH) -> None:
    save_local_sell_queue_state([], db_path=db_path)


def sell_queue_sort_key(item: Dict[str, Any]) -> tuple[Any, ...]:
    main_tier = str(item.get("main_tier") or "")
    level = int(item.get("level") or 0)
    verdict = str(item.get("advice_verdict") or "")
    realized_score = float(item.get("realized_score") or 0.0)
    pre12_score = float(item.get("pre12_score") or 0.0)
    rank = int(item.get("rank") or 0)

    if main_tier == "weak" and level < 12:
        bucket = 0
    elif main_tier == "weak":
        bucket = 1
    elif verdict == "sell_now":
        bucket = 2
    else:
        bucket = 3

    return (
        bucket,
        level,
        SELL_QUEUE_MAIN_TIER_ORDER.get(main_tier, 99),
        pre12_score,
        realized_score,
        rank,
        gear_slot_sort_key(str(item.get("slot") or "")),
        str(item.get("item_id") or ""),
    )


def sell_artifacts_from_queue(
    artifact_ids: List[Any],
    db_path: Path = DB_PATH,
    access_token: str | None = None,
) -> Dict[str, Any]:
    requested_ids: List[str] = []
    seen_ids = set()
    for raw_value in artifact_ids:
        item_id = str(raw_value or "").strip()
        if not item_id or item_id in seen_ids:
            continue
        seen_ids.add(item_id)
        requested_ids.append(item_id)

    if not requested_ids:
        raise ValueError("artifact_ids mancanti.")

    candidates_by_id: Dict[str, Dict[str, Any]] = {}
    for page_candidates in collect_sell_queue_candidates(db_path).values():
        for item in page_candidates:
            candidates_by_id[str(item["item_id"])] = item

    approved_ids = [item_id for item_id in requested_ids if item_id in candidates_by_id]
    rejected_ids = [item_id for item_id in requested_ids if item_id not in candidates_by_id]
    if not approved_ids:
        raise ValueError("Nessun ID vendibile trovato nella coda corrente.")

    bridge_result = assert_local_hh_bridge_command_succeeded(
        invoke_local_hh_bridge("sell", ",".join(approved_ids))
    )
    approved_items = [candidates_by_id[item_id] for item_id in approved_ids]
    queued_ids = load_local_sell_queue_state(db_path)
    merged_queue = list(queued_ids)
    known_ids = set(merged_queue)
    for item_id in approved_ids:
        if item_id in known_ids:
            continue
        known_ids.add(item_id)
        merged_queue.append(item_id)
    save_local_sell_queue_state(merged_queue, db_path=db_path)
    message = f"{len(approved_ids)} ID inviati al bridge locale per la vendita."
    if rejected_ids:
        message = f"{message} Ignorati {len(rejected_ids)} ID fuori coda o non vendibili."
    return {
        "status": "sold_local",
        "requested_count": len(requested_ids),
        "queued_count": len(merged_queue),
        "requested_ids": requested_ids,
        "approved_ids": approved_ids,
        "rejected_ids": rejected_ids,
        "approved_items": approved_items,
        "result": bridge_result,
        "message": message.strip(),
    }


def gear_item_detail(item_id: str, db_path: Path = DB_PATH) -> Dict[str, Any]:
    with open_db(db_path) as conn:
        item_row = conn.execute(
            """
            SELECT
                gi.item_id,
                gi.item_class,
                gi.slot,
                gi.set_name,
                gi.rarity,
                gi.rank,
                gi.level,
                gi.ascension_level,
                gi.required_faction,
                gi.required_faction_id,
                gi.equipped_by,
                gi.locked,
                gi.main_stat_type,
                gi.main_stat_value,
                ac.champion_name AS owner_name
            FROM gear_items gi
            LEFT JOIN account_champions ac
                ON ac.champ_id = gi.equipped_by
            WHERE gi.item_id = ?
            """,
            (item_id,),
        ).fetchone()
        if item_row is None:
            raise KeyError(f"Equip non trovato: {item_id}")
        substat_rows = conn.execute(
            """
            SELECT substat_order, stat_type, stat_value, rolls, glyph_value
            FROM gear_substats
            WHERE item_id = ?
            ORDER BY substat_order ASC
            """,
            (item_id,),
        ).fetchall()

    substats = [
        {
            "substat_order": int(row["substat_order"] or 0),
            "stat_type": str(row["stat_type"] or ""),
            "stat_value": row["stat_value"],
            "rolls": int(row["rolls"] or 0),
            "glyph_value": row["glyph_value"],
        }
        for row in substat_rows
    ]
    item = {
        "item_id": str(item_row["item_id"]),
        "item_class": str(item_row["item_class"] or ""),
        "slot": str(item_row["slot"] or ""),
        "set_name": str(item_row["set_name"] or ""),
        "rarity": str(item_row["rarity"] or ""),
        "rank": int(item_row["rank"] or 0),
        "level": int(item_row["level"] or 0),
        "ascension_level": int(item_row["ascension_level"] or 0),
        "required_faction": str(item_row["required_faction"] or ""),
        "required_faction_id": int(item_row["required_faction_id"] or 0),
        "equipped_by": str(item_row["equipped_by"] or ""),
        "owner_name": str(item_row["owner_name"] or ""),
        "equipped": bool(item_row["equipped_by"]),
        "locked": bool(item_row["locked"]),
        "main_stat_type": str(item_row["main_stat_type"] or ""),
        "main_stat_value": item_row["main_stat_value"],
    }
    return {
        "item": item,
        "substats": substats,
        "advice": evaluate_gear_item(item, substats),
    }


def gear_slot_sort_key(slot: str) -> tuple[int, str]:
    normalized = str(slot or "").strip().lower()
    return (GEAR_SLOT_ORDER.get(normalized, 99), normalized)


def load_gear_substats_map(conn: sqlite3.Connection) -> Dict[str, List[Dict[str, Any]]]:
    rows = conn.execute(
        """
        SELECT item_id, substat_order, stat_type, stat_value, rolls, glyph_value
        FROM gear_substats
        ORDER BY item_id ASC, substat_order ASC
        """
    ).fetchall()
    substats_by_item: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        substats_by_item.setdefault(str(row["item_id"]), []).append(
            {
                "substat_order": int(row["substat_order"] or 0),
                "stat_type": str(row["stat_type"] or ""),
                "stat_value": row["stat_value"],
                "rolls": int(row["rolls"] or 0),
                "glyph_value": row["glyph_value"],
            }
        )
    return substats_by_item


def champion_detail(champion_name: str, db_path: Path = DB_PATH) -> Dict[str, Any]:
    with open_db(db_path) as conn:
        account_row = conn.execute(
            """
            SELECT champ_id, champion_name, rarity, affinity, faction, level, rank, awakening_level, empowerment_level, booked, relic_count
            FROM account_champions
            WHERE champion_name = ?
            ORDER BY level DESC, rank DESC, awakening_level DESC, empowerment_level DESC
            LIMIT 1
            """,
            (champion_name,),
        ).fetchone()
        if account_row is None:
            raise KeyError(f"Campione non trovato: {champion_name}")

        catalog_row = conn.execute(
            """
            SELECT champion_name, hellhades_post_id, hellhades_url, last_enriched_at
            FROM champion_catalog
            WHERE champion_name = ?
            """,
            (champion_name,),
        ).fetchone()
        role_rows = conn.execute(
            "SELECT role_tag FROM champion_roles WHERE champion_name = ? ORDER BY role_tag ASC",
            (champion_name,),
        ).fetchall()
        base_stat_rows = conn.execute(
            "SELECT stat_name, stat_value FROM champion_base_stats WHERE champion_name = ? ORDER BY stat_name ASC",
            (champion_name,),
        ).fetchall()
        total_stat_rows = conn.execute(
            """
            SELECT stat_name, stat_value
            FROM account_champion_total_stats
            WHERE champ_id = ?
            ORDER BY stat_name ASC
            """,
            (account_row["champ_id"],),
        ).fetchall()
        imported_total_stat_rows = conn.execute(
            """
            SELECT stat_name, stat_value
            FROM account_champion_imported_total_stats
            WHERE champ_id = ?
            ORDER BY stat_name ASC
            """,
            (account_row["champ_id"],),
        ).fetchall()
        stat_model_row = conn.execute(
            """
            SELECT source, completeness, unsupported_sets_json, applied_sets_json, computed_at
            FROM account_champion_stat_models
            WHERE champ_id = ?
            """,
            (account_row["champ_id"],),
        ).fetchone()
        bonus_source_rows = conn.execute(
            """
            SELECT DISTINCT source
            FROM account_bonuses
            ORDER BY source ASC
            """
        ).fetchall()
        skill_rows = conn.execute(
            """
            SELECT slot, skill_order, skill_id, skill_name, cooldown, booked_cooldown, description, skill_type, description_clean, source
            FROM champion_skills
            WHERE champion_name = ?
            ORDER BY skill_order ASC
            """,
            (champion_name,),
        ).fetchall()
        effect_rows = conn.execute(
            """
            SELECT slot, effect_order, effect_type, target, effect_value, duration, chance, condition_text
            FROM champion_skill_effects
            WHERE champion_name = ?
            ORDER BY slot ASC, effect_order ASC
            """,
            (champion_name,),
        ).fetchall()

    unsupported_sets: List[str] = []
    applied_sets: List[Dict[str, Any]] = []
    if stat_model_row is not None:
        try:
            unsupported_sets = json.loads(stat_model_row["unsupported_sets_json"] or "[]")
        except json.JSONDecodeError:
            unsupported_sets = []
        try:
            applied_sets = json.loads(stat_model_row["applied_sets_json"] or "[]")
        except json.JSONDecodeError:
            applied_sets = []

    base_stats = {str(row["stat_name"]): row["stat_value"] for row in base_stat_rows}
    imported_total_stats = {str(row["stat_name"]): row["stat_value"] for row in imported_total_stat_rows}
    imported_total_stats_present = any(abs(float(row["stat_value"] or 0.0)) > 0.001 for row in imported_total_stat_rows)
    bonus_sources = sorted({str(row["source"] or "").strip() for row in bonus_source_rows if str(row["source"] or "").strip()})
    stat_warnings: List[str] = []
    missing_sources: List[str] = []

    if not imported_total_stats_present:
        missing_sources.append("imported_total_stats")
        stat_warnings.append("Total stats importati assenti: valori ricostruiti dal gear, non letti direttamente dal client.")
    if int(account_row["relic_count"] or 0) > 0 and not imported_total_stats_present:
        missing_sources.append("relic_stats")
        stat_warnings.append("Relic presenti sul campione, ma il loro contributo stats non e ancora modellato in modo trusted.")
    if bonus_sources and set(bonus_sources).issubset({"great_hall", "area_bonus"}):
        missing_sources.extend(["classic_arena", "faction_guardians"])
        stat_warnings.append("Bonus account incompleti nell'import attuale: mancano almeno Classic Arena e Faction Guardians.")
    if stat_model_row is not None and str(stat_model_row["completeness"] or "") == "partial":
        stat_warnings.append("Sono presenti set speciali o effetti non quantificati completamente nel modello stats.")

    effects_by_slot: Dict[str, List[Dict[str, Any]]] = {}
    for row in effect_rows:
        effects_by_slot.setdefault(str(row["slot"]), []).append(
            {
                "effect_order": int(row["effect_order"] or 0),
                "effect_type": str(row["effect_type"] or ""),
                "target": str(row["target"] or ""),
                "effect_value": row["effect_value"],
                "duration": row["duration"],
                "chance": row["chance"],
                "condition_text": str(row["condition_text"] or ""),
            }
        )
    skill_rows_with_data = 0
    skill_sources = sorted({str(row["source"] or "").strip() for row in skill_rows if str(row["source"] or "").strip()})
    for row in skill_rows:
        slot_key = str(row["slot"])
        has_data = (
            row["cooldown"] is not None
            or row["booked_cooldown"] is not None
            or bool(str(row["skill_type"] or "").strip())
            or bool(str(row["description_clean"] or row["description"] or "").strip())
            or bool(effects_by_slot.get(slot_key))
        )
        if has_data:
            skill_rows_with_data += 1
    skill_data_status = classify_skill_data_status(len(skill_rows), skill_rows_with_data)
    external_provider = skill_sources[0] if len(skill_sources) == 1 else ""
    if not external_provider and catalog_row and (
        catalog_row["hellhades_post_id"] is not None
        or str(catalog_row["hellhades_url"] or "").strip()
        or str(catalog_row["last_enriched_at"] or "").strip()
    ):
        external_provider = "hellhades"

    return {
        "account": {
            "champ_id": str(account_row["champ_id"]),
            "champion_name": str(account_row["champion_name"]),
            "rarity": str(account_row["rarity"] or ""),
            "affinity": str(account_row["affinity"] or ""),
            "faction": str(account_row["faction"] or ""),
            "level": int(account_row["level"] or 0),
            "rank": int(account_row["rank"] or 0),
            "awakening_level": int(account_row["awakening_level"] or 0),
            "empowerment_level": int(account_row["empowerment_level"] or 0),
            "booked": bool(account_row["booked"]),
            "relic_count": int(account_row["relic_count"] or 0),
        },
        "catalog": {
            "external_provider": external_provider,
            "external_ref_id": int(catalog_row["hellhades_post_id"]) if catalog_row and catalog_row["hellhades_post_id"] is not None else None,
            "external_url": str(catalog_row["hellhades_url"] or "") if catalog_row else "",
            "external_synced_at": str(catalog_row["last_enriched_at"] or "") if catalog_row else "",
            "hellhades_post_id": int(catalog_row["hellhades_post_id"]) if catalog_row and catalog_row["hellhades_post_id"] is not None else None,
            "hellhades_url": str(catalog_row["hellhades_url"] or "") if catalog_row else "",
            "last_enriched_at": str(catalog_row["last_enriched_at"] or "") if catalog_row else "",
        },
        "roles": [str(row["role_tag"]) for row in role_rows],
        "base_stats": base_stats,
        "base_totals": materialize_base_totals(base_stats),
        "total_stats": {str(row["stat_name"]): row["stat_value"] for row in total_stat_rows},
        "stat_model": {
            "source": str(stat_model_row["source"] or "") if stat_model_row else "",
            "completeness": str(stat_model_row["completeness"] or "") if stat_model_row else "",
            "unsupported_sets": unsupported_sets if isinstance(unsupported_sets, list) else [],
            "applied_sets": applied_sets if isinstance(applied_sets, list) else [],
            "computed_at": str(stat_model_row["computed_at"] or "") if stat_model_row else "",
            "imported_total_stats_present": imported_total_stats_present,
            "imported_total_stats": imported_total_stats,
            "bonus_sources": bonus_sources,
            "missing_sources": sorted(set(filter(None, missing_sources))),
            "warnings": stat_warnings,
        },
        "skills": [
            {
                "slot": str(row["slot"]),
                "skill_order": int(row["skill_order"] or 0),
                "skill_id": str(row["skill_id"] or ""),
                "skill_name": str(row["skill_name"] or ""),
                "cooldown": row["cooldown"],
                "booked_cooldown": row["booked_cooldown"],
                "description": str(row["description"] or ""),
                "skill_type": str(row["skill_type"] or ""),
                "description_clean": str(row["description_clean"] or ""),
                "source": str(row["source"] or ""),
                "effects": effects_by_slot.get(str(row["slot"]), []),
            }
            for row in skill_rows
        ],
        "skill_data": {
            "skill_rows": len(skill_rows),
            "skill_rows_with_data": skill_rows_with_data,
            "skill_rows_with_effects": sum(1 for effects in effects_by_slot.values() if effects),
            "data_status": skill_data_status,
            "sources": skill_sources,
            "primary_source": skill_sources[0] if len(skill_sources) == 1 else "",
        },
    }


def first_query_value(query: Dict[str, List[str]], key: str) -> str:
    values = query.get(key) or [""]
    return values[0]


class CBForgeHandler(BaseHTTPRequestHandler):
    server_version = "CBForgeWeb/0.1"

    @property
    def app(self) -> "CBForgeWebServer":
        return self.server  # type: ignore[return-value]

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._send_file(WEB_DIR / "index.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/gear":
            self._send_file(WEB_DIR / "gear.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/build":
            self._send_file(WEB_DIR / "build.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/optimizer":
            self._send_file(WEB_DIR / "optimizer.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/clan-boss":
            self._send_file(WEB_DIR / "clan-boss.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/ai-lab":
            self._send_file(WEB_DIR / "ai-lab.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/runs":
            self._send_file(WEB_DIR / "runs.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/sets":
            self._send_file(WEB_DIR / "sets.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/set-curation":
            self._send_file(WEB_DIR / "set-curation.html", "text/html; charset=utf-8")
            return
        if parsed.path == "/app.js":
            self._send_file(WEB_DIR / "app.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/gear.js":
            self._send_file(WEB_DIR / "gear.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/build.js":
            self._send_file(WEB_DIR / "build.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/optimizer.js":
            self._send_file(WEB_DIR / "optimizer.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/clanboss.js":
            self._send_file(WEB_DIR / "clanboss.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/ailab.js":
            self._send_file(WEB_DIR / "ailab.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/runs.js":
            self._send_file(WEB_DIR / "runs.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/sets.js":
            self._send_file(WEB_DIR / "sets.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/set-curation.js":
            self._send_file(WEB_DIR / "set-curation.js", "application/javascript; charset=utf-8")
            return
        if parsed.path == "/style.css":
            self._send_file(WEB_DIR / "style.css", "text/css; charset=utf-8")
            return
        if parsed.path == "/api/summary":
            self._send_json(build_web_summary(self.app.db_path))
            return
        if parsed.path == "/api/gear-summary":
            self._send_json(build_gear_summary(self.app.db_path))
            return
        if parsed.path == "/api/set-registry":
            self._send_json(build_set_registry(self.app.db_path))
            return
        if parsed.path == "/api/set-curation":
            self._send_json(build_set_curation_payload(self.app.db_path))
            return
        if parsed.path == "/api/champions":
            query = parse_qs(parsed.query)
            self._send_json(
                list_owned_champions(
                    db_path=self.app.db_path,
                    search=first_query_value(query, "search"),
                    scope=first_query_value(query, "scope") or "all",
                    sort=first_query_value(query, "sort") or "power",
                )
            )
            return
        if parsed.path == "/api/build-profiles":
            self._send_json({"profiles": list_build_profiles(), "area_regions": list_area_bonus_regions()})
            return
        if parsed.path == "/api/team-optimizer":
            query = parse_qs(parsed.query)
            self._send_json(
                build_team_optimizer_view(
                    boss_key=first_query_value(query, "boss") or "demon_lord",
                    level_key=first_query_value(query, "level") or "ultra_nightmare",
                    affinity=first_query_value(query, "affinity") or "void",
                    recommendation_source=first_query_value(query, "source") or "optimizer",
                    db_path=self.app.db_path,
                )
            )
            return
        if parsed.path == "/api/team-optimizer-loadout":
            query = parse_qs(parsed.query)
            self._send_json(
                build_team_optimizer_loadout(
                    boss_key=first_query_value(query, "boss") or "demon_lord",
                    level_key=first_query_value(query, "level") or "ultra_nightmare",
                    affinity=first_query_value(query, "affinity") or "void",
                    recommendation_source=first_query_value(query, "source") or "optimizer",
                    db_path=self.app.db_path,
                )
            )
            return
        if parsed.path == "/api/team-optimizer-local-bridge":
            query = parse_qs(parsed.query)
            self._send_json(
                build_team_optimizer_local_bridge_plan(
                    boss_key=first_query_value(query, "boss") or "demon_lord",
                    level_key=first_query_value(query, "level") or "ultra_nightmare",
                    affinity=first_query_value(query, "affinity") or "void",
                    recommendation_source=first_query_value(query, "source") or "optimizer",
                    db_path=self.app.db_path,
                )
            )
            return
        if parsed.path == "/api/team-optimizer-restore-status":
            query = parse_qs(parsed.query)
            self._send_json(
                build_team_optimizer_restore_status(
                    boss_key=first_query_value(query, "boss") or "demon_lord",
                    level_key=first_query_value(query, "level") or "ultra_nightmare",
                    affinity=first_query_value(query, "affinity") or "void",
                    recommendation_source=first_query_value(query, "source") or "optimizer",
                    db_path=self.app.db_path,
                )
            )
            return
        if parsed.path == "/api/clan-boss-simulator-bootstrap":
            self._send_json(build_clan_boss_simulator_bootstrap(self.app.db_path))
            return
        if parsed.path == "/api/clan-boss-recommendations":
            query = parse_qs(parsed.query)
            self._send_json(
                build_clan_boss_recommendations(
                    difficulty=first_query_value(query, "difficulty") or "ultra_nightmare",
                    affinity=first_query_value(query, "affinity") or "void",
                    db_path=self.app.db_path,
                )
            )
            return
        if parsed.path == "/api/ai-training-overview":
            self._send_json(build_ai_training_overview(self.app.db_path))
            return
        if parsed.path == "/api/run-recorder-status":
            self._send_json(build_run_recorder_status())
            return
        if parsed.path == "/api/run-recorder-sessions":
            self._send_json(list_run_recorder_sessions(db_path=self.app.db_path))
            return
        if parsed.path == "/api/run-recorder-session":
            query = parse_qs(parsed.query)
            session_slug = first_query_value(query, "slug")
            if not session_slug:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "Parametro 'slug' mancante.")
                return
            try:
                payload = run_recorder_session_detail(unquote(session_slug), db_path=self.app.db_path)
            except KeyError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
                return
            self._send_json(payload)
            return
        if parsed.path == "/api/run-history-run":
            query = parse_qs(parsed.query)
            run_id = first_query_value(query, "run_id")
            if not run_id:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "Parametro 'run_id' mancante.")
                return
            try:
                payload = run_history_run_detail(int(run_id), self.app.db_path)
            except ValueError:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "Parametro 'run_id' non valido.")
                return
            except KeyError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
                return
            self._send_json(payload)
            return
        if parsed.path == "/api/build-plan":
            query = parse_qs(parsed.query)
            name = first_query_value(query, "name")
            profile = first_query_value(query, "profile") or "arena_speed_lead"
            area_region = first_query_value(query, "region")
            if not name:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "Parametro 'name' mancante.")
                return
            try:
                payload = build_champion_plan(unquote(name), profile_key=profile, area_region=area_region, db_path=self.app.db_path)
            except KeyError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
                return
            self._send_json(payload)
            return
        if parsed.path == "/api/gear-items":
            query = parse_qs(parsed.query)
            self._send_json(
                list_gear_items(
                    db_path=self.app.db_path,
                    search=first_query_value(query, "search"),
                    ownership=first_query_value(query, "ownership") or "all",
                    item_class=first_query_value(query, "item_class"),
                    slot=first_query_value(query, "slot"),
                    set_name=first_query_value(query, "set"),
                    advice=first_query_value(query, "advice"),
                    sort=first_query_value(query, "sort") or "rank",
                )
            )
            return
        if parsed.path == "/api/sell-queue":
            query = parse_qs(parsed.query)
            exclude_ids = query.get("exclude_id") or []
            self._send_json(build_sell_queue_summary(self.app.db_path, exclude_ids=exclude_ids))
            return
        if parsed.path == "/api/champion":
            query = parse_qs(parsed.query)
            name = first_query_value(query, "name")
            if not name:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "Parametro 'name' mancante.")
                return
            try:
                payload = champion_detail(unquote(name), self.app.db_path)
            except KeyError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
                return
            self._send_json(payload)
            return
        if parsed.path == "/api/gear-item":
            query = parse_qs(parsed.query)
            item_id = first_query_value(query, "id")
            if not item_id:
                self._send_error_json(HTTPStatus.BAD_REQUEST, "Parametro 'id' mancante.")
                return
            try:
                payload = gear_item_detail(unquote(item_id), self.app.db_path)
            except KeyError as exc:
                self._send_error_json(HTTPStatus.NOT_FOUND, str(exc))
                return
            self._send_json(payload)
            return
        self._send_error_json(HTTPStatus.NOT_FOUND, "Endpoint non trovato.")

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        try:
            payload = self._read_json_body()
        except UnicodeDecodeError:
            self._send_error_json(HTTPStatus.BAD_REQUEST, "Body JSON non UTF-8.")
            return
        except json.JSONDecodeError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, f"Body JSON non valido: {exc.msg}")
            return
        except ValueError as exc:
            self._send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        try:
            if parsed.path == "/api/rebuild-db":
                summary = bootstrap_database(
                    source_path=self.app.source_path,
                    db_path=self.app.db_path,
                    rebuild=True,
                )
                self._send_json({"ok": True, "summary": summary})
                return
            if parsed.path == "/api/update-targets":
                summary = enrich_registry_from_source("auto", db_path=self.app.db_path)
                self._send_json({"ok": True, "summary": summary})
                return
            if parsed.path == "/api/recompute-stats":
                summary = refresh_account_stats_from_source(
                    source_path=self.app.source_path,
                    db_path=self.app.db_path,
                )
                self._send_json({"ok": True, "summary": summary})
                return
            if parsed.path == "/api/run-recorder-start":
                interval_seconds = parse_float_value(payload.get("interval_seconds"), 0.35)
                duration_seconds = parse_float_value(payload.get("duration_seconds"), 0.0)
                status = RUN_RECORDER.start(interval_seconds=interval_seconds, duration_seconds=duration_seconds)
                self._send_json({"ok": True, "status": status})
                return
            if parsed.path == "/api/run-recorder-stop":
                was_running = bool(RUN_RECORDER.status().get("running"))
                status = RUN_RECORDER.stop()
                import_summary: Dict[str, Any] = {}
                session_slug = str(status.get("session_slug") or "").strip()
                if was_running and session_slug:
                    import_summary = import_run_recorder_session(
                        session_slug,
                        db_path=self.app.db_path,
                        recorder=RUN_RECORDER,
                        allow_running=True,
                    )
                self._send_json({"ok": True, "status": status, "import_summary": import_summary})
                return
            if parsed.path == "/api/run-recorder-import-session":
                session_slug = str(payload.get("session_slug") or "").strip()
                if not session_slug:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "session_slug mancante.")
                    return
                result = import_run_recorder_session(session_slug, db_path=self.app.db_path, recorder=RUN_RECORDER)
                self._send_json({"ok": True, "result": result})
                return
            if parsed.path == "/api/run-recorder-import-all":
                include_running = bool(payload.get("include_running"))
                result = import_all_run_recorder_sessions(
                    db_path=self.app.db_path,
                    recorder=RUN_RECORDER,
                    include_running=include_running,
                )
                self._send_json({"ok": True, "result": result})
                return
            if parsed.path == "/api/run-recorder-delete-session":
                session_slug = str(payload.get("session_slug") or "").strip()
                if not session_slug:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "session_slug mancante.")
                    return
                result = delete_run_recorder_session(session_slug)
                self._send_json(result)
                return
            if parsed.path == "/api/refresh-gear":
                payload = refresh_gear_from_game(
                    db_path=self.app.db_path,
                    source_path=self.app.source_path,
                )
                self._send_json(payload)
                return
            if parsed.path == "/api/update-champion":
                champion_name = str(payload.get("champion_name") or "").strip()
                if not champion_name:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "champion_name mancante.")
                    return
                summary = enrich_registry_from_source(
                    "auto",
                    db_path=self.app.db_path,
                    champion_names=[champion_name],
                )
                self._send_json({"ok": True, "summary": summary})
                return
            if parsed.path in {"/api/live-sell-artifacts", "/api/queue-sell-artifacts", "/api/local-sell-artifacts"}:
                result = sell_artifacts_from_queue(
                    artifact_ids=list(payload.get("artifact_ids") or []),
                    db_path=self.app.db_path,
                    access_token=str(payload.get("access_token") or "").strip() or None,
                )
                self._send_json({"ok": True, "result": result})
                return
            if parsed.path == "/api/team-optimizer-equip":
                result = equip_team_optimizer_in_game(
                    boss_key=str(payload.get("boss") or "").strip() or "demon_lord",
                    level_key=str(payload.get("level") or "").strip() or "ultra_nightmare",
                    affinity=str(payload.get("affinity") or "").strip() or "void",
                    recommendation_source=str(payload.get("source") or "").strip() or "optimizer",
                    db_path=self.app.db_path,
                )
                emit_attention_beep()
                self._send_json(result)
                return
            if parsed.path == "/api/team-optimizer-equip-member":
                result = equip_team_optimizer_member_in_game(
                    champion_name=str(payload.get("champion_name") or "").strip(),
                    champ_id=str(payload.get("champ_id") or "").strip(),
                    boss_key=str(payload.get("boss") or "").strip() or "demon_lord",
                    level_key=str(payload.get("level") or "").strip() or "ultra_nightmare",
                    affinity=str(payload.get("affinity") or "").strip() or "void",
                    recommendation_source=str(payload.get("source") or "").strip() or "optimizer",
                    db_path=self.app.db_path,
                )
                emit_attention_beep()
                self._send_json(result)
                return
            if parsed.path == "/api/team-optimizer-save-snapshot":
                result = save_named_team_optimizer_snapshot(
                    boss_key=str(payload.get("boss") or "").strip() or "demon_lord",
                    level_key=str(payload.get("level") or "").strip() or "ultra_nightmare",
                    affinity=str(payload.get("affinity") or "").strip() or "void",
                    recommendation_source=str(payload.get("source") or "").strip() or "optimizer",
                    db_path=self.app.db_path,
                )
                self._send_json({"ok": True, "snapshot": build_snapshot_status_payload(result)})
                return
            if parsed.path == "/api/team-optimizer-restore-last":
                result = restore_last_team_optimizer_equip(db_path=self.app.db_path)
                emit_attention_beep()
                self._send_json(result)
                return
            if parsed.path == "/api/team-optimizer-simulate":
                result = simulate_team_optimizer_opening_preferences(
                    boss_key=str(payload.get("boss") or "").strip() or "demon_lord",
                    level_key=str(payload.get("level") or "").strip() or "ultra_nightmare",
                    affinity=str(payload.get("affinity") or "").strip() or "void",
                    recommendation_source=str(payload.get("source") or "").strip() or "optimizer",
                    opener_preferences=dict(payload.get("opener_preferences") or {}),
                    max_boss_turns=int(payload.get("max_boss_turns") or 6),
                    db_path=self.app.db_path,
                )
                self._send_json(result)
                return
            if parsed.path == "/api/team-optimizer-restore-snapshot":
                result = restore_named_team_optimizer_snapshot(
                    boss_key=str(payload.get("boss") or "").strip() or "demon_lord",
                    level_key=str(payload.get("level") or "").strip() or "ultra_nightmare",
                    affinity=str(payload.get("affinity") or "").strip() or "void",
                    recommendation_source=str(payload.get("source") or "").strip() or "optimizer",
                    db_path=self.app.db_path,
                )
                emit_attention_beep()
                self._send_json(result)
                return
            if parsed.path == "/api/clan-boss-simulate":
                self._send_json(simulate_clan_boss_battle(payload))
                return
            if parsed.path == "/api/ai-train-baseline":
                encounter_key = str(payload.get("encounter_key") or "").strip()
                if not encounter_key:
                    self._send_error_json(HTTPStatus.BAD_REQUEST, "Parametro 'encounter_key' mancante.")
                    return
                output_path = str(payload.get("output_path") or "").strip()
                resolved_output = Path(output_path) if output_path else None
                self._send_json(
                    train_ai_baseline_model(
                        encounter_key=encounter_key,
                        db_path=self.app.db_path,
                        output_path=resolved_output,
                    )
                )
                return
            if parsed.path == "/api/ai-cleanup-duplicates":
                self._send_json(
                    cleanup_ai_training_duplicates(
                        db_path=self.app.db_path,
                        source=str(payload.get("source") or "").strip() or "probe_import",
                    )
                )
                return
            if parsed.path == "/api/set-curation-save":
                entry = save_local_set_entry(payload)
                summary = bootstrap_database(
                    source_path=self.app.source_path,
                    db_path=self.app.db_path,
                    rebuild=True,
                )
                self._send_json({"ok": True, "entry": entry, "summary": summary})
                return
        except Exception as exc:
            self._send_error_json(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            return
        self._send_error_json(HTTPStatus.NOT_FOUND, "Endpoint non trovato.")

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _emit_response(self, encoded: bytes, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        try:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        except Exception as exc:
            # Browsers can cancel in-flight requests while a large payload is still being sent.
            if is_client_disconnect_error(exc):
                return
            raise

    def _send_file(self, path: Path, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        if not path.exists():
            self._send_error_json(HTTPStatus.NOT_FOUND, f"Asset mancante: {path.name}")
            return
        encoded = path.read_bytes()
        self._emit_response(encoded, content_type, status=status)

    def _send_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._emit_response(encoded, "application/json; charset=utf-8", status=status)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _read_json_body(self) -> Dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("Header Content-Length non valido.") from exc
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        payload = json.loads(raw.decode("utf-8"))
        return payload if isinstance(payload, dict) else {}


class CBForgeWebServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], handler_cls: type[BaseHTTPRequestHandler], db_path: Path, source_path: Path):
        super().__init__(server_address, handler_cls)
        self.db_path = db_path
        self.source_path = source_path


def prepare_server_runtime(db_path: Path = DB_PATH, source_path: Path = NORMALIZED_SOURCE_PATH, refresh_on_start: bool = True) -> Dict[str, Any]:
    ensure_schema(db_path)
    if not refresh_on_start:
        return {
            "ok": True,
            "mode": "startup_skip",
            "message": "Refresh iniziale saltato.",
        }
    if not source_path.exists():
        return {
            "ok": False,
            "mode": "startup_missing_source",
            "message": f"Dump locale non trovato: {source_path}",
        }
    return refresh_gear_from_game(
        db_path=db_path,
        source_path=source_path,
        mode="local_only",
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CB Forge web interface")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--source-path", type=Path, default=NORMALIZED_SOURCE_PATH)
    parser.add_argument("--skip-startup-refresh", action="store_true", help="Non ricarica il DB dal dump locale all'avvio del server.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    startup_summary = prepare_server_runtime(
        db_path=args.db_path,
        source_path=args.source_path,
        refresh_on_start=not bool(args.skip_startup_refresh),
    )
    startup_message = str(startup_summary.get("message") or "").strip()
    if startup_message:
        print(startup_message)
    server = CBForgeWebServer((args.host, args.port), CBForgeHandler, db_path=args.db_path, source_path=args.source_path)
    print(f"CB Forge web listening on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
