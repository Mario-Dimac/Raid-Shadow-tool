from __future__ import annotations

import argparse
import itertools
import json
import pickle
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from forge_db import DB_PATH, ensure_schema


MODEL_VERSION = "team_baseline_v1"
CORE_STATS = ("hp", "atk", "def", "spd", "acc", "res", "crit_rate", "crit_dmg")
DEFAULT_MODEL_DIR = Path("models")
ENCOUNTER_STAT_FLOORS: Dict[str, Dict[str, float]] = {
    "demon_lord_easy": {"required_speed": 140.0, "required_accuracy": 100.0, "survival_floor": 0.48},
    "demon_lord_normal": {"required_speed": 150.0, "required_accuracy": 140.0, "survival_floor": 0.54},
    "demon_lord_hard": {"required_speed": 160.0, "required_accuracy": 180.0, "survival_floor": 0.58},
    "demon_lord_brutal": {"required_speed": 170.0, "required_accuracy": 210.0, "survival_floor": 0.62},
    "demon_lord_nm": {"required_speed": 176.0, "required_accuracy": 230.0, "survival_floor": 0.66},
    "demon_lord_nightmare": {"required_speed": 176.0, "required_accuracy": 230.0, "survival_floor": 0.66},
    "demon_lord_unm": {"required_speed": 190.0, "required_accuracy": 250.0, "survival_floor": 0.70},
    "demon_lord_ultra_nightmare": {"required_speed": 190.0, "required_accuracy": 250.0, "survival_floor": 0.70},
}


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


def dict_value(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_value(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def parse_json_text(value: Any, default: Any) -> Any:
    text = string_value(value).strip()
    if not text:
        return default
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return default
    return parsed


def _normalize_token(value: Any) -> str:
    return string_value(value).strip().lower().replace("-", "_").replace(" ", "_")


def _resolve_stat_floors(encounter_key: str, difficulty: str) -> Dict[str, float]:
    normalized_encounter = string_value(encounter_key).strip().lower()
    normalized_difficulty = _normalize_token(difficulty)
    if normalized_encounter in ENCOUNTER_STAT_FLOORS:
        return dict(ENCOUNTER_STAT_FLOORS[normalized_encounter])
    if normalized_encounter.startswith("demon_lord_"):
        fallback = {
            "ultra_nightmare": "demon_lord_ultra_nightmare",
            "nightmare": "demon_lord_nightmare",
            "nm": "demon_lord_nm",
            "brutal": "demon_lord_brutal",
            "hard": "demon_lord_hard",
            "normal": "demon_lord_normal",
            "easy": "demon_lord_easy",
        }.get(normalized_difficulty)
        if fallback:
            return dict(ENCOUNTER_STAT_FLOORS.get(fallback, {}))
    return {}


def _survival_signal(stats: Dict[str, Any]) -> float:
    hp = float_value(stats.get("hp"))
    defense = float_value(stats.get("def"))
    resistance = float_value(stats.get("res"))
    return max(0.0, min((((hp / 70_000.0) + (defense / 4_500.0) + (resistance / 350.0)) / 3.0), 1.25))


def ai_dependency_status() -> Dict[str, Any]:
    runtime = {
        "python_executable": sys.executable,
        "python_version": sys.version.split()[0],
    }
    try:
        import numpy
        import pandas
        import sklearn
    except Exception as exc:
        return {
            "ok": False,
            "error": "Dipendenze AI mancanti nel Python del server. Installa requirements-ai.txt nello stesso ambiente con cui avvii cbforge_web.py.",
            "detail": str(exc),
            "runtime": runtime,
        }
    return {
        "ok": True,
        "error": "",
        "detail": "",
        "runtime": {
            **runtime,
            "numpy_version": getattr(numpy, "__version__", ""),
            "pandas_version": getattr(pandas, "__version__", ""),
            "sklearn_version": getattr(sklearn, "__version__", ""),
        },
    }


def import_sklearn_dependencies() -> Dict[str, Any]:
    status = ai_dependency_status()
    if not bool(status.get("ok")):
        raise RuntimeError(str(status.get("error") or "Dipendenze AI non disponibili."))

    from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
    from sklearn.feature_extraction import DictVectorizer
    from sklearn.metrics import accuracy_score, mean_absolute_error, r2_score
    from sklearn.model_selection import train_test_split

    return {
        "RandomForestClassifier": RandomForestClassifier,
        "RandomForestRegressor": RandomForestRegressor,
        "DictVectorizer": DictVectorizer,
        "accuracy_score": accuracy_score,
        "mean_absolute_error": mean_absolute_error,
        "r2_score": r2_score,
        "train_test_split": train_test_split,
    }


def load_training_rows(
    db_path: Path = DB_PATH,
    encounter_key: str = "",
    require_total_damage: bool = True,
) -> List[Dict[str, Any]]:
    ensure_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        run_query = """
            SELECT
                run_id,
                encounter_key,
                encounter_name,
                encounter_family,
                difficulty,
                boss_affinity,
                stage_id,
                elapsed_seconds,
                total_damage,
                success,
                leader_slot
            FROM run_history_runs
        """
        params: List[Any] = []
        filters: List[str] = []
        if encounter_key:
            filters.append("encounter_key = ?")
            params.append(encounter_key)
        if require_total_damage:
            filters.append("total_damage IS NOT NULL")
        if filters:
            run_query += " WHERE " + " AND ".join(filters)
        run_query += " ORDER BY run_id ASC"
        run_rows = conn.execute(run_query, params).fetchall()
        if not run_rows:
            return []

        member_rows = conn.execute(
            """
            SELECT
                run_id,
                member_order,
                champion_name,
                role_hint,
                level,
                rank,
                awakening_level,
                empowerment_level,
                booked,
                set_summary_json,
                tags_json
            FROM run_history_members
            ORDER BY run_id ASC, member_order ASC
            """
        ).fetchall()
        stat_rows = conn.execute(
            """
            SELECT run_id, member_order, stat_name, stat_value
            FROM run_history_member_stats
            WHERE stat_name IN ('hp', 'atk', 'def', 'spd', 'acc', 'res', 'crit_rate', 'crit_dmg')
            ORDER BY run_id ASC, member_order ASC, stat_name ASC
            """
        ).fetchall()

    members_by_run: Dict[int, List[Dict[str, Any]]] = {}
    for row in member_rows:
        run_id = int(row["run_id"])
        members_by_run.setdefault(run_id, []).append(
            {
                "member_order": int_value(row["member_order"]),
                "champion_name": string_value(row["champion_name"]).strip(),
                "role_hint": string_value(row["role_hint"]).strip(),
                "level": int_value(row["level"]),
                "rank": int_value(row["rank"]),
                "awakening_level": int_value(row["awakening_level"]),
                "empowerment_level": int_value(row["empowerment_level"]),
                "booked": bool(row["booked"]),
                "set_summary": list_value(parse_json_text(row["set_summary_json"], [])),
                "tags": list_value(parse_json_text(row["tags_json"], [])),
                "stats": {},
            }
        )

    member_index: Dict[Tuple[int, int], Dict[str, Any]] = {}
    for run_id, members in members_by_run.items():
        for member in members:
            member_index[(run_id, int(member["member_order"]))] = member

    for row in stat_rows:
        key = (int(row["run_id"]), int(row["member_order"]))
        member = member_index.get(key)
        if member is None:
            continue
        member["stats"][string_value(row["stat_name"]).strip()] = float_value(row["stat_value"])

    output: List[Dict[str, Any]] = []
    for row in run_rows:
        run_id = int(row["run_id"])
        output.append(
            {
                "run_id": run_id,
                "encounter_key": string_value(row["encounter_key"]).strip(),
                "encounter_name": string_value(row["encounter_name"]).strip(),
                "encounter_family": string_value(row["encounter_family"]).strip(),
                "difficulty": string_value(row["difficulty"]).strip(),
                "boss_affinity": string_value(row["boss_affinity"]).strip(),
                "stage_id": string_value(row["stage_id"]).strip(),
                "elapsed_seconds": float_value(row["elapsed_seconds"]),
                "total_damage": float_value(row["total_damage"]),
                "success": int_value(row["success"]),
                "leader_slot": int_value(row["leader_slot"]),
                "members": list(members_by_run.get(run_id, [])),
            }
        )
    return output


def summarize_team_features(run_row: Dict[str, Any]) -> Dict[str, float | int | str]:
    members = list_value(run_row.get("members"))
    stat_floors = _resolve_stat_floors(
        string_value(run_row.get("encounter_key")),
        string_value(run_row.get("difficulty")),
    )
    features: Dict[str, float | int | str] = {
        "encounter_key": string_value(run_row.get("encounter_key")),
        "difficulty": string_value(run_row.get("difficulty")),
        "boss_affinity": string_value(run_row.get("boss_affinity")),
        "team_size": len(members),
        "leader_slot": int_value(run_row.get("leader_slot")),
    }

    values_by_stat: Dict[str, List[float]] = {stat_name: [] for stat_name in CORE_STATS}
    role_counts: Dict[str, int] = {}
    set_counts: Dict[str, int] = {}
    champion_names: List[str] = []
    booked_count = 0
    total_rank = 0
    total_level = 0
    total_awakening = 0
    total_empowerment = 0
    sustain_members = 0
    healing_members = 0
    shield_members = 0
    cleanse_members = 0
    unkillable_members = 0
    attack_down_members = 0
    pressure_members = 0
    speed_floor_hits = 0
    accuracy_floor_hits = 0
    survival_floor_hits = 0
    speed_floor_gap_sum = 0.0
    accuracy_floor_gap_sum = 0.0

    for member in members:
        member_map = dict_value(member)
        champion_name = string_value(member_map.get("champion_name")).strip()
        if champion_name:
            champion_names.append(champion_name)
            features[f"champ:{champion_name}"] = 1
        if bool(member_map.get("booked")):
            booked_count += 1
        total_rank += int_value(member_map.get("rank"))
        total_level += int_value(member_map.get("level"))
        total_awakening += int_value(member_map.get("awakening_level"))
        total_empowerment += int_value(member_map.get("empowerment_level"))

        role_hint = string_value(member_map.get("role_hint")).strip()
        if role_hint:
            role_counts[role_hint] = role_counts.get(role_hint, 0) + 1
        member_tags = {
            _normalize_token(role_hint),
            *[_normalize_token(tag) for tag in list_value(member_map.get("tags"))],
        }
        member_tags.discard("")
        for tag in member_tags:
            normalized_tag = string_value(tag).strip()
            if normalized_tag:
                role_counts[normalized_tag] = role_counts.get(normalized_tag, 0) + 1
        for set_row in list_value(member_map.get("set_summary")):
            set_map = dict_value(set_row)
            set_name = string_value(set_map.get("display_name") or set_map.get("set_name")).strip()
            if set_name:
                set_counts[set_name] = set_counts.get(set_name, 0) + max(1, int_value(set_map.get("completed_sets")) or 1)

        stats = dict_value(member_map.get("stats"))
        if member_tags & {"sustain", "healing", "shield", "ally_protect"}:
            sustain_members += 1
        if member_tags & {"healing", "heal"}:
            healing_members += 1
        if "shield" in member_tags:
            shield_members += 1
        if member_tags & {"cleanse", "block_debuffs"}:
            cleanse_members += 1
        if "unkillable" in member_tags:
            unkillable_members += 1
        if "decrease_attack" in member_tags:
            attack_down_members += 1
        if member_tags & {"boss_pressure", "poison", "hp_burn", "burner", "poisoner", "damage"}:
            pressure_members += 1
        required_speed = float_value(stat_floors.get("required_speed"))
        required_accuracy = float_value(stat_floors.get("required_accuracy"))
        required_survival = float_value(stat_floors.get("survival_floor"))
        speed_value = float_value(stats.get("spd"))
        accuracy_value = float_value(stats.get("acc"))
        survival_value = _survival_signal(stats)
        if required_speed > 0:
            if speed_value >= required_speed:
                speed_floor_hits += 1
            speed_floor_gap_sum += max(0.0, required_speed - speed_value)
        if required_accuracy > 0:
            if accuracy_value >= required_accuracy:
                accuracy_floor_hits += 1
            accuracy_floor_gap_sum += max(0.0, required_accuracy - accuracy_value)
        if required_survival > 0 and survival_value >= required_survival:
            survival_floor_hits += 1
        for stat_name in CORE_STATS:
            value = float_value(stats.get(stat_name))
            if value > 0:
                values_by_stat[stat_name].append(value)

    team_size = max(1, len(members))
    features["booked_count"] = booked_count
    features["booked_ratio"] = round(booked_count / team_size, 4)
    features["avg_rank"] = round(total_rank / team_size, 3)
    features["avg_level"] = round(total_level / team_size, 3)
    features["avg_awakening"] = round(total_awakening / team_size, 3)
    features["avg_empowerment"] = round(total_empowerment / team_size, 3)
    features["team_signature"] = "|".join(sorted(champion_names))
    features["sustain_members"] = sustain_members
    features["healing_members"] = healing_members
    features["shield_members"] = shield_members
    features["cleanse_members"] = cleanse_members
    features["unkillable_members"] = unkillable_members
    features["attack_down_members"] = attack_down_members
    features["pressure_members"] = pressure_members
    features["speed_floor_hits"] = speed_floor_hits
    features["accuracy_floor_hits"] = accuracy_floor_hits
    features["survival_floor_hits"] = survival_floor_hits
    features["speed_floor_ratio"] = round(speed_floor_hits / team_size, 4)
    features["accuracy_floor_ratio"] = round(accuracy_floor_hits / team_size, 4)
    features["survival_floor_ratio"] = round(survival_floor_hits / team_size, 4)
    features["speed_floor_gap_sum"] = round(speed_floor_gap_sum, 3)
    features["accuracy_floor_gap_sum"] = round(accuracy_floor_gap_sum, 3)

    for stat_name, values in values_by_stat.items():
        if not values:
            features[f"{stat_name}_avg"] = 0.0
            features[f"{stat_name}_min"] = 0.0
            features[f"{stat_name}_max"] = 0.0
            features[f"{stat_name}_sum"] = 0.0
            continue
        features[f"{stat_name}_avg"] = round(sum(values) / len(values), 3)
        features[f"{stat_name}_min"] = round(min(values), 3)
        features[f"{stat_name}_max"] = round(max(values), 3)
        features[f"{stat_name}_sum"] = round(sum(values), 3)

    for role_name, count in sorted(role_counts.items()):
        features[f"role:{role_name}"] = count
    for set_name, count in sorted(set_counts.items()):
        features[f"set:{set_name}"] = count

    return features


def build_supervised_rows(
    db_path: Path = DB_PATH,
    encounter_key: str = "",
) -> List[Dict[str, Any]]:
    rows = load_training_rows(db_path=db_path, encounter_key=encounter_key, require_total_damage=True)
    output: List[Dict[str, Any]] = []
    for row in rows:
        members = list_value(row.get("members"))
        if not members:
            continue
        features = summarize_team_features(row)
        output.append(
            {
                "run_id": int_value(row.get("run_id")),
                "features": features,
                "target_total_damage": float_value(row.get("total_damage")),
                "target_success": int_value(row.get("success")),
                "elapsed_seconds": float_value(row.get("elapsed_seconds")),
                "team_signature": string_value(features.get("team_signature")),
            }
        )
    return output


def _split_feature_target_rows(rows: Iterable[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[float], List[int]]:
    feature_rows: List[Dict[str, Any]] = []
    damage_targets: List[float] = []
    success_targets: List[int] = []
    for row in rows:
        feature_rows.append(dict(dict_value(row.get("features"))))
        damage_targets.append(float_value(row.get("target_total_damage")))
        success_targets.append(int_value(row.get("target_success")))
    return feature_rows, damage_targets, success_targets


def vectorizer_feature_names(vectorizer: Any) -> List[str]:
    if hasattr(vectorizer, "get_feature_names_out"):
        return [string_value(item) for item in vectorizer.get_feature_names_out()]
    return [string_value(item) for item in getattr(vectorizer, "feature_names_", [])]


def default_model_path(encounter_key: str) -> Path:
    normalized = string_value(encounter_key).strip() or "all_encounters"
    return DEFAULT_MODEL_DIR / f"{normalized}_{MODEL_VERSION}.joblib"


def load_model_bundle(model_path: Path) -> Dict[str, Any]:
    with model_path.open("rb") as handle:
        return dict_value(pickle.load(handle))


def score_feature_dicts(model_bundle: Dict[str, Any], feature_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not feature_rows:
        return []
    vectorizer = model_bundle["vectorizer"]
    regressor = model_bundle["damage_regressor"]
    classifier = model_bundle.get("success_classifier")
    matrix = vectorizer.transform(feature_rows)
    damage_predictions = list(regressor.predict(matrix))

    success_probabilities: List[float | None] = [None] * len(feature_rows)
    if classifier is not None and hasattr(classifier, "predict_proba"):
        probabilities = classifier.predict_proba(matrix)
        class_labels = list(getattr(classifier, "classes_", []))
        success_index = class_labels.index(1) if 1 in class_labels else (len(class_labels) - 1 if class_labels else 0)
        success_probabilities = [float(row[success_index]) for row in probabilities]

    return [
        {
            "predicted_total_damage": round(float(damage_predictions[index]), 3),
            "predicted_success_probability": (
                round(float(success_probabilities[index]), 4)
                if success_probabilities[index] is not None
                else None
            ),
        }
        for index in range(len(feature_rows))
    ]


def candidate_to_member_feature_row(candidate: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "champion_name": string_value(candidate.get("champion_name")).strip(),
        "role_hint": (
            string_value(list_value(candidate.get("roles"))[0]).strip()
            if list_value(candidate.get("roles"))
            else ""
        ),
        "level": int_value(candidate.get("level")),
        "rank": int_value(candidate.get("rank")),
        "awakening_level": int_value(candidate.get("awakening_level")),
        "empowerment_level": int_value(candidate.get("empowerment_level")),
        "booked": bool(candidate.get("booked")),
        "set_summary": list_value(candidate.get("set_summary")),
        "tags": sorted(
            {
                string_value(item).strip()
                for item in [*list_value(candidate.get("roles")), *list_value(candidate.get("capability_tags"))]
                if string_value(item).strip()
            }
        ),
        "stats": dict(dict_value(candidate.get("stats"))),
    }


def build_feature_row_for_candidate_team(
    team: List[Dict[str, Any]],
    encounter_key: str,
    difficulty: str,
    boss_affinity: str,
    leader_slot: int = 1,
) -> Dict[str, Any]:
    pseudo_run = {
        "encounter_key": encounter_key,
        "difficulty": difficulty,
        "boss_affinity": boss_affinity,
        "leader_slot": leader_slot,
        "members": [candidate_to_member_feature_row(candidate) for candidate in team],
    }
    return summarize_team_features(pseudo_run)


def _team_satisfies_hard_rules(team: List[Dict[str, Any]], hard_rules: Dict[str, Any]) -> bool:
    if not hard_rules:
        return True
    team_names = {string_value(candidate.get("champion_name")).strip() for candidate in team}
    union_tags = {
        _normalize_token(tag)
        for candidate in team
        for tag in [*list_value(candidate.get("roles")), *list_value(candidate.get("capability_tags"))]
        if _normalize_token(tag)
    }
    required_names = {
        string_value(name).strip()
        for name in list_value(hard_rules.get("required_champion_names"))
        if string_value(name).strip()
    }
    if required_names and not required_names.issubset(team_names):
        return False
    required_tags = {
        _normalize_token(tag)
        for tag in list_value(hard_rules.get("required_tags"))
        if _normalize_token(tag)
    }
    if required_tags and not required_tags.issubset(union_tags):
        return False

    minimum_speed = float_value(hard_rules.get("minimum_speed"))
    minimum_accuracy = float_value(hard_rules.get("minimum_accuracy"))
    minimum_speed_hits = int_value(hard_rules.get("minimum_speed_hits"))
    minimum_accuracy_hits = int_value(hard_rules.get("minimum_accuracy_hits"))

    speed_hits = 0
    accuracy_hits = 0
    for candidate in team:
        stats = dict_value(candidate.get("stats"))
        if minimum_speed > 0 and float_value(stats.get("spd")) >= minimum_speed:
            speed_hits += 1
        if minimum_accuracy > 0 and float_value(stats.get("acc")) >= minimum_accuracy:
            accuracy_hits += 1
    if minimum_speed_hits > 0 and speed_hits < minimum_speed_hits:
        return False
    if minimum_accuracy_hits > 0 and accuracy_hits < minimum_accuracy_hits:
        return False
    return True


def recommend_best_team_from_candidates(
    candidates: List[Dict[str, Any]],
    encounter_key: str,
    difficulty: str,
    boss_affinity: str,
    model_path: Path,
    team_size: int = 5,
    pool_size: int = 10,
    hard_rules: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    if not model_path.exists():
        raise FileNotFoundError(f"Modello baseline non trovato: {model_path}")
    if len(candidates) < team_size:
        raise ValueError("Candidati insufficienti per costruire un team AI.")

    model_bundle = load_model_bundle(model_path)
    ordered_candidates = sorted(
        list(candidates),
        key=lambda item: (-float(item.get("score") or 0.0), string_value(item.get("champion_name")).lower()),
    )
    search_pool = ordered_candidates[: max(team_size, pool_size)]

    combinations = [
        combo
        for combo in itertools.combinations(search_pool, team_size)
        if _team_satisfies_hard_rules(list(combo), dict_value(hard_rules))
    ]
    if not combinations:
        raise ValueError("Nessuna combinazione AI soddisfa i vincoli richiesti.")
    feature_rows = [
        build_feature_row_for_candidate_team(
            list(team),
            encounter_key=encounter_key,
            difficulty=difficulty,
            boss_affinity=boss_affinity,
        )
        for team in combinations
    ]
    predictions = score_feature_dicts(model_bundle, feature_rows)

    ranked_rows: List[Dict[str, Any]] = []
    for team, prediction in zip(combinations, predictions):
        ranked_rows.append(
            {
                "team": [dict(candidate) for candidate in team],
                "predicted_total_damage": float_value(prediction.get("predicted_total_damage")),
                "predicted_success_probability": prediction.get("predicted_success_probability"),
                "optimizer_score_sum": round(sum(float_value(candidate.get("score")) for candidate in team), 3),
                "team_signature": "|".join(sorted(string_value(candidate.get("champion_name")) for candidate in team)),
            }
        )

    ranked_rows.sort(
        key=lambda row: (
            (-1.0 if row.get("predicted_success_probability") is None else float_value(row.get("predicted_success_probability"))),
            float_value(row.get("predicted_total_damage")),
            float_value(row.get("optimizer_score_sum")),
        ),
        reverse=True,
    )
    best = ranked_rows[0]
    return {
        "model_version": string_value(model_bundle.get("model_version")) or MODEL_VERSION,
        "model_path": str(model_path),
        "pool_size": len(search_pool),
        "evaluated_combinations": len(ranked_rows),
        "hard_rules": dict(dict_value(hard_rules)),
        "best_team": list(best.get("team") or []),
        "predicted_total_damage": round(float_value(best.get("predicted_total_damage")), 3),
        "predicted_success_probability": (
            round(float_value(best.get("predicted_success_probability")), 4)
            if best.get("predicted_success_probability") is not None
            else None
        ),
        "top_teams": [
            {
                "team_signature": string_value(row.get("team_signature")),
                "predicted_total_damage": round(float_value(row.get("predicted_total_damage")), 3),
                "predicted_success_probability": (
                    round(float_value(row.get("predicted_success_probability")), 4)
                    if row.get("predicted_success_probability") is not None
                    else None
                ),
            }
            for row in ranked_rows[:3]
        ],
    }


def train_team_baseline(
    rows: List[Dict[str, Any]],
    output_path: Path,
    random_state: int = 42,
) -> Dict[str, Any]:
    if len(rows) < 3:
        raise ValueError("Servono almeno 3 run con total_damage per allenare il baseline.")

    deps = import_sklearn_dependencies()
    DictVectorizer = deps["DictVectorizer"]
    RandomForestRegressor = deps["RandomForestRegressor"]
    RandomForestClassifier = deps["RandomForestClassifier"]
    mean_absolute_error = deps["mean_absolute_error"]
    r2_score = deps["r2_score"]
    accuracy_score = deps["accuracy_score"]
    train_test_split = deps["train_test_split"]

    feature_rows, damage_targets, success_targets = _split_feature_target_rows(rows)
    vectorizer = DictVectorizer(sparse=False)
    matrix = vectorizer.fit_transform(feature_rows)

    regressor = RandomForestRegressor(
        n_estimators=300,
        random_state=random_state,
        min_samples_leaf=1,
    )
    classifier = RandomForestClassifier(
        n_estimators=300,
        random_state=random_state,
        min_samples_leaf=1,
    )

    metrics: Dict[str, Any] = {"rows": len(rows)}

    if len(rows) >= 6:
        x_train, x_test, y_train, y_test = train_test_split(
            matrix,
            damage_targets,
            test_size=0.33,
            random_state=random_state,
        )
        regressor.fit(x_train, y_train)
        predictions = regressor.predict(x_test)
        metrics["damage_mae_holdout"] = round(mean_absolute_error(y_test, predictions), 3)
        metrics["damage_r2_holdout"] = round(r2_score(y_test, predictions), 4)
    else:
        regressor.fit(matrix, damage_targets)
        predictions = regressor.predict(matrix)
        metrics["damage_mae_train"] = round(mean_absolute_error(damage_targets, predictions), 3)
        metrics["damage_r2_train"] = round(r2_score(damage_targets, predictions), 4)

    success_class_count = len(set(success_targets))
    if success_class_count >= 2:
        if len(rows) >= 8:
            x_train, x_test, y_train, y_test = train_test_split(
                matrix,
                success_targets,
                test_size=0.33,
                random_state=random_state,
                stratify=success_targets,
            )
            classifier.fit(x_train, y_train)
            class_predictions = classifier.predict(x_test)
            metrics["success_accuracy_holdout"] = round(accuracy_score(y_test, class_predictions), 4)
        else:
            classifier.fit(matrix, success_targets)
            class_predictions = classifier.predict(matrix)
            metrics["success_accuracy_train"] = round(accuracy_score(success_targets, class_predictions), 4)
    else:
        classifier = None
        metrics["success_model"] = "skipped_single_class"

    feature_importances: List[Dict[str, Any]] = []
    for feature_name, importance in sorted(
        zip(vectorizer_feature_names(vectorizer), regressor.feature_importances_),
        key=lambda item: item[1],
        reverse=True,
    )[:20]:
        feature_importances.append({"feature": feature_name, "importance": round(float(importance), 6)})

    bundle = {
        "model_version": MODEL_VERSION,
        "vectorizer": vectorizer,
        "damage_regressor": regressor,
        "success_classifier": classifier,
        "metrics": metrics,
        "feature_importances": feature_importances,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("wb") as handle:
        pickle.dump(bundle, handle)

    return {
        "ok": True,
        "output_path": str(output_path),
        "rows": len(rows),
        "metrics": metrics,
        "feature_importances": feature_importances,
    }


def train_from_database(
    db_path: Path = DB_PATH,
    encounter_key: str = "",
    output_path: Path | None = None,
) -> Dict[str, Any]:
    rows = build_supervised_rows(db_path=db_path, encounter_key=encounter_key)
    if not rows:
        raise ValueError("Nessuna run utile trovata nel DB per il training baseline.")
    resolved_output = output_path or default_model_path(encounter_key)
    return train_team_baseline(rows, resolved_output)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Allena il primo baseline AI per la valutazione team.")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--encounter", default="demon_lord_ultra_nightmare")
    parser.add_argument("--output", type=Path, default=Path("models") / "demon_lord_unm_baseline.joblib")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = train_from_database(
        db_path=args.db_path,
        encounter_key=str(args.encounter or "").strip(),
        output_path=args.output,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
