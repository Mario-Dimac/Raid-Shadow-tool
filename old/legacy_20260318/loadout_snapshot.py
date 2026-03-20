from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
NORMALIZED_PATH = INPUT_DIR / "normalized_account.json"
SNAPSHOT_DIR = INPUT_DIR / "loadout_snapshots"
LATEST_SNAPSHOT_PATH = INPUT_DIR / "latest_loadout_snapshot.json"


def load_account(path: Path = NORMALIZED_PATH) -> Dict[str, Any]:
    account = json.loads(path.read_text(encoding="utf-8-sig"))
    reconcile_loaded_account_ownership(account)
    return account


def build_loadout_snapshot(account: Dict[str, Any]) -> Dict[str, Any]:
    champions = sorted(list_value(account.get("champions")), key=champion_sort_key, reverse=True)
    gear = list_value(account.get("gear"))
    champion_names = {
        string_value(champion.get("champ_id")): string_value(champion.get("name"))
        for champion in champions
    }

    snapshot_champions: List[Dict[str, Any]] = []
    for champion in champions:
        champ_id = string_value(champion.get("champ_id"))
        equipped = [
            {
                "item_id": string_value(item.get("item_id")),
                "slot": string_value(item.get("slot")),
                "set_name": string_value(item.get("set_name")),
                "main_stat": mapping_value(item.get("main_stat")),
                "substats": list_value(item.get("substats")),
            }
            for item in gear
            if string_value(item.get("equipped_by")) == champ_id
        ]
        snapshot_champions.append(
            {
                "champ_id": champ_id,
                "name": string_value(champion.get("name")),
                "level": champion.get("level"),
                "rank": champion.get("rank"),
                "equipped_items": sorted(equipped, key=lambda item: slot_sort_key(item.get("slot"))),
            }
        )

    snapshot_gear = [
        {
            "item_id": string_value(item.get("item_id")),
            "slot": string_value(item.get("slot")),
            "set_name": string_value(item.get("set_name")),
            "equipped_by": string_value(item.get("equipped_by")),
            "equipped_by_name": champion_names.get(string_value(item.get("equipped_by")), ""),
            "main_stat": mapping_value(item.get("main_stat")),
            "substats": list_value(item.get("substats")),
        }
        for item in gear
    ]

    return {
        "saved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "source": str(NORMALIZED_PATH),
        "champion_count": len(champions),
        "gear_count": len(gear),
        "champions": snapshot_champions,
        "gear": snapshot_gear,
    }


def save_current_loadout_snapshot(label: str = "manual") -> Dict[str, str]:
    account = load_account()
    snapshot = build_loadout_snapshot(account)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot_path = SNAPSHOT_DIR / f"{timestamp}_{sanitize_label(label)}.json"
    snapshot_path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    LATEST_SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False), encoding="utf-8")
    return {
        "snapshot_path": str(snapshot_path),
        "latest_path": str(LATEST_SNAPSHOT_PATH),
    }


def ensure_current_loadout_snapshot() -> Dict[str, str]:
    if LATEST_SNAPSHOT_PATH.exists():
        return {
            "latest_path": str(LATEST_SNAPSHOT_PATH),
        }
    return save_current_loadout_snapshot(label="initial")


def snapshot_status() -> Dict[str, Any]:
    status: Dict[str, Any] = {
        "latest_path": str(LATEST_SNAPSHOT_PATH),
        "latest_exists": LATEST_SNAPSHOT_PATH.exists(),
        "snapshot_dir": str(SNAPSHOT_DIR),
        "count": 0,
    }
    if SNAPSHOT_DIR.exists():
        status["count"] = len(list(SNAPSHOT_DIR.glob("*.json")))
    return status


def sanitize_label(value: str) -> str:
    cleaned = "".join(char.lower() if char.isalnum() else "_" for char in value.strip())
    return cleaned.strip("_") or "snapshot"


def slot_sort_key(slot: Any) -> int:
    order = {
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
    return order.get(string_value(slot), 99)


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def mapping_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


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


def champion_sort_key(champion: Dict[str, Any]) -> tuple[int, int, int, int]:
    return (
        len(list_value(champion.get("equipped_item_ids"))),
        int_value(champion.get("level")),
        int_value(champion.get("rank")),
        int_value(champion.get("ascension_level")),
    )


def int_value(value: Any) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def main() -> None:
    print(json.dumps(save_current_loadout_snapshot("manual"), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
