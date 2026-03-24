from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


BASE_DIR = Path(__file__).resolve().parent
LOCAL_SET_REGISTRY_PATH = BASE_DIR / "data_sources" / "local_set_registry.json"

STAT_ALIASES = {
    "spd": "spd",
    "speed": "spd",
    "acc": "acc",
    "accuracy": "acc",
    "res": "res",
    "resist": "res",
    "resistance": "res",
    "c.rate": "crit_rate",
    "crit rate": "crit_rate",
    "critical rate": "crit_rate",
    "critical chance": "crit_rate",
    "crit chance": "crit_rate",
    "c.dmg": "crit_dmg",
    "crit dmg": "crit_dmg",
    "critical damage": "crit_dmg",
    "crit damage": "crit_dmg",
    "hp": "hp",
    "hp%": "hp_pct",
    "hp pct": "hp_pct",
    "hp percent": "hp_pct",
    "health": "hp",
    "health%": "hp_pct",
    "atk": "atk",
    "atk%": "atk_pct",
    "atk pct": "atk_pct",
    "attack": "atk",
    "attack%": "atk_pct",
    "attack pct": "atk_pct",
    "def": "def",
    "def%": "def_pct",
    "def pct": "def_pct",
    "defense": "def",
    "defense%": "def_pct",
    "defence": "def",
    "defence%": "def_pct",
}


def load_local_set_registry(path: Path = LOCAL_SET_REGISTRY_PATH) -> Dict[str, Any]:
    if not path.exists():
        return {"version": 1, "updated_at": "", "sets": []}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {"version": 1, "updated_at": "", "sets": []}
    entries = payload.get("sets")
    if not isinstance(entries, list):
        payload["sets"] = []
    return payload


def load_local_set_rules(path: Path = LOCAL_SET_REGISTRY_PATH) -> Dict[str, Dict[str, Any]]:
    payload = load_local_set_registry(path)
    rules: Dict[str, Dict[str, Any]] = {}
    for entry in payload.get("sets") or []:
        if not isinstance(entry, dict):
            continue
        set_name = str(entry.get("set_name") or "").strip()
        if not set_name:
            continue
        rules[set_name] = normalized_rule_from_entry(entry)
    return rules


def load_local_set_entries(path: Path = LOCAL_SET_REGISTRY_PATH) -> List[Dict[str, Any]]:
    payload = load_local_set_registry(path)
    entries = [entry for entry in (payload.get("sets") or []) if isinstance(entry, dict)]
    entries.sort(key=lambda entry: str(entry.get("set_name") or "").lower())
    return entries


def save_local_set_entry(payload: Dict[str, Any], path: Path = LOCAL_SET_REGISTRY_PATH) -> Dict[str, Any]:
    entry = normalize_local_set_entry(payload)
    registry = load_local_set_registry(path)
    entries = [row for row in (registry.get("sets") or []) if isinstance(row, dict)]
    updated = False
    for index, current in enumerate(entries):
        if str(current.get("set_name") or "").strip() != entry["set_name"]:
            continue
        entries[index] = entry
        updated = True
        break
    if not updated:
        entries.append(entry)
    entries.sort(key=lambda row: str(row.get("set_name") or "").lower())
    registry["version"] = 1
    registry["updated_at"] = utc_now_text()
    registry["sets"] = entries
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8")
    return entry


def normalize_local_set_entry(payload: Dict[str, Any]) -> Dict[str, Any]:
    set_name = str(payload.get("set_name") or "").strip()
    if not set_name:
        raise ValueError("set_name mancante.")

    canonical_name = str(payload.get("canonical_name") or "").strip()
    set_kind = str(payload.get("set_kind") or "fixed").strip().lower() or "fixed"
    if set_kind not in {"fixed", "variable", "accessory"}:
        raise ValueError(f"set_kind non supportato: {set_kind}")

    pieces_required = int_value(payload.get("pieces_required"))
    max_pieces = int_value(payload.get("max_pieces"))
    counts_accessories = bool_value(payload.get("counts_accessories"))
    display_name = str(payload.get("display_name") or "").strip()
    base_bonus_text = normalize_multiline_text(payload.get("base_bonus_text"))
    thresholds_text = normalize_multiline_text(payload.get("thresholds_text"))

    if set_kind == "fixed":
        pieces_required = max(pieces_required, 1)
        max_pieces = max(max_pieces, 6)
    elif set_kind == "variable":
        pieces_required = 1
        max_pieces = max(max_pieces, 9)
        counts_accessories = bool_value(payload.get("counts_accessories"), True)
    else:
        pieces_required = 1
        max_pieces = max(max_pieces, 3)
        counts_accessories = True

    base_bonus = parse_bonus_text(base_bonus_text)
    threshold_rows = parse_thresholds_text(thresholds_text)
    piece_bonuses = [
        {
            "pieces_required": row["pieces_required"],
            "stats": row["parsed"]["stats"],
            "effect_text": " | ".join(row["parsed"]["effects"]).strip(),
        }
        for row in threshold_rows
    ]
    for piece_bonus in piece_bonuses:
        if not piece_bonus["effect_text"]:
            piece_bonus.pop("effect_text")

    return {
        "set_name": set_name,
        "canonical_name": canonical_name,
        "display_name": display_name,
        "set_kind": set_kind,
        "pieces_required": pieces_required,
        "max_pieces": max_pieces,
        "counts_accessories": counts_accessories,
        "heal_each_turn_pct": base_bonus["heal_each_turn_pct"],
        "stats": base_bonus["stats"],
        "piece_bonuses": piece_bonuses,
        "base_bonus_text": base_bonus_text,
        "thresholds_text": thresholds_text,
        "source": "local_curation",
        "updated_at": utc_now_text(),
    }


def normalized_rule_from_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    rule = {
        "set_kind": str(entry.get("set_kind") or "fixed").strip().lower() or "fixed",
        "pieces_required": int_value(entry.get("pieces_required")),
        "max_pieces": int_value(entry.get("max_pieces")),
        "counts_accessories": bool_value(entry.get("counts_accessories")),
        "heal_each_turn_pct": float_value(entry.get("heal_each_turn_pct")),
        "canonical_name": str(entry.get("canonical_name") or "").strip(),
        "display_name": str(entry.get("display_name") or "").strip(),
        "stats": [],
        "piece_bonuses": [],
        "source": "local_curation",
    }
    for row in list_value(entry.get("stats")):
        if not isinstance(row, dict):
            continue
        stat_type = str(row.get("stat_type") or "").strip()
        if not stat_type:
            continue
        rule["stats"].append((stat_type, float_value(row.get("stat_value"))))
    for row in list_value(entry.get("piece_bonuses")):
        if not isinstance(row, dict):
            continue
        piece_bonus = {
            "pieces_required": int_value(row.get("pieces_required")),
            "stats": [],
        }
        for stat_row in list_value(row.get("stats")):
            if not isinstance(stat_row, dict):
                continue
            stat_type = str(stat_row.get("stat_type") or "").strip()
            if not stat_type:
                continue
            piece_bonus["stats"].append((stat_type, float_value(stat_row.get("stat_value"))))
        effect_text = str(row.get("effect_text") or "").strip()
        if effect_text:
            piece_bonus["effect_text"] = effect_text
        rule["piece_bonuses"].append(piece_bonus)
    return rule


def parse_bonus_text(text: str) -> Dict[str, Any]:
    stats: List[Dict[str, Any]] = []
    effects: List[str] = []
    heal_each_turn_pct = 0.0
    for raw_line in split_bonus_lines(text):
        line = raw_line.strip()
        if not line:
            continue
        heal_value = parse_heal_each_turn(line)
        if heal_value is not None:
            heal_each_turn_pct = heal_value
            continue
        stat_row = parse_stat_line(line)
        if stat_row is not None:
            stats.append(stat_row)
            continue
        normalized_effect = re.sub(r"^(effect|note)\s*:\s*", "", line, flags=re.IGNORECASE).strip()
        if normalized_effect:
            effects.append(normalized_effect)
    return {
        "stats": stats,
        "effects": effects,
        "heal_each_turn_pct": heal_each_turn_pct,
    }


def parse_thresholds_text(text: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in normalize_multiline_text(text).splitlines():
        raw_line = line.strip()
        if not raw_line:
            continue
        match = re.match(r"^\s*(\d+)\s*([:|\-])\s*(.+)$", raw_line)
        if match is None:
            raise ValueError(f"Formato soglia non valido: {raw_line}")
        pieces_required = int(match.group(1))
        bonus_text = match.group(3).strip()
        parsed = parse_bonus_text(bonus_text)
        rows.append(
            {
                "pieces_required": pieces_required,
                "bonus_text": bonus_text,
                "parsed": parsed,
            }
        )
    rows.sort(key=lambda row: int(row["pieces_required"]))
    return rows


def parse_stat_line(line: str) -> Dict[str, Any] | None:
    match = re.match(r"^\s*([A-Za-z.% ]+?)\s*([+-]?\d+(?:[.,]\d+)?)\s*%?\s*$", line)
    if match is None:
        return None
    stat_key = normalize_stat_label(match.group(1))
    if not stat_key:
        return None
    value = float(match.group(2).replace(",", "."))
    return {"stat_type": stat_key, "stat_value": value}


def parse_heal_each_turn(line: str) -> float | None:
    match = re.match(r"^\s*(heal each turn|heal_each_turn|regen each turn)\s*[: ]\s*([+-]?\d+(?:[.,]\d+)?)\s*%?\s*$", line, flags=re.IGNORECASE)
    if match is None:
        return None
    return float(match.group(2).replace(",", "."))


def normalize_stat_label(label: str) -> str:
    normalized = re.sub(r"[^a-z0-9%]+", " ", str(label or "").lower()).strip()
    normalized = normalized.replace("crit. ", "crit ").replace("c rate", "crit rate").replace("c dmg", "crit dmg")
    normalized = normalized.replace("critical heal multiplier", "critical damage")
    return STAT_ALIASES.get(normalized, "")


def split_bonus_lines(text: str) -> List[str]:
    normalized = normalize_multiline_text(text)
    rows: List[str] = []
    for line in normalized.splitlines():
        parts = [part.strip() for part in line.split(";")]
        rows.extend(part for part in parts if part)
    return rows


def normalize_multiline_text(value: Any) -> str:
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(line.rstrip() for line in text.split("\n")).strip()


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


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


def bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return bool(value)
