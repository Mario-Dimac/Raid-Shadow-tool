from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
SQLITE_DB_PATH = INPUT_DIR / "cbforge.db"
NORMALIZED_ACCOUNT_PATH = INPUT_DIR / "normalized_account.json"


def ensure_schema(path: Path = SQLITE_DB_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS roster_champions (
                champ_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                rarity TEXT,
                rank INTEGER,
                level INTEGER,
                affinity TEXT,
                faction TEXT,
                awakening_level INTEGER,
                empowerment_level INTEGER,
                booked INTEGER,
                role_tags_json TEXT NOT NULL,
                base_stats_json TEXT NOT NULL,
                total_stats_json TEXT NOT NULL,
                equipped_item_ids_json TEXT NOT NULL,
                skills_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS champion_skill_registry (
                champion_name TEXT PRIMARY KEY,
                simulator_supported INTEGER NOT NULL,
                hint_roles_json TEXT NOT NULL,
                hint_boss_scores_json TEXT NOT NULL,
                simulator_definition_json TEXT NOT NULL,
                account_skill_rows_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS gear_items (
                item_id TEXT PRIMARY KEY,
                item_class TEXT,
                slot TEXT,
                set_name TEXT,
                rarity TEXT,
                rank INTEGER,
                level INTEGER,
                ascension_level INTEGER,
                required_faction TEXT,
                required_faction_id INTEGER,
                equipped_by TEXT,
                locked INTEGER NOT NULL,
                main_stat_type TEXT,
                main_stat_value REAL NOT NULL,
                substats_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS account_bonuses (
                bonus_id TEXT PRIMARY KEY,
                source TEXT,
                scope TEXT,
                target TEXT,
                stat TEXT,
                value REAL NOT NULL,
                active INTEGER NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS set_registry (
                set_name TEXT PRIMARY KEY,
                observed_items INTEGER NOT NULL,
                pieces_required INTEGER NOT NULL,
                supported_in_simulator INTEGER NOT NULL,
                heal_each_turn_pct REAL NOT NULL,
                stats_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS combat_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                saved_at TEXT NOT NULL,
                team_name TEXT NOT NULL,
                difficulty TEXT,
                affinity TEXT,
                boss_turn INTEGER NOT NULL,
                damage REAL NOT NULL,
                source TEXT,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS combat_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT,
                ended_at TEXT,
                team_name TEXT,
                difficulty TEXT,
                affinity TEXT,
                source TEXT,
                members_json TEXT NOT NULL,
                payload_json TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS app_state (
                state_key TEXT PRIMARY KEY,
                state_value_json TEXT NOT NULL
            )
            """
        )
        conn.commit()


def rebuild_registry_database(account: Optional[Dict[str, Any]] = None, path: Path = SQLITE_DB_PATH) -> Dict[str, Any]:
    from cb_rules import CHAMPION_HINTS
    from cb_simulator import CHAMPION_DEFINITIONS, SET_BONUS_RULES

    account_data = account or load_account_from_json()
    ensure_schema(path)

    best_skill_rows: Dict[str, Dict[str, Any]] = {}
    observed_sets: Dict[str, int] = {}
    for champion in list_value(account_data.get("champions")):
        name = string_value(champion.get("name"))
        current = best_skill_rows.get(name)
        if current is None or (int_value(champion.get("level")), int_value(champion.get("rank"))) > (
            int_value(current.get("level")),
            int_value(current.get("rank")),
        ):
            best_skill_rows[name] = champion
    for gear in list_value(account_data.get("gear")):
        set_name = string_value(gear.get("set_name")).strip()
        if set_name:
            observed_sets[set_name] = observed_sets.get(set_name, 0) + 1

    with sqlite3.connect(path) as conn:
        conn.execute("DELETE FROM roster_champions")
        conn.execute("DELETE FROM champion_skill_registry")
        conn.execute("DELETE FROM gear_items")
        conn.execute("DELETE FROM account_bonuses")
        conn.execute("DELETE FROM set_registry")

        for champion in list_value(account_data.get("champions")):
            conn.execute(
                """
                INSERT INTO roster_champions (
                    champ_id, name, rarity, rank, level, affinity, faction,
                    awakening_level, empowerment_level, booked,
                    role_tags_json, base_stats_json, total_stats_json,
                    equipped_item_ids_json, skills_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    string_value(champion.get("champ_id")),
                    string_value(champion.get("name")),
                    string_value(champion.get("rarity")),
                    int_value(champion.get("rank")),
                    int_value(champion.get("level")),
                    string_value(champion.get("affinity")),
                    string_value(champion.get("faction")),
                    int_value(champion.get("awakening_level")),
                    int_value(champion.get("empowerment_level")),
                    1 if bool(champion.get("booked")) else 0,
                    dumps_json(list_value(champion.get("role_tags"))),
                    dumps_json(dict_value(champion.get("base_stats"))),
                    dumps_json(dict_value(champion.get("total_stats"))),
                    dumps_json([string_value(item) for item in list_value(champion.get("equipped_item_ids"))]),
                    dumps_json(list_value(champion.get("skills"))),
                ),
            )

        for item in list_value(account_data.get("gear")):
            main_stat = dict_value(item.get("main_stat"))
            conn.execute(
                """
                INSERT INTO gear_items (
                    item_id, item_class, slot, set_name, rarity, rank, level,
                    ascension_level, required_faction, required_faction_id,
                    equipped_by, locked, main_stat_type, main_stat_value, substats_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    string_value(item.get("item_id")),
                    string_value(item.get("item_class")),
                    string_value(item.get("slot")),
                    string_value(item.get("set_name")),
                    string_value(item.get("rarity")),
                    int_value(item.get("rank")),
                    int_value(item.get("level")),
                    int_value(item.get("ascension_level")),
                    string_value(item.get("required_faction")),
                    int_value(item.get("required_faction_id")),
                    string_value(item.get("equipped_by")),
                    1 if bool(item.get("locked")) else 0,
                    string_value(main_stat.get("type")),
                    float_value(main_stat.get("value")),
                    dumps_json(list_value(item.get("substats"))),
                ),
            )

        for bonus in list_value(account_data.get("account_bonuses")):
            conn.execute(
                """
                INSERT INTO account_bonuses (
                    bonus_id, source, scope, target, stat, value, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    string_value(bonus.get("bonus_id")),
                    string_value(bonus.get("source")),
                    string_value(bonus.get("scope")),
                    string_value(bonus.get("target")),
                    string_value(bonus.get("stat")),
                    float_value(bonus.get("value")),
                    1 if bool(bonus.get("active")) else 0,
                ),
            )

        for name in sorted(best_skill_rows):
            champion = best_skill_rows[name]
            hint = CHAMPION_HINTS.get(name)
            simulator_definition = CHAMPION_DEFINITIONS.get(name)
            conn.execute(
                """
                INSERT INTO champion_skill_registry (
                    champion_name, simulator_supported, hint_roles_json,
                    hint_boss_scores_json, simulator_definition_json, account_skill_rows_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    1 if simulator_definition else 0,
                    dumps_json(list(hint.roles) if hint else []),
                    dumps_json(dict(hint.boss_scores) if hint else {}),
                    dumps_json(serialize_champion_definition(simulator_definition)),
                    dumps_json(list_value(champion.get("skills"))),
                ),
            )

        for set_name in sorted(set(observed_sets) | set(SET_BONUS_RULES)):
            rule = dict_value(SET_BONUS_RULES.get(set_name))
            conn.execute(
                """
                INSERT INTO set_registry (
                    set_name, observed_items, pieces_required,
                    supported_in_simulator, heal_each_turn_pct, stats_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    set_name,
                    int(observed_sets.get(set_name, 0)),
                    int_value(rule.get("pieces")),
                    1 if rule else 0,
                    float_value(rule.get("heal_each_turn_pct")),
                    dumps_json(dict_value(rule.get("stats"))),
                ),
            )

        conn.commit()

    return sqlite_status(path)


def list_combat_runs(limit: int = 50, path: Path = SQLITE_DB_PATH) -> List[Dict[str, Any]]:
    ensure_schema(path)
    with sqlite3.connect(path) as conn:
        rows = conn.execute(
            "SELECT payload_json FROM combat_runs ORDER BY saved_at DESC LIMIT ?",
            (int(limit),),
        ).fetchall()
    return [loads_json(row[0]) for row in rows]


def insert_combat_run(entry: Dict[str, Any], path: Path = SQLITE_DB_PATH) -> None:
    ensure_schema(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO combat_runs (
                saved_at, team_name, difficulty, affinity, boss_turn, damage, source, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                string_value(entry.get("saved_at")),
                string_value(entry.get("team_name")),
                string_value(entry.get("difficulty")),
                string_value(entry.get("affinity")),
                int_value(entry.get("boss_turn")),
                float_value(entry.get("damage")),
                string_value(entry.get("source")),
                dumps_json(entry),
            ),
        )
        conn.commit()


def get_active_session(path: Path = SQLITE_DB_PATH) -> Optional[Dict[str, Any]]:
    ensure_schema(path)
    with sqlite3.connect(path) as conn:
        row = conn.execute(
            "SELECT state_value_json FROM app_state WHERE state_key = 'active_session'"
        ).fetchone()
    if not row:
        return None
    session = loads_json(row[0])
    return session if isinstance(session, dict) and session else None


def set_active_session(session: Optional[Dict[str, Any]], path: Path = SQLITE_DB_PATH) -> None:
    ensure_schema(path)
    with sqlite3.connect(path) as conn:
        if session:
            conn.execute(
                """
                INSERT INTO app_state (state_key, state_value_json)
                VALUES ('active_session', ?)
                ON CONFLICT(state_key) DO UPDATE SET state_value_json = excluded.state_value_json
                """,
                (dumps_json(session),),
            )
        else:
            conn.execute("DELETE FROM app_state WHERE state_key = 'active_session'")
        conn.commit()


def insert_combat_session(entry: Dict[str, Any], path: Path = SQLITE_DB_PATH) -> None:
    ensure_schema(path)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO combat_sessions (
                started_at, ended_at, team_name, difficulty, affinity, source, members_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                string_value(entry.get("started_at")),
                string_value(entry.get("ended_at")),
                string_value(entry.get("team_name")),
                string_value(entry.get("difficulty")),
                string_value(entry.get("affinity")),
                string_value(entry.get("source")),
                dumps_json(list_value(entry.get("members"))),
                dumps_json(entry),
            ),
        )
        conn.commit()


def sqlite_status(path: Path = SQLITE_DB_PATH) -> Dict[str, Any]:
    ensure_schema(path)
    status = {
        "path": str(path),
        "exists": path.exists(),
        "size": path.stat().st_size if path.exists() else 0,
        "roster_champions": 0,
        "skill_registry": 0,
        "gear_items": 0,
        "account_bonuses": 0,
        "set_registry": 0,
        "combat_runs": 0,
        "combat_sessions": 0,
    }
    with sqlite3.connect(path) as conn:
        for table, key in (
            ("roster_champions", "roster_champions"),
            ("champion_skill_registry", "skill_registry"),
            ("gear_items", "gear_items"),
            ("account_bonuses", "account_bonuses"),
            ("set_registry", "set_registry"),
            ("combat_runs", "combat_runs"),
            ("combat_sessions", "combat_sessions"),
        ):
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            status[key] = int(row[0] if row else 0)
    return status


def has_runtime_account(path: Path = SQLITE_DB_PATH) -> bool:
    ensure_schema(path)
    with sqlite3.connect(path) as conn:
        champion_row = conn.execute("SELECT COUNT(*) FROM roster_champions").fetchone()
        gear_row = conn.execute("SELECT COUNT(*) FROM gear_items").fetchone()
    champion_count = int(champion_row[0] if champion_row else 0)
    gear_count = int(gear_row[0] if gear_row else 0)
    return champion_count > 0 and gear_count > 0


def load_account_from_sqlite(path: Path = SQLITE_DB_PATH) -> Dict[str, Any]:
    ensure_schema(path)
    with sqlite3.connect(path) as conn:
        champion_rows = conn.execute(
            """
            SELECT
                champ_id, name, rarity, rank, level, affinity, faction,
                awakening_level, empowerment_level, booked,
                role_tags_json, base_stats_json, total_stats_json,
                equipped_item_ids_json, skills_json
            FROM roster_champions
            ORDER BY level DESC, rank DESC, name ASC, champ_id ASC
            """
        ).fetchall()
        gear_rows = conn.execute(
            """
            SELECT
                item_id, item_class, slot, set_name, rarity, rank, level,
                ascension_level, required_faction, required_faction_id,
                equipped_by, locked, main_stat_type, main_stat_value, substats_json
            FROM gear_items
            ORDER BY slot ASC, item_id ASC
            """
        ).fetchall()
        bonus_rows = conn.execute(
            """
            SELECT bonus_id, source, scope, target, stat, value, active
            FROM account_bonuses
            ORDER BY source ASC, bonus_id ASC
            """
        ).fetchall()

    champions = [
        {
            "champ_id": string_value(row[0]),
            "name": string_value(row[1]),
            "rarity": string_value(row[2]),
            "rank": int_value(row[3]),
            "level": int_value(row[4]),
            "affinity": string_value(row[5]),
            "faction": string_value(row[6]),
            "awakening_level": int_value(row[7]),
            "empowerment_level": int_value(row[8]),
            "booked": bool(int_value(row[9])),
            "role_tags": list_value(loads_json(row[10])),
            "base_stats": dict_value(loads_json(row[11])),
            "total_stats": dict_value(loads_json(row[12])),
            "equipped_item_ids": [string_value(item_id) for item_id in list_value(loads_json(row[13]))],
            "skills": list_value(loads_json(row[14])),
        }
        for row in champion_rows
    ]
    gear = [
        {
            "item_id": string_value(row[0]),
            "item_class": string_value(row[1]),
            "slot": string_value(row[2]),
            "set_name": string_value(row[3]),
            "rarity": string_value(row[4]),
            "rank": int_value(row[5]),
            "level": int_value(row[6]),
            "ascension_level": int_value(row[7]),
            "required_faction": string_value(row[8]),
            "required_faction_id": int_value(row[9]),
            "equipped_by": string_value(row[10]),
            "locked": bool(int_value(row[11])),
            "main_stat": {
                "type": string_value(row[12]),
                "value": float_value(row[13]),
            },
            "substats": list_value(loads_json(row[14])),
        }
        for row in gear_rows
    ]
    bonuses = [
        {
            "bonus_id": string_value(row[0]),
            "source": string_value(row[1]),
            "scope": string_value(row[2]),
            "target": string_value(row[3]),
            "stat": string_value(row[4]),
            "value": float_value(row[5]),
            "active": bool(int_value(row[6])),
        }
        for row in bonus_rows
    ]
    account = {
        "source": str(path),
        "champions": champions,
        "gear": gear,
        "account_bonuses": bonuses,
    }
    reconcile_loaded_account_ownership(account)
    return account


def load_account_from_json(path: Path = NORMALIZED_ACCOUNT_PATH) -> Dict[str, Any]:
    account = json.loads(path.read_text(encoding="utf-8-sig"))
    reconcile_loaded_account_ownership(account)
    return account


def serialize_champion_definition(definition: Any) -> Dict[str, Any]:
    if not definition:
        return {}
    return {
        "opener": list(definition.opener),
        "priority": list(definition.priority),
        "passive": definition.passive or "",
        "notes": definition.notes,
        "skills": {
            slot: {
                "slot": skill.slot,
                "name": skill.name,
                "cooldown": skill.cooldown,
                "damage_factor": skill.damage_factor,
                "team_buffs": dict(skill.team_buffs),
                "self_buffs": dict(skill.self_buffs),
                "boss_debuffs": dict(skill.boss_debuffs),
                "cooldown_reduction_allies": skill.cooldown_reduction_allies,
                "turn_meter_fill_allies": skill.turn_meter_fill_allies,
                "direct_heal_allies": skill.direct_heal_allies,
            }
            for slot, skill in definition.skills.items()
        },
    }


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def loads_json(value: Any) -> Dict[str, Any]:
    if not value:
        return {}
    try:
        loaded = json.loads(str(value))
    except (TypeError, json.JSONDecodeError):
        return {}
    return loaded if isinstance(loaded, dict) else loaded


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def float_value(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def reconcile_loaded_account_ownership(account: Dict[str, Any]) -> None:
    champions = list_value(account.get("champions"))
    gear = list_value(account.get("gear"))
    owner_by_item_id: Dict[str, str] = {}

    for champion in champions:
        champ_id = string_value(champion.get("champ_id"))
        for item_id in list_value(champion.get("equipped_item_ids")):
            normalized_item_id = string_value(item_id)
            if normalized_item_id:
                owner_by_item_id[normalized_item_id] = champ_id

    for item in gear:
        item_id = string_value(item.get("item_id"))
        owner_id = owner_by_item_id.get(item_id)
        if owner_id:
            item["equipped_by"] = owner_id
