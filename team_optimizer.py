from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence, Set

from forge_db import DB_PATH, ensure_schema


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
}

LEVEL_THRESHOLDS: Dict[str, Dict[str, float]] = {
    "easy": {"required_speed": 140.0, "required_accuracy": 100.0, "survival_floor": 0.48},
    "normal": {"required_speed": 150.0, "required_accuracy": 140.0, "survival_floor": 0.54},
    "hard": {"required_speed": 160.0, "required_accuracy": 180.0, "survival_floor": 0.58},
    "brutal": {"required_speed": 170.0, "required_accuracy": 210.0, "survival_floor": 0.62},
    "nightmare": {"required_speed": 176.0, "required_accuracy": 230.0, "survival_floor": 0.66},
    "ultra_nightmare": {"required_speed": 190.0, "required_accuracy": 250.0, "survival_floor": 0.70},
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
}

DEMON_LORD_ENCOUNTER_KEYS: Dict[str, str] = {
    "easy": "demon_lord_easy",
    "normal": "demon_lord_normal",
    "hard": "demon_lord_hard",
    "brutal": "demon_lord_brutal",
    "nightmare": "demon_lord_nm",
    "ultra_nightmare": "demon_lord_unm",
}


CHAMPION_HINTS: Dict[str, ChampionHint] = {
    "Maneater": ChampionHint(("speed", "survival", "unkillable", "support"), {"demon_lord_unm": 100.0}, "speed_tuned_support"),
    "Pain Keeper": ChampionHint(("speed", "support", "cooldown"), {"demon_lord_unm": 94.0}, "cooldown_support"),
    "Geomancer": ChampionHint(("damage", "burner", "debuffer"), {"demon_lord_unm": 96.0}, "hp_burner"),
    "Frozen Banshee": ChampionHint(("damage", "poisoner", "debuffer"), {"demon_lord_unm": 90.0}, "poisoner"),
    "Ninja": ChampionHint(("damage", "burner"), {"demon_lord_unm": 93.0}, "clan_boss_dps"),
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
    "Mithrala Lifebane": ChampionHint(("support", "cleanse", "survival"), {"demon_lord_unm": 80.0}, "support_general"),
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
    (("decrease attack", "decrease atk"), ("debuffer", "decrease_attack", "survival")),
    (("decrease def", "decrease defense", "weaken"), ("debuffer",)),
    (("ally protect",), ("ally_protect", "support", "survival")),
    (("shield",), ("support", "survival")),
    (("counterattack", "counter attack"), ("counterattack", "support", "damage")),
    (("unkillable", "block damage"), ("unkillable", "survival", "support")),
    (("remove debuff", "remove all debuffs", "removes all debuffs", "cleanse", "block debuffs"), ("cleanse", "support", "survival")),
    (("heal", "continuous heal"), ("support", "survival")),
    (("revive",), ("revive", "support")),
    (("turn meter", "fill turn meter", "increase speed", "increase turn meter"), ("speed", "support")),
    (("damage",), ("damage",)),
)


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
    db_path: Path = DB_PATH,
) -> Dict[str, Any]:
    family, profile, effective_level, effective_affinity, encounter_key, thresholds = resolve_optimizer_context(
        boss_key=boss_key,
        level_key=level_key,
        affinity=affinity,
    )

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
        role_rows = conn.execute("SELECT champion_name, role_tag FROM champion_roles").fetchall()
        skill_rows = conn.execute(
            """
            SELECT champion_name, slot, skill_type, description, description_clean
            FROM champion_skills
            """
        ).fetchall()
        effect_rows = conn.execute(
            """
            SELECT champion_name, effect_type, target, condition_text
            FROM champion_skill_effects
            """
        ).fetchall()
        evidence_rows = conn.execute(
            """
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
            WHERE rr.encounter_key = ?
            GROUP BY rm.champion_name
            """,
            (encounter_key,),
        ).fetchall()

    best_roster_rows = _dedupe_roster_by_champion_name(roster_rows)
    stats_by_champ_id = _group_stats_by_champion(stat_rows)
    stat_models_by_champ_id = _group_stat_models_by_champion(stat_model_rows)
    bonus_sources = sorted({str(row["source"] or "").strip() for row in bonus_source_rows if str(row["source"] or "").strip()})
    account_roles_by_name = _group_roles_by_name(role_rows)
    effect_texts_by_name = _group_effect_texts_by_name(skill_rows, effect_rows)
    evidence_by_name = {
        str(row["champion_name"] or ""): {
            "run_count": int(row["run_count"] or 0),
            "avg_damage_done": _to_float(row["avg_damage_done"]),
            "avg_damage_taken": _to_float(row["avg_damage_taken"]),
            "avg_healing_done": _to_float(row["avg_healing_done"]),
        }
        for row in evidence_rows
    }

    candidates = [
        _build_candidate(
            roster_row=row,
            stats=stats_by_champ_id.get(str(row["champ_id"] or ""), {}),
            stat_model=stat_models_by_champ_id.get(str(row["champ_id"] or ""), {}),
            account_roles=account_roles_by_name.get(str(row["champion_name"] or ""), set()),
            effect_texts=effect_texts_by_name.get(str(row["champion_name"] or ""), []),
            evidence=evidence_by_name.get(str(row["champion_name"] or ""), {}),
            target_key=encounter_key,
            boss_affinity=effective_affinity,
            thresholds=thresholds,
            bonus_sources=bonus_sources,
        )
        for row in best_roster_rows
    ]
    candidates.sort(key=lambda item: (-float(item["score"]), item["champion_name"].lower()))

    selected_team = _select_team(candidates, profile)
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
    warnings: List[str] = []
    if missing_required:
        warnings.append(f"Coverage incompleta: {', '.join(missing_required)}.")
    if "speed" not in team_roles:
        warnings.append("Il team non ha un motore speed esplicito.")
    if "cleanse" not in team_roles and "unkillable" not in team_roles:
        warnings.append("Manca una risposta chiara a stun/debuff, salvo tune specifici.")
    if sum(1 for member in selected_team if "damage" in list(member.get("roles") or [])) < 2:
        warnings.append("Il team ha pochi slot dichiaratamente offensivi.")
    if effective_affinity != "void":
        warnings.append(f"Affinita boss selezionata: {effective_affinity}. Controlla i campioni in weak affinity.")

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
            "thresholds": dict(thresholds),
        },
        "selected_team": selected_team,
        "bench": bench,
        "candidates": candidates,
        "coverage": coverage,
        "valuable_role_coverage": valuable_coverage,
        "missing_required_roles": missing_required,
        "warnings": warnings,
        "notes": [
            "Scheletro euristico: usa hint statici, role inference da skill/effect e stats correnti del roster.",
            "I punteggi non sono ancora un simulatore turn-order e non sostituiscono uno speed tune trusted.",
        ],
    }


def _select_team(candidates: Sequence[Dict[str, Any]], profile: OptimizerBossProfile) -> List[Dict[str, Any]]:
    selected: List[Dict[str, Any]] = []
    selected_names: Set[str] = set()
    covered_roles: Set[str] = set()

    for requirement in profile.required_role_groups:
        options = [
            candidate
            for candidate in candidates
            if candidate["champion_name"] not in selected_names
            and any(role in requirement.acceptable_roles for role in list(candidate.get("roles") or []))
        ]
        if not options:
            continue
        chosen = max(options, key=lambda item: (_selection_score(item, covered_roles, profile), item["score"]))
        selected.append(chosen)
        selected_names.add(str(chosen["champion_name"]))
        covered_roles.update(list(chosen.get("roles") or []))

    while len(selected) < profile.team_size:
        options = [candidate for candidate in candidates if candidate["champion_name"] not in selected_names]
        if not options:
            break
        chosen = max(options, key=lambda item: (_selection_score(item, covered_roles, profile), item["score"]))
        selected.append(chosen)
        selected_names.add(str(chosen["champion_name"]))
        covered_roles.update(list(chosen.get("roles") or []))

    return selected


def _selection_score(candidate: Mapping[str, Any], covered_roles: Set[str], profile: OptimizerBossProfile) -> float:
    candidate_roles = set(str(role) for role in list(candidate.get("roles") or []))
    new_valuable_roles = sum(1 for role in profile.valuable_roles if role in candidate_roles and role not in covered_roles)
    new_required_roles = 0
    for requirement in profile.required_role_groups:
        if any(role in requirement.acceptable_roles for role in candidate_roles) and not any(
            role in requirement.acceptable_roles for role in covered_roles
        ):
            new_required_roles += 1
    return float(candidate.get("score") or 0.0) + (new_required_roles * 8.0) + (new_valuable_roles * 2.0)


def _build_candidate(
    roster_row: sqlite3.Row,
    stats: Mapping[str, float],
    stat_model: Mapping[str, Any],
    account_roles: Set[str],
    effect_texts: Sequence[str],
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

    risks = _build_risk_flags(target_key, roles, weighted_stat_signals, affinity_state, thresholds)
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
    roles: Sequence[str],
    stat_signals: Mapping[str, float],
    affinity_state: str,
    thresholds: Mapping[str, float],
) -> List[str]:
    risks: List[str] = []
    required_speed = _to_float(thresholds.get("required_speed"))
    required_accuracy = _to_float(thresholds.get("required_accuracy"))
    survival_floor = _to_float(thresholds.get("survival_floor"))

    if target_key.startswith("demon_lord_"):
        if stat_signals.get("speed_raw", 0.0) < required_speed:
            risks.append(f"SPD ancora bassa per il livello scelto ({int(required_speed)}+ consigliata).")
        if any(role in {"debuffer", "poisoner", "burner", "decrease_attack"} for role in roles) and stat_signals.get("accuracy_raw", 0.0) < required_accuracy:
            risks.append(f"ACC probabilmente corta per tenere i debuff ({int(required_accuracy)}+ consigliata).")
        if any(role in {"survival", "ally_protect", "support", "cleanse"} for role in roles) and stat_signals.get("survival", 0.0) < survival_floor:
            risks.append("Tenuta ancora fragile per fight lunghi.")
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
    if role_set & {"debuffer", "poisoner", "burner", "decrease_attack"}:
        bonus += 9.0 * ((speed + accuracy) / 2.0)
    if role_set & {"support", "survival", "cleanse", "ally_protect", "unkillable"}:
        bonus += 10.0 * ((survival * 0.7) + (speed * 0.3))
    if role_set & {"damage", "poisoner", "burner", "counterattack"}:
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
    }


def _infer_default_build(roles: Sequence[str]) -> str:
    role_set = set(roles)
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
    return "support_general"


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
