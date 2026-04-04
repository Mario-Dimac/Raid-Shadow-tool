from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


BOSS_DIFFICULTIES: Dict[str, Dict[str, Any]] = {
    "normal": {"label": "Normal", "boss_speed": 120.0},
    "hard": {"label": "Hard", "boss_speed": 140.0},
    "brutal": {"label": "Brutal", "boss_speed": 160.0},
    "nightmare": {"label": "Nightmare", "boss_speed": 170.0},
    "ultra_nightmare": {"label": "Ultra-Nightmare", "boss_speed": 190.0},
}

AFFINITY_OPTIONS: List[Dict[str, str]] = [
    {"key": "void", "label": "Void"},
    {"key": "magic", "label": "Magic"},
    {"key": "force", "label": "Force"},
    {"key": "spirit", "label": "Spirit"},
]

EFFECT_LIBRARY: List[Dict[str, Any]] = [
    {"key": "decrease_attack", "label": "Decrease ATK sul boss", "category": "boss_debuff", "default_duration": 2, "default_target": "boss"},
    {"key": "decrease_def", "label": "Decrease DEF sul boss", "category": "boss_debuff", "default_duration": 2, "default_target": "boss"},
    {"key": "weaken", "label": "Weaken sul boss", "category": "boss_debuff", "default_duration": 2, "default_target": "boss"},
    {"key": "poison", "label": "Poison", "category": "boss_debuff", "default_duration": 2, "default_target": "boss", "stackable": True, "default_stacks": 1},
    {"key": "hp_burn", "label": "HP Burn", "category": "boss_debuff", "default_duration": 3, "default_target": "boss"},
    {"key": "leech", "label": "Leech sul boss", "category": "boss_debuff", "default_duration": 2, "default_target": "boss"},
    {"key": "block_debuffs", "label": "Block Debuffs", "category": "ally_buff", "default_duration": 2, "default_target": "all_allies"},
    {"key": "increase_def", "label": "Increase DEF", "category": "ally_buff", "default_duration": 2, "default_target": "all_allies"},
    {"key": "ally_protect", "label": "Ally Protect", "category": "ally_buff", "default_duration": 2, "default_target": "all_allies"},
    {"key": "counterattack", "label": "Counterattack", "category": "ally_buff", "default_duration": 2, "default_target": "all_allies"},
    {"key": "increase_speed", "label": "Increase SPD", "category": "ally_buff", "default_duration": 2, "default_target": "all_allies"},
    {"key": "shield", "label": "Shield", "category": "ally_buff", "default_duration": 2, "default_target": "all_allies"},
    {"key": "unkillable", "label": "Unkillable", "category": "ally_buff", "default_duration": 2, "default_target": "all_allies"},
    {"key": "strengthen", "label": "Strengthen", "category": "ally_buff", "default_duration": 2, "default_target": "all_allies"},
    {"key": "cleanse", "label": "Cleanse / remove debuffs", "category": "utility", "default_duration": 0, "default_target": "all_allies"},
    {"key": "turn_meter_fill", "label": "Turn Meter Fill %", "category": "utility", "default_duration": 0, "default_target": "all_allies", "default_value": 15.0},
]

STACKABLE_EFFECTS = {"poison"}
ALLY_BUFF_KEYS = {"block_debuffs", "increase_def", "ally_protect", "counterattack", "increase_speed", "shield", "unkillable", "strengthen"}
BOSS_DEBUFF_KEYS = {"decrease_attack", "decrease_def", "weaken", "poison", "hp_burn", "leech"}
START_OF_TURN_DURATION_OFFSET = 1

DEFAULT_TEAM_PRESETS: List[Dict[str, Any]] = [
    {"key": "blank", "label": "Vuoto", "description": "Scheletro neutro: imposti skill ed effetti a mano.", "skills": []},
    {
        "key": "counterattack_anchor",
        "label": "Counterattack Anchor",
        "description": "Setup tipico per anchor killable con counterattack.",
        "skills": [{"slot": "A2", "skill_name": "Counterattack window", "cooldown": 3, "priority": 320, "use_as_opener": True, "effects": [{"effect_type": "counterattack", "target": "all_allies", "duration": 2}, {"effect_type": "shield", "target": "all_allies", "duration": 2}]}],
    },
    {
        "key": "block_debuffs_support",
        "label": "Block Debuffs Support",
        "description": "Copre stun/AOE con Block Debuffs e un layer difensivo.",
        "skills": [{"slot": "A3", "skill_name": "Block Debuffs window", "cooldown": 3, "priority": 320, "use_as_opener": True, "effects": [{"effect_type": "block_debuffs", "target": "all_allies", "duration": 2}, {"effect_type": "increase_def", "target": "all_allies", "duration": 2}]}],
    },
    {
        "key": "ally_protect_support",
        "label": "Ally Protect Support",
        "description": "Setup da protector con finestra difensiva.",
        "skills": [{"slot": "A2", "skill_name": "Protective window", "cooldown": 3, "priority": 300, "use_as_opener": True, "effects": [{"effect_type": "ally_protect", "target": "all_allies", "duration": 2}, {"effect_type": "increase_def", "target": "all_allies", "duration": 2}]}],
    },
    {
        "key": "decrease_attack_a1",
        "label": "Decrease ATK A1",
        "description": "Debuffer che vuole tenere quasi sempre Decrease ATK sul boss.",
        "skills": [{"slot": "A1", "skill_name": "A1 Decrease ATK", "cooldown": 0, "priority": 100, "effects": [{"effect_type": "decrease_attack", "target": "boss", "duration": 2}]}],
    },
    {
        "key": "poisoner",
        "label": "Poisoner",
        "description": "Schema semplice per chi vuole riempire il boss di poison.",
        "skills": [{"slot": "A1", "skill_name": "A1 Poison", "cooldown": 0, "priority": 100, "effects": [{"effect_type": "poison", "target": "boss", "duration": 2, "stacks": 1}]}, {"slot": "A2", "skill_name": "Poison burst", "cooldown": 3, "priority": 240, "use_as_opener": True, "effects": [{"effect_type": "poison", "target": "boss", "duration": 2, "stacks": 2}]}],
    },
    {
        "key": "burner",
        "label": "HP Burner",
        "description": "Pattern semplice per tenere HP Burn alto sul boss.",
        "skills": [{"slot": "A2", "skill_name": "HP Burn setup", "cooldown": 3, "priority": 250, "use_as_opener": True, "effects": [{"effect_type": "hp_burn", "target": "boss", "duration": 3}]}],
    },
    {
        "key": "unkillable_support",
        "label": "Unkillable Support",
        "description": "Primo template per shell unkillable.",
        "skills": [{"slot": "A3", "skill_name": "Unkillable window", "cooldown": 5, "priority": 340, "use_as_opener": True, "effects": [{"effect_type": "unkillable", "target": "all_allies", "duration": 2}]}],
    },
    {
        "key": "cleanser_speed",
        "label": "Cleanser + SPD",
        "description": "Pulisce e rilancia i turni con Increase SPD.",
        "skills": [{"slot": "A2", "skill_name": "Cleanse cycle", "cooldown": 3, "priority": 310, "use_as_opener": True, "effects": [{"effect_type": "cleanse", "target": "all_allies"}, {"effect_type": "increase_speed", "target": "all_allies", "duration": 2}]}],
    },
]


def string_value(value: Any) -> str:
    return "" if value is None else str(value)


def int_value(value: Any, default: int = 0) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def float_value(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def effect_definition(effect_type: str) -> Dict[str, Any]:
    normalized = string_value(effect_type).strip()
    for item in EFFECT_LIBRARY:
        if string_value(item.get("key")) == normalized:
            return item
    return {"key": normalized, "label": normalized, "category": "unknown", "default_duration": 0, "default_target": "boss"}


def default_skill_row(slot: str, priority: int) -> Dict[str, Any]:
    return {"slot": slot, "skill_name": slot, "cooldown": 0 if slot == "A1" else 3, "priority": priority, "use_as_opener": slot != "A1", "enabled": True, "effects": []}


def default_member_row(slot_index: int) -> Dict[str, Any]:
    return {"slot_index": slot_index, "champion_name": "", "champ_id": "", "speed": 170.0, "notes": "", "skills": [default_skill_row("A1", 100), default_skill_row("A2", 240), default_skill_row("A3", 320), default_skill_row("A4", 160)]}


@dataclass
class SkillEffect:
    effect_type: str
    target: str
    duration: int = 0
    chance: float = 100.0
    value: float = 0.0
    stacks: int = 1


@dataclass
class SkillConfig:
    slot: str
    skill_name: str
    cooldown: int
    priority: int
    use_as_opener: bool
    enabled: bool
    effects: List[SkillEffect]
    cooldown_remaining: int = 0


@dataclass
class StatusInstance:
    effect_type: str
    label: str
    remaining: int
    source_name: str


@dataclass
class ChampionState:
    slot_index: int
    champion_name: str
    champ_id: str
    speed: float
    notes: str
    turn_meter: float = 0.0
    turns_taken: int = 0
    skipped_turns: int = 0
    skills: List[SkillConfig] = field(default_factory=list)
    buffs: Dict[str, List[StatusInstance]] = field(default_factory=dict)
    debuffs: Dict[str, List[StatusInstance]] = field(default_factory=dict)


def normalize_skill_effect(effect_row: Dict[str, Any]) -> SkillEffect:
    effect_type = string_value(effect_row.get("effect_type")).strip()
    definition = effect_definition(effect_type)
    return SkillEffect(
        effect_type=effect_type,
        target=string_value(effect_row.get("target") or definition.get("default_target")).strip() or "boss",
        duration=max(0, int_value(effect_row.get("duration"), int_value(definition.get("default_duration"), 0))),
        chance=max(0.0, min(100.0, float_value(effect_row.get("chance"), 100.0))),
        value=float_value(effect_row.get("value"), float_value(definition.get("default_value"), 0.0)),
        stacks=max(1, int_value(effect_row.get("stacks"), int_value(definition.get("default_stacks"), 1))),
    )


def normalize_skill(skill_row: Dict[str, Any], default_slot: str, default_priority: int) -> SkillConfig:
    slot = string_value(skill_row.get("slot") or default_slot).strip() or default_slot
    return SkillConfig(
        slot=slot,
        skill_name=string_value(skill_row.get("skill_name") or slot).strip() or slot,
        cooldown=max(0, int_value(skill_row.get("cooldown"), 0)),
        priority=int_value(skill_row.get("priority"), default_priority),
        use_as_opener=bool(skill_row.get("use_as_opener")),
        enabled=bool(skill_row.get("enabled", True)),
        effects=[normalize_skill_effect(dict_value(effect_row)) for effect_row in list_value(skill_row.get("effects"))],
    )


def normalize_member(member_row: Dict[str, Any], fallback_slot_index: int) -> ChampionState:
    skill_rows = list_value(member_row.get("skills"))[:4]
    while len(skill_rows) < 4:
        default_slot, default_priority = (("A1", 100), ("A2", 240), ("A3", 320), ("A4", 160))[len(skill_rows)]
        skill_rows.append(default_skill_row(default_slot, default_priority))
    skills = [
        normalize_skill(dict_value(skill_row), default_slot, default_priority)
        for skill_row, default_slot, default_priority in zip(skill_rows, ("A1", "A2", "A3", "A4"), (100, 240, 320, 160))
    ]
    return ChampionState(
        slot_index=max(1, int_value(member_row.get("slot_index"), fallback_slot_index)),
        champion_name=string_value(member_row.get("champion_name")).strip(),
        champ_id=string_value(member_row.get("champ_id")).strip(),
        speed=max(1.0, float_value(member_row.get("speed"), 170.0)),
        notes=string_value(member_row.get("notes")).strip(),
        skills=skills,
    )


def add_status(bucket: Dict[str, List[StatusInstance]], effect_type: str, duration: int, source_name: str, stacks: int = 1) -> None:
    definition = effect_definition(effect_type)
    internal_duration = max(0, duration) + START_OF_TURN_DURATION_OFFSET
    if effect_type in STACKABLE_EFFECTS:
        items = bucket.setdefault(effect_type, [])
        for _ in range(max(1, stacks)):
            items.append(StatusInstance(effect_type=effect_type, label=string_value(definition.get("label") or effect_type), remaining=internal_duration, source_name=source_name))
        return
    items = bucket.setdefault(effect_type, [])
    if items:
        items[0].remaining = max(items[0].remaining, internal_duration)
        items[0].source_name = source_name or items[0].source_name
        return
    items.append(StatusInstance(effect_type=effect_type, label=string_value(definition.get("label") or effect_type), remaining=internal_duration, source_name=source_name))


def consume_start_of_turn(statuses: Dict[str, List[StatusInstance]]) -> None:
    expired: List[str] = []
    for effect_type, items in list(statuses.items()):
        kept: List[StatusInstance] = []
        for item in items:
            item.remaining -= 1
            if item.remaining > 0:
                kept.append(item)
        if kept:
            statuses[effect_type] = kept
        else:
            expired.append(effect_type)
    for effect_type in expired:
        statuses.pop(effect_type, None)


def has_status(statuses: Dict[str, List[StatusInstance]], effect_type: str) -> bool:
    return bool(list(statuses.get(effect_type) or []))


def count_status(statuses: Dict[str, List[StatusInstance]], effect_type: str) -> int:
    return len(list(statuses.get(effect_type) or []))


def describe_active_statuses(statuses: Dict[str, List[StatusInstance]]) -> str:
    labels: List[str] = []
    for effect_type in sorted(statuses):
        definition = effect_definition(effect_type)
        count = count_status(statuses, effect_type)
        label = string_value(definition.get("label") or effect_type)
        labels.append(f"{label} x{count}" if count > 1 else label)
    return ", ".join(labels)


def choose_skill(actor: ChampionState) -> SkillConfig:
    available = [skill for skill in actor.skills if skill.enabled and skill.cooldown_remaining <= 0]
    if not available:
        return next((skill for skill in actor.skills if skill.slot == "A1"), actor.skills[0])
    if actor.turns_taken == 0:
        opener = [skill for skill in available if skill.use_as_opener]
        if opener:
            return sorted(opener, key=lambda row: (-row.priority, row.slot))[0]
    return sorted(available, key=lambda row: (-row.priority, row.slot))[0]


def effective_speed(actor: ChampionState, speed_aura_pct: float) -> float:
    multiplier = 1.0 + max(0.0, speed_aura_pct) / 100.0
    if has_status(actor.buffs, "increase_speed"):
        multiplier += 0.30
    return actor.speed * multiplier


def apply_skill_effects(actor: ChampionState, skill: SkillConfig, team: List[ChampionState], boss_debuffs: Dict[str, List[StatusInstance]]) -> List[str]:
    notes: List[str] = []
    for effect in skill.effects:
        if not effect.effect_type:
            continue
        target = effect.target or string_value(effect_definition(effect.effect_type).get("default_target") or "boss")
        if effect.effect_type in BOSS_DEBUFF_KEYS:
            add_status(boss_debuffs, effect.effect_type, effect.duration, actor.champion_name, stacks=effect.stacks)
            label = string_value(effect_definition(effect.effect_type).get("label") or effect.effect_type)
            notes.append(f"{label} x{effect.stacks} ({effect.duration}t)" if effect.effect_type in STACKABLE_EFFECTS and effect.stacks > 1 else f"{label} ({effect.duration}t)")
            continue
        if effect.effect_type in ALLY_BUFF_KEYS:
            targets = team if target == "all_allies" else [actor]
            for member in targets:
                add_status(member.buffs, effect.effect_type, effect.duration, actor.champion_name, stacks=effect.stacks)
            label = string_value(effect_definition(effect.effect_type).get("label") or effect.effect_type)
            notes.append(f"{label} su {'team' if target == 'all_allies' else actor.champion_name} ({effect.duration}t)")
            continue
        if effect.effect_type == "cleanse":
            targets = team if target == "all_allies" else [actor]
            for member in targets:
                member.debuffs.clear()
            notes.append("Cleanse team" if target == "all_allies" else f"Cleanse {actor.champion_name}")
            continue
        if effect.effect_type == "turn_meter_fill":
            targets = team if target == "all_allies" else [actor]
            for member in targets:
                member.turn_meter = min(0.999, member.turn_meter + max(0.0, effect.value) / 100.0)
            notes.append(f"Turn Meter +{effect.value:.0f}%")
    return notes


def boss_skill_label(turn_index: int) -> str:
    cycle = ("AoE 1", "AoE 2", "Stun")
    return cycle[(turn_index - 1) % len(cycle)]


def build_boss_turn_snapshot(
    boss_turn: int,
    skill_label: str,
    team: List[ChampionState],
    boss_debuffs: Dict[str, List[StatusInstance]],
    stun_target_slot: int,
) -> Dict[str, Any]:
    active_team = [member for member in team if member.champion_name]
    team_size = max(1, len(active_team))
    stun_target = next((member for member in active_team if member.slot_index == stun_target_slot), active_team[-1] if active_team else None)
    row = {
        "boss_turn": boss_turn,
        "skill_label": skill_label,
        "decrease_attack_active": has_status(boss_debuffs, "decrease_attack"),
        "decrease_def_active": has_status(boss_debuffs, "decrease_def"),
        "weaken_active": has_status(boss_debuffs, "weaken"),
        "poison_stacks": count_status(boss_debuffs, "poison"),
        "hp_burn_active": has_status(boss_debuffs, "hp_burn"),
        "increase_def_coverage": sum(1 for member in active_team if has_status(member.buffs, "increase_def")),
        "ally_protect_coverage": sum(1 for member in active_team if has_status(member.buffs, "ally_protect")),
        "counterattack_coverage": sum(1 for member in active_team if has_status(member.buffs, "counterattack")),
        "block_debuffs_coverage": sum(1 for member in active_team if has_status(member.buffs, "block_debuffs")),
        "unkillable_coverage": sum(1 for member in active_team if has_status(member.buffs, "unkillable")),
        "coverage_team_size": team_size,
        "stun_target_name": stun_target.champion_name if stun_target else "",
        "stun_target_slot": stun_target.slot_index if stun_target else 0,
        "stun_blocked": False,
        "notes": [],
    }
    if skill_label == "Stun" and stun_target is not None:
        if has_status(stun_target.buffs, "block_debuffs"):
            row["stun_blocked"] = True
            row["notes"].append(f"Stun su {stun_target.champion_name} bloccato da Block Debuffs.")
        else:
            add_status(stun_target.debuffs, "stun", 1, "Demon Lord")
            row["notes"].append(f"{stun_target.champion_name} viene stunnato.")
    return row


def summarize_boss_turns(boss_turns: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not boss_turns:
        return {"boss_turns": 0, "decrease_attack_uptime_pct": 0.0, "increase_def_uptime_pct": 0.0, "ally_protect_uptime_pct": 0.0, "counterattack_uptime_pct": 0.0, "blocked_stuns_pct": 0.0, "stun_turns": 0, "avg_poison_stacks": 0.0}
    total = len(boss_turns)
    stun_turns = [row for row in boss_turns if row["skill_label"] == "Stun"]
    team_slots = sum(int(row.get("coverage_team_size") or 0) for row in boss_turns) or 1
    return {
        "boss_turns": total,
        "decrease_attack_uptime_pct": round(100.0 * sum(1 for row in boss_turns if row["decrease_attack_active"]) / total, 1),
        "increase_def_uptime_pct": round(100.0 * sum(float(row.get("increase_def_coverage") or 0) for row in boss_turns) / team_slots, 1),
        "ally_protect_uptime_pct": round(100.0 * sum(float(row.get("ally_protect_coverage") or 0) for row in boss_turns) / team_slots, 1),
        "counterattack_uptime_pct": round(100.0 * sum(float(row.get("counterattack_coverage") or 0) for row in boss_turns) / team_slots, 1),
        "blocked_stuns_pct": round(100.0 * sum(1 for row in stun_turns if row["stun_blocked"]) / max(1, len(stun_turns)), 1),
        "stun_turns": len(stun_turns),
        "avg_poison_stacks": round(sum(float(row.get("poison_stacks") or 0) for row in boss_turns) / total, 2),
    }


def build_warnings(boss_turns: List[Dict[str, Any]], team: List[ChampionState]) -> List[str]:
    warnings: List[str] = []
    no_dec_atk = [row["boss_turn"] for row in boss_turns if not row["decrease_attack_active"]]
    if no_dec_atk:
        warnings.append(f"Manca Decrease ATK sui turni boss: {', '.join(str(turn) for turn in no_dec_atk[:8])}.")
    stun_breaks = [row for row in boss_turns if row["skill_label"] == "Stun" and not row["stun_blocked"]]
    if stun_breaks:
        stun_labels = ", ".join(f"T{row['boss_turn']}->{row['stun_target_name']}" for row in stun_breaks[:6])
        warnings.append(f"Lo stun passa senza Block Debuffs: {stun_labels}.")
    aoe_gaps = [row["boss_turn"] for row in boss_turns if row["skill_label"] != "Stun" and row["increase_def_coverage"] < row["coverage_team_size"]]
    if aoe_gaps:
        warnings.append(f"Non tutti gli alleati hanno Increase DEF sulle AOE boss: {', '.join(str(turn) for turn in aoe_gaps[:8])}.")
    skipped = [member for member in team if member.skipped_turns > 0]
    if skipped:
        warnings.append(f"Turni persi per stun: {', '.join(f'{member.champion_name} ({member.skipped_turns})' for member in skipped)}.")
    if not warnings:
        warnings.append("Nessuna rottura evidente nella finestra simulata. Verifica comunque danno e survivability reale in game.")
    return warnings


def normalize_simulation_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    difficulty = string_value(payload.get("difficulty")).strip() or "ultra_nightmare"
    if difficulty not in BOSS_DIFFICULTIES:
        difficulty = "ultra_nightmare"
    affinity = string_value(payload.get("affinity")).strip() or "void"
    if affinity not in {row["key"] for row in AFFINITY_OPTIONS}:
        affinity = "void"
    return {
        "difficulty": difficulty,
        "difficulty_label": string_value(BOSS_DIFFICULTIES[difficulty]["label"]),
        "boss_speed": float_value(payload.get("boss_speed"), float_value(BOSS_DIFFICULTIES[difficulty]["boss_speed"], 190.0)),
        "affinity": affinity,
        "max_boss_turns": max(3, int_value(payload.get("max_boss_turns"), 12)),
        "max_events": max(20, int_value(payload.get("max_events"), 120)),
        "stun_target_slot": max(1, min(5, int_value(payload.get("stun_target_slot"), 5))),
        "speed_aura_pct": max(0.0, float_value(payload.get("speed_aura_pct"), 0.0)),
    }


def simulate_clan_boss_battle(payload: Dict[str, Any]) -> Dict[str, Any]:
    settings = normalize_simulation_settings(dict_value(payload.get("settings")))
    members = [
        normalize_member(dict_value(member_row), index)
        for index, member_row in enumerate(list_value(payload.get("team"))[:5], start=1)
        if string_value(dict_value(member_row).get("champion_name")).strip()
    ]
    errors: List[str] = []
    if not members:
        errors.append("Inserisci almeno un campione nel team.")
    for member in members:
        if member.speed <= 0:
            errors.append(f"SPD non valida per {member.champion_name or f'Slot {member.slot_index}'}")
    if errors:
        return {"ok": False, "errors": errors, "settings": settings, "timeline": [], "boss_turns": [], "summary": {}, "team_state": []}

    boss_turn_meter = 0.0
    boss_turns_taken = 0
    boss_debuffs: Dict[str, List[StatusInstance]] = {}
    timeline: List[Dict[str, Any]] = []
    boss_turn_rows: List[Dict[str, Any]] = []
    elapsed_seconds = 0.0
    event_index = 0

    while boss_turns_taken < settings["max_boss_turns"] and event_index < settings["max_events"]:
        race: List[Tuple[float, str, int]] = []
        boss_speed = max(1.0, float(settings["boss_speed"]))
        race.append(((1.0 - boss_turn_meter) / boss_speed, "boss", 0))
        for index, member in enumerate(members, start=1):
            race.append(((1.0 - member.turn_meter) / max(1.0, effective_speed(member, settings["speed_aura_pct"])), "member", index))

        advance = min(max(0.0, item[0]) for item in race)
        elapsed_seconds += advance
        boss_turn_meter = min(1.0, boss_turn_meter + boss_speed * advance)
        for member in members:
            member.turn_meter = min(1.0, member.turn_meter + effective_speed(member, settings["speed_aura_pct"]) * advance)

        ready_members = [member for member in members if member.turn_meter >= 0.999999]
        boss_ready = boss_turn_meter >= 0.999999

        if ready_members:
            actor = sorted(ready_members, key=lambda row: row.slot_index)[0]
            actor.turn_meter = 0.0
            consume_start_of_turn(actor.buffs)
            consume_start_of_turn(actor.debuffs)
            for skill in actor.skills:
                if skill.cooldown_remaining > 0:
                    skill.cooldown_remaining -= 1
            actor.turns_taken += 1
            if has_status(actor.debuffs, "stun"):
                actor.skipped_turns += 1
                timeline.append({"event_index": event_index + 1, "time_seconds": round(elapsed_seconds, 3), "actor_type": "champion", "actor_name": actor.champion_name, "slot_index": actor.slot_index, "turn_number": actor.turns_taken, "skill_slot": "", "skill_name": "Turno perso", "summary": "Turno saltato per Stun.", "active_buffs": describe_active_statuses(actor.buffs), "boss_debuffs": describe_active_statuses(boss_debuffs), "skipped": True})
                event_index += 1
                continue
            skill = choose_skill(actor)
            if skill.cooldown > 0:
                skill.cooldown_remaining = skill.cooldown
            notes = apply_skill_effects(actor, skill, members, boss_debuffs)
            timeline.append({"event_index": event_index + 1, "time_seconds": round(elapsed_seconds, 3), "actor_type": "champion", "actor_name": actor.champion_name, "slot_index": actor.slot_index, "turn_number": actor.turns_taken, "skill_slot": skill.slot, "skill_name": skill.skill_name, "summary": "; ".join(notes) if notes else "Nessun effetto modellato.", "active_buffs": describe_active_statuses(actor.buffs), "boss_debuffs": describe_active_statuses(boss_debuffs), "skipped": False})
            event_index += 1
            continue

        if boss_ready:
            boss_turn_meter = 0.0
            consume_start_of_turn(boss_debuffs)
            boss_turns_taken += 1
            skill_label = boss_skill_label(boss_turns_taken)
            row = build_boss_turn_snapshot(boss_turns_taken, skill_label, members, boss_debuffs, settings["stun_target_slot"])
            boss_turn_rows.append(row)
            timeline.append({"event_index": event_index + 1, "time_seconds": round(elapsed_seconds, 3), "actor_type": "boss", "actor_name": "Demon Lord", "slot_index": 0, "turn_number": boss_turns_taken, "skill_slot": f"B{((boss_turns_taken - 1) % 3) + 1}", "skill_name": skill_label, "summary": "; ".join(list_value(row.get("notes"))) or "Boss turn.", "active_buffs": "", "boss_debuffs": describe_active_statuses(boss_debuffs), "skipped": False})
            event_index += 1
            continue

        break

    summary = summarize_boss_turns(boss_turn_rows)
    summary["warnings"] = build_warnings(boss_turn_rows, members)
    summary["elapsed_seconds"] = round(elapsed_seconds, 2)
    summary["event_count"] = len(timeline)
    return {
        "ok": True,
        "errors": [],
        "settings": settings,
        "timeline": timeline,
        "boss_turns": boss_turn_rows,
        "summary": summary,
        "team_state": [{"slot_index": member.slot_index, "champion_name": member.champion_name, "speed": round(member.speed, 2), "turns_taken": member.turns_taken, "skipped_turns": member.skipped_turns, "notes": member.notes} for member in members],
    }
