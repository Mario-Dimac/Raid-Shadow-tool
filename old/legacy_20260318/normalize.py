from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from models import (
    AccountBonus,
    AccountData,
    Blessing,
    Champion,
    ChampionStats,
    Effect,
    GearItem,
    Mastery,
    Meta,
    Skill,
    StatValue,
    SubStat,
)


BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
RAW_PATH = INPUT_DIR / "raw_account.json"
OUTPUT_PATH = INPUT_DIR / "normalized_account.json"


def load_raw_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(
            f"Raw account JSON not found: {path}. "
            "Place your export in input/raw_account.json and run normalize.py again."
        )
    with path.open("r", encoding="utf-8-sig") as handle:
        return json.load(handle)


def save_normalized_account(account: AccountData, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(serialize_for_json(account), handle, indent=2, ensure_ascii=False)


def serialize_for_json(value: Any) -> Any:
    if isinstance(value, ChampionStats):
        return value.to_dict()
    if is_dataclass(value):
        return {field.name: serialize_for_json(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {key: serialize_for_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [serialize_for_json(item) for item in value]
    return value


def normalize_account(raw_data: Any) -> AccountData:
    meta_block = find_first_mapping(raw_data, ("meta", "metadata", "account_meta", "profile"))
    bonuses_block = find_first_list(raw_data, ("account_bonuses", "bonuses", "great_hall", "area_bonuses"))
    champions_block = find_first_list(raw_data, ("champions", "heroes", "units", "roster"))
    gear_block = find_first_list(raw_data, ("gear", "items", "artifacts", "equipment", "inventory"))

    account = AccountData(
        meta=parse_meta(meta_block, raw_data),
        account_bonuses=[parse_account_bonus(item, index) for index, item in enumerate(bonuses_block, start=1)],
        champions=[parse_champion(item, index) for index, item in enumerate(champions_block, start=1)],
        gear=[parse_gear_item(item, index) for index, item in enumerate(gear_block, start=1)],
    )
    reconcile_gear_ownership(account)
    return account


def parse_meta(meta_block: Optional[Dict[str, Any]], raw_data: Any) -> Meta:
    data = meta_block or {}
    return Meta(
        project=string_value(first_present(data, ("project",), "CB Forge")),
        schema_version=string_value(first_present(data, ("schema_version", "version"), "1.0")),
        source=string_value(first_present(data, ("source", "source_file", "origin"), "")),
        extracted_at=string_value(first_present(data, ("extracted_at", "timestamp", "created_at"), "")),
        player_name=string_value(
            first_present(data, ("player_name", "name", "username"), extract_from_anywhere(raw_data, ("player_name", "username", "name"), ""))
        ),
        account_level=int_value(
            first_present(data, ("account_level", "level"), extract_from_anywhere(raw_data, ("account_level", "level"), 0))
        ),
    )


def parse_account_bonus(raw_bonus: Any, index: int) -> AccountBonus:
    bonus = ensure_mapping(raw_bonus)
    return AccountBonus(
        bonus_id=string_value(first_present(bonus, ("bonus_id", "id", "key"), f"bonus_{index:03d}")),
        source=string_value(first_present(bonus, ("source", "category", "origin"), "")),
        scope=string_value(first_present(bonus, ("scope", "area", "mode"), "global")),
        target=string_value(first_present(bonus, ("target", "affinity", "applies_to"), "all")),
        stat=string_value(first_present(bonus, ("stat", "stat_type", "type"), "")),
        value=float_value(first_present(bonus, ("value", "amount", "bonus"), 0.0)),
        active=bool_value(first_present(bonus, ("active", "enabled", "is_active"), True)),
    )


def parse_champion(raw_champion: Any, index: int) -> Champion:
    champion = ensure_mapping(raw_champion)
    skills_block = list_value(first_present(champion, ("skills", "abilities", "moves"), []))
    masteries_block = list_value(first_present(champion, ("masteries", "mastery_list"), []))
    blessing_block = mapping_value(first_present(champion, ("blessing", "awakened_blessing"), {}))

    base_stats_block = merge_stat_sources(
        mapping_value(first_present(champion, ("base_stats", "stats_base"), {})),
        mapping_value(first_present(champion, ("stats",), {})),
    )
    total_stats_block = merge_stat_sources(
        mapping_value(first_present(champion, ("total_stats", "stats_total", "final_stats"), {})),
        mapping_value(first_present(champion, ("calculated_stats",), {})),
    )

    return Champion(
        champ_id=string_value(first_present(champion, ("champ_id", "id", "hero_id"), f"champ_{index:03d}")),
        name=string_value(first_present(champion, ("name", "champion_name"), f"Champion {index}")),
        rarity=string_value(first_present(champion, ("rarity",), "")),
        affinity=string_value(first_present(champion, ("affinity", "element"), "")),
        faction=string_value(first_present(champion, ("faction",), "")),
        level=int_value(first_present(champion, ("level",), 1)),
        rank=int_value(first_present(champion, ("rank", "stars"), 1)),
        ascension=int_value(first_present(champion, ("ascension", "ascended"), 0)),
        awakening_level=int_value(first_present(champion, ("awakening_level", "awakening", "awakened_level"), 0)),
        empowerment_level=int_value(first_present(champion, ("empowerment_level", "empowerment"), 0)),
        booked=bool_value(first_present(champion, ("booked", "fully_booked"), False)),
        in_vault=bool_value(first_present(champion, ("in_vault", "vault"), False)),
        locked=bool_value(first_present(champion, ("locked", "is_locked"), False)),
        role_tags=string_list(first_present(champion, ("role_tags", "roles", "tags"), [])),
        base_stats=ChampionStats.from_dict(base_stats_block),
        total_stats=ChampionStats.from_dict(total_stats_block),
        equipped_item_ids=string_list(first_present(champion, ("equipped_item_ids", "equipped_items", "item_ids"), [])),
        masteries=[parse_mastery(item, pos) for pos, item in enumerate(masteries_block, start=1)],
        blessing=parse_blessing(blessing_block),
        skills=[parse_skill(item, pos) for pos, item in enumerate(skills_block, start=1)],
    )


def parse_mastery(raw_mastery: Any, index: int) -> Mastery:
    mastery = ensure_mapping(raw_mastery)
    return Mastery(
        tree=string_value(first_present(mastery, ("tree", "branch"), "")),
        mastery_id=string_value(first_present(mastery, ("mastery_id", "id"), f"mastery_{index:03d}")),
        name=string_value(first_present(mastery, ("name", "mastery_name"), f"Mastery {index}")),
        active=bool_value(first_present(mastery, ("active", "enabled", "selected"), True)),
    )


def parse_blessing(raw_blessing: Any) -> Blessing:
    blessing = ensure_mapping(raw_blessing)
    return Blessing(
        name=string_value(first_present(blessing, ("name", "blessing_name"), "")),
        level=int_value(first_present(blessing, ("level", "rank"), 0)),
    )


def parse_skill(raw_skill: Any, index: int) -> Skill:
    skill = ensure_mapping(raw_skill)
    effects_block = list_value(first_present(skill, ("effects", "skill_effects"), []))
    return Skill(
        skill_id=string_value(first_present(skill, ("skill_id", "id"), f"skill_{index:03d}")),
        name=string_value(first_present(skill, ("name", "skill_name"), f"Skill {index}")),
        slot=string_value(first_present(skill, ("slot", "type", "button"), f"A{index}")),
        booked=bool_value(first_present(skill, ("booked", "upgraded"), False)),
        cooldown_base=optional_int(first_present(skill, ("cooldown_base", "cooldown"), None)),
        cooldown_booked=optional_int(first_present(skill, ("cooldown_booked", "cooldown_min"), None)),
        cooldown_current=optional_int(first_present(skill, ("cooldown_current", "current_cooldown"), None)),
        turn_meter_fill_pct=float_value(first_present(skill, ("turn_meter_fill_pct", "tm_fill", "turn_meter_fill"), 0.0)),
        turn_meter_reduce_pct=float_value(first_present(skill, ("turn_meter_reduce_pct", "tm_reduce", "turn_meter_reduce"), 0.0)),
        grants_extra_turn=bool_value(first_present(skill, ("grants_extra_turn", "extra_turn"), False)),
        resets_cooldowns=bool_value(first_present(skill, ("resets_cooldowns", "reset_cooldowns"), False)),
        hits=int_value(first_present(skill, ("hits", "hit_count"), 1)),
        effects=[parse_effect(item) for item in effects_block],
        cb_tags=string_list(first_present(skill, ("cb_tags", "tags"), [])),
    )


def parse_effect(raw_effect: Any) -> Effect:
    effect = ensure_mapping(raw_effect)
    return Effect(
        type=string_value(first_present(effect, ("type", "effect_type"), "")),
        name=string_value(first_present(effect, ("name", "effect_name"), "")),
        duration=int_value(first_present(effect, ("duration", "turns"), 0)),
        target=string_value(first_present(effect, ("target", "applies_to"), "")),
        chance=float_value(first_present(effect, ("chance", "rate"), 100.0)),
    )


def parse_gear_item(raw_item: Any, index: int) -> GearItem:
    item = ensure_mapping(raw_item)
    main_stat_block = mapping_value(first_present(item, ("main_stat", "primary_stat"), {}))
    substats_block = list_value(first_present(item, ("substats", "sub_stats", "secondary_stats"), []))

    return GearItem(
        item_id=string_value(first_present(item, ("item_id", "id"), f"item_{index:03d}")),
        item_class=string_value(first_present(item, ("item_class", "class", "category"), "")),
        slot=string_value(first_present(item, ("slot", "position"), "")),
        set_name=string_value(first_present(item, ("set_name", "set", "set_id"), "")),
        rarity=string_value(first_present(item, ("rarity",), "")),
        rank=int_value(first_present(item, ("rank", "stars"), 0)),
        level=int_value(first_present(item, ("level",), 0)),
        ascension_level=int_value(first_present(item, ("ascension_level", "ascension"), 0)),
        main_stat=parse_stat_value(main_stat_block) if main_stat_block else None,
        substats=[parse_substat(stat) for stat in substats_block],
        required_faction=string_value(first_present(item, ("required_faction", "faction_requirement", "required_fraction_name"), "")),
        required_faction_id=int_value(first_present(item, ("required_faction_id", "required_fraction"), 0)),
        equipped_by=optional_string(first_present(item, ("equipped_by", "equippedBy", "owner_id"), None)),
        locked=bool_value(first_present(item, ("locked", "is_locked"), False)),
    )


def reconcile_gear_ownership(account: AccountData) -> None:
    owner_by_item_id: Dict[str, str] = {}
    for champion in account.champions:
        for item_id in champion.equipped_item_ids:
            normalized_item_id = string_value(item_id)
            if normalized_item_id:
                owner_by_item_id[normalized_item_id] = champion.champ_id

    for item in account.gear:
        owner_id = owner_by_item_id.get(item.item_id)
        if owner_id:
            item.equipped_by = owner_id


def parse_stat_value(raw_stat: Any) -> StatValue:
    stat = ensure_mapping(raw_stat)
    return StatValue(
        type=string_value(first_present(stat, ("type", "stat"), "")),
        value=float_value(first_present(stat, ("value", "amount"), 0.0)),
    )


def parse_substat(raw_substat: Any) -> SubStat:
    substat = ensure_mapping(raw_substat)
    return SubStat(
        type=string_value(first_present(substat, ("type", "stat"), "")),
        value=float_value(first_present(substat, ("value", "amount"), 0.0)),
        rolls=int_value(first_present(substat, ("rolls", "upgrades"), 0)),
        glyph_value=float_value(first_present(substat, ("glyph_value", "glyph"), 0.0)),
    )


def find_first_mapping(raw_data: Any, keys: Sequence[str]) -> Optional[Dict[str, Any]]:
    if isinstance(raw_data, dict):
        direct = first_present(raw_data, keys, None)
        if isinstance(direct, dict):
            return direct
    found = extract_from_anywhere(raw_data, keys, None)
    if isinstance(found, dict):
        return found
    return None


def find_first_list(raw_data: Any, keys: Sequence[str]) -> List[Any]:
    if isinstance(raw_data, dict):
        direct = first_present(raw_data, keys, [])
        if isinstance(direct, list):
            return direct
        if isinstance(direct, dict):
            return list(direct.values())
    found = extract_from_anywhere(raw_data, keys, [])
    if isinstance(found, list):
        return found
    if isinstance(found, dict):
        return list(found.values())
    return []


def extract_from_anywhere(raw_data: Any, keys: Sequence[str], default: Any) -> Any:
    normalized_keys = {normalize_key(key) for key in keys}
    for candidate in walk_values(raw_data):
        if not isinstance(candidate, dict):
            continue
        for key, value in candidate.items():
            if normalize_key(key) in normalized_keys:
                return value
    return default


def walk_values(raw_data: Any) -> Iterable[Any]:
    yield raw_data
    if isinstance(raw_data, dict):
        for value in raw_data.values():
            yield from walk_values(value)
    elif isinstance(raw_data, list):
        for item in raw_data:
            yield from walk_values(item)


def merge_stat_sources(*sources: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for source in sources:
        for key, value in source.items():
            if normalize_key(key) in {"hp", "atk", "def", "def_", "spd", "speed", "critrate", "critrate", "critdmg", "critdamage", "res", "resistance", "acc", "accuracy"}:
                merged[normalize_stat_key(key)] = value
    return merged


def normalize_stat_key(key: str) -> str:
    normalized = normalize_key(key)
    aliases = {
        "def": "def",
        "def_": "def",
        "speed": "spd",
        "critrate": "crit_rate",
        "critratepct": "crit_rate",
        "critdmg": "crit_dmg",
        "critdamage": "crit_dmg",
        "resistance": "res",
        "accuracy": "acc",
    }
    return aliases.get(normalized, normalized)


def normalize_key(value: Any) -> str:
    return "".join(char for char in str(value).lower() if char.isalnum())


def first_present(mapping: Dict[str, Any], keys: Sequence[str], default: Any = None) -> Any:
    normalized = {normalize_key(key): key for key in mapping.keys()}
    for key in keys:
        candidate = normalized.get(normalize_key(key))
        if candidate is not None:
            return mapping[candidate]
    return default


def ensure_mapping(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def mapping_value(value: Any, default: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {} if default is None else default


def list_value(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    return []


def string_list(value: Any) -> List[str]:
    if isinstance(value, list):
        return [string_value(item) for item in value if string_value(item)]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def string_value(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def optional_string(value: Any) -> Optional[str]:
    text = string_value(value)
    return text or None


def int_value(value: Any, default: int = 0) -> int:
    if value in (None, ""):
        return default
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def optional_int(value: Any) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def float_value(value: Any, default: float = 0.0) -> float:
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def bool_value(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "y", "on"}:
            return True
        if normalized in {"false", "0", "no", "n", "off"}:
            return False
    return default


def main() -> None:
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    raw_data = load_raw_json(RAW_PATH)
    account = normalize_account(raw_data)
    save_normalized_account(account, OUTPUT_PATH)
    print(f"Normalized account saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
