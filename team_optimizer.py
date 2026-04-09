from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

from clan_boss_simulator import default_member_row as default_clan_boss_member_row, simulate_clan_boss_battle
from forge_db import DB_PATH, ensure_schema, load_set_rules


@dataclass(frozen=True)
class RoleRequirement:
    key: str
    label: str
    acceptable_roles: tuple[str, ...]


@dataclass(frozen=True)
class OptimizerBossProfile:
    key: str
    label: str
    description: str
    team_size: int
    required_role_groups: tuple[RoleRequirement, ...] = field(default_factory=tuple)
    valuable_roles: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ChampionHint:
    roles: tuple[str, ...]
    boss_scores: Mapping[str, float]
    default_build: str
    notes: str = ""


@dataclass(frozen=True)
class BossFamily:
    key: str
    label: str
    description: str
    levels: tuple[tuple[str, str], ...]
    affinities: tuple[tuple[str, str], ...]
    default_level: str
    default_affinity: str


BOSS_PROFILES: Dict[str, OptimizerBossProfile] = {
    "demon_lord_unm": OptimizerBossProfile(
        key="demon_lord_unm",
        label="Demon Lord UNM",
        description="Scheletro optimizer per Clan Boss Ultra-Nightmare orientato a team killable o quasi-killable.",
        team_size=5,
        required_role_groups=(
            RoleRequirement("damage_core", "Damage core", ("damage", "poisoner", "burner")),
            RoleRequirement("survival_core", "Survival core", ("survival", "support", "ally_protect", "cleanse", "unkillable")),
            RoleRequirement("debuff_core", "Debuff core", ("debuffer", "poisoner", "burner", "decrease_attack")),
        ),
        valuable_roles=("speed", "poisoner", "burner", "cleanse", "ally_protect", "counterattack", "decrease_attack"),
    ),
    "hydra": OptimizerBossProfile(
        key="hydra",
        label="Hydra",
        description="Optimizer Hydra orientato a utility coverage: Block Buffs, Provoke, Hex, sustain e controllo della rotazione.",
        team_size=6,
        required_role_groups=(
            RoleRequirement("damage_core", "Damage core", ("damage", "burner", "hexer")),
            RoleRequirement("control_core", "Control core", ("block_buffs", "provoke", "hexer", "debuffer")),
            RoleRequirement("survival_core", "Survival core", ("support", "survival", "cleanse", "revive", "mischief_tank")),
        ),
        valuable_roles=("speed", "block_buffs", "provoke", "hexer", "cleanse", "revive", "mischief_tank", "decrease_speed"),
    ),
    "iron_twins": OptimizerBossProfile(
        key="iron_twins",
        label="Iron Twins Fortress",
        description="Optimizer Iron Twins orientato a comp dedicate con controllo velocita, sustain e gestione delle finestre punitive.",
        team_size=5,
        required_role_groups=(
            RoleRequirement("pressure_core", "Pressure core", ("damage", "burner", "decrease_speed")),
            RoleRequirement("survival_core", "Survival core", ("support", "survival", "cleanse", "ally_protect", "revive_on_death")),
            RoleRequirement("utility_core", "Utility core", ("debuffer", "decrease_speed", "cleanse", "block_buffs")),
        ),
        valuable_roles=("speed", "decrease_speed", "cleanse", "ally_protect", "block_buffs", "burner", "revive_on_death"),
    ),
}

LEVEL_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "easy": {"required_speed": 140.0, "required_accuracy": 100.0, "survival_floor": 0.48},
    "normal": {"required_speed": 150.0, "required_accuracy": 140.0, "survival_floor": 0.54},
    "hard": {"required_speed": 160.0, "required_accuracy": 180.0, "survival_floor": 0.58},
    "brutal": {"required_speed": 170.0, "required_accuracy": 210.0, "survival_floor": 0.62},
    "nightmare": {"required_speed": 176.0, "required_accuracy": 230.0, "survival_floor": 0.66},
    "ultra_nightmare": {"required_speed": 190.0, "required_accuracy": 250.0, "survival_floor": 0.70},
}

HYDRA_LEVEL_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "normal": {"required_speed": 190.0, "required_accuracy": 220.0, "required_resistance": 250.0, "survival_floor": 0.62},
    "hard": {"required_speed": 215.0, "required_accuracy": 270.0, "required_resistance": 320.0, "survival_floor": 0.68},
    "brutal": {"required_speed": 230.0, "required_accuracy": 330.0, "required_resistance": 390.0, "survival_floor": 0.73},
    "nightmare": {"required_speed": 245.0, "required_accuracy": 380.0, "required_resistance": 470.0, "survival_floor": 0.78},
}

HYDRA_ROTATION_RULES: Dict[str, Dict[str, Any]] = {
    "rotation_1": {
        "label": "Rotazione 1",
        "starter_heads": ("Decay", "Torment", "Suffering", "Mischief"),
        "priority_roles": ("provoke", "block_buffs", "mischief_tank"),
        "needs_perfect_veil": True,
        "needs_wrath_mitigation": False,
    },
    "rotation_2": {
        "label": "Rotazione 2",
        "starter_heads": ("Blight", "Torment", "Mischief", "Wrath"),
        "priority_roles": ("block_buffs", "mischief_tank", "decrease_attack"),
        "needs_perfect_veil": True,
        "needs_wrath_mitigation": True,
    },
    "rotation_3": {
        "label": "Rotazione 3",
        "starter_heads": ("Decay", "Blight", "Suffering", "Wrath"),
        "priority_roles": ("provoke", "block_buffs", "decrease_attack"),
        "needs_perfect_veil": False,
        "needs_wrath_mitigation": True,
    },
    "rotation_4": {
        "label": "Rotazione 4",
        "starter_heads": ("Decay", "Blight", "Mischief", "Wrath"),
        "priority_roles": ("provoke", "block_buffs", "mischief_tank", "decrease_attack"),
        "needs_perfect_veil": False,
        "needs_wrath_mitigation": True,
    },
    "rotation_5": {
        "label": "Rotazione 5",
        "starter_heads": ("Decay", "Blight", "Suffering", "Mischief"),
        "priority_roles": ("provoke", "block_buffs", "mischief_tank"),
        "needs_perfect_veil": False,
        "needs_wrath_mitigation": False,
    },
}

IRON_TWINS_LEVEL_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "stage_6": {"required_speed": 180.0, "required_accuracy": 180.0, "required_resistance": 0.0, "survival_floor": 0.62},
    "stage_12": {"required_speed": 220.0, "required_accuracy": 280.0, "required_resistance": 300.0, "survival_floor": 0.70},
    "stage_15": {"required_speed": 240.0, "required_accuracy": 360.0, "required_resistance": 450.0, "survival_floor": 0.76},
}

BOSS_FAMILIES: Dict[str, BossFamily] = {
    "demon_lord": BossFamily(
        key="demon_lord",
        label="Demon Lord",
        description="Clan Boss con priorita su speed tune, debuff uptime, sustain e danno consistente.",
        levels=(
            ("easy", "Easy"),
            ("normal", "Normal"),
            ("hard", "Hard"),
            ("brutal", "Brutal"),
            ("nightmare", "Nightmare"),
            ("ultra_nightmare", "Ultra-Nightmare"),
        ),
        affinities=(
            ("void", "Void"),
            ("force", "Force"),
            ("magic", "Magic"),
            ("spirit", "Spirit"),
        ),
        default_level="ultra_nightmare",
        default_affinity="void",
    ),
    "hydra": BossFamily(
        key="hydra",
        label="Hydra",
        description="Clan Boss a sei teste con focus su utility coverage, sustain e gestione della rotazione.",
        levels=(
            ("normal", "Normal"),
            ("hard", "Hard"),
            ("brutal", "Brutal"),
            ("nightmare", "Nightmare"),
        ),
        affinities=(
            ("rotation_1", "Rotazione 1"),
            ("rotation_2", "Rotazione 2"),
            ("rotation_3", "Rotazione 3"),
            ("rotation_4", "Rotazione 4"),
            ("rotation_5", "Rotazione 5"),
        ),
        default_level="normal",
        default_affinity="rotation_1",
    ),
    "iron_twins": BossFamily(
        key="iron_twins",
        label="Iron Twins Fortress",
        description="Dungeon con affinity giornaliera, stage dedicate e comp molto piu rigide del dungeon medio.",
        levels=(
            ("stage_6", "Stage 6+"),
            ("stage_12", "Stage 12+"),
            ("stage_15", "Stage 15"),
        ),
        affinities=(
            ("void", "Void"),
            ("magic", "Magic"),
            ("force", "Force"),
            ("spirit", "Spirit"),
        ),
        default_level="stage_15",
        default_affinity="void",
    ),
}

DEMON_LORD_ENCOUNTER_KEYS: Dict[str, str] = {
    "easy": "demon_lord_easy",
    "normal": "demon_lord_normal",
    "hard": "demon_lord_hard",
    "brutal": "demon_lord_brutal",
    "nightmare": "demon_lord_nm",
    "ultra_nightmare": "demon_lord_unm",
}


def clan_boss_model_encounter_key(level_key: str) -> str:
    normalized = str(level_key or "").strip() or "ultra_nightmare"
    if normalized == "ultra_nightmare":
        return "demon_lord_ultra_nightmare"
    if normalized == "nightmare":
        return "demon_lord_nm"
    return f"demon_lord_{normalized}"


def normalize_team_recommendation_source(source: str, boss_key: str) -> str:
    normalized = str(source or "").strip().lower() or "optimizer"
    if normalized == "ai" and str(boss_key or "").strip() == "demon_lord":
        return "ai"
    return "optimizer"


def resolve_team_recommendation_strategy(source: str, boss_key: str) -> tuple[str, str, Dict[str, Any]]:
    normalized = str(source or "").strip().lower() or "optimizer"
    family = str(boss_key or "").strip().lower()
    objective = "stable"
    if normalized in {"push", "optimizer_push", "optimizer_70m", "push_70m"}:
        normalized = "optimizer"
        objective = "push_70m"
    elif normalized in {"ai_push", "ai_70m"}:
        normalized = "ai"
        objective = "push_70m"
    elif normalized in {"stable", "optimizer_stable"}:
        normalized = "optimizer"
        objective = "stable"
    elif normalized in {"ai_stable"}:
        normalized = "ai"
        objective = "stable"

    effective_source = normalize_team_recommendation_source(normalized, family)
    objective_meta: Dict[str, Any] = {
        "key": objective,
        "label": "Baseline stabile" if objective == "stable" else "Push 70M",
        "description": (
            "Privilegia shell affidabili, storico medio e copertura difensiva reale."
            if objective == "stable"
            else "Spinge shell ad alto ceiling, danno massimo storico e core offensivi piu aggressivi."
        ),
        "target_damage": 70_000_000.0 if family == "demon_lord" and objective == "push_70m" else None,
    }
    return effective_source, objective, objective_meta


def historical_encounter_keys(family_key: str, level_key: str, encounter_key: str) -> tuple[str, ...]:
    family = str(family_key or "").strip().lower()
    level = str(level_key or "").strip().lower()
    primary = str(encounter_key or "").strip()
    keys: List[str] = [primary] if primary else []
    if family == "demon_lord":
        if level == "ultra_nightmare":
            keys.extend(["demon_lord_unm", "demon_lord_ultra_nightmare"])
        elif level == "nightmare":
            keys.extend(["demon_lord_nm", "demon_lord_nightmare"])
    deduped: List[str] = []
    seen: Set[str] = set()
    for key in keys:
        normalized = str(key or "").strip()
        if not normalized or normalized in seen:
            continue
        deduped.append(normalized)
        seen.add(normalized)
    return tuple(deduped)


def _team_signature(names: Iterable[str]) -> str:
    normalized = sorted(str(name or "").strip() for name in names if str(name or "").strip())
    return "|".join(normalized)


def _merge_history_metric(target: Dict[str, Any], total_damage: float) -> None:
    target["run_count"] = int(target.get("run_count") or 0) + 1
    target["total_damage_sum"] = float(target.get("total_damage_sum") or 0.0) + float(total_damage)
    target["avg_total_damage"] = round(float(target["total_damage_sum"]) / max(int(target["run_count"]), 1), 2)
    target["max_total_damage"] = round(max(float(target.get("max_total_damage") or 0.0), float(total_damage)), 2)


def _build_team_history_index(rows: Iterable[sqlite3.Row]) -> Dict[str, Dict[str, Dict[str, Any]]]:
    members_by_run: Dict[int, Dict[str, Any]] = {}
    for row in rows:
        run_id = int(row["run_id"] or 0)
        run = members_by_run.setdefault(
            run_id,
            {
                "total_damage": _to_float(row["total_damage"]),
                "champion_names": [],
            },
        )
        champion_name = str(row["champion_name"] or "").strip()
        if champion_name:
            run["champion_names"].append(champion_name)

    exact_teams: Dict[str, Dict[str, Any]] = {}
    pair_teams: Dict[str, Dict[str, Any]] = {}
    for run in members_by_run.values():
        champion_names = sorted({str(name) for name in list(run.get("champion_names") or []) if str(name)})
        total_damage = _to_float(run.get("total_damage"))
        if len(champion_names) >= 2:
            for first_index, first_name in enumerate(champion_names):
                for second_name in champion_names[first_index + 1:]:
                    pair_key = _team_signature((first_name, second_name))
                    pair_row = pair_teams.setdefault(pair_key, {"run_count": 0, "total_damage_sum": 0.0, "avg_total_damage": 0.0, "max_total_damage": 0.0})
                    _merge_history_metric(pair_row, total_damage)
        if champion_names:
            exact_key = _team_signature(champion_names)
            exact_row = exact_teams.setdefault(exact_key, {"run_count": 0, "total_damage_sum": 0.0, "avg_total_damage": 0.0, "max_total_damage": 0.0})
            exact_row["team_size"] = len(champion_names)
            _merge_history_metric(exact_row, total_damage)
    return {"exact": exact_teams, "pairs": pair_teams}


def _group_equipped_sets_by_champion(
    rows: Iterable[sqlite3.Row],
    set_rules: Mapping[str, Mapping[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    piece_counts: Dict[str, Dict[str, int]] = {}
    for row in rows:
        champ_id = str(row["equipped_by"] or "").strip()
        set_name = str(row["set_name"] or "").strip()
        if not champ_id or not set_name:
            continue
        piece_counts.setdefault(champ_id, {})
        piece_counts[champ_id][set_name] = int(piece_counts[champ_id].get(set_name) or 0) + 1

    output: Dict[str, List[Dict[str, Any]]] = {}
    for champ_id, counts in piece_counts.items():
        summary: List[Dict[str, Any]] = []
        for set_name, piece_count in sorted(counts.items()):
            rule = dict(set_rules.get(set_name) or {})
            pieces_required = max(int(rule.get("pieces_required") or 0), 1)
            completed_sets = int(piece_count // pieces_required)
            if completed_sets <= 0:
                continue
            summary.append(
                {
                    "set_name": set_name,
                    "display_name": set_name,
                    "pieces": int(piece_count),
                    "completed_sets": completed_sets,
                    "pieces_required": pieces_required,
                }
            )
        output[champ_id] = summary
    return output


CHAMPION_HINTS: Dict[str, ChampionHint] = {
    "Maneater": ChampionHint(("speed", "survival", "unkillable", "support"), {"demon_lord_unm": 100.0}, "speed_tuned_support"),
    "Pain Keeper": ChampionHint(("speed", "support", "cooldown"), {"demon_lord_unm": 94.0}, "cooldown_support"),
    "Geomancer": ChampionHint(("damage", "burner", "debuffer"), {"demon_lord_unm": 96.0, "iron_twins_stage_15": 99.0, "hydra_hard": 84.0}, "hp_burner"),
    "Frozen Banshee": ChampionHint(("damage", "poisoner", "debuffer"), {"demon_lord_unm": 90.0}, "poisoner"),
    "Ninja": ChampionHint(("damage", "burner"), {"demon_lord_unm": 93.0, "hydra_hard": 82.0}, "clan_boss_dps"),
    "Heiress": ChampionHint(("cleanse", "speed", "support"), {"demon_lord_unm": 78.0}, "cleanser"),
    "Doompriest": ChampionHint(("cleanse", "support", "survival"), {"demon_lord_unm": 84.0}, "cleanser"),
    "Martyr": ChampionHint(("survival", "ally_protect", "damage", "debuffer"), {"demon_lord_unm": 88.0}, "ally_protector"),
    "Stag Knight": ChampionHint(
        ("debuffer", "support", "survival", "decrease_attack"),
        {"demon_lord_unm": 86.0},
        "decrease_attack_support",
        notes="Decrease ATK + utility solida per Clan Boss.",
    ),
    "Underpriest Brogni": ChampionHint(("survival", "support", "burner"), {"demon_lord_unm": 92.0}, "ally_protector"),
    "Valkyrie": ChampionHint(
        ("survival", "support", "damage", "counterattack"),
        {"demon_lord_unm": 94.0},
        "ally_protector",
        notes="Counterattack e scudi la rendono una delle killable piu solide sul Clan Boss.",
    ),
    "Venus": ChampionHint(("damage", "debuffer", "poisoner"), {"demon_lord_unm": 92.0}, "poisoner"),
    "Riho Bonespear": ChampionHint(("support", "debuffer", "cleanse", "survival"), {"demon_lord_unm": 86.0}, "cleanser"),
    "Jintoro": ChampionHint(("damage",), {"demon_lord_unm": 91.0}, "clan_boss_dps"),
    "Teodor the Savant": ChampionHint(("poisoner", "support", "survival"), {"demon_lord_unm": 90.0}, "poisoner"),
    "Michinaki": ChampionHint(("damage", "burner", "debuffer", "survival"), {"demon_lord_unm": 88.0}, "clan_boss_dps"),
    "Tyrant Ixlimor": ChampionHint(("survival", "ally_protect", "burner"), {"demon_lord_unm": 88.0}, "ally_protector"),
    "Rhazin Scarhide": ChampionHint(("damage", "debuffer"), {"demon_lord_unm": 78.0}, "clan_boss_dps"),
    "Catacomb Councilor": ChampionHint(("damage", "support", "multi_hit"), {"demon_lord_unm": 76.0}, "clan_boss_dps"),
    "High Khatun": ChampionHint(("speed", "support"), {"demon_lord_unm": 68.0}, "support_general"),
    "Aox the Rememberer": ChampionHint(("poisoner", "support", "debuffer"), {"demon_lord_unm": 70.0}, "poisoner"),
    "Occult Brawler": ChampionHint(("poisoner", "damage"), {"demon_lord_unm": 74.0}, "poisoner"),
    "Apothecary": ChampionHint(("speed", "support"), {"demon_lord_unm": 58.0}, "support_general"),
    "Mithrala Lifebane": ChampionHint(("support", "cleanse", "survival", "hexer"), {"demon_lord_unm": 80.0, "hydra_hard": 96.0, "iron_twins_stage_15": 94.0}, "debuffer_acc_spd"),
    "Uugo": ChampionHint(("support", "debuffer", "block_buffs"), {"hydra_hard": 92.0}, "debuffer_acc_spd"),
    "Husk": ChampionHint(("damage", "provoke"), {"hydra_hard": 88.0}, "support_tank"),
    "Firrol the Barkhorn": ChampionHint(("support", "block_buffs", "mischief_tank", "decrease_speed"), {"hydra_hard": 98.0}, "debuffer_acc_spd"),
    "Duchess Lilitu": ChampionHint(("support", "revive", "survival"), {"hydra_hard": 94.0, "iron_twins_stage_15": 90.0}, "support_tank"),
    "Krisk the Ageless": ChampionHint(("support", "ally_protect", "decrease_speed", "survival"), {"hydra_hard": 95.0, "iron_twins_stage_15": 93.0}, "ally_protector"),
    "Pythion": ChampionHint(("support", "cleanse", "revive", "survival"), {"hydra_hard": 91.0, "iron_twins_stage_15": 89.0}, "support_tank"),
}

CHAMPION_CAPABILITY_HINTS: Dict[str, Set[str]] = {
    "Doompriest": {"healing", "sustain", "cleanse"},
    "Riho Bonespear": {"healing", "sustain", "cleanse"},
    "Underpriest Brogni": {"shield", "sustain", "defense_core"},
    "Rakka Viletide": {"revive", "sustain"},
    "Tyrant Ixlimor": {"ally_protect", "sustain", "defense_core"},
    "Teodor the Savant": {"poison", "boss_pressure"},
    "Martyr": {"ally_protect", "defense_core", "counterattack", "sustain"},
    "Valkyrie": {"shield", "defense_core", "counterattack", "sustain"},
}

SET_SUSTAIN_HINTS: Dict[str, Set[str]] = {
    "Life Drain": {"sustain"},
    "Crit Rate And Life Drain": {"sustain"},
    "HP And Heal": {"sustain"},
    "Shield And HP": {"shield", "sustain", "defense_core"},
    "Shield And Speed": {"shield", "sustain", "defense_core"},
}


ACCOUNT_ROLE_MAP: Dict[str, tuple[str, ...]] = {
    "attack": ("damage",),
    "attack support": ("damage", "support"),
    "support": ("support",),
    "defense": ("survival",),
    "defence": ("survival",),
    "health": ("survival",),
    "hp": ("survival",),
}

ROLE_INFERENCE_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("poison",), ("poisoner", "debuffer", "damage")),
    (("hp burn", "burn"), ("burner", "debuffer", "damage")),
    (("block buffs",), ("block_buffs", "debuffer", "support")),
    (("provoke",), ("provoke", "support")),
    (("hex",), ("hexer", "debuffer", "damage")),
    (("decrease speed", "spd down"), ("decrease_speed", "debuffer", "support")),
    (("decrease attack", "decrease atk"), ("debuffer", "decrease_attack", "survival")),
    (("decrease def", "decrease defense", "weaken"), ("debuffer",)),
    (("perfect veil", "increase resistance"), ("mischief_tank", "support", "survival")),
    (("ally protect",), ("ally_protect", "support", "survival")),
    (("shield",), ("support", "survival")),
    (("counterattack", "counter attack"), ("counterattack", "support", "damage")),
    (("unkillable", "block damage"), ("unkillable", "survival", "support")),
    (("revive on death",), ("revive_on_death", "support", "survival")),
    (("remove debuff", "remove all debuffs", "removes all debuffs", "cleanse", "block debuffs"), ("cleanse", "support", "survival")),
    (("heal", "continuous heal"), ("support", "survival")),
    (("revive",), ("revive", "support")),
    (("turn meter", "fill turn meter", "increase speed", "increase turn meter"), ("speed", "support")),
    (("damage",), ("damage",)),
)

CAPABILITY_INFERENCE_RULES: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (("heal", "continuous heal", "leech"), ("healing", "sustain")),
    (("shield",), ("shield", "sustain", "defense_core")),
    (("ally protect",), ("ally_protect", "sustain", "defense_core")),
    (("increase def", "increase defense", "strengthen"), ("increase_defense", "defense_core")),
    (("increase resistance",), ("increase_resistance", "defense_core")),
    (("counterattack", "counter attack"), ("counterattack", "defense_core")),
    (("unkillable", "block damage"), ("unkillable", "defense_core")),
    (("block buffs",), ("block_buffs", "boss_control")),
    (("provoke",), ("provoke", "boss_control")),
    (("hex",), ("hex", "boss_pressure")),
    (("decrease speed", "spd down"), ("decrease_speed", "boss_control")),
    (("perfect veil",), ("perfect_veil", "mischief_tank")),
    (("revive on death",), ("revive_on_death", "defense_core")),
    (("block debuffs",), ("block_debuffs", "cleanse_support")),
    (("remove debuff", "remove all debuffs", "removes all debuffs", "cleanse"), ("cleanse", "cleanse_support")),
    (("decrease attack", "decrease atk"), ("decrease_attack", "boss_debuff")),
    (("decrease def", "decrease defense"), ("decrease_defense", "boss_debuff")),
    (("weaken",), ("weaken", "boss_debuff")),
    (("poison",), ("poison", "boss_pressure")),
    (("hp burn", "burn"), ("hp_burn", "boss_pressure")),
    (("increase speed", "increase turn meter", "fill turn meter", "turn meter"), ("speed_boost",)),
    (("decrease cooldown", "cooldown"), ("cooldown_reset",)),
)

EFFECT_TYPE_ALIASES: Dict[str, str] = {
    "decrease attack": "decrease_attack",
    "decrease def": "decrease_defense",
    "decrease defense": "decrease_defense",
    "decrease_defense": "decrease_defense",
    "decrease speed": "decrease_speed",
    "decrease_speed": "decrease_speed",
    "weaken": "weaken",
    "poison": "poison",
    "block buffs": "block_buffs",
    "block_buffs": "block_buffs",
    "provoke": "provoke",
    "hex": "hex",
    "increase def": "increase_defense",
    "increase defense": "increase_defense",
    "increase_defense": "increase_defense",
    "increase resistance": "increase_resistance",
    "increase_resistance": "increase_resistance",
    "perfect veil": "perfect_veil",
    "perfect_veil": "perfect_veil",
    "block debuffs": "block_debuffs",
    "ally protect": "ally_protect",
    "counterattack": "counterattack",
    "counter attack": "counterattack",
    "hp burn": "hp_burn",
    "burn": "hp_burn",
    "unkillable": "unkillable",
    "shield": "shield",
    "cleanse": "cleanse",
    "remove debuff": "cleanse",
    "revive on death": "revive_on_death",
    "revive_on_death": "revive_on_death",
    "cooldown reset": "cooldown_reset",
    "decrease cooldown": "cooldown_reset",
    "turn meter fill": "speed_boost",
    "increase speed": "speed_boost",
}

WINDOW_DEFAULT_DURATIONS: Dict[str, int] = {
    "decrease_attack": 2,
    "decrease_defense": 2,
    "decrease_speed": 2,
    "weaken": 2,
    "hp_burn": 3,
    "poison": 2,
    "block_buffs": 2,
    "provoke": 1,
    "hex": 2,
    "block_debuffs": 2,
    "increase_defense": 2,
    "increase_resistance": 2,
    "ally_protect": 2,
    "counterattack": 2,
    "unkillable": 2,
    "shield": 2,
    "perfect_veil": 2,
    "revive_on_death": 2,
    "speed_boost": 2,
}

MANEATER_TUNE_PARTNERS: Set[str] = {
    "Pain Keeper",
    "Heiress",
    "Seeker",
    "Warcaster",
    "Roschard the Tower",
    "Helicath",
    "Demytha",
}


def list_team_optimizer_targets() -> List[Dict[str, Any]]:
    return [
        {
            "key": family.key,
            "label": family.label,
            "description": family.description,
            "levels": [{"key": key, "label": label} for key, label in family.levels],
            "affinities": [{"key": key, "label": label} for key, label in family.affinities],
            "default_level": family.default_level,
            "default_affinity": family.default_affinity,
        }
        for family in BOSS_FAMILIES.values()
    ]


def build_team_optimizer_report(
    boss_key: str = "demon_lord",
    level_key: str = "ultra_nightmare",
    affinity: str = "void",
    recommendation_source: str = "optimizer",
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    family, profile, effective_level, effective_affinity, encounter_key, thresholds = resolve_optimizer_context(
        boss_key=boss_key,
        level_key=level_key,
        affinity=affinity,
    )
    encounter_history_keys = historical_encounter_keys(
        family_key=family.key,
        level_key=effective_level,
        encounter_key=encounter_key,
    )
    history_placeholders = ", ".join("?" for _ in encounter_history_keys) or "?"

    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        roster_rows = conn.execute(
            """
            SELECT champ_id, champion_name, rarity, affinity, faction, level, rank,
                   awakening_level, empowerment_level, booked, relic_count
            FROM account_champions
            """
        ).fetchall()
        stat_rows = conn.execute(
            """
            SELECT champ_id, stat_name, stat_value
            FROM account_champion_total_stats
            WHERE stat_name IN ('hp', 'atk', 'def', 'spd', 'acc', 'res', 'crit_rate', 'crit_dmg')
            """
        ).fetchall()
        stat_model_rows = conn.execute(
            """
            SELECT champ_id, source, completeness
            FROM account_champion_stat_models
            """
        ).fetchall()
        bonus_source_rows = conn.execute(
            """
            SELECT DISTINCT source
            FROM account_bonuses
            ORDER BY source ASC
            """
        ).fetchall()
        equipped_set_rows = conn.execute(
            """
            SELECT equipped_by, set_name
            FROM gear_items
            WHERE equipped_by IS NOT NULL
              AND equipped_by != ''
              AND set_name IS NOT NULL
              AND set_name != ''
            """
        ).fetchall()
        set_rules = load_set_rules(conn)
        role_rows = conn.execute("SELECT champion_name, role_tag FROM champion_roles").fetchall()
        skill_rows = conn.execute(
            """
            SELECT champion_name, slot, skill_order, skill_id, skill_name, cooldown, booked_cooldown, skill_type, description, description_clean
            FROM champion_skills
            """
        ).fetchall()
        effect_rows = conn.execute(
            """
            SELECT champion_name, slot, effect_order, effect_type, target, effect_value, duration, chance, condition_text
            FROM champion_skill_effects
            """
        ).fetchall()
        evidence_rows = conn.execute(
            f"""
            SELECT
                rm.champion_name,
                COUNT(DISTINCT rr.run_id) AS run_count,
                AVG(COALESCE(rmm.damage_done, 0)) AS avg_damage_done,
                AVG(COALESCE(rmm.damage_taken, 0)) AS avg_damage_taken,
                AVG(COALESCE(rmm.healing_done, 0)) AS avg_healing_done
            FROM run_history_runs rr
            JOIN run_history_members rm
                ON rm.run_id = rr.run_id
            LEFT JOIN run_history_member_metrics rmm
                ON rmm.run_id = rm.run_id
                AND rmm.member_order = rm.member_order
            WHERE rr.encounter_key IN ({history_placeholders})
            GROUP BY rm.champion_name
            """,
            encounter_history_keys,
        ).fetchall()
        team_history_rows = conn.execute(
            f"""
            SELECT rr.run_id, rr.total_damage, rm.champion_name
            FROM run_history_runs rr
            JOIN run_history_members rm
                ON rm.run_id = rr.run_id
            WHERE rr.encounter_key IN ({history_placeholders})
              AND rr.total_damage IS NOT NULL
            ORDER BY rr.run_id ASC, rm.member_order ASC
            """,
            encounter_history_keys,
        ).fetchall()

    best_roster_rows = _dedupe_roster_by_champion_name(roster_rows)
    stats_by_champ_id = _group_stats_by_champion(stat_rows)
    stat_models_by_champ_id = _group_stat_models_by_champion(stat_model_rows)
    bonus_sources = sorted({str(row["source"] or "").strip() for row in bonus_source_rows if str(row["source"] or "").strip()})
    account_roles_by_name = _group_roles_by_name(role_rows)
    effect_texts_by_name = _group_effect_texts_by_name(skill_rows, effect_rows)
    skills_by_name = _group_skills_by_name(skill_rows, effect_rows)
    equipped_sets_by_champ_id = _group_equipped_sets_by_champion(equipped_set_rows, set_rules)
    evidence_by_name = {
        str(row["champion_name"] or ""): {
            "run_count": int(row["run_count"] or 0),
            "avg_damage_done": _to_float(row["avg_damage_done"]),
            "avg_damage_taken": _to_float(row["avg_damage_taken"]),
            "avg_healing_done": _to_float(row["avg_healing_done"]),
        }
        for row in evidence_rows
    }
    team_history = _build_team_history_index(team_history_rows)

    candidates = [
        _build_candidate(
            roster_row=row,
            stats=stats_by_champ_id.get(str(row["champ_id"] or ""), {}),
            stat_model=stat_models_by_champ_id.get(str(row["champ_id"] or ""), {}),
            account_roles=account_roles_by_name.get(str(row["champion_name"] or ""), set()),
            effect_texts=effect_texts_by_name.get(str(row["champion_name"] or ""), []),
            skills=skills_by_name.get(str(row["champion_name"] or ""), []),
            current_set_summary=equipped_sets_by_champ_id.get(str(row["champ_id"] or ""), []),
            evidence=evidence_by_name.get(str(row["champion_name"] or ""), {}),
            target_key=encounter_key,
            boss_affinity=effective_affinity,
            thresholds=thresholds,
            bonus_sources=bonus_sources,
        )
        for row in best_roster_rows
    ]
    candidates.sort(key=lambda item: (-float(item["score"]), item["champion_name"].lower()))

    effective_source, objective_key, objective_meta = resolve_team_recommendation_strategy(recommendation_source, family.key)
    selection_notes: List[str] = []
    source_warnings: List[str] = []
    selected_team = _select_team(
        candidates,
        profile,
        target_key=encounter_key,
        thresholds=thresholds,
        boss_affinity=effective_affinity,
        team_history=team_history,
        objective_key=objective_key,
    )
    if effective_source == "ai":
        try:
            from ml_team_baseline import default_model_path, recommend_best_team_from_candidates

            model_path = default_model_path(clan_boss_model_encounter_key(effective_level))
            if not model_path.exists():
                source_warnings.append(f"Modello AI non trovato: {model_path.name}. Uso proposta optimizer.")
                effective_source = "optimizer"
            else:
                ai_hard_rules: Dict[str, Any] = {}
                if family.key == "demon_lord":
                    ai_hard_rules = {
                        "required_tags": ["decrease_attack"],
                        "minimum_speed": _to_float(thresholds.get("required_speed")),
                        "minimum_speed_hits": max(profile.team_size - 1, 1),
                        "minimum_accuracy": _to_float(thresholds.get("required_accuracy")),
                        "minimum_accuracy_hits": 2 if objective_key == "push_70m" else 1,
                    }
                ai_payload = recommend_best_team_from_candidates(
                    candidates=list(candidates),
                    encounter_key=clan_boss_model_encounter_key(effective_level),
                    difficulty=effective_level,
                    boss_affinity=effective_affinity,
                    model_path=model_path,
                    hard_rules=ai_hard_rules,
                )
                ai_team = list(ai_payload.get("best_team") or [])
                if len(ai_team) == profile.team_size:
                    selected_team = ai_team
                    selection_notes.extend(
                        [
                            f"Selezione team: AI baseline ({int(ai_payload.get('evaluated_combinations') or 0)} combinazioni).",
                            f"Danno previsto: {_to_float(ai_payload.get('predicted_total_damage')):.0f}.",
                            f"Obiettivo ranking: {objective_meta.get('label')}.",
                        ]
                    )
                    if ai_payload.get("hard_rules"):
                        selection_notes.append("AI filtrata con vincoli minimi di speed/debuff prima del ranking.")
                    if ai_payload.get("predicted_success_probability") is not None:
                        selection_notes.append(
                            f"Probabilita successo stimata: {_to_float(ai_payload.get('predicted_success_probability')) * 100:.1f}%."
                        )
                else:
                    source_warnings.append("AI senza team completo: uso proposta optimizer.")
                    effective_source = "optimizer"
        except Exception as exc:
            source_warnings.append(f"AI non disponibile: {exc}. Uso proposta optimizer.")
            effective_source = "optimizer"
    selected_names = {str(item["champion_name"] or "") for item in selected_team}
    bench = [item for item in candidates if str(item["champion_name"] or "") not in selected_names][:5]

    coverage = []
    team_roles = {role for member in selected_team for role in list(member.get("roles") or [])}
    for requirement in profile.required_role_groups:
        covered_by = [
            str(member["champion_name"])
            for member in selected_team
            if any(role in requirement.acceptable_roles for role in list(member.get("roles") or []))
        ]
        coverage.append(
            {
                "key": requirement.key,
                "label": requirement.label,
                "acceptable_roles": list(requirement.acceptable_roles),
                "covered": bool(covered_by),
                "covered_by": covered_by,
            }
        )

    missing_required = [item["label"] for item in coverage if not item["covered"]]
    valuable_coverage = {
        role: [str(member["champion_name"]) for member in selected_team if role in list(member.get("roles") or [])]
        for role in profile.valuable_roles
    }
    team_fit = _evaluate_team_fit(
        selected_team,
        target_key=encounter_key,
        thresholds=thresholds,
        boss_affinity=effective_affinity,
    )
    selected_team_history = dict((team_history.get("exact") or {}).get(_team_signature(selected_names)) or {})
    objective_target_damage = _to_float(objective_meta.get("target_damage"))
    warnings: List[str] = []
    if missing_required:
        warnings.append(f"Coverage incompleta: {', '.join(missing_required)}.")
    if "speed" not in team_roles:
        warnings.append("Il team non ha un motore speed esplicito.")
    if family.key == "demon_lord":
        if "cleanse" not in team_roles and "unkillable" not in team_roles:
            warnings.append("Manca una risposta chiara a stun/debuff, salvo tune specifici.")
        if sum(1 for member in selected_team if "damage" in list(member.get("roles") or [])) < 2:
            warnings.append("Il team ha pochi slot dichiaratamente offensivi.")
        weak_affinity_members = list(team_fit.get("weak_affinity_members") or [])
        if effective_affinity != "void" and weak_affinity_members:
            warnings.append(
                f"Roster corto su affinity {effective_affinity}: restano dentro campioni weak affinity ({', '.join(weak_affinity_members[:3])})."
            )
    elif family.key == "hydra":
        if "block_buffs" not in team_roles:
            warnings.append("Hydra senza ruolo Block Buffs esplicito nel team proposto.")
        if "provoke" not in team_roles:
            warnings.append("Hydra senza ruolo Provoke esplicito nel team proposto.")
    elif family.key == "iron_twins":
        if "decrease_speed" not in team_roles:
            warnings.append("Iron Twins senza ruolo Decrease SPD esplicito nel team proposto.")
        if effective_affinity != "void":
            warnings.append(f"Affinity Iron Twins selezionata: {effective_affinity}. Controlla i weak hits.")
    warnings.extend(list(team_fit.get("warnings") or []))
    if objective_key == "push_70m" and family.key == "demon_lord":
        history_max = _to_float(selected_team_history.get("max_total_damage"))
        if history_max > 0.0 and objective_target_damage > 0.0 and history_max < objective_target_damage:
            warnings.append(
                f"Ceiling storico sotto target: shell vista fino a {history_max:.0f} danni, target {objective_target_damage:.0f}."
            )

    return {
        "target": {
            "key": encounter_key,
            "label": f"{family.label} {display_level_label(family, effective_level)}",
            "description": profile.description,
            "team_size": profile.team_size,
            "boss_key": family.key,
            "boss_label": family.label,
            "level_key": effective_level,
            "level_label": display_level_label(family, effective_level),
            "affinity_key": effective_affinity,
            "affinity_label": display_affinity_label(family, effective_affinity),
            "recommendation_source": effective_source,
            "recommendation_label": (
                f"{'AI baseline' if effective_source == 'ai' else 'Optimizer'} - {objective_meta.get('label')}"
            ),
            "objective_key": objective_key,
            "objective_label": str(objective_meta.get("label") or objective_key),
            "objective_description": str(objective_meta.get("description") or ""),
            "target_damage": objective_meta.get("target_damage"),
            "thresholds": dict(thresholds),
        },
        "selected_team": selected_team,
        "bench": bench,
        "candidates": candidates,
        "coverage": coverage,
        "valuable_role_coverage": valuable_coverage,
        "team_fit": team_fit,
        "historical_team_evidence": selected_team_history,
        "missing_required_roles": missing_required,
        "warnings": source_warnings + warnings,
        "notes": [
            *selection_notes,
            f"Obiettivo attivo: {objective_meta.get('label')}. {objective_meta.get('description')}",
            *(
                [
                    f"Storico forte su questa shell: {int(selected_team_history.get('run_count') or 0)} run, media {_to_float(selected_team_history.get('avg_total_damage')):.0f} danni."
                ]
                if selected_team_history
                else []
            ),
            *(
                [
                    f"Gap dal target: max storico {_to_float(selected_team_history.get('max_total_damage')):.0f} su target {objective_target_damage:.0f}."
                ]
                if objective_key == "push_70m" and objective_target_damage > 0.0 and selected_team_history
                else []
            ),
            "Scheletro euristico: usa hint statici, role inference da skill/effect e stats correnti del roster.",
            "I punteggi ora pesano anche sustain, strati difensivi, debuff chiave e sinergia di squadra, ma non sono ancora un simulatore turn-order trusted.",
        ],
    }


def _select_team(
    candidates: Sequence[Dict[str, Any]],
    profile: OptimizerBossProfile,
    target_key: str,
    thresholds: Mapping[str, float],
    boss_affinity: str,
    team_history: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
    objective_key: str = "stable",
) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    selected_names: Set[str] = set()
    covered_roles: Set[str] = set()

    for requirement in profile.required_role_groups:
        all_options = [
            candidate
            for candidate in candidates
            if candidate["champion_name"] not in selected_names
            and any(role in requirement.acceptable_roles for role in list(candidate.get("roles") or []))
        ]
        options = [
            candidate
            for candidate in all_options
            if not _candidate_is_weak_for_selected_boss(candidate, target_key, boss_affinity)
        ] or all_options
        if not options:
            continue
        chosen = max(
            options,
            key=lambda item: (
                _selection_score(
                    item,
                    selected_team=selected,
                    covered_roles=covered_roles,
                    profile=profile,
                    target_key=target_key,
                    thresholds=thresholds,
                    boss_affinity=boss_affinity,
                    team_history=team_history,
                    objective_key=objective_key,
                ),
                item["score"],
            ),
        )
        selected.append(chosen)
        selected_names.add(str(chosen["champion_name"]))
        covered_roles.update(list(chosen.get("roles") or []))

    while len(selected) < profile.team_size:
        all_options = [candidate for candidate in candidates if candidate["champion_name"] not in selected_names]
        options = [
            candidate
            for candidate in all_options
            if not _candidate_is_weak_for_selected_boss(candidate, target_key, boss_affinity)
        ] or all_options
        if not options:
            break
        chosen = max(
            options,
            key=lambda item: (
                _selection_score(
                    item,
                    selected_team=selected,
                    covered_roles=covered_roles,
                    profile=profile,
                    target_key=target_key,
                    thresholds=thresholds,
                    boss_affinity=boss_affinity,
                    team_history=team_history,
                    objective_key=objective_key,
                ),
                item["score"],
            ),
        )
        selected.append(chosen)
        selected_names.add(str(chosen["champion_name"]))
        covered_roles.update(list(chosen.get("roles") or []))

    return _refine_team_selection(
        selected,
        candidates,
        profile=profile,
        target_key=target_key,
        thresholds=thresholds,
        boss_affinity=boss_affinity,
        team_history=team_history,
        objective_key=objective_key,
    )


def _selection_score(
    candidate: Mapping[str, Any],
    selected_team: Sequence[Mapping[str, Any]],
    covered_roles: Set[str],
    profile: OptimizerBossProfile,
    target_key: str,
    thresholds: Mapping[str, float],
    boss_affinity: str,
    team_history: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
    objective_key: str = "stable",
) -> float:
    candidate_roles = set(str(role) for role in list(candidate.get("roles") or []))
    new_valuable_roles = sum(1 for role in profile.valuable_roles if role in candidate_roles and role not in covered_roles)
    new_required_roles = 0
    for requirement in profile.required_role_groups:
        if any(role in requirement.acceptable_roles for role in candidate_roles) and not any(
            role in requirement.acceptable_roles for role in covered_roles
        ):
            new_required_roles += 1
    team_before = _evaluate_team_fit(
        selected_team,
        target_key=target_key,
        thresholds=thresholds,
        boss_affinity=boss_affinity,
    )
    team_after = _evaluate_team_fit(
        [*selected_team, candidate],
        target_key=target_key,
        thresholds=thresholds,
        boss_affinity=boss_affinity,
    )
    team_delta = float(team_after.get("score") or 0.0) - float(team_before.get("score") or 0.0)
    historical_pair_bonus = _historical_pair_bonus([*selected_team, candidate], team_history, objective_key=objective_key)
    objective_bonus = _objective_candidate_bonus(
        candidate,
        selected_team=selected_team,
        objective_key=objective_key,
        target_key=target_key,
        thresholds=thresholds,
    )
    return (
        _candidate_base_score_for_objective(candidate, objective_key=objective_key, target_key=target_key)
        + (new_required_roles * 8.0)
        + (new_valuable_roles * 2.0)
        + team_delta
        + historical_pair_bonus
        + objective_bonus
    )


def _exclude_weak_affinity_for_target(target_key: str, boss_affinity: str) -> bool:
    return str(target_key or "").startswith("demon_lord_") and str(boss_affinity or "").strip().lower() != "void"


def _candidate_is_weak_for_selected_boss(candidate: Mapping[str, Any], target_key: str, boss_affinity: str) -> bool:
    if not _exclude_weak_affinity_for_target(target_key, boss_affinity):
        return False
    return str(candidate.get("affinity_matchup") or "").strip().lower() == "weak"


def _team_has_disallowed_weak_affinity(team: Sequence[Mapping[str, Any]], target_key: str, boss_affinity: str) -> bool:
    if not _exclude_weak_affinity_for_target(target_key, boss_affinity):
        return False
    return any(_candidate_is_weak_for_selected_boss(member, target_key, boss_affinity) for member in team)


def _candidate_base_score_for_objective(
    candidate: Mapping[str, Any],
    objective_key: str,
    target_key: str,
) -> float:
    base_score = float(candidate.get("score") or 0.0)
    if objective_key != "push_70m" or not str(target_key or "").startswith("demon_lord_"):
        return base_score
    weighted_signals = dict(candidate.get("weighted_stat_signals") or {})
    roles = {str(role) for role in list(candidate.get("roles") or [])}
    capability_tags = {str(tag) for tag in list(candidate.get("capability_tags") or [])}
    evidence = dict(candidate.get("evidence") or {})
    generic_score = base_score * 0.18
    generic_score += min(_to_float(weighted_signals.get("damage")) * 36.0, 42.0)
    generic_score += min(_to_float(weighted_signals.get("speed")) * 16.0, 18.0)
    generic_score += min(_to_float(weighted_signals.get("accuracy")) * 10.0, 12.0)
    generic_score += min(_to_float(weighted_signals.get("survival")) * 8.0, 10.0)
    if roles & {"damage", "poisoner", "burner"}:
        generic_score += 8.0
    if capability_tags & {"poison", "hp_burn", "boss_pressure"}:
        generic_score += 8.0
    if capability_tags & {"decrease_defense", "weaken"}:
        generic_score += 6.0
    if "decrease_attack" in roles:
        generic_score += 4.0
    if "speed" in roles:
        generic_score += 3.0
    if int(evidence.get("run_count") or 0) == 0:
        generic_score += 4.0
    return round(generic_score, 2)


def _build_candidate(
    roster_row: sqlite3.Row,
    stats: Mapping[str, float],
    stat_model: Mapping[str, Any],
    account_roles: Set[str],
    effect_texts: Sequence[str],
    skills: Sequence[Mapping[str, Any]],
    current_set_summary: Sequence[Mapping[str, Any]],
    evidence: Mapping[str, Any],
    target_key: str,
    boss_affinity: str,
    thresholds: Mapping[str, float],
    bonus_sources: Sequence[str],
) -> Dict[str, Any]:
    champion_name = str(roster_row["champion_name"] or "")
    champion_affinity = str(roster_row["affinity"] or "")
    hint = CHAMPION_HINTS.get(champion_name)
    hint_roles = set(hint.roles) if hint else set()
    mapped_account_roles = _map_account_roles(account_roles)
    inferred_roles = infer_roles_from_texts(effect_texts)
    roles = sorted(hint_roles | mapped_account_roles | inferred_roles)
    capability_tags = sorted(infer_capabilities_from_texts(effect_texts, roles=roles, champion_name=champion_name))
    capability_tags = sorted(set(capability_tags) | _infer_set_based_capabilities(current_set_summary))
    skill_windows = _summarize_skill_windows(skills=skills, booked=bool(roster_row["booked"]))
    default_build = hint.default_build if hint else _infer_default_build(roles)

    stat_signals = _compute_stat_signals(stats, thresholds)
    stat_reliability = _build_stat_reliability(
        stat_model=stat_model,
        relic_count=int(roster_row["relic_count"] or 0),
        bonus_sources=bonus_sources,
    )
    weighted_stat_signals = _apply_reliability_to_signals(stat_signals, stat_reliability)
    base_hint_score = _resolve_hint_score(hint, target_key)
    fallback_role_score = 28.0 + (len(roles) * 4.0)

    score_breakdown: List[Dict[str, Any]] = []
    score = base_hint_score if base_hint_score > 0 else fallback_role_score
    score_breakdown.append({"label": "Boss hint", "value": round(score, 2)})

    rank_bonus = min(int(roster_row["rank"] or 0), 6) * 2.4
    level_bonus = min(int(roster_row["level"] or 0), 60) * 0.22
    booked_bonus = 5.5 if bool(roster_row["booked"]) else 0.0
    awakening_bonus = min(int(roster_row["awakening_level"] or 0), 6) * 0.7
    empowerment_bonus = min(int(roster_row["empowerment_level"] or 0), 4) * 0.6
    score += rank_bonus + level_bonus + booked_bonus + awakening_bonus + empowerment_bonus
    score_breakdown.extend(
        [
            {"label": "Rank bonus", "value": round(rank_bonus, 2)},
            {"label": "Level bonus", "value": round(level_bonus, 2)},
            {"label": "Booked bonus", "value": round(booked_bonus, 2)},
        ]
    )

    role_bonus = _compute_role_bonus(roles, weighted_stat_signals)
    score += role_bonus
    score_breakdown.append({"label": "Stat-role fit", "value": round(role_bonus, 2)})

    affinity_state = evaluate_affinity_matchup(champion_affinity, boss_affinity)
    affinity_bonus = 0.0
    if affinity_state == "strong":
        affinity_bonus = 4.0
    elif affinity_state == "weak":
        affinity_bonus = -10.0
    score += affinity_bonus
    if affinity_bonus:
        score_breakdown.append({"label": "Affinity", "value": round(affinity_bonus, 2)})

    evidence_bonus = _compute_evidence_bonus(evidence, roles)
    if evidence_bonus:
        score += evidence_bonus
        score_breakdown.append({"label": "Run evidence", "value": round(evidence_bonus, 2)})

    risks = _build_risk_flags(target_key, champion_name, roles, capability_tags, weighted_stat_signals, affinity_state, thresholds)
    risks.extend(stat_reliability["warnings"])
    reasons = _build_reasons(roles, weighted_stat_signals, evidence, hint, affinity_state, boss_affinity, stat_reliability)

    return {
        "champ_id": str(roster_row["champ_id"] or ""),
        "champion_name": champion_name,
        "rarity": str(roster_row["rarity"] or ""),
        "affinity": str(roster_row["affinity"] or ""),
        "affinity_matchup": affinity_state,
        "faction": str(roster_row["faction"] or ""),
        "level": int(roster_row["level"] or 0),
        "rank": int(roster_row["rank"] or 0),
        "booked": bool(roster_row["booked"]),
        "roles": roles,
        "default_build": default_build,
        "capability_tags": capability_tags,
        "skills": [dict(skill) for skill in skills],
        "set_summary": [dict(row) for row in current_set_summary],
        "skill_windows": skill_windows,
        "score": round(score, 2),
        "score_breakdown": score_breakdown,
        "stats": dict(stats),
        "stat_signals": stat_signals,
        "weighted_stat_signals": weighted_stat_signals,
        "stat_reliability": stat_reliability,
        "evidence": {
            "run_count": int(evidence.get("run_count") or 0),
            "avg_damage_done": round(_to_float(evidence.get("avg_damage_done")), 2),
            "avg_damage_taken": round(_to_float(evidence.get("avg_damage_taken")), 2),
            "avg_healing_done": round(_to_float(evidence.get("avg_healing_done")), 2),
        },
        "risks": risks,
        "reasons": reasons,
        "notes": hint.notes if hint and hint.notes else "",
        "role_sources": {
            "hint_roles": sorted(hint_roles),
            "account_roles": sorted(mapped_account_roles),
            "inferred_roles": sorted(inferred_roles),
        },
    }


def infer_roles_from_texts(texts: Iterable[str]) -> Set[str]:
    normalized_text = " ".join(_normalize_token(text) for text in texts if str(text or "").strip())
    roles: Set[str] = set()
    if not normalized_text:
        return roles
    for keywords, inferred_roles in ROLE_INFERENCE_RULES:
        if any(keyword in normalized_text for keyword in keywords):
            roles.update(inferred_roles)
    return roles


def infer_capabilities_from_texts(texts: Iterable[str], roles: Iterable[str] = (), champion_name: str = "") -> Set[str]:
    normalized_text = " ".join(_normalize_token(text) for text in texts if str(text or "").strip())
    capabilities: Set[str] = set()
    for keywords, inferred_capabilities in CAPABILITY_INFERENCE_RULES:
        if any(keyword in normalized_text for keyword in keywords):
            capabilities.update(inferred_capabilities)

    role_set = {_normalize_token(role) for role in roles if str(role or "").strip()}
    if "ally protect" in role_set:
        capabilities.update({"ally_protect", "sustain", "defense_core"})
    if "counterattack" in role_set:
        capabilities.update({"counterattack", "defense_core"})
    if "cleanse" in role_set:
        capabilities.update({"cleanse", "cleanse_support"})
    if "unkillable" in role_set:
        capabilities.update({"unkillable", "defense_core"})
    if "decrease attack" in role_set:
        capabilities.update({"decrease_attack", "boss_debuff"})
    if "decrease speed" in role_set:
        capabilities.update({"decrease_speed", "boss_control"})
    if "block buffs" in role_set:
        capabilities.update({"block_buffs", "boss_control"})
    if "provoke" in role_set:
        capabilities.update({"provoke", "boss_control"})
    if "hexer" in role_set:
        capabilities.update({"hex", "boss_pressure"})
    if "mischief tank" in role_set:
        capabilities.update({"perfect_veil", "mischief_tank"})
    if "revive on death" in role_set:
        capabilities.update({"revive_on_death", "defense_core"})
    if "poisoner" in role_set:
        capabilities.update({"poison", "boss_pressure"})
    if "burner" in role_set:
        capabilities.update({"hp_burn", "boss_pressure"})
    if "cooldown" in role_set:
        capabilities.add("cooldown_reset")
    if _normalize_token(champion_name) == "maneater":
        capabilities.add("unkillable")
    capabilities.update(CHAMPION_CAPABILITY_HINTS.get(str(champion_name or "").strip(), set()))
    return capabilities


def _infer_set_based_capabilities(set_summary: Sequence[Mapping[str, Any]]) -> Set[str]:
    capabilities: Set[str] = set()
    for row in list(set_summary or []):
        set_name = str(row.get("display_name") or row.get("set_name") or "").strip()
        completed_sets = int(row.get("completed_sets") or 0)
        if not set_name or completed_sets <= 0:
            continue
        capabilities.update(SET_SUSTAIN_HINTS.get(set_name, set()))
    return capabilities


def _speed_value(member: Mapping[str, Any]) -> float:
    return _to_float(dict(member.get("stats") or {}).get("spd"))


def _in_speed_range(speed: float, minimum: float, maximum: float) -> bool:
    return minimum <= speed <= maximum


def _evaluate_maneater_tune(team: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    members = {str(member.get("champion_name") or ""): member for member in team}
    maneater = members.get("Maneater")
    if maneater is None:
        return {"ready": False, "label": "", "warnings": [], "build_requirements": []}

    partner = members.get("Pain Keeper")
    if partner is None:
        return {
            "ready": False,
            "label": "",
            "warnings": ["Maneater richiede un partner tipo Pain Keeper o altro cooldown/tune engine."],
            "build_requirements": ["Per un asse Maneater serve almeno un partner reale di tune, non solo buoni campioni di contorno."],
        }

    speeds = {name: _speed_value(member) for name, member in members.items()}
    maneater_booked = bool(maneater.get("booked"))
    partner_booked = bool(partner.get("booked"))
    dps_members = [(name, speed) for name, speed in speeds.items() if name not in {"Maneater", "Pain Keeper"}]
    build_requirements = [
        "Maneater/Pain Keeper vanno trattati come progetto speed-tune dedicato, non come pick generici.",
    ]
    warnings: List[str] = []

    def has_range(excluded: Set[str], minimum: float, maximum: float) -> bool:
        return any(_in_speed_range(speed, minimum, maximum) for name, speed in dps_members if name not in excluded)

    def count_range(excluded: Set[str], minimum: float, maximum: float) -> int:
        return sum(1 for name, speed in dps_members if name not in excluded and _in_speed_range(speed, minimum, maximum))

    ninja_present = "Ninja" in members
    ninja_speed = speeds.get("Ninja", 0.0)
    standard_ready = (
        maneater_booked
        and partner_booked
        and _in_speed_range(speeds.get("Maneater", 0.0), 240.0, 241.0)
        and _in_speed_range(speeds.get("Pain Keeper", 0.0), 218.0, 222.0)
        and count_range(set(), 175.0, 178.0) >= 2
        and has_range(set(), 111.0, 121.0)
    )
    ninja_ready = (
        maneater_booked
        and partner_booked
        and ninja_present
        and bool(members["Ninja"].get("booked"))
        and _in_speed_range(speeds.get("Maneater", 0.0), 240.0, 241.0)
        and _in_speed_range(speeds.get("Pain Keeper", 0.0), 218.0, 222.0)
        and _in_speed_range(ninja_speed, 161.0, 165.0)
        and has_range({"Ninja"}, 175.0, 178.0)
        and has_range({"Ninja"}, 111.0, 121.0)
    )
    ultimate_ready = (
        maneater_booked
        and partner_booked
        and _in_speed_range(speeds.get("Maneater", 0.0), 256.0, 257.0)
        and _in_speed_range(speeds.get("Pain Keeper", 0.0), 222.0, 226.0)
        and has_range(set(), 187.0, 189.0)
        and has_range(set(), 179.0, 185.0)
        and has_range(set(), 129.0, 129.0)
    )

    if ninja_ready:
        return {
            "ready": True,
            "label": "Budget Unkillable Ninja",
            "warnings": [],
            "build_requirements": [
                "Tune centrata: ME 240-241, PK 218-222, Ninja 161-165, DPS 175-178, slowboi 111-121.",
                "Ninja deve restare dentro una tune dedicata: fuori finestra rompe facilmente il ciclo.",
            ],
        }
    if ultimate_ready:
        return {
            "ready": True,
            "label": "Ultimate Budget Unkillable",
            "warnings": [],
            "build_requirements": [
                "Tune centrata: ME 256-257, PK 222-226, DPS 187-189, DPS 179-185, slow 129.",
            ],
        }
    if standard_ready:
        return {
            "ready": True,
            "label": "Budget Unkillable",
            "warnings": [],
            "build_requirements": [
                "Tune centrata: ME 240-241, PK 218-222, 2 DPS 175-178, slowboi 111-121.",
            ],
        }

    if not maneater_booked:
        warnings.append("Maneater senza libri sull'A3: cosi la tune Unkillable non e affidabile.")
    if not partner_booked:
        warnings.append("Pain Keeper senza libri: il reset cooldown non e ancora in stato da tune seria.")

    warnings.append(
        f"Speed attuali ME/PK fuori tune reale ({speeds.get('Maneater', 0.0):.0f}/{speeds.get('Pain Keeper', 0.0):.0f})."
    )
    build_requirements.extend(
        [
            "Per Budget/Ninja: ME 240-241 e PK 218-222 con slot lenti e DPS nelle finestre giuste.",
            "Per Ultimate Budget: ME 256-257 e PK 222-226 con un lento fisso a 129.",
        ]
    )
    return {
        "ready": False,
        "label": "",
        "warnings": warnings[:3],
        "build_requirements": build_requirements[:4],
    }


def _sim_priority_for_slot(slot: str) -> int:
    return {"A1": 100, "A2": 240, "A3": 320, "A4": 160}.get(str(slot or "").upper(), 100)


def _default_sim_target(effect_type: str) -> str:
    if effect_type in {"decrease_attack", "decrease_defense", "weaken", "poison", "hp_burn"}:
        return "boss"
    if effect_type == "cleanse":
        return "all_allies"
    return "all_allies"


def _normalize_sim_target(raw_target: Any, effect_type: str) -> str:
    normalized = _normalize_token(raw_target)
    if normalized in {"self", "self ally"}:
        return "self"
    if normalized in {"boss", "enemy", "enemies", "target enemy"}:
        return "boss"
    if normalized in {"all allies", "all ally", "ally team", "team"}:
        return "all_allies"
    if normalized == "ally":
        return "boss" if effect_type in {"decrease_attack", "decrease_defense", "weaken", "poison", "hp_burn"} else "all_allies"
    return _default_sim_target(effect_type)


def _infer_fallback_sim_skill(candidate: Mapping[str, Any]) -> Dict[str, Any] | None:
    capability_tags = {str(tag) for tag in list(candidate.get("capability_tags") or [])}
    roles = {str(role) for role in list(candidate.get("roles") or [])}
    if "unkillable" in capability_tags:
        return {"slot": "A3", "skill_name": "Unkillable window", "cooldown": 5, "priority": 320, "use_as_opener": True, "enabled": True, "effects": [{"effect_type": "unkillable", "target": "all_allies", "duration": 2, "chance": 100.0}]}
    if "block_debuffs" in capability_tags:
        return {"slot": "A3", "skill_name": "Block Debuffs window", "cooldown": 3, "priority": 320, "use_as_opener": True, "enabled": True, "effects": [{"effect_type": "block_debuffs", "target": "all_allies", "duration": 2, "chance": 100.0}]}
    if "ally_protect" in capability_tags:
        return {"slot": "A2", "skill_name": "Ally Protect window", "cooldown": 3, "priority": 240, "use_as_opener": True, "enabled": True, "effects": [{"effect_type": "ally_protect", "target": "all_allies", "duration": 2, "chance": 100.0}]}
    if "counterattack" in capability_tags:
        return {"slot": "A2", "skill_name": "Counterattack window", "cooldown": 3, "priority": 240, "use_as_opener": True, "enabled": True, "effects": [{"effect_type": "counterattack", "target": "all_allies", "duration": 2, "chance": 100.0}]}
    if "decrease_attack" in capability_tags or "decrease_attack" in roles:
        return {"slot": "A1", "skill_name": "Decrease ATK", "cooldown": 0, "priority": 100, "use_as_opener": False, "enabled": True, "effects": [{"effect_type": "decrease_attack", "target": "boss", "duration": 2, "chance": 100.0}]}
    if "hp_burn" in capability_tags or "burner" in roles:
        return {"slot": "A2", "skill_name": "HP Burn", "cooldown": 3, "priority": 240, "use_as_opener": True, "enabled": True, "effects": [{"effect_type": "hp_burn", "target": "boss", "duration": 3, "chance": 100.0}]}
    if "poison" in capability_tags or "poisoner" in roles:
        return {"slot": "A1", "skill_name": "Poison", "cooldown": 0, "priority": 100, "use_as_opener": False, "enabled": True, "effects": [{"effect_type": "poison", "target": "boss", "duration": 2, "chance": 100.0}]}
    if "cleanse" in capability_tags or "cleanse" in roles:
        return {"slot": "A2", "skill_name": "Cleanse", "cooldown": 3, "priority": 240, "use_as_opener": True, "enabled": True, "effects": [{"effect_type": "cleanse", "target": "all_allies", "duration": 0, "chance": 100.0}]}
    return None


def _sim_effects_for_skill(candidate: Mapping[str, Any], skill: Mapping[str, Any]) -> List[Dict[str, Any]]:
    effects: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for effect in list(skill.get("effects") or []):
        effect_type = _normalize_effect_type(effect.get("effect_type"))
        if not effect_type:
            continue
        seen.add(effect_type)
        duration = max(0, int(effect.get("duration") or WINDOW_DEFAULT_DURATIONS.get(effect_type, 0)))
        chance = _to_float(effect.get("chance") or 100.0) or 100.0
        effects.append(
            {
                "effect_type": effect_type,
                "target": _normalize_sim_target(effect.get("target"), effect_type),
                "duration": duration,
                "chance": chance,
                "stacks": max(1, int(effect.get("stacks") or 1)),
            }
        )

    slot = str(skill.get("slot") or "")
    for effect_type, window in dict(candidate.get("skill_windows") or {}).items():
        normalized_effect = _normalize_effect_type(effect_type)
        if normalized_effect in seen or str(window.get("slot") or "") != slot:
            continue
        seen.add(normalized_effect)
        effects.append(
            {
                "effect_type": normalized_effect,
                "target": _default_sim_target(normalized_effect),
                "duration": max(0, int(window.get("duration") or WINDOW_DEFAULT_DURATIONS.get(normalized_effect, 0))),
                "chance": _to_float(window.get("chance") or 100.0) or 100.0,
                "stacks": 1,
            }
        )
    return effects


def build_candidate_clan_boss_member_row(
    candidate: Mapping[str, Any],
    slot_index: int,
    opener_slot: str | None = None,
) -> Dict[str, Any]:
    member_row = default_clan_boss_member_row(slot_index)
    member_row["champ_id"] = str(candidate.get("champ_id") or "").strip()
    member_row["champion_name"] = str(candidate.get("champion_name") or "").strip()
    member_row["speed"] = _to_float(dict(candidate.get("stats") or {}).get("spd")) or 170.0
    note_bits: List[str] = []
    if candidate.get("default_build"):
        note_bits.append(f"build {candidate['default_build']}")
    if candidate.get("score") is not None:
        note_bits.append(f"optimizer {_to_float(candidate.get('score')):.1f}")
    member_row["notes"] = " | ".join(note_bits)

    default_skills = list(member_row.get("skills") or [])
    for skill_row in default_skills:
        skill_row["enabled"] = False
    built_any = False
    for skill in list(candidate.get("skills") or []):
        slot = str(skill.get("slot") or "").upper()
        if slot not in {"A1", "A2", "A3", "A4"}:
            continue
        effects = _sim_effects_for_skill(candidate, skill)
        if not effects:
            continue
        built_any = True
        default_skills[{"A1": 0, "A2": 1, "A3": 2, "A4": 3}[slot]] = {
            "slot": slot,
            "skill_name": str(skill.get("skill_name") or slot),
            "cooldown": _effective_skill_cooldown(skill, booked=bool(candidate.get("booked"))),
            "priority": _sim_priority_for_slot(slot),
            "use_as_opener": slot in {"A2", "A3"} and _effective_skill_cooldown(skill, booked=bool(candidate.get("booked"))) > 0,
            "enabled": True,
            "effects": effects,
        }

    if not built_any:
        fallback_skill = _infer_fallback_sim_skill(candidate)
        if fallback_skill:
            default_skills[{"A1": 0, "A2": 1, "A3": 2, "A4": 3}[str(fallback_skill["slot"])] ] = fallback_skill
            built_any = True

    if not built_any and default_skills:
        default_skills[0]["enabled"] = True

    normalized_opener = str(opener_slot or "").strip().upper()
    if normalized_opener in {"A1", "A2", "A3", "A4"}:
        opener_applied = False
        for skill_row in default_skills:
            is_requested_slot = bool(skill_row.get("enabled")) and str(skill_row.get("slot") or "").upper() == normalized_opener
            skill_row["use_as_opener"] = is_requested_slot
            if is_requested_slot:
                skill_row["priority"] = max(int(skill_row.get("priority") or 0), 500)
                opener_applied = True
        if opener_applied:
            member_row["notes"] = f"{member_row['notes']} | opener {normalized_opener}".strip(" |")
    elif normalized_opener == "NONE":
        for skill_row in default_skills:
            skill_row["use_as_opener"] = False
        member_row["notes"] = f"{member_row['notes']} | opener manuale disattivato".strip(" |")

    member_row["skills"] = default_skills
    return member_row


def _difficulty_from_target_key(target_key: str) -> str:
    normalized = str(target_key or "").lower()
    if normalized.endswith("_ultra_nightmare") or normalized.endswith("_unm"):
        return "ultra_nightmare"
    if normalized.endswith("_nightmare") or normalized.endswith("_nm"):
        return "nightmare"
    if normalized.endswith("_brutal"):
        return "brutal"
    if normalized.endswith("_hard"):
        return "hard"
    if normalized.endswith("_normal"):
        return "normal"
    return "ultra_nightmare"


def simulate_candidate_team(
    team: Sequence[Mapping[str, Any]],
    difficulty: str = "ultra_nightmare",
    affinity: str = "void",
    max_boss_turns: int = 6,
    opener_overrides: Mapping[str, str] | None = None,
) -> Dict[str, Any]:
    opener_map = {
        str(champion_name or "").strip(): str(slot or "").strip().upper()
        for champion_name, slot in dict(opener_overrides or {}).items()
        if str(champion_name or "").strip() and str(slot or "").strip()
    }
    members = [
        build_candidate_clan_boss_member_row(
            candidate,
            index,
            opener_slot=opener_map.get(str(candidate.get("champion_name") or "").strip()),
        )
        for index, candidate in enumerate(team, start=1)
    ]
    if not members:
        return {"ok": False, "errors": ["Inserisci almeno un campione nel team."], "team": []}
    stun_target_slot = min(members, key=lambda row: (_to_float(row.get("speed") or 0.0), int(row.get("slot_index") or 99))).get("slot_index") or len(members)
    return simulate_clan_boss_battle(
        {
            "settings": {
                "difficulty": difficulty,
                "affinity": affinity,
                "max_boss_turns": max_boss_turns,
                "stun_target_slot": int(stun_target_slot),
            },
            "team": members,
        }
    )


def _evaluate_team_fit(
    team: Sequence[Mapping[str, Any]],
    target_key: str,
    thresholds: Mapping[str, float],
    boss_affinity: str,
) -> Dict[str, Any]:
    members = list(team or [])
    names = [str(member.get("champion_name") or "") for member in members]
    capability_sets = {
        str(member.get("champion_name") or ""): {str(tag) for tag in list(member.get("capability_tags") or [])}
        for member in members
    }
    roles_by_name = {
        str(member.get("champion_name") or ""): {str(role) for role in list(member.get("roles") or [])}
        for member in members
    }
    skill_windows_by_name = {
        str(member.get("champion_name") or ""): {
            _normalize_effect_type(effect_type): dict(window)
            for effect_type, window in dict(member.get("skill_windows") or {}).items()
        }
        for member in members
    }
    union_capabilities = {tag for tags in capability_sets.values() for tag in tags}

    sustain_members = sorted(
        name
        for name, tags in capability_sets.items()
        if tags & {"healing", "sustain", "shield", "ally_protect"}
        or any(effect in skill_windows_by_name.get(name, {}) for effect in {"shield", "ally_protect", "increase_defense"})
    )
    defense_members = sorted(
        name
        for name, tags in capability_sets.items()
        if tags & {"shield", "ally_protect", "increase_defense", "counterattack", "unkillable", "defense_core"}
        or any(effect in skill_windows_by_name.get(name, {}) for effect in {"shield", "ally_protect", "increase_defense", "counterattack", "block_debuffs", "unkillable"})
    )
    attack_down_members = sorted(
        name
        for name, tags in capability_sets.items()
        if "decrease_attack" in tags or "decrease_attack" in skill_windows_by_name.get(name, {})
    )
    defense_down_members = sorted(
        name
        for name, tags in capability_sets.items()
        if tags & {"decrease_defense", "weaken"} or any(effect in skill_windows_by_name.get(name, {}) for effect in {"decrease_defense", "weaken"})
    )
    pressure_members = sorted(
        name
        for name, tags in capability_sets.items()
        if tags & {"poison", "hp_burn", "boss_pressure"} or any(effect in skill_windows_by_name.get(name, {}) for effect in {"poison", "hp_burn"})
    )
    healing_members = sorted(
        name
        for name, tags in capability_sets.items()
        if "healing" in tags
    )
    shield_members = sorted(
        name
        for name, tags in capability_sets.items()
        if "shield" in tags or "shield" in skill_windows_by_name.get(name, {})
    )
    ally_protect_members = sorted(
        name
        for name, tags in capability_sets.items()
        if "ally_protect" in tags or "ally_protect" in skill_windows_by_name.get(name, {})
    )
    cleanse_members = sorted(
        name
        for name, tags in capability_sets.items()
        if tags & {"cleanse", "block_debuffs", "cleanse_support", "unkillable"} or any(effect in skill_windows_by_name.get(name, {}) for effect in {"cleanse", "block_debuffs", "unkillable"})
    )
    speed_members = sorted(
        str(member.get("champion_name") or "")
        for member in members
        if "speed" in list(member.get("roles") or []) or "speed_boost" in capability_sets.get(str(member.get("champion_name") or ""), set())
    )
    weak_affinity_members = sorted(str(member.get("champion_name") or "") for member in members if str(member.get("affinity_matchup") or "") == "weak")

    def windows_for(effect_type: str) -> List[Dict[str, Any]]:
        windows: List[Dict[str, Any]] = []
        for member in members:
            name = str(member.get("champion_name") or "")
            window = dict(skill_windows_by_name.get(name, {}).get(effect_type) or {})
            if not window:
                continue
            windows.append({"champion_name": name, **window})
        windows.sort(
            key=lambda row: (
                -float(row.get("quality") or 0.0),
                int(row.get("cooldown") or 0),
                str(row.get("champion_name") or ""),
            )
        )
        return windows

    def best_window(effect_type: str) -> Dict[str, Any]:
        best: Dict[str, Any] = {}
        for member in members:
            name = str(member.get("champion_name") or "")
            window = dict(skill_windows_by_name.get(name, {}).get(effect_type) or {})
            if not window:
                continue
            quality = float(window.get("quality") or 0.0)
            if quality > float(best.get("quality") or 0.0):
                best = {"champion_name": name, **window}
        return best

    attack_down_window = best_window("decrease_attack")
    defense_down_window = best_window("decrease_defense")
    weaken_window = best_window("weaken")
    shield_windows = windows_for("shield")
    block_debuffs_window = best_window("block_debuffs")
    increase_def_window = best_window("increase_defense")
    ally_protect_window = best_window("ally_protect")
    counterattack_window = best_window("counterattack")
    unkillable_window = best_window("unkillable")
    hp_burn_window = best_window("hp_burn")
    poison_window = best_window("poison")
    cleanse_window = best_window("cleanse")
    block_buffs_window = best_window("block_buffs")
    provoke_window = best_window("provoke")
    hex_window = best_window("hex")
    decrease_speed_window = best_window("decrease_speed")
    perfect_veil_window = best_window("perfect_veil")
    revive_on_death_window = best_window("revive_on_death")

    score = 0.0
    warnings: List[str] = []
    notes: List[str] = []
    build_requirements: List[str] = []
    simulation: Dict[str, Any] = {}
    maneater_tune: Dict[str, Any] = {"ready": False, "label": "", "build_requirements": []}

    if target_key.startswith("demon_lord_"):
        if len(sustain_members) >= 2:
            score += 18.0
            notes.append("Sustain presente su piu slot.")
        elif len(sustain_members) == 1:
            score += 6.0
            warnings.append(f"Sustain corto: solo {sustain_members[0]} copre cure/scudi/protezione in modo esplicito.")
        else:
            score -= 24.0
            warnings.append("Mancano cure o sustain affidabile: il team rischia di collassare presto.")

        if not healing_members and float(unkillable_window.get("quality") or 0.0) < 0.7:
            score -= 14.0
            warnings.append("Sustain reale assente: vedo scudi/protezioni ma non cure o leech affidabili per i turni lunghi.")

        if len(defense_members) >= 2:
            score += 16.0
            notes.append("Difesa di squadra con almeno due strati.")
        elif len(defense_members) == 1:
            score += 4.0
            warnings.append(f"Difesa di squadra leggera: solo {defense_members[0]} porta uno strato difensivo chiaro.")
        else:
            score -= 18.0
            warnings.append("Mancano strati difensivi stabili: serve piu protezione su tutto il team.")

        if len(shield_windows) >= 2:
            primary_shield = shield_windows[0]
            secondary_shield = shield_windows[1]
            if (
                float(primary_shield.get("quality") or 0.0) >= 0.58
                and float(secondary_shield.get("quality") or 0.0) >= 0.58
                and abs(int(primary_shield.get("cooldown") or 0) - int(secondary_shield.get("cooldown") or 0)) <= 1
                and not healing_members
                and not ally_protect_members
            ):
                score -= 10.0
                warnings.append(
                    f"Scudi sovrapposti: {primary_shield.get('champion_name')} e {secondary_shield.get('champion_name')} rischiano di coprire lo stesso turno lasciando buchi dopo."
                )

        if float(attack_down_window.get("quality") or 0.0) >= 0.85:
            score += 18.0
            notes.append(f"Decrease ATK affidabile da {attack_down_window.get('champion_name')}.")
        elif float(attack_down_window.get("quality") or 0.0) >= 0.58:
            score += 8.0
            warnings.append(f"Decrease ATK affidato a una sola finestra fragile: {attack_down_window.get('champion_name')}.")
        elif len(attack_down_members) >= 2:
            score += 18.0
        elif len(attack_down_members) == 1:
            score += 8.0
            warnings.append(f"Decrease ATK affidato a una sola fonte: {attack_down_members[0]}.")
        else:
            score -= 32.0
            warnings.append("Manca Decrease ATK stabile sul boss: cosi il Clan Boss picchia troppo.")

        if float(defense_down_window.get("quality") or 0.0) >= 0.75 or float(weaken_window.get("quality") or 0.0) >= 0.7:
            score += 10.0 if len(defense_down_members) >= 2 else 6.0
            if defense_down_window:
                notes.append(f"Decrease DEF/Weaken con finestra utile da {defense_down_window.get('champion_name') or weaken_window.get('champion_name')}.")
        elif defense_down_members:
            score += 4.0
            warnings.append("Decrease DEF o Weaken presenti ma con finestra non chiarissima.")
        else:
            score -= 12.0
            warnings.append("Manca una copertura chiara di Decrease DEF o Weaken sul boss.")

        if "Geomancer" in names:
            extra_burners = sorted(
                name for name in pressure_members if name != "Geomancer" and "hp_burn" in skill_windows_by_name.get(name, {})
            )
            if extra_burners:
                score -= 16.0
                warnings.append(f"Geomancer rischia di perdere valore se un altro burner sovrascrive il suo HP Burn: {', '.join(extra_burners[:3])}.")

        if float(hp_burn_window.get("quality") or 0.0) >= 0.7 or float(poison_window.get("quality") or 0.0) >= 0.7:
            score += 8.0 if len(pressure_members) >= 2 else 4.0
            if hp_burn_window or poison_window:
                notes.append(
                    f"Pressione danno appoggiata su {hp_burn_window.get('champion_name') or poison_window.get('champion_name')}."
                )
        else:
            warnings.append("Manca una fonte chiara di Poison o HP Burn per tenere alta la pressione danno.")

        if float(block_debuffs_window.get("quality") or 0.0) >= 0.75 or float(cleanse_window.get("quality") or 0.0) >= 0.75 or float(unkillable_window.get("quality") or 0.0) >= 0.7:
            score += 8.0
            if block_debuffs_window:
                notes.append(f"Risposta a stun/debuff con {block_debuffs_window.get('champion_name')}.")
        else:
            score -= 10.0
            warnings.append("Manca una risposta affidabile a stun/debuff del Clan Boss.")

        if speed_members:
            score += 6.0 if len(speed_members) >= 2 else 3.0
        else:
            score -= 4.0
            warnings.append("Il team non ha un motore speed davvero evidente.")

        has_maneater = "Maneater" in names
        has_maneater_partner = any(
            name in MANEATER_TUNE_PARTNERS or "cooldown_reset" in capability_sets.get(name, set())
            for name in names
            if name != "Maneater"
        )
        maneater_tune = _evaluate_maneater_tune(members)
        build_requirements.extend(list(maneater_tune.get("build_requirements") or []))
        if has_maneater and bool(maneater_tune.get("ready")):
            score += 24.0
            notes.append(f"Maneater pronto per tune reale: {maneater_tune.get('label')}.")
        elif has_maneater and has_maneater_partner:
            score -= 12.0
            notes.append("Maneater ha un partner reale, ma la tune non e pronta con speed/book attuali.")
            warnings.extend(list(maneater_tune.get("warnings") or [])[:2])
        elif has_maneater:
            score -= 45.0
            warnings.append("Maneater senza partner/tune compatibile: cosi l'Unkillable non regge e il pick va penalizzato forte.")
        else:
            has_maneater_partner = False

        defense_window_quality = max(
            float(increase_def_window.get("quality") or 0.0),
            float(ally_protect_window.get("quality") or 0.0),
            float(counterattack_window.get("quality") or 0.0),
            float(unkillable_window.get("quality") or 0.0),
        )
        if defense_window_quality >= 0.78:
            score += 8.0
            notes.append("Il team ha almeno una finestra difensiva ben cadenzata.")
        elif defense_members:
            warnings.append("I layer difensivi ci sono, ma la rotazione non sembra ancora abbastanza stretta.")

        if boss_affinity != "void" and len(weak_affinity_members) >= 2:
            score -= 12.0
            warnings.append(f"Troppi campioni in weak affinity per {boss_affinity}: {', '.join(weak_affinity_members[:3])}.")

        if len(members) == 5:
            simulation = simulate_candidate_team(
                members,
                difficulty=_difficulty_from_target_key(target_key),
                affinity=boss_affinity,
                max_boss_turns=6,
            )
            if simulation.get("ok"):
                sim_summary = dict(simulation.get("summary") or {})
                dec_atk_uptime = _to_float(sim_summary.get("decrease_attack_uptime_pct"))
                block_stuns = _to_float(sim_summary.get("blocked_stuns_pct"))
                def_uptime = max(
                    _to_float(sim_summary.get("increase_def_uptime_pct")),
                    _to_float(sim_summary.get("ally_protect_uptime_pct")),
                    _to_float(sim_summary.get("counterattack_uptime_pct")),
                )
                if dec_atk_uptime >= 90.0:
                    score += 12.0
                    notes.append(f"Sim: Decrease ATK regge bene ({dec_atk_uptime:.0f}%).")
                elif dec_atk_uptime >= 65.0:
                    score += 3.0
                    warnings.append(f"Sim: Decrease ATK coperto solo a tratti ({dec_atk_uptime:.0f}%).")
                else:
                    score -= 20.0
                    warnings.append(f"Sim: Decrease ATK crolla nella rotazione ({dec_atk_uptime:.0f}%).")

                if block_stuns >= 80.0:
                    score += 6.0
                    notes.append(f"Sim: stun gestito bene ({block_stuns:.0f}% bloccati).")
                elif block_stuns <= 20.0:
                    score -= 8.0
                    warnings.append("Sim: lo stun passa quasi sempre, quindi la rotazione e fragile.")

                if def_uptime >= 80.0:
                    score += 6.0
                elif def_uptime < 45.0:
                    score -= 8.0
                    warnings.append("Sim: layer difensivi troppo intermittenti sulle AOE.")

                warnings.extend(list(sim_summary.get("warnings") or [])[:3])
            else:
                warnings.append("Simulazione Clan Boss non riuscita sulla squadra completa proposta.")
    elif target_key.startswith("hydra_"):
        hydra_rotation = HYDRA_ROTATION_RULES.get(str(boss_affinity or "").strip().lower()) or HYDRA_ROTATION_RULES["rotation_1"]
        block_buffs_members = sorted(
            name
            for name, tags in capability_sets.items()
            if "block_buffs" in tags or "block_buffs" in skill_windows_by_name.get(name, {})
        )
        provoke_members = sorted(
            name
            for name, tags in capability_sets.items()
            if "provoke" in tags or "provoke" in skill_windows_by_name.get(name, {})
        )
        hex_members = sorted(
            name
            for name, tags in capability_sets.items()
            if "hex" in tags or "hex" in skill_windows_by_name.get(name, {})
        )
        revive_members = sorted(
            name
            for name, tags in capability_sets.items()
            if "revive" in roles_by_name.get(name, set()) or "revive_on_death" in tags
        )
        mischief_members = sorted(
            name
            for name, tags in capability_sets.items()
            if "mischief_tank" in tags or "perfect_veil" in tags or "perfect_veil" in skill_windows_by_name.get(name, {})
        )

        if len(sustain_members) >= 3:
            score += 16.0
            notes.append("Hydra con sustain distribuito su piu slot.")
        elif len(sustain_members) >= 2:
            score += 8.0
        else:
            score -= 20.0
            warnings.append("Hydra senza sustain reale su almeno due slot: team troppo fragile.")

        if float(block_buffs_window.get("quality") or 0.0) >= 0.72:
            score += 18.0
            notes.append(f"Block Buffs affidabile da {block_buffs_window.get('champion_name')}.")
        elif block_buffs_members:
            score += 6.0
            warnings.append(f"Block Buffs presente ma non ancora molto solido: {block_buffs_members[0]}.")
        else:
            score -= 26.0
            warnings.append("Manca Block Buffs: Hydra rischia di andare fuori controllo.")

        if float(provoke_window.get("quality") or 0.0) >= 0.58:
            score += 12.0
            notes.append(f"Provoke riconosciuto su {provoke_window.get('champion_name')}.")
        elif provoke_members:
            score += 4.0
            warnings.append("Provoke c'e, ma la finestra non e ancora chiarissima.")
        else:
            score -= 18.0
            warnings.append("Manca Provoke: una testa chiave puo rompere il fight.")

        if float(hex_window.get("quality") or 0.0) >= 0.6:
            score += 10.0
            notes.append(f"Hex disponibile con {hex_window.get('champion_name')}.")
        elif hex_members:
            score += 4.0
        else:
            score -= 10.0
            warnings.append("Manca Hex: liberare il divorato e spingere il danno sara piu difficile.")

        if revive_members:
            score += 8.0
        else:
            warnings.append("Nessun revive esplicito: recover piu fragile nei run lunghi.")

        if mischief_members:
            score += 7.0
            if perfect_veil_window:
                notes.append(f"Gestione Mischief supportata da {perfect_veil_window.get('champion_name')}.")
        else:
            warnings.append("Manca una risposta evidente a Mischief tank / Perfect Veil.")

        if float(decrease_speed_window.get("quality") or 0.0) >= 0.58:
            score += 4.0
        if speed_members:
            score += 4.0 if len(speed_members) >= 2 else 2.0
        else:
            warnings.append("Hydra senza motore speed evidente: rotazione piu rigida.")

        if "Decay" in hydra_rotation["starter_heads"] and not provoke_members:
            score -= 14.0
            warnings.append(f"{hydra_rotation['label']}: Decay parte subito e manca un Provoke affidabile.")
        if "Mischief" in hydra_rotation["starter_heads"] and not mischief_members and not block_buffs_members:
            score -= 12.0
            warnings.append(f"{hydra_rotation['label']}: Mischief in apertura senza tank dedicato o Block Buffs stabile.")
        if hydra_rotation.get("needs_perfect_veil") and not (
            perfect_veil_window
            or any("perfect_veil" in capability_sets.get(name, set()) for name in capability_sets)
            or cleanse_members
        ):
            score -= 10.0
            warnings.append(f"{hydra_rotation['label']}: Torment in apertura, ma non vedo Perfect Veil o una risposta pulita.")
        if hydra_rotation.get("needs_wrath_mitigation") and not (
            attack_down_members
            or defense_members
            or float(ally_protect_window.get('quality') or 0.0) >= 0.58
        ):
            score -= 10.0
            warnings.append(f"{hydra_rotation['label']}: Wrath in apertura senza mitigazione danni abbastanza chiara.")
        notes.append(f"{hydra_rotation['label']} starter: {', '.join(hydra_rotation['starter_heads'])}.")
    elif target_key.startswith("iron_twins_"):
        decrease_speed_members = sorted(
            name
            for name, tags in capability_sets.items()
            if "decrease_speed" in tags or "decrease_speed" in skill_windows_by_name.get(name, {})
        )
        revive_on_death_members = sorted(
            name
            for name, tags in capability_sets.items()
            if "revive_on_death" in tags or "revive_on_death" in skill_windows_by_name.get(name, {})
        )

        if len(sustain_members) >= 2:
            score += 14.0
            notes.append("Iron Twins con sustain su piu slot.")
        elif len(sustain_members) == 1:
            score += 4.0
            warnings.append(f"Sustain leggero per Iron Twins: solo {sustain_members[0]}.")
        else:
            score -= 18.0
            warnings.append("Manca sustain chiaro per Iron Twins.")

        if float(decrease_speed_window.get("quality") or 0.0) >= 0.58:
            score += 14.0
            notes.append(f"Decrease SPD affidabile da {decrease_speed_window.get('champion_name')}.")
        elif decrease_speed_members:
            score += 5.0
            warnings.append("Decrease SPD presente ma non ancora molto stabile.")
        else:
            score -= 20.0
            warnings.append("Manca Decrease SPD: Iron Twins perde molto controllo.")

        if float(block_debuffs_window.get("quality") or 0.0) >= 0.72 or float(cleanse_window.get("quality") or 0.0) >= 0.72:
            score += 10.0
        else:
            score -= 8.0
            warnings.append("Manca una risposta affidabile a debuff e finestre punitive di Iron Twins.")

        if float(hp_burn_window.get("quality") or 0.0) >= 0.7 or "Geomancer" in names:
            score += 8.0
        else:
            warnings.append("Manca una fonte chiara di pressione single-target utile per Iron Twins.")

        if revive_on_death_members or float(revive_on_death_window.get("quality") or 0.0) >= 0.5:
            score += 6.0
            notes.append("Archetipo revive-on-death disponibile come piano difensivo.")

        if boss_affinity != "void" and len(weak_affinity_members) >= 2:
            score -= 10.0
            warnings.append(f"Troppi campioni in weak affinity per Iron Twins {boss_affinity}: {', '.join(weak_affinity_members[:3])}.")
    return {
        "score": round(score, 2),
        "sustain_members": sustain_members,
        "healing_members": healing_members,
        "shield_members": shield_members,
        "ally_protect_members": ally_protect_members,
        "defense_members": defense_members,
        "attack_down_members": attack_down_members,
        "defense_down_members": defense_down_members,
        "pressure_members": pressure_members,
        "cleanse_members": cleanse_members,
        "speed_members": speed_members,
        "weak_affinity_members": weak_affinity_members,
        "has_maneater_tune": bool(maneater_tune.get("ready")) if target_key.startswith("demon_lord_") else False,
        "maneater_tune_label": str(maneater_tune.get("label") or ""),
        "build_requirements": build_requirements[:6],
        "simulation": simulation,
        "warnings": warnings[:8],
        "notes": notes[:6],
        "capability_coverage": sorted(union_capabilities),
    }


def _historical_pair_bonus(
    team: Sequence[Mapping[str, Any]],
    team_history: Mapping[str, Mapping[str, Mapping[str, Any]]] | None,
    objective_key: str = "stable",
) -> float:
    pair_index = dict((team_history or {}).get("pairs") or {})
    if len(team) < 2 or not pair_index:
        return 0.0
    names = sorted({str(member.get("champion_name") or "").strip() for member in team if str(member.get("champion_name") or "").strip()})
    bonus = 0.0
    for first_index, first_name in enumerate(names):
        for second_name in names[first_index + 1:]:
            pair_row = dict(pair_index.get(_team_signature((first_name, second_name))) or {})
            if not pair_row:
                continue
            run_count = int(pair_row.get("run_count") or 0)
            avg_total_damage = _to_float(pair_row.get("avg_total_damage"))
            max_total_damage = _to_float(pair_row.get("max_total_damage"))
            if objective_key == "push_70m":
                if max_total_damage >= 60_000_000.0:
                    bonus += min(run_count, 2) * 1.5
                    bonus += min(max_total_damage / 10_000_000.0, 8.0) * 2.0
            else:
                bonus += min(run_count, 4) * 0.8
                bonus += min(avg_total_damage / 10_000_000.0, 5.0) * 0.8
    return round(bonus, 2)


def _historical_exact_team_bonus(
    team: Sequence[Mapping[str, Any]],
    team_history: Mapping[str, Mapping[str, Mapping[str, Any]]] | None,
    objective_key: str = "stable",
) -> float:
    exact_index = dict((team_history or {}).get("exact") or {})
    if not team or not exact_index:
        return 0.0
    exact_row = dict(exact_index.get(_team_signature(str(member.get("champion_name") or "") for member in team)) or {})
    if not exact_row:
        return 0.0
    avg_total_damage = _to_float(exact_row.get("avg_total_damage"))
    max_total_damage = _to_float(exact_row.get("max_total_damage"))
    run_count = int(exact_row.get("run_count") or 0)
    if objective_key == "push_70m":
        if max_total_damage < 60_000_000.0:
            return 0.0
        bonus = min(run_count, 3) * 3.0
        bonus += min(max_total_damage / 1_000_000.0, 90.0) * 2.5
        if max_total_damage >= 70_000_000.0:
            bonus += 140.0
    else:
        bonus = min(run_count, 8) * 3.0
        bonus += min(avg_total_damage / 1_000_000.0, 60.0) * 0.35
        bonus += min(max_total_damage / 1_000_000.0, 60.0) * 0.1
    return round(bonus, 2)


def _objective_candidate_bonus(
    candidate: Mapping[str, Any],
    selected_team: Sequence[Mapping[str, Any]],
    objective_key: str,
    target_key: str,
    thresholds: Mapping[str, float],
) -> float:
    if not str(target_key or "").startswith("demon_lord_"):
        return 0.0
    roles = {str(role) for role in list(candidate.get("roles") or [])}
    capability_tags = {str(tag) for tag in list(candidate.get("capability_tags") or [])}
    weighted_signals = dict(candidate.get("weighted_stat_signals") or {})
    selected_names = {str(member.get("champion_name") or "") for member in selected_team}
    selected_roles = {str(role) for member in selected_team for role in list(member.get("roles") or [])}
    if objective_key == "stable":
        selected_tags = {str(tag) for member in selected_team for tag in list(member.get("capability_tags") or [])}
        bonus = 0.0
        if "healing" not in selected_tags and "healing" in capability_tags:
            bonus += 48.0
        if "cleanse" not in selected_tags and capability_tags & {"cleanse", "block_debuffs"}:
            bonus += 16.0
        if len(selected_team) >= 2 and "decrease_attack" not in selected_roles and "decrease_attack" in roles:
            bonus += 12.0
        if "sustain" in capability_tags:
            bonus += 6.0
        return round(bonus, 2)

    if objective_key != "push_70m":
        return 0.0
    bonus = 0.0
    if roles & {"damage", "poisoner", "burner"}:
        bonus += 9.0
    if capability_tags & {"poison", "hp_burn", "boss_pressure"}:
        bonus += 7.0
    if capability_tags & {"decrease_defense", "weaken"}:
        bonus += 6.0
    if "counterattack" in roles:
        bonus += 4.0
    bonus += min(_to_float(weighted_signals.get("damage")) * 9.0, 12.0)
    bonus += min(_to_float(weighted_signals.get("speed")) * 5.0, 6.0)
    if "decrease_attack" in roles and "decrease_attack" not in selected_roles:
        bonus += 5.0
    if "speed" in roles and "speed" not in selected_roles:
        bonus += 3.0
    if "Maneater" in selected_names and str(candidate.get("champion_name") or "") == "Pain Keeper":
        bonus += 10.0
    return round(bonus, 2)


def _objective_team_bonus(
    team: Sequence[Mapping[str, Any]],
    objective_key: str,
    target_key: str,
    thresholds: Mapping[str, float],
    boss_affinity: str,
    team_fit: Mapping[str, Any] | None = None,
    team_history: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
) -> float:
    fit = dict(team_fit or _evaluate_team_fit(team, target_key=target_key, thresholds=thresholds, boss_affinity=boss_affinity))
    if not str(target_key or "").startswith("demon_lord_"):
        return 0.0
    damage_roles = sum(1 for member in team if {"damage", "poisoner", "burner"} & {str(role) for role in list(member.get("roles") or [])})
    capability_union = {str(tag) for member in team for tag in list(member.get("capability_tags") or [])}
    capability_by_name = {
        str(member.get("champion_name") or ""): {str(tag) for tag in list(member.get("capability_tags") or [])}
        for member in team
    }
    roles_by_name = {
        str(member.get("champion_name") or ""): {str(role) for role in list(member.get("roles") or [])}
        for member in team
    }
    exact_history = dict((team_history or {}).get("exact", {}).get(_team_signature(str(member.get("champion_name") or "") for member in team)) or {})
    avg_total_damage = _to_float(exact_history.get("avg_total_damage"))
    max_total_damage = _to_float(exact_history.get("max_total_damage"))
    run_count = int(exact_history.get("run_count") or 0)
    attack_down_members = len(list(fit.get("attack_down_members") or []))
    pressure_members = len(list(fit.get("pressure_members") or []))
    defense_members = len(list(fit.get("defense_members") or []))
    cleanse_members = len(list(fit.get("cleanse_members") or []))
    speed_members = len(list(fit.get("speed_members") or []))

    if objective_key == "push_70m":
        bonus = 0.0
        bonus += damage_roles * 10.0
        bonus += pressure_members * 7.0
        bonus += 8.0 if capability_union & {"decrease_defense", "weaken"} else -8.0
        bonus += 6.0 if attack_down_members >= 1 else -18.0
        bonus += 4.0 if speed_members >= 1 else 0.0
        bonus += min(max_total_damage / 1_000_000.0, 90.0) * 1.8
        bonus += min(avg_total_damage / 1_000_000.0, 90.0) * 0.8
        bonus += min(run_count, 3) * 3.0
        if run_count == 0:
            bonus += 28.0
        elif max_total_damage < 50_000_000.0:
            bonus -= 35.0
        elif max_total_damage < 60_000_000.0:
            bonus -= 12.0
        if max_total_damage >= 70_000_000.0:
            bonus += 120.0
        elif max_total_damage >= 60_000_000.0:
            bonus += 70.0
        elif max_total_damage <= 0.0:
            bonus += 10.0 if damage_roles >= 3 and pressure_members >= 2 else -10.0
        if damage_roles < 3:
            bonus -= 22.0
        if pressure_members == 0:
            bonus -= 18.0
        return round(bonus, 2)

    bonus = 0.0
    bonus += min(run_count, 8) * 9.0
    bonus += min(avg_total_damage / 1_000_000.0, 60.0) * 0.8
    bonus += min(max_total_damage / 1_000_000.0, 60.0) * 0.3
    bonus += attack_down_members * 6.0
    bonus += defense_members * 4.0
    bonus += cleanse_members * 4.0
    healing_members = len(list(fit.get("healing_members") or []))
    sustain_members = len(list(fit.get("sustain_members") or []))
    undercovered_supports = [
        name
        for name, roles in roles_by_name.items()
        if roles & {"support", "debuffer", "decrease_attack"}
        and not capability_by_name.get(name, set()) & {"healing", "sustain", "shield", "ally_protect", "defense_core", "unkillable"}
    ]
    exposed_attack_down = [
        name
        for name in list(fit.get("attack_down_members") or [])
        if not capability_by_name.get(name, set()) & {"healing", "sustain", "shield", "ally_protect", "defense_core", "unkillable"}
    ]
    if str(target_key or "").startswith("demon_lord_"):
        if healing_members == 0:
            bonus -= 220.0
        else:
            bonus += healing_members * 36.0
        if sustain_members < 2:
            bonus -= 70.0
        else:
            bonus += sustain_members * 10.0
        if cleanse_members == 0:
            bonus -= 24.0
        if undercovered_supports:
            bonus -= 90.0
        if exposed_attack_down:
            bonus -= 120.0
    if len(list(fit.get("warnings") or [])) >= 6:
        bonus -= 12.0
    return round(bonus, 2)


def _evaluate_team_total_score(
    team: Sequence[Mapping[str, Any]],
    profile: OptimizerBossProfile,
    target_key: str,
    thresholds: Mapping[str, float],
    boss_affinity: str,
    team_history: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
    objective_key: str = "stable",
) -> float:
    if _team_has_disallowed_weak_affinity(team, target_key, boss_affinity):
        return -10000.0
    if objective_key == "stable" and str(target_key or "").startswith("demon_lord_"):
        preview_fit = _evaluate_team_fit(team, target_key=target_key, thresholds=thresholds, boss_affinity=boss_affinity)
        if not list(preview_fit.get("attack_down_members") or []):
            return -9000.0
    covered_roles = {str(role) for member in team for role in list(member.get("roles") or [])}
    required_coverage = sum(
        1 for requirement in profile.required_role_groups if any(role in requirement.acceptable_roles for role in covered_roles)
    )
    valuable_coverage = sum(1 for role in profile.valuable_roles if role in covered_roles)
    base_score = sum(
        _candidate_base_score_for_objective(member, objective_key=objective_key, target_key=target_key)
        for member in team
    )
    team_fit = _evaluate_team_fit(team, target_key=target_key, thresholds=thresholds, boss_affinity=boss_affinity)
    return (
        base_score
        + (required_coverage * 10.0)
        + (valuable_coverage * 2.0)
        + float(team_fit.get("score") or 0.0)
        + _historical_exact_team_bonus(team, team_history, objective_key=objective_key)
        + _historical_pair_bonus(team, team_history, objective_key=objective_key)
        + _objective_team_bonus(
            team,
            objective_key=objective_key,
            target_key=target_key,
            thresholds=thresholds,
            boss_affinity=boss_affinity,
            team_fit=team_fit,
            team_history=team_history,
        )
    )


def _refine_team_selection(
    selected: Sequence[Mapping[str, Any]],
    candidates: Sequence[Mapping[str, Any]],
    profile: OptimizerBossProfile,
    target_key: str,
    thresholds: Mapping[str, float],
    boss_affinity: str,
    team_history: Mapping[str, Mapping[str, Mapping[str, Any]]] | None = None,
    objective_key: str = "stable",
) -> List[Dict[str, Any]]:
    best_team = [dict(member) for member in selected]
    if not best_team:
        return []

    best_score = _evaluate_team_total_score(
        best_team,
        profile=profile,
        target_key=target_key,
        thresholds=thresholds,
        boss_affinity=boss_affinity,
        team_history=team_history,
        objective_key=objective_key,
    )

    for _ in range(2):
        improved = False
        best_names = {str(member.get("champion_name") or "") for member in best_team}
        for index, outgoing in enumerate(list(best_team)):
            outgoing_name = str(outgoing.get("champion_name") or "")
            for candidate in candidates:
                candidate_name = str(candidate.get("champion_name") or "")
                if candidate_name in best_names and candidate_name != outgoing_name:
                    continue
                proposal = list(best_team)
                proposal[index] = dict(candidate)
                if _team_has_disallowed_weak_affinity(proposal, target_key, boss_affinity):
                    continue
                proposal_score = _evaluate_team_total_score(
                    proposal,
                    profile=profile,
                    target_key=target_key,
                    thresholds=thresholds,
                    boss_affinity=boss_affinity,
                    team_history=team_history,
                    objective_key=objective_key,
                )
                if proposal_score > (best_score + 0.5):
                    best_team = proposal
                    best_score = proposal_score
                    best_names = {str(member.get("champion_name") or "") for member in best_team}
                    improved = True
        if not improved:
            break

    exact_history_index = dict((team_history or {}).get("exact") or {})
    candidate_by_name = {
        str(candidate.get("champion_name") or ""): dict(candidate)
        for candidate in candidates
        if str(candidate.get("champion_name") or "")
    }
    ranked_history = sorted(
        exact_history_index.items(),
        key=lambda item: (
            _to_float(dict(item[1]).get("max_total_damage")) if objective_key == "push_70m" else _to_float(dict(item[1]).get("avg_total_damage")),
            int(dict(item[1]).get("run_count") or 0),
            _to_float(dict(item[1]).get("avg_total_damage")),
        ),
        reverse=True,
    )
    for signature, history_row in ranked_history[:12]:
        team_names = [name for name in str(signature or "").split("|") if name]
        if len(team_names) != profile.team_size:
            continue
        if any(name not in candidate_by_name for name in team_names):
            continue
        proposal = [dict(candidate_by_name[name]) for name in team_names]
        if _team_has_disallowed_weak_affinity(proposal, target_key, boss_affinity):
            continue
        proposal_score = _evaluate_team_total_score(
            proposal,
            profile=profile,
            target_key=target_key,
            thresholds=thresholds,
            boss_affinity=boss_affinity,
            team_history=team_history,
            objective_key=objective_key,
        )
        if proposal_score > (best_score + 0.5):
            best_team = proposal
            best_score = proposal_score

    return sorted(best_team, key=lambda item: (-float(item.get("score") or 0.0), str(item.get("champion_name") or "").lower()))


def _build_reasons(
    roles: Sequence[str],
    stat_signals: Mapping[str, float],
    evidence: Mapping[str, Any],
    hint: ChampionHint | None,
    affinity_state: str,
    boss_affinity: str,
    stat_reliability: Mapping[str, Any],
) -> List[str]:
    reasons: List[str] = []
    if roles:
        reasons.append(f"Ruoli riconosciuti: {', '.join(roles[:5])}.")
    if str(stat_reliability.get("source") or "") != "raw":
        reasons.append("Stats correnti derivate: utili per lo scheletro, ma non ancora trusted al 100%.")
    if stat_signals.get("speed", 0.0) >= 0.8:
        reasons.append("Speed gia buona per un primo scheletro Clan Boss.")
    if stat_signals.get("survival", 0.0) >= 0.8:
        reasons.append("Tenuta promettente su HP/DEF/RES.")
    if stat_signals.get("damage", 0.0) >= 0.8 and "damage" in roles:
        reasons.append("Profilo offensivo gia competitivo.")
    if int(evidence.get("run_count") or 0) > 0:
        reasons.append(f"Gia visto in {int(evidence.get('run_count') or 0)} run registrate su questo target.")
    if affinity_state == "strong":
        reasons.append(f"Affinita favorevole contro boss {boss_affinity}.")
    elif affinity_state == "weak":
        reasons.append(f"Affinita sfavorevole contro boss {boss_affinity}.")
    if hint and hint.notes:
        reasons.append(hint.notes)
    return reasons[:4]


def _build_risk_flags(
    target_key: str,
    champion_name: str,
    roles: Sequence[str],
    capability_tags: Sequence[str],
    stat_signals: Mapping[str, float],
    affinity_state: str,
    thresholds: Mapping[str, float],
) -> List[str]:
    risks: List[str] = []
    role_set = set(roles)
    required_speed = _to_float(thresholds.get("required_speed"))
    required_accuracy = _to_float(thresholds.get("required_accuracy"))
    required_resistance = _to_float(thresholds.get("required_resistance"))
    survival_floor = _to_float(thresholds.get("survival_floor"))

    if target_key.startswith("demon_lord_"):
        if stat_signals.get("speed_raw", 0.0) < required_speed:
            risks.append(f"SPD ancora bassa per il livello scelto ({int(required_speed)}+ consigliata).")
        if any(role in {"debuffer", "poisoner", "burner", "decrease_attack"} for role in role_set) and stat_signals.get("accuracy_raw", 0.0) < required_accuracy:
            risks.append(f"ACC probabilmente corta per tenere i debuff ({int(required_accuracy)}+ consigliata).")
        if any(role in {"survival", "ally_protect", "support", "cleanse"} for role in role_set) and stat_signals.get("survival", 0.0) < survival_floor:
            risks.append("Tenuta ancora fragile per fight lunghi.")
        if champion_name == "Maneater" and "unkillable" in capability_tags:
            risks.append("Maneater vale davvero solo dentro una tune con partner compatibile: fuori comp va ridimensionato.")
    elif target_key.startswith("hydra_"):
        if stat_signals.get("speed_raw", 0.0) < required_speed:
            risks.append(f"SPD corta per Hydra {target_key.split('_', 1)[1]} ({int(required_speed)}+ euristica).")
        if any(role in {"debuffer", "block_buffs", "provoke", "hexer", "decrease_speed"} for role in role_set) and stat_signals.get("accuracy_raw", 0.0) < required_accuracy:
            risks.append(f"ACC corta per utility Hydra ({int(required_accuracy)}+ euristica).")
        if any(role in {"support", "survival", "cleanse", "revive", "mischief_tank"} for role in role_set) and stat_signals.get("survival", 0.0) < survival_floor:
            risks.append("Tenuta bassa per un fight Hydra lungo e sporco.")
        if "mischief_tank" in role_set and required_resistance > 0 and _to_float(stat_signals.get("res_raw")) < required_resistance:
            risks.append(f"RES corta per ruolo Mischief tank ({int(required_resistance)}+ euristica).")
    elif target_key.startswith("iron_twins_"):
        if stat_signals.get("speed_raw", 0.0) < required_speed:
            risks.append(f"SPD corta per Iron Twins ({int(required_speed)}+ euristica).")
        if any(role in {"debuffer", "decrease_speed", "block_buffs", "burner"} for role in role_set) and stat_signals.get("accuracy_raw", 0.0) < required_accuracy:
            risks.append(f"ACC corta per Iron Twins ({int(required_accuracy)}+ euristica).")
        if any(role in {"support", "survival", "cleanse", "ally_protect", "revive_on_death"} for role in role_set) and stat_signals.get("survival", 0.0) < survival_floor:
            risks.append("Tenuta ancora corta per le finestre punitive di Iron Twins.")
        if required_resistance > 0 and any(role in {"support", "survival", "revive_on_death"} for role in role_set) and _to_float(stat_signals.get("res_raw")) < required_resistance:
            risks.append(f"RES corta per stage alta Iron Twins ({int(required_resistance)}+ euristica).")
    if affinity_state == "weak":
        risks.append("Weak affinity contro il boss: possibile calo consistenza su debuff e danno.")
    return risks


def _compute_evidence_bonus(evidence: Mapping[str, Any], roles: Sequence[str]) -> float:
    run_count = int(evidence.get("run_count") or 0)
    if run_count <= 0:
        return 0.0
    damage_done = _to_float(evidence.get("avg_damage_done"))
    healing_done = _to_float(evidence.get("avg_healing_done"))
    damage_taken = _to_float(evidence.get("avg_damage_taken"))
    bonus = min(run_count, 8) * 0.8
    if "damage" in roles or "poisoner" in roles or "burner" in roles:
        bonus += min(damage_done / 1_000_000.0, 6.0) * 0.9
    if "support" in roles or "cleanse" in roles:
        bonus += min(healing_done / 250_000.0, 4.0) * 0.5
    if "survival" in roles or "ally_protect" in roles:
        bonus += min(damage_taken / 400_000.0, 4.0) * 0.35
    return bonus


def _compute_role_bonus(roles: Sequence[str], stat_signals: Mapping[str, float]) -> float:
    role_set = set(roles)
    speed = stat_signals["speed"]
    accuracy = stat_signals["accuracy"]
    survival = stat_signals["survival"]
    damage = stat_signals["damage"]

    bonus = 0.0
    if "speed" in role_set:
        bonus += 8.0 * speed
    if role_set & {"debuffer", "poisoner", "burner", "decrease_attack", "block_buffs", "provoke", "hexer", "decrease_speed"}:
        bonus += 9.0 * ((speed + accuracy) / 2.0)
    if role_set & {"support", "survival", "cleanse", "ally_protect", "unkillable", "mischief_tank", "revive", "revive_on_death"}:
        bonus += 10.0 * ((survival * 0.7) + (speed * 0.3))
    if role_set & {"damage", "poisoner", "burner", "counterattack", "hexer"}:
        bonus += 12.0 * ((damage * 0.65) + (speed * 0.2) + (accuracy * 0.15))
    return bonus


def _build_stat_reliability(
    stat_model: Mapping[str, Any],
    relic_count: int,
    bonus_sources: Sequence[str],
) -> Dict[str, Any]:
    source = str(stat_model.get("source") or "").strip() or "missing"
    completeness = str(stat_model.get("completeness") or "").strip() or "missing"
    warnings: List[str] = []
    missing_sources: List[str] = []

    if source != "raw":
        warnings.append("Stats derivate: alcune colonne in-game possono divergere.")
        missing_sources.append("imported_total_stats")
    if relic_count > 0 and source != "raw":
        warnings.append("Relic presenti ma non ancora modellati nel totale optimizer.")
        missing_sources.append("relic_stats")
    if bonus_sources and set(bonus_sources).issubset({"great_hall", "area_bonus"}):
        warnings.append("Classic Arena e Faction Guardians non entrano ancora nel totale.")
        missing_sources.extend(["classic_arena", "faction_guardians"])
    if completeness == "partial":
        warnings.append("Set speciali o effetti accessori non quantificati completamente.")

    if source == "raw":
        signal_weights = {"speed": 1.0, "accuracy": 1.0, "survival": 1.0, "damage": 1.0}
        confidence = 1.0
    else:
        signal_weights = {"speed": 0.95, "accuracy": 0.72, "survival": 0.45, "damage": 0.45}
        confidence = 0.62
        if relic_count > 0:
            signal_weights["survival"] = 0.38
            signal_weights["damage"] = 0.40
            confidence -= 0.08
        if completeness == "partial":
            signal_weights["survival"] = min(signal_weights["survival"], 0.35)
            signal_weights["damage"] = min(signal_weights["damage"], 0.35)
            confidence -= 0.08
        if bonus_sources and set(bonus_sources).issubset({"great_hall", "area_bonus"}):
            signal_weights["survival"] = min(signal_weights["survival"], 0.30)
            signal_weights["damage"] = min(signal_weights["damage"], 0.32)
            confidence -= 0.08

    return {
        "source": source,
        "completeness": completeness,
        "confidence": round(max(confidence, 0.2), 2),
        "signal_weights": signal_weights,
        "warnings": warnings[:4],
        "missing_sources": sorted(set(filter(None, missing_sources))),
    }


def _apply_reliability_to_signals(
    stat_signals: Mapping[str, float],
    stat_reliability: Mapping[str, Any],
) -> Dict[str, float]:
    weights = stat_reliability.get("signal_weights") or {}
    return {
        "speed": round(_to_float(stat_signals.get("speed")) * _to_float(weights.get("speed", 1.0)), 3),
        "accuracy": round(_to_float(stat_signals.get("accuracy")) * _to_float(weights.get("accuracy", 1.0)), 3),
        "survival": round(_to_float(stat_signals.get("survival")) * _to_float(weights.get("survival", 1.0)), 3),
        "damage": round(_to_float(stat_signals.get("damage")) * _to_float(weights.get("damage", 1.0)), 3),
        "speed_raw": round(_to_float(stat_signals.get("speed_raw")), 2),
        "accuracy_raw": round(_to_float(stat_signals.get("accuracy_raw")), 2),
        "res_raw": round(_to_float(stat_signals.get("res_raw")), 2),
    }


def _compute_stat_signals(stats: Mapping[str, float], thresholds: Mapping[str, float]) -> Dict[str, float]:
    hp = _to_float(stats.get("hp"))
    atk = _to_float(stats.get("atk"))
    defense = _to_float(stats.get("def"))
    spd = _to_float(stats.get("spd"))
    acc = _to_float(stats.get("acc"))
    res = _to_float(stats.get("res"))
    crit_rate = _to_float(stats.get("crit_rate"))
    crit_dmg = _to_float(stats.get("crit_dmg"))

    required_speed = max(_to_float(thresholds.get("required_speed")), 1.0)
    required_accuracy = max(_to_float(thresholds.get("required_accuracy")), 1.0)

    speed_signal = _clamp(spd / required_speed, 0.0, 1.25)
    accuracy_signal = _clamp(acc / required_accuracy, 0.0, 1.25)
    survival_signal = _clamp((((hp / 70_000.0) + (defense / 4_500.0) + (res / 350.0)) / 3.0), 0.0, 1.25)
    offense_anchor = max(atk / 5_500.0, defense / 5_000.0, hp / 95_000.0)
    damage_signal = _clamp((((crit_rate / 100.0) + (crit_dmg / 260.0) + offense_anchor) / 3.0), 0.0, 1.25)

    return {
        "speed": round(speed_signal, 3),
        "accuracy": round(accuracy_signal, 3),
        "survival": round(survival_signal, 3),
        "damage": round(damage_signal, 3),
        "speed_raw": round(spd, 2),
        "accuracy_raw": round(acc, 2),
        "res_raw": round(res, 2),
    }


def _infer_default_build(roles: Sequence[str]) -> str:
    role_set = set(roles)
    if role_set & {"block_buffs", "provoke", "hexer", "decrease_speed"}:
        return "debuffer_acc_spd"
    if role_set & {"revive", "revive_on_death", "mischief_tank"}:
        return "support_tank"
    if "poisoner" in role_set:
        return "poisoner"
    if "burner" in role_set:
        return "hp_burner"
    if "ally_protect" in role_set or "survival" in role_set:
        return "ally_protector"
    if "cleanse" in role_set:
        return "cleanser"
    if "speed" in role_set:
        return "speed_tuned_support"
    if "damage" in role_set:
        return "clan_boss_dps"
    return "support_tank"


def optimizer_area_region_for_boss(boss_key: str) -> str:
    normalized = str(boss_key or "").strip().lower()
    if normalized == "hydra":
        return "hydra"
    if normalized == "iron_twins":
        return "iron_twins"
    return "clan_boss"


def resolve_optimizer_context(
    boss_key: str,
    level_key: str,
    affinity: str,
) -> tuple[BossFamily, OptimizerBossProfile, str, str, str, Dict[str, float]]:
    family = BOSS_FAMILIES.get(str(boss_key or "").strip().lower()) or BOSS_FAMILIES["demon_lord"]
    available_levels = {key for key, _label in family.levels}
    available_affinities = {key for key, _label in family.affinities}
    effective_level = str(level_key or "").strip().lower()
    effective_affinity = str(affinity or "").strip().lower()
    if effective_level not in available_levels:
        effective_level = family.default_level
    if effective_affinity not in available_affinities:
        effective_affinity = family.default_affinity

    if family.key == "demon_lord":
        encounter_key = DEMON_LORD_ENCOUNTER_KEYS.get(effective_level, "demon_lord_unm")
        profile = BOSS_PROFILES["demon_lord_unm"]
        thresholds = dict(LEVEL_THRESHOLDS.get(effective_level, LEVEL_THRESHOLDS["ultra_nightmare"]))
        return family, profile, effective_level, effective_affinity, encounter_key, thresholds

    if family.key == "hydra":
        encounter_key = f"hydra_{effective_level}"
        profile = BOSS_PROFILES["hydra"]
        thresholds = dict(HYDRA_LEVEL_THRESHOLDS.get(effective_level, HYDRA_LEVEL_THRESHOLDS["hard"]))
        return family, profile, effective_level, effective_affinity, encounter_key, thresholds

    if family.key == "iron_twins":
        encounter_key = f"iron_twins_{effective_level}"
        profile = BOSS_PROFILES["iron_twins"]
        thresholds = dict(IRON_TWINS_LEVEL_THRESHOLDS.get(effective_level, IRON_TWINS_LEVEL_THRESHOLDS["stage_15"]))
        return family, profile, effective_level, effective_affinity, encounter_key, thresholds

    encounter_key = family.key
    profile = BOSS_PROFILES["demon_lord_unm"]
    thresholds = dict(LEVEL_THRESHOLDS["ultra_nightmare"])
    return family, profile, effective_level, effective_affinity, encounter_key, thresholds


def display_level_label(family: BossFamily, level_key: str) -> str:
    for key, label in family.levels:
        if key == level_key:
            return label
    return level_key


def display_affinity_label(family: BossFamily, affinity_key: str) -> str:
    for key, label in family.affinities:
        if key == affinity_key:
            return label
    return affinity_key


def evaluate_affinity_matchup(champion_affinity: str, boss_affinity: str) -> str:
    champion = _normalize_token(champion_affinity)
    boss = _normalize_token(boss_affinity)
    if not champion or not boss or champion == "void" or boss == "void":
        return "neutral"
    beats = {"force": "magic", "magic": "spirit", "spirit": "force"}
    if beats.get(champion) == boss:
        return "strong"
    if beats.get(boss) == champion:
        return "weak"
    return "neutral"


def _resolve_hint_score(hint: ChampionHint | None, target_key: str) -> float:
    if hint is None:
        return 0.0
    score = float(hint.boss_scores.get(target_key) or 0.0)
    if score > 0.0:
        return score
    if target_key.startswith("demon_lord_"):
        return float(hint.boss_scores.get("demon_lord_unm") or 0.0)
    if target_key.startswith("hydra_"):
        return float(hint.boss_scores.get("hydra_hard") or hint.boss_scores.get("hydra") or 0.0)
    if target_key.startswith("iron_twins_"):
        return float(hint.boss_scores.get("iron_twins_stage_15") or hint.boss_scores.get("iron_twins") or 0.0)
    return 0.0


def _group_stats_by_champion(rows: Iterable[sqlite3.Row]) -> Dict[str, Dict[str, float]]:
    grouped: Dict[str, Dict[str, float]] = {}
    for row in rows:
        grouped.setdefault(str(row["champ_id"] or ""), {})[str(row["stat_name"] or "")] = _to_float(row["stat_value"])
    return grouped


def _group_roles_by_name(rows: Iterable[sqlite3.Row]) -> Dict[str, Set[str]]:
    grouped: Dict[str, Set[str]] = {}
    for row in rows:
        grouped.setdefault(str(row["champion_name"] or ""), set()).add(_normalize_token(row["role_tag"]))
    return grouped


def _group_stat_models_by_champion(rows: Iterable[sqlite3.Row]) -> Dict[str, Dict[str, Any]]:
    grouped: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        grouped[str(row["champ_id"] or "")] = {
            "source": str(row["source"] or ""),
            "completeness": str(row["completeness"] or ""),
        }
    return grouped


def _group_effect_texts_by_name(skill_rows: Iterable[sqlite3.Row], effect_rows: Iterable[sqlite3.Row]) -> Dict[str, List[str]]:
    grouped: Dict[str, List[str]] = {}
    for row in skill_rows:
        champion_name = str(row["champion_name"] or "")
        fragments = grouped.setdefault(champion_name, [])
        fragments.extend(
            [
                str(row["slot"] or ""),
                str(row["skill_type"] or ""),
                str(row["description_clean"] or ""),
                str(row["description"] or ""),
            ]
        )
    for row in effect_rows:
        champion_name = str(row["champion_name"] or "")
        fragments = grouped.setdefault(champion_name, [])
        fragments.extend([str(row["effect_type"] or ""), str(row["target"] or ""), str(row["condition_text"] or "")])
    return grouped


def _group_skills_by_name(skill_rows: Iterable[sqlite3.Row], effect_rows: Iterable[sqlite3.Row]) -> Dict[str, List[Dict[str, Any]]]:
    grouped: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for row in skill_rows:
        champion_name = str(row["champion_name"] or "")
        slot = str(row["slot"] or "")
        champion_skills = grouped.setdefault(champion_name, {})
        champion_skills[slot] = {
            "slot": slot,
            "skill_order": int(row["skill_order"] or 0),
            "skill_id": str(row["skill_id"] or ""),
            "skill_name": str(row["skill_name"] or ""),
            "cooldown": row["cooldown"],
            "booked_cooldown": row["booked_cooldown"],
            "skill_type": str(row["skill_type"] or ""),
            "description": str(row["description"] or ""),
            "description_clean": str(row["description_clean"] or ""),
            "effects": [],
        }
    for row in effect_rows:
        champion_name = str(row["champion_name"] or "")
        slot = str(row["slot"] or "")
        champion_skills = grouped.setdefault(champion_name, {})
        skill = champion_skills.setdefault(
            slot,
            {
                "slot": slot,
                "skill_order": _slot_sort_key(slot),
                "skill_id": "",
                "skill_name": slot,
                "cooldown": None,
                "booked_cooldown": None,
                "skill_type": "",
                "description": "",
                "description_clean": "",
                "effects": [],
            },
        )
        skill["effects"].append(
            {
                "effect_order": int(row["effect_order"] or 0),
                "effect_type": str(row["effect_type"] or ""),
                "target": str(row["target"] or ""),
                "effect_value": _to_float(row["effect_value"]),
                "duration": int(row["duration"] or 0),
                "chance": _to_float(row["chance"] or 0.0),
                "condition_text": str(row["condition_text"] or ""),
            }
        )
    return {
        champion_name: sorted(
            (
                {
                    **skill,
                    "effects": sorted(
                        list(skill.get("effects") or []),
                        key=lambda item: (int(item.get("effect_order") or 0), str(item.get("effect_type") or "")),
                    ),
                }
                for skill in champion_skills.values()
            ),
            key=lambda item: (_slot_sort_key(str(item.get("slot") or "")), int(item.get("skill_order") or 0)),
        )
        for champion_name, champion_skills in grouped.items()
    }


def _normalize_effect_type(effect_type: Any) -> str:
    normalized = _normalize_token(effect_type)
    return EFFECT_TYPE_ALIASES.get(normalized, normalized)


def _effective_skill_cooldown(skill: Mapping[str, Any], booked: bool) -> int:
    if booked and skill.get("booked_cooldown") is not None:
        return max(0, int(skill.get("booked_cooldown") or 0))
    return max(0, int(skill.get("cooldown") or 0))


def _estimate_window_quality(
    effect_type: str,
    slot: str,
    cooldown: int,
    duration: int,
    chance: float,
) -> float:
    normalized_slot = str(slot or "").upper()
    if normalized_slot.startswith("P"):
        base = 0.95
    elif cooldown <= 0 or normalized_slot == "A1":
        base = 0.88
    elif cooldown <= 3:
        base = 0.82
    elif cooldown == 4:
        base = 0.68
    elif cooldown == 5:
        base = 0.54
    else:
        base = 0.4

    if duration >= 2 and effect_type not in {"cleanse", "cooldown_reset"}:
        base += 0.1
    elif duration == 1 and effect_type in {"decrease_attack", "block_debuffs", "increase_defense", "ally_protect", "counterattack", "unkillable"}:
        base -= 0.08

    normalized_chance = chance if chance > 0 else 100.0
    return _clamp(base * (normalized_chance / 100.0), 0.0, 1.15)


def _infer_skill_effects_from_text(skill: Mapping[str, Any]) -> List[Dict[str, Any]]:
    text = " ".join(
        [
            _normalize_token(skill.get("skill_name")),
            _normalize_token(skill.get("description_clean")),
            _normalize_token(skill.get("description")),
        ]
    )
    inferred: List[Dict[str, Any]] = []
    for keywords, effect_type in (
        (("decrease attack", "decrease atk"), "decrease_attack"),
        (("decrease def", "decrease defense"), "decrease_defense"),
        (("weaken",), "weaken"),
        (("poison",), "poison"),
        (("hp burn", "burn"), "hp_burn"),
        (("block debuffs",), "block_debuffs"),
        (("increase def", "increase defense"), "increase_defense"),
        (("ally protect",), "ally_protect"),
        (("counterattack", "counter attack"), "counterattack"),
        (("unkillable",), "unkillable"),
        (("shield",), "shield"),
        (("remove debuff", "remove all debuffs", "cleanse"), "cleanse"),
        (("decrease cooldown", "cooldown"), "cooldown_reset"),
        (("increase speed", "turn meter", "fill turn meter"), "speed_boost"),
    ):
        if any(keyword in text for keyword in keywords):
            inferred.append({"effect_type": effect_type})
    return inferred


def _summarize_skill_windows(skills: Sequence[Mapping[str, Any]], booked: bool) -> Dict[str, Dict[str, Any]]:
    windows: Dict[str, Dict[str, Any]] = {}
    for skill in skills:
        slot = str(skill.get("slot") or "")
        cooldown = _effective_skill_cooldown(skill, booked=booked)
        skill_name = str(skill.get("skill_name") or slot)
        raw_effects = list(skill.get("effects") or [])
        if not raw_effects:
            raw_effects = _infer_skill_effects_from_text(skill)
        for effect in raw_effects:
            effect_type = _normalize_effect_type(effect.get("effect_type"))
            if not effect_type:
                continue
            duration = max(0, int(effect.get("duration") or WINDOW_DEFAULT_DURATIONS.get(effect_type, 0)))
            chance = _to_float(effect.get("chance") or 0.0)
            quality = _estimate_window_quality(
                effect_type=effect_type,
                slot=slot,
                cooldown=cooldown,
                duration=duration,
                chance=chance,
            )
            current = windows.get(effect_type)
            candidate = {
                "slot": slot,
                "skill_name": skill_name,
                "cooldown": cooldown,
                "duration": duration,
                "chance": 100.0 if chance <= 0 else chance,
                "quality": round(quality, 3),
            }
            if current is None or float(candidate["quality"]) > float(current.get("quality") or 0.0):
                windows[effect_type] = candidate
    return windows


def _map_account_roles(account_roles: Iterable[str]) -> Set[str]:
    roles: Set[str] = set()
    for account_role in account_roles:
        normalized = _normalize_token(account_role)
        mapped = ACCOUNT_ROLE_MAP.get(normalized)
        if mapped:
            roles.update(mapped)
        elif normalized:
            roles.add(normalized)
    return roles


def _dedupe_roster_by_champion_name(rows: Iterable[sqlite3.Row]) -> List[sqlite3.Row]:
    best_by_name: Dict[str, sqlite3.Row] = {}
    for row in rows:
        champion_name = str(row["champion_name"] or "")
        current = best_by_name.get(champion_name)
        if current is None or _roster_sort_key(row) > _roster_sort_key(current):
            best_by_name[champion_name] = row
    return list(best_by_name.values())


def _roster_sort_key(row: sqlite3.Row) -> tuple[int, int, int, int, int]:
    return (
        int(row["rank"] or 0),
        int(row["level"] or 0),
        1 if bool(row["booked"]) else 0,
        int(row["awakening_level"] or 0),
        int(row["relic_count"] or 0),
    )


def _slot_sort_key(slot: str) -> int:
    normalized = str(slot or "").upper()
    if normalized.startswith("A"):
        suffix = normalized[1:]
        return int(suffix) if suffix.isdigit() else 50
    if normalized.startswith("P"):
        suffix = normalized[1:]
        return 100 + (int(suffix) if suffix.isdigit() else 0)
    return 999


def _normalize_token(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", " ").replace("_", " ")


def _to_float(value: Any) -> float:
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float, minimum: float, maximum: float) -> float:
    if value < minimum:
        return minimum
    if value > maximum:
        return maximum
    return value
