from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from cb_rules import BOSS_PROFILES, BUILD_PROFILES, CHAMPION_HINTS, BossProfile


BASE_DIR = Path(__file__).resolve().parent
NORMALIZED_PATH = BASE_DIR / "input" / "normalized_account.json"
ACCESSORY_SLOTS = {"ring", "amulet", "banner"}
SLOT_ORDER = {
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

STAT_SCORE_DIVISORS = {
    "hp": 100.0,
    "hp_pct": 1.0,
    "atk": 10.0,
    "atk_pct": 1.0,
    "def": 10.0,
    "def_pct": 1.0,
    "spd": 1.0,
    "crit_rate": 1.0,
    "crit_dmg": 1.0,
    "acc": 1.0,
    "res": 1.0,
}

ROLE_FALLBACK_SCORES: Dict[str, Dict[str, float]] = {
    "demon_lord_unm": {
        "support": 10.0,
        "defense": 8.0,
        "health": 8.0,
        "attack": 6.0,
    },
    "hydra_normal": {
        "support": 12.0,
        "defense": 8.0,
        "health": 8.0,
        "attack": 6.0,
    },
    "dragon_hard": {
        "attack": 10.0,
        "support": 8.0,
        "defense": 6.0,
    },
    "fire_knight_hard": {
        "attack": 8.0,
        "support": 8.0,
        "defense": 5.0,
    },
    "spider_hard": {
        "attack": 8.0,
        "support": 8.0,
        "health": 6.0,
    },
    "ice_golem_hard": {
        "defense": 9.0,
        "support": 8.0,
        "attack": 6.0,
        "health": 6.0,
    },
}


@dataclass
class TeamMemberPlan:
    champ_id: str
    name: str
    build_key: str
    reason: str
    score: float
    current_gear_count: int
    faction: str = ""
    gear_plan: List[Dict[str, Any]] = field(default_factory=list)


@dataclass
class TeamRecommendation:
    boss_key: str
    boss_label: str
    team_name: str
    score: float
    summary: str
    warnings: List[str]
    members: List[TeamMemberPlan]


def load_account(path: Path = NORMALIZED_PATH) -> Dict[str, Any]:
    account = json.loads(path.read_text(encoding="utf-8-sig"))
    reconcile_loaded_account_ownership(account)
    return account


def available_bosses() -> List[Dict[str, str]]:
    return [
        {"key": profile.key, "label": profile.label, "focus": profile.focus}
        for profile in BOSS_PROFILES.values()
    ]


def recommend_for_boss(boss_key: str, account: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    account_data = account or load_account()
    if boss_key not in BOSS_PROFILES:
        raise KeyError(f"Unsupported boss: {boss_key}")

    options = build_recommendations(account_data, boss_key)
    return {
        "boss": asdict(BOSS_PROFILES[boss_key]),
        "options": [serialize_team(option) for option in options],
    }


def build_recommendations(account: Dict[str, Any], boss_key: str) -> List[TeamRecommendation]:
    all_champions = list_value(account.get("champions"))
    champions = [champ for champ in all_champions if is_usable_champion(champ)]
    gear = list_value(account.get("gear"))
    owner_names = {
        string_value(champion.get("champ_id")): string_value(champion.get("name"))
        for champion in all_champions
    }
    owner_factions = {
        string_value(champion.get("champ_id")): string_value(champion.get("faction"))
        for champion in all_champions
    }
    if not champions:
        return []

    options: List[TeamRecommendation] = []
    if boss_key == "demon_lord_unm":
        options.extend(build_demon_lord_options(champions, gear, boss_key, owner_names, owner_factions))

    generic_option = build_generic_option(champions, gear, boss_key, owner_names, owner_factions)
    if generic_option:
        options.append(generic_option)

    unique: Dict[Tuple[str, ...], TeamRecommendation] = {}
    for option in options:
        key = tuple(sorted(member.champ_id for member in option.members))
        if key not in unique:
            unique[key] = option

    return sorted(unique.values(), key=lambda option: option.score, reverse=True)


def build_demon_lord_options(
    champions: List[Dict[str, Any]],
    gear: List[Dict[str, Any]],
    boss_key: str,
    owner_names: Dict[str, str],
    owner_factions: Dict[str, str],
) -> List[TeamRecommendation]:
    options: List[TeamRecommendation] = []
    specialists = collect_boss_specialists(champions, boss_key, minimum_hint_score=80.0)

    maneater = pick_best_named(champions, "Maneater")
    pain_keeper = pick_best_named(champions, "Pain Keeper")
    ninja = pick_best_named(champions, "Ninja")
    geomancer = pick_best_named(champions, "Geomancer")
    frozen_banshee = pick_best_named(champions, "Frozen Banshee")
    doompriest = pick_best_named(champions, "Doompriest")
    martyr = pick_best_named(champions, "Martyr")
    stag_knight = pick_best_named(champions, "Stag Knight")
    brogni = pick_best_named(champions, "Underpriest Brogni")
    deacon = pick_best_named(champions, "Deacon Armstrong")
    heiress = pick_best_named(champions, "Heiress")
    rhazin = pick_best_named(champions, "Rhazin Scarhide")

    if maneater and pain_keeper:
        core = [
            make_member(maneater, boss_key, "speed_tuned_support", "Unkillable core e buff denial."),
            make_member(pain_keeper, boss_key, "cooldown_support", "Riduce cooldown e chiude il loop del team."),
        ]
        if geomancer and frozen_banshee and deacon:
            pressure_variant_members = core + [
                make_member(geomancer, boss_key, "hp_burner", "HP Burn e danno riflesso molto efficaci sul Clan Boss."),
                make_member(frozen_banshee, boss_key, "poisoner", "Poison Sensitivity e veleni per spingere il danno nel lungo periodo."),
                make_member(deacon, boss_key, "support_general", "Aggiunge Increase Speed, turn meter e Decrease DEF per aumentare l'uptime offensivo."),
            ]
            pressure_variant = TeamRecommendation(
                boss_key=boss_key,
                boss_label=BOSS_PROFILES[boss_key].label,
                team_name="Poison Unkillable Pressure",
                score=team_score(pressure_variant_members, bonus=38.0),
                summary="Shell unkillable piu aggressiva orientata all'uptime: HP Burn, Poison Sensitivity, veleni e Decrease DEF per spremere piu danno continuativo.",
                warnings=[
                    "Va comunque validato il tune reale per garantire che la shell resti chiusa.",
                    "Se il danno reale cala su una certa affinity, confrontala con la variante che usa Ninja al posto di Deacon.",
                ],
                members=pressure_variant_members,
            )
            assign_gear(pressure_variant, gear, owner_names, owner_factions)
            options.append(pressure_variant)

        if geomancer and frozen_banshee:
            for decrease_attack_anchor in [candidate for candidate in [stag_knight, martyr] if candidate]:
                stable_variant_members = core + [
                    make_member(geomancer, boss_key, "hp_burner", "HP Burn e weaken mantengono pressione lunga sul boss."),
                    make_member(frozen_banshee, boss_key, "poisoner", "Veleni continui per trasformare la sopravvivenza in danno reale."),
                    make_member(
                        decrease_attack_anchor,
                        boss_key,
                        "decrease_attack_support",
                        "Porta Decrease ATK in modo piu affidabile per ridurre il rischio di collasso della run lunga.",
                    ),
                ]
                stable_variant = TeamRecommendation(
                    boss_key=boss_key,
                    boss_label=BOSS_PROFILES[boss_key].label,
                    team_name=f"Stabilized Unkillable Guard ({string_value(decrease_attack_anchor.get('name'))})",
                    score=team_score(stable_variant_members, bonus=36.0),
                    summary="Variante unkillable meno greed: sacrifica un po' di ceiling per aumentare la copertura di Decrease ATK e la stabilita sulle run lunghe.",
                    warnings=[
                        "Valida comunque speed tune e stun target prima di consolidarla come team definitivo.",
                        "Se la copertura Attack Down resta bassa, controlla subito accuracy reale e ordine skill del debuffer.",
                    ],
                    members=stable_variant_members,
                )
                assign_gear(stable_variant, gear, owner_names, owner_factions)
                options.append(stable_variant)

        if geomancer and ninja and frozen_banshee:
            poison_variant_members = core + [
                make_member(geomancer, boss_key, "hp_burner", "HP Burn primario e danno riflesso fortissimo sul Clan Boss."),
                make_member(ninja, boss_key, "clan_boss_dps", "Burst damage alto sul target singolo."),
                make_member(frozen_banshee, boss_key, "poisoner", "Aggiunge il pacchetto veleno che alza molto il ceiling del team."),
            ]
            poison_variant = TeamRecommendation(
                boss_key=boss_key,
                boss_label=BOSS_PROFILES[boss_key].label,
                team_name="Poison Unkillable Burst",
                score=team_score(poison_variant_members, bonus=34.0),
                summary="Versione piu offensiva della shell unkillable: punta su HP Burn + Poison Sensitivity + veleni per alzare il danno lungo la run.",
                warnings=[
                    "Va validato l'ordine skill reale per non rompere la shell.",
                    "Controlla accuracy, speed tune e stun target prima di adottarla come team definitivo.",
                ],
                members=poison_variant_members,
            )
            assign_gear(poison_variant, gear, owner_names, owner_factions)
            options.append(poison_variant)

        damage_pool = merge_named_candidates(
            [ninja, geomancer, frozen_banshee, rhazin, doompriest, heiress, deacon, stag_knight, martyr],
            specialists,
            exclude_names={"Maneater", "Pain Keeper"},
        )
        picked_damage = pick_top_candidates(damage_pool, boss_key, count=3, exclude_ids={member.champ_id for member in core})
        members = core + picked_damage
        if len(members) == 5:
            option = TeamRecommendation(
                boss_key=boss_key,
                boss_label=BOSS_PROFILES[boss_key].label,
                team_name="Budget Unkillable Shell",
                score=team_score(members, bonus=26.0),
                summary="La shell migliore rilevata nel tuo roster parte da Maneater + Pain Keeper e punta al massimo danno teorico.",
                warnings=[
                    "Serve validazione reale di speed tune, stun target e ordine skill prima di considerarla definitiva.",
                    "I suggerimenti gear sono euristici: utili per la build iniziale, non ancora un simulatore turn-by-turn.",
                ],
                members=members,
            )
            assign_gear(option, gear, owner_names, owner_factions)
            options.append(option)

    killable_pool = merge_named_candidates(
        [martyr, stag_knight, geomancer, frozen_banshee, doompriest, brogni, rhazin, deacon, heiress],
        specialists,
        exclude_names={"Maneater", "Pain Keeper"},
    )
    killable_members = pick_top_candidates(killable_pool, boss_key, count=5)
    if len(killable_members) == 5:
        option = TeamRecommendation(
            boss_key=boss_key,
            boss_label=BOSS_PROFILES[boss_key].label,
            team_name="Reliable Killable Core",
            score=team_score(killable_members, bonus=16.0),
            summary="Team piu conservativo, piu facile da mettere in campo e ottimo per iniziare a chiudere run stabili.",
            warnings=[
                "Ceiling inferiore rispetto alla shell unkillable, ma molto meno fragile da validare.",
            ],
            members=killable_members,
        )
        assign_gear(option, gear, owner_names, owner_factions)
        options.append(option)

    return options


def collect_boss_specialists(
    champions: Sequence[Dict[str, Any]],
    boss_key: str,
    minimum_hint_score: float = 0.0,
) -> List[Dict[str, Any]]:
    ranked: List[Dict[str, Any]] = []
    seen_names: set[str] = set()
    for champion in champions:
        name = string_value(champion.get("name"))
        normalized = normalize_name(name)
        if not normalized or normalized in seen_names:
            continue
        hint = CHAMPION_HINTS.get(name)
        if not hint:
            continue
        if float(hint.boss_scores.get(boss_key, 0.0)) < minimum_hint_score:
            continue
        ranked.append(champion)
        seen_names.add(normalized)
    ranked.sort(key=lambda item: champion_score(item, boss_key), reverse=True)
    return ranked


def merge_named_candidates(
    seeded: Sequence[Optional[Dict[str, Any]]],
    extras: Sequence[Dict[str, Any]],
    exclude_names: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    merged: List[Dict[str, Any]] = []
    seen_names: set[str] = set()
    blocked = {normalize_name(name) for name in exclude_names or set()}
    for champion in list(seeded) + list(extras):
        if not champion:
            continue
        name = string_value(champion.get("name"))
        normalized = normalize_name(name)
        if not normalized or normalized in seen_names or normalized in blocked:
            continue
        seen_names.add(normalized)
        merged.append(champion)
    return merged


def build_generic_option(
    champions: List[Dict[str, Any]],
    gear: List[Dict[str, Any]],
    boss_key: str,
    owner_names: Dict[str, str],
    owner_factions: Dict[str, str],
) -> Optional[TeamRecommendation]:
    profile = BOSS_PROFILES[boss_key]
    selected: List[TeamMemberPlan] = []
    used_ids: set[str] = set()

    for role in profile.required_roles:
        champion = best_for_role(champions, boss_key, role, used_ids)
        if champion is None:
            continue
        selected.append(champion)
        used_ids.add(champion.champ_id)

    remaining = max(0, 5 - len(selected))
    fillers = pick_top_candidates(champions, boss_key, remaining, exclude_ids=used_ids)
    selected.extend(fillers)

    if len(selected) < 5:
        return None

    option = TeamRecommendation(
        boss_key=boss_key,
        boss_label=profile.label,
        team_name="Heuristic Boss Team",
        score=team_score(selected, bonus=8.0),
        summary=profile.focus,
        warnings=[
            "Questo e un MVP euristico: usa il tuo roster reale e i metadati noti, ma non simula ancora le skill turno per turno.",
        ],
        members=selected[:5],
    )
    assign_gear(option, gear, owner_names, owner_factions)
    return option


def best_for_role(
    champions: Sequence[Dict[str, Any]],
    boss_key: str,
    role: str,
    exclude_ids: set[str],
) -> Optional[TeamMemberPlan]:
    best_plan: Optional[TeamMemberPlan] = None
    best_score = float("-inf")
    for champion in champions:
        champ_id = string_value(champion.get("champ_id"))
        if champ_id in exclude_ids:
            continue
        role_score = role_match_score(champion, role, boss_key)
        if role_score <= 0:
            continue
        plan = make_member(champion, boss_key, choose_build_key(champion, boss_key), f"Copre il ruolo chiave: {role}.")
        score = plan.score + role_score
        if score > best_score:
            best_score = score
            best_plan = plan
    return best_plan


def pick_top_candidates(
    candidates: Sequence[Dict[str, Any]] | Sequence[TeamMemberPlan],
    boss_key: str,
    count: int,
    exclude_ids: Optional[set[str]] = None,
) -> List[TeamMemberPlan]:
    used_ids = exclude_ids or set()
    scored: List[TeamMemberPlan] = []
    seen_names: set[str] = set()
    for candidate in candidates:
        plan = candidate if isinstance(candidate, TeamMemberPlan) else make_member(
            candidate,
            boss_key,
            choose_build_key(candidate, boss_key),
            describe_candidate(candidate, boss_key),
        )
        if plan.champ_id in used_ids:
            continue
        normalized_name = normalize_name(plan.name)
        if normalized_name in seen_names:
            continue
        seen_names.add(normalized_name)
        scored.append(plan)

    scored.sort(key=lambda item: item.score, reverse=True)
    return scored[:count]


def make_member(champion: Dict[str, Any], boss_key: str, build_key: str, reason: str) -> TeamMemberPlan:
    return TeamMemberPlan(
        champ_id=string_value(champion.get("champ_id")),
        name=string_value(champion.get("name")),
        build_key=build_key,
        reason=reason,
        score=champion_score(champion, boss_key),
        current_gear_count=len(list_value(champion.get("equipped_item_ids"))),
        faction=string_value(champion.get("faction")),
    )


def champion_score(champion: Dict[str, Any], boss_key: str) -> float:
    score = 0.0
    level = int_value(champion.get("level"))
    rank = int_value(champion.get("rank"))
    awakening = int_value(champion.get("awakening_level"))
    empowerment = int_value(champion.get("empowerment_level"))
    score += level * 0.35
    score += rank * 8.0
    score += awakening * 2.0
    score += empowerment * 1.5
    score += min(len(list_value(champion.get("equipped_item_ids"))) * 1.2, 12.0)
    if bool_value(champion.get("locked"), False):
        score += 2.0
    if bool_value(champion.get("in_vault"), False):
        score -= 25.0

    hint = CHAMPION_HINTS.get(string_value(champion.get("name")))
    if hint:
        score += hint.boss_scores.get(boss_key, 0.0)

    for role_tag in list_value(champion.get("role_tags")):
        score += ROLE_FALLBACK_SCORES.get(boss_key, {}).get(string_value(role_tag), 0.0)
    return score


def choose_build_key(champion: Dict[str, Any], boss_key: str) -> str:
    hint = CHAMPION_HINTS.get(string_value(champion.get("name")))
    if hint:
        return hint.build_overrides.get(boss_key, hint.default_build)
    role_tags = {string_value(tag) for tag in list_value(champion.get("role_tags"))}
    if "support" in role_tags:
        return "support_general"
    if "health" in role_tags or "defense" in role_tags:
        return "ally_protector"
    return "clan_boss_dps" if boss_key == "demon_lord_unm" else "wave_nuker"


def describe_candidate(champion: Dict[str, Any], boss_key: str) -> str:
    hint = CHAMPION_HINTS.get(string_value(champion.get("name")))
    if hint and hint.notes:
        return hint.notes
    return f"Buon fit euristico per {BOSS_PROFILES[boss_key].label}."


def role_match_score(champion: Dict[str, Any], role: str, boss_key: str) -> float:
    name = string_value(champion.get("name"))
    hint = CHAMPION_HINTS.get(name)
    score = 0.0
    if hint and role in hint.roles:
        score += 26.0
    if hint:
        score += hint.boss_scores.get(boss_key, 0.0) * 0.1
    return score


def team_score(members: Sequence[TeamMemberPlan], bonus: float = 0.0) -> float:
    return round(sum(member.score for member in members) + bonus, 2)


def assign_gear(
    option: TeamRecommendation,
    gear: List[Dict[str, Any]],
    owner_names: Dict[str, str],
    owner_factions: Dict[str, str],
) -> None:
    gear_by_slot: Dict[str, List[Dict[str, Any]]] = {}
    for item in gear:
        gear_by_slot.setdefault(string_value(item.get("slot")), []).append(item)

    used_item_ids: set[str] = set()
    members = sorted(
        option.members,
        key=lambda member: BUILD_PROFILES[member.build_key].allocation_priority,
        reverse=True,
    )

    for member in members:
        build = BUILD_PROFILES[member.build_key]
        plan: List[Dict[str, Any]] = []
        for slot, items in gear_by_slot.items():
            best_item = None
            best_score = float("-inf")
            best_breakdown: Optional[Dict[str, float]] = None
            for item in items:
                item_id = string_value(item.get("item_id"))
                if item_id in used_item_ids:
                    continue
                if not is_item_compatible(item, member.faction, owner_factions):
                    continue
                score, breakdown = gear_item_score(item, build.stat_weights, build.preferred_sets, member.champ_id)
                if score > best_score:
                    best_score = score
                    best_item = item
                    best_breakdown = breakdown
            if best_item is None:
                continue
            used_item_ids.add(string_value(best_item.get("item_id")))
            previous_owner_id = string_value(best_item.get("equipped_by"))
            plan.append(
                {
                    "item_id": best_item.get("item_id"),
                    "slot": best_item.get("slot"),
                    "set_name": best_item.get("set_name"),
                    "rarity": best_item.get("rarity"),
                    "rank": best_item.get("rank"),
                    "level": best_item.get("level"),
                    "score": round(best_score, 2),
                    "equipped_by": previous_owner_id or None,
                    "equipped_by_name": owner_names.get(previous_owner_id, "") if previous_owner_id else "",
                    "needs_swap": previous_owner_id not in {"", member.champ_id},
                    "main_stat": best_item.get("main_stat"),
                    "substats": best_item.get("substats", []),
                    "required_faction": item_required_faction(best_item, owner_factions),
                    "why": explain_breakdown(best_breakdown or {}),
                }
            )
        member.gear_plan = sorted(plan, key=lambda item: SLOT_ORDER.get(string_value(item.get("slot")), 99))


def is_item_compatible(item: Dict[str, Any], target_faction: str, owner_factions: Dict[str, str]) -> bool:
    slot = string_value(item.get("slot"))
    if slot not in ACCESSORY_SLOTS:
        return True

    required_faction = item_required_faction(item, owner_factions)
    if not required_faction:
        return False
    return normalize_name(required_faction) == normalize_name(target_faction)


def item_required_faction(item: Dict[str, Any], owner_factions: Dict[str, str]) -> str:
    explicit = string_value(item.get("required_faction")).strip()
    if explicit:
        return explicit

    owner_id = string_value(item.get("equipped_by"))
    if owner_id:
        return string_value(owner_factions.get(owner_id)).strip()
    return ""


def gear_item_score(
    item: Dict[str, Any],
    stat_weights: Dict[str, float],
    preferred_sets: Sequence[str],
    target_champ_id: str,
) -> Tuple[float, Dict[str, float]]:
    score = 0.0
    damage = 0.0
    survival = 0.0
    utility = 0.0
    main_stat = mapping_value(item.get("main_stat"))
    if main_stat:
        stat_score = stat_value_score(main_stat, stat_weights) * 1.8
        score += stat_score
        damage += category_score(main_stat, stat_score, "damage")
        survival += category_score(main_stat, stat_score, "survival")
        utility += category_score(main_stat, stat_score, "utility")
    for substat in list_value(item.get("substats")):
        substat_map = mapping_value(substat)
        stat_score = stat_value_score(substat_map, stat_weights)
        score += stat_score
        damage += category_score(substat_map, stat_score, "damage")
        survival += category_score(substat_map, stat_score, "survival")
        utility += category_score(substat_map, stat_score, "utility")
    set_name = string_value(item.get("set_name"))
    if set_name in preferred_sets:
        score += 12.0
        utility += 12.0
    elif set_name:
        score += 2.0
        utility += 2.0
    if string_value(item.get("equipped_by")) == target_champ_id:
        score += 8.0
    elif not string_value(item.get("equipped_by")):
        score += 3.0
    else:
        score -= 3.5
    score += int_value(item.get("level")) * 0.15
    score += int_value(item.get("rank")) * 0.8
    return score, {
        "damage": round(damage, 2),
        "survival": round(survival, 2),
        "utility": round(utility, 2),
    }


def stat_value_score(stat: Dict[str, Any], stat_weights: Dict[str, float]) -> float:
    stat_type = string_value(stat.get("type"))
    weight = stat_weights.get(stat_type, 0.0)
    if weight <= 0:
        return 0.0
    raw_value = normalize_stat_amount(stat_type, float_value(stat.get("value")))
    normalized_value = raw_value / STAT_SCORE_DIVISORS.get(stat_type, 1.0)
    return normalized_value * weight


def normalize_stat_amount(stat_type: str, value: float) -> float:
    # Some extracted percentage-like stats and ACC/RES substats arrive as fractions: 0.06 => 6.
    if 0 < abs(value) <= 1.0 and stat_type in {"hp_pct", "atk_pct", "def_pct", "acc", "res"}:
        return value * 100.0
    return value


def category_score(stat: Dict[str, Any], stat_score: float, category: str) -> float:
    stat_type = string_value(stat.get("type"))
    damage_stats = {"atk", "atk_pct", "crit_rate", "crit_dmg"}
    survival_stats = {"hp", "hp_pct", "def", "def_pct", "res"}
    utility_stats = {"spd", "acc"}
    if category == "damage" and stat_type in damage_stats:
        return stat_score
    if category == "survival" and stat_type in survival_stats:
        return stat_score
    if category == "utility" and stat_type in utility_stats:
        return stat_score
    return 0.0


def explain_breakdown(breakdown: Dict[str, float]) -> str:
    ordered = sorted(breakdown.items(), key=lambda item: item[1], reverse=True)
    useful = [label for label, value in ordered if value > 0]
    if not useful:
        return "pezzo neutro"
    return " / ".join(useful[:2])


def pick_best_named(champions: Sequence[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    matches = [champion for champion in champions if string_value(champion.get("name")) == name]
    if not matches:
        return None
    return max(matches, key=lambda champion: champion_score(champion, "demon_lord_unm"))


def build_assisted_swap_plan(team: TeamRecommendation) -> Dict[str, Any]:
    member_name_by_id = {member.champ_id: member.name for member in team.members}
    member_blocks: List[Dict[str, Any]] = []
    steps: List[Dict[str, Any]] = []
    source_owner_names: set[str] = set()
    ready_count = 0
    free_equip_count = 0
    swap_count = 0
    step_number = 1

    for member in team.members:
        block_steps: List[Dict[str, Any]] = []
        member_ready_count = 0
        member_swap_count = 0
        member_free_equip_count = 0
        for item in member.gear_plan:
            previous_owner_id = string_value(item.get("equipped_by"))
            previous_owner_name = string_value(item.get("equipped_by_name")) or member_name_by_id.get(previous_owner_id, "")
            if previous_owner_id == member.champ_id:
                ready_count += 1
                member_ready_count += 1
                continue

            action = "swap" if bool(item.get("needs_swap")) else "equip_free"
            if action == "swap":
                swap_count += 1
                member_swap_count += 1
                if previous_owner_name:
                    source_owner_names.add(previous_owner_name)
            else:
                free_equip_count += 1
                member_free_equip_count += 1

            step = {
                "step": step_number,
                "action": action,
                "member_name": member.name,
                "build_label": BUILD_PROFILES[member.build_key].label,
                "slot": string_value(item.get("slot")),
                "item_id": string_value(item.get("item_id")),
                "set_name": string_value(item.get("set_name")),
                "rarity": string_value(item.get("rarity")),
                "rank": int_value(item.get("rank")),
                "level": int_value(item.get("level")),
                "source_name": previous_owner_name,
                "main_stat": mapping_value(item.get("main_stat")),
                "required_faction": string_value(item.get("required_faction")),
                "why": string_value(item.get("why")),
            }
            steps.append(step)
            block_steps.append(step)
            step_number += 1

        member_blocks.append(
            {
                "member_name": member.name,
                "build_label": BUILD_PROFILES[member.build_key].label,
                "ready_count": member_ready_count,
                "free_equip_count": member_free_equip_count,
                "swap_count": member_swap_count,
                "action_count": len(block_steps),
                "steps": block_steps,
            }
        )

    action_count = len(steps)
    notes: List[str] = []
    if action_count == 0:
        notes.append("Team gia pronto: i pezzi consigliati risultano gia indossati dai campioni target.")
    else:
        notes.append(
            f"{action_count} azioni manuali: {swap_count} swap da altri campioni e {free_equip_count} pezzi liberi da montare."
        )
        if source_owner_names:
            notes.append(f"Campioni toccati dagli swap: {', '.join(sorted(source_owner_names))}.")

    return {
        "total_items": sum(len(member.gear_plan) for member in team.members),
        "ready_count": ready_count,
        "action_count": action_count,
        "free_equip_count": free_equip_count,
        "swap_count": swap_count,
        "source_owners": sorted(source_owner_names),
        "notes": notes,
        "member_blocks": member_blocks,
        "steps": steps,
    }


def serialize_team(team: TeamRecommendation) -> Dict[str, Any]:
    swap_plan = build_assisted_swap_plan(team)
    return {
        "boss_key": team.boss_key,
        "boss_label": team.boss_label,
        "team_name": team.team_name,
        "score": team.score,
        "summary": team.summary,
        "warnings": team.warnings,
        "swap_count": swap_plan["swap_count"],
        "swap_plan": swap_plan,
        "members": [
            {
                "champ_id": member.champ_id,
                "name": member.name,
                "build_key": member.build_key,
                "build_label": BUILD_PROFILES[member.build_key].label,
                "build_notes": BUILD_PROFILES[member.build_key].notes,
                "target_stats": BUILD_PROFILES[member.build_key].target_stats,
                "reason": member.reason,
                "score": round(member.score, 2),
                "current_gear_count": member.current_gear_count,
                "gear_plan": member.gear_plan,
            }
            for member in team.members
        ],
    }


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


def is_usable_champion(champion: Dict[str, Any]) -> bool:
    return int_value(champion.get("rank")) >= 4 and int_value(champion.get("level")) >= 40


def normalize_name(value: str) -> str:
    return "".join(char for char in value.lower() if char.isalnum())


def list_value(value: Any) -> List[Any]:
    if isinstance(value, list):
        return value
    return []


def mapping_value(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {}


def string_value(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


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


def main() -> None:
    payload = recommend_for_boss("demon_lord_unm")
    print(json.dumps(payload, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
