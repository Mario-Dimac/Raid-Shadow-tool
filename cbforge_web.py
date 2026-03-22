from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import subprocess
from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib.parse import parse_qs, unquote, urlparse

from account_stats import materialize_base_totals
from build_planner import build_champion_plan, list_area_bonus_regions, list_build_profiles
from forge_db import DB_PATH, NORMALIZED_SOURCE_PATH, bootstrap_database, ensure_schema, refresh_account_stats_from_source
from gear_advisor import evaluate_gear_item, summarize_gear_verdicts
import hellhades_live
from hellhades_enrich import enrich_registry_from_source
from registry_report import build_registry_report
from set_curation import load_local_set_entries, save_local_set_entry


BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"
LEGACY_DIR = BASE_DIR / "old" / "legacy_20260318"
LEGACY_INPUT_DIR = LEGACY_DIR / "input"
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


def choose_set_display_name(set_name: str, curated_entry: Dict[str, Any] | None = None) -> str:
    curated_entry = curated_entry or {}
    raw_name = str(set_name or "").strip()
    canonical_name = str(curated_entry.get("canonical_name") or "").strip()
    display_name = str(curated_entry.get("display_name") or "").strip()
    if canonical_name and (not display_name or display_name == raw_name):
        return canonical_name
    return display_name or canonical_name or SET_DISPLAY_NAMES.get(raw_name, raw_name)


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


def refresh_gear_from_game(
    db_path: Path = DB_PATH,
    source_path: Path = NORMALIZED_SOURCE_PATH,
) -> Dict[str, Any]:
    if not LEGACY_DIR.exists():
        raise FileNotFoundError(f"Pipeline legacy non trovata: {LEGACY_DIR}")

    commands = [
        ["python", "extract_local.py"],
        ["python", "normalize.py"],
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
    return {
        "ok": True,
        "results": results,
        "copied_files": copied_files,
        "summary": rebuild_summary,
        "output": "\n\n".join(chunk for chunk in combined_output if chunk),
    }


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


def champion_sort_key(champion: Dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        int(champion["level"]),
        int(champion["rank"]),
        1 if champion["booked"] else 0,
        1 if champion["enriched"] else 0,
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
    return {"pages": pages_payload}


def collect_sell_queue_candidates(
    db_path: Path = DB_PATH,
    exclude_ids: List[str] | None = None,
) -> Dict[str, List[Dict[str, Any]]]:
    excluded = {str(item_id).strip() for item_id in (exclude_ids or []) if str(item_id).strip()}
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

    result = hellhades_live.sell_artifacts_live(approved_ids, access_token=access_token)
    approved_items = [candidates_by_id[item_id] for item_id in approved_ids]
    message = str(result.get("message") or "")
    if rejected_ids:
        message = f"{message} Ignorati {len(rejected_ids)} ID fuori coda o non vendibili."
    result.update(
        {
            "requested_ids": requested_ids,
            "approved_ids": approved_ids,
            "rejected_ids": rejected_ids,
            "approved_items": approved_items,
            "message": message.strip(),
        }
    )
    return result


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
            SELECT champ_id, champion_name, rarity, affinity, faction, level, rank, awakening_level, empowerment_level, booked
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
        stat_model_row = conn.execute(
            """
            SELECT source, completeness, unsupported_sets_json, applied_sets_json, computed_at
            FROM account_champion_stat_models
            WHERE champ_id = ?
            """,
            (account_row["champ_id"],),
        ).fetchone()
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
        payload = self._read_json_body()
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
            if parsed.path == "/api/live-sell-artifacts":
                result = sell_artifacts_from_queue(
                    artifact_ids=list(payload.get("artifact_ids") or []),
                    db_path=self.app.db_path,
                    access_token=str(payload.get("access_token") or "").strip() or None,
                )
                self._send_json({"ok": True, "result": result})
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

    def _send_file(self, path: Path, content_type: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        if not path.exists():
            self._send_error_json(HTTPStatus.NOT_FOUND, f"Asset mancante: {path.name}")
            return
        encoded = path.read_bytes()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_json(self, payload: Dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
        encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _send_error_json(self, status: HTTPStatus, message: str) -> None:
        self._send_json({"error": message}, status=status)

    def _read_json_body(self) -> Dict[str, Any]:
        length = int(self.headers.get("Content-Length") or 0)
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CB Forge web interface")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--source-path", type=Path, default=NORMALIZED_SOURCE_PATH)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_schema(args.db_path)
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
