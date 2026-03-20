from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlencode, urlparse

from forge_db import DB_PATH, ensure_schema, now_utc_iso, save_app_state


HH_SEARCH_URL = "https://hellhades.com/wp-json/wp/v2/search"
HH_SKILLS_URL_TEMPLATE = "https://hellhades.com/wp-json/hh-api/v3/raid/skills/{post_id}"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://hellhades.com/",
    "Origin": "https://hellhades.com",
}

LEVEL_LINE_RE = re.compile(r"^Level\s+\d+\s*:", re.IGNORECASE)
TAG_RE = re.compile(r"<[^>]+>")
BRACKET_EFFECT_RE = re.compile(r"\[([^\]]+)\]")
SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class HellHadesChampionMatch:
    post_id: int
    title: str
    url: str


def fetch_json(url: str) -> Any:
    request = urllib.request.Request(url, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def normalize_lookup_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def slug_from_url(value: str) -> str:
    path = urlparse(value).path.strip("/")
    if not path:
        return ""
    return path.split("/")[-1]


def resolve_champion_match(champion_name: str) -> Optional[HellHadesChampionMatch]:
    query = urlencode({"search": champion_name, "subtype": "champions", "per_page": "20"})
    payload = fetch_json(f"{HH_SEARCH_URL}?{query}")
    if not isinstance(payload, list):
        return None

    normalized_name = normalize_lookup_text(champion_name)
    best_candidate: Optional[Tuple[int, int, HellHadesChampionMatch]] = None

    for item in payload:
        if not isinstance(item, dict):
            continue
        post_id = int(item.get("id") or 0)
        title = str(item.get("title") or "").strip()
        url = str(item.get("url") or "").strip()
        if not post_id or not title or not url:
            continue

        title_norm = normalize_lookup_text(title)
        slug_norm = normalize_lookup_text(slug_from_url(url))
        score = 0
        if title_norm == normalized_name:
            score += 1000
        if slug_norm == normalized_name:
            score += 900
        if normalized_name and normalized_name in title_norm:
            score += 300
        if normalized_name and normalized_name in slug_norm:
            score += 250

        token_overlap = len(set(re.findall(r"[a-z0-9]+", champion_name.lower())) & set(re.findall(r"[a-z0-9]+", title.lower())))
        score += token_overlap * 10
        length_delta = abs(len(title_norm) - len(normalized_name))

        match = HellHadesChampionMatch(post_id=post_id, title=title, url=url)
        candidate = (score, -length_delta, match)
        if best_candidate is None or candidate > best_candidate:
            best_candidate = candidate

    if best_candidate is None or best_candidate[0] <= 0:
        return None
    return best_candidate[2]


def fetch_champion_skills(post_id: int) -> List[Dict[str, Any]]:
    payload = fetch_json(HH_SKILLS_URL_TEMPLATE.format(post_id=post_id))
    if isinstance(payload, list) and payload and isinstance(payload[0], list):
        return [item for item in payload[0] if isinstance(item, dict)]
    return []


def html_to_text(value: Any) -> str:
    text = str(value or "")
    if not text.strip():
        return ""
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</p>", "\n\n", text)
    text = re.sub(r"(?i)<p[^>]*>", "", text)
    text = TAG_RE.sub("", text)
    text = html.unescape(text).replace("\r", "")
    lines = [normalize_space(line) for line in text.splitlines()]

    cleaned_lines: List[str] = []
    previous_blank = False
    for line in lines:
        if line:
            cleaned_lines.append(line)
            previous_blank = False
        elif not previous_blank:
            cleaned_lines.append("")
            previous_blank = True
    return "\n".join(cleaned_lines).strip()


def normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def split_description(description_text: str) -> Tuple[str, str, List[str]]:
    lines = [line.strip() for line in description_text.splitlines()]
    full_lines = [line for line in lines if line]
    book_lines = [line for line in full_lines if LEVEL_LINE_RE.match(line)]
    detail_lines = [line for line in full_lines if not LEVEL_LINE_RE.match(line)]
    return "\n".join(full_lines), "\n".join(detail_lines), book_lines


def flatten_book_payload(books: Any) -> Iterable[str]:
    if isinstance(books, list):
        for item in books:
            if isinstance(item, dict):
                for value in item.values():
                    text = normalize_space(str(value))
                    if text:
                        yield text
            else:
                text = normalize_space(str(item))
                if text:
                    yield text


def infer_booked_cooldown(base_cooldown: Optional[int], book_lines: Sequence[str], books: Any) -> Optional[int]:
    if base_cooldown is None:
        return None
    reduction = 0
    for line in list(book_lines) + list(flatten_book_payload(books)):
        match = re.search(r"Cooldown\s*-\s*(\d+)", line, re.IGNORECASE)
        if match:
            reduction += int(match.group(1))
    return max(base_cooldown - reduction, 0)


def infer_target(text: str) -> str:
    lowered = text.lower()
    if "this champion" in lowered:
        return "self"
    if "all allies" in lowered:
        return "all_allies"
    if "all enemy" in lowered or "all enemies" in lowered:
        return "all_enemies"
    if " ally " in f" {lowered} " or lowered.startswith("ally "):
        return "ally"
    if "target enemy" in lowered or "enemy target" in lowered or "1 enemy" in lowered:
        return "enemy"
    if "enemy" in lowered:
        return "enemy"
    return ""


def normalize_effect_label(label: str) -> Tuple[str, Optional[float]]:
    text = normalize_space(label)
    value_match = re.match(r"(?P<value>\d+(?:\.\d+)?)%\s+(?P<label>.+)", text)
    if value_match:
        effect_value = float(value_match.group("value"))
        base_label = value_match.group("label")
    else:
        effect_value = None
        base_label = text
    normalized_label = re.sub(r"[^a-z0-9]+", "_", base_label.lower()).strip("_")
    return normalized_label, effect_value


def extract_sentences(description_clean: str) -> List[str]:
    chunks: List[str] = []
    for paragraph in description_clean.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        parts = [part.strip() for part in SENTENCE_SPLIT_RE.split(paragraph) if part.strip()]
        chunks.extend(parts or [paragraph])
    return chunks


def normalize_effect_target(raw_target: str) -> str:
    lowered = raw_target.lower()
    if "all ally" in lowered:
        return "all_allies"
    if "all enemy" in lowered:
        return "all_enemies"
    if "this champion" in lowered:
        return "self"
    if "ally" in lowered:
        return "ally"
    if "enemy" in lowered:
        return "enemy"
    return ""


def extract_effect_rows(description_clean: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[Tuple[Any, ...]] = set()

    def append_effect(
        effect_type: str,
        target: str,
        effect_value: Optional[float],
        duration: Optional[int],
        chance: Optional[float],
        condition_text: str,
    ) -> None:
        key = (effect_type, target, effect_value, duration, chance, condition_text)
        if not effect_type or key in seen:
            return
        seen.add(key)
        rows.append(
            {
                "effect_type": effect_type,
                "target": target or None,
                "effect_value": effect_value,
                "duration": duration,
                "chance": chance,
                "condition_text": condition_text,
            }
        )

    for sentence in extract_sentences(description_clean):
        target = infer_target(sentence)
        duration_match = re.search(r"for\s+(\d+)\s+turns?", sentence, re.IGNORECASE)
        chance_match = re.search(r"(\d+(?:\.\d+)?)%\s+chance", sentence, re.IGNORECASE)
        duration = int(duration_match.group(1)) if duration_match else None
        chance = float(chance_match.group(1)) if chance_match else None

        for label in BRACKET_EFFECT_RE.findall(sentence):
            effect_type, effect_value = normalize_effect_label(label)
            append_effect(effect_type, target, effect_value, duration, chance, sentence)

        for match in re.finditer(r"fill(?:s)? .*?turn meter by (\d+(?:\.\d+)?)%", sentence, re.IGNORECASE):
            append_effect("turn_meter_fill", target or "self", float(match.group(1)), None, chance, sentence)

        if re.search(r"fully deplete(?:s)? .*turn meter", sentence, re.IGNORECASE):
            append_effect("turn_meter_reduce", target or "enemy", 100.0, None, chance, sentence)

        for match in re.finditer(r"reduce(?:s)? .*?turn meter by (\d+(?:\.\d+)?)%", sentence, re.IGNORECASE):
            append_effect("turn_meter_reduce", target or "enemy", float(match.group(1)), None, chance, sentence)

        for match in re.finditer(r"steal(?:s)? (\d+(?:\.\d+)?)% of .*?turn meter", sentence, re.IGNORECASE):
            append_effect("turn_meter_steal", target or "enemy", float(match.group(1)), None, chance, sentence)

        if re.search(r"fills? .*turn meter by the amount .* loses", sentence, re.IGNORECASE):
            append_effect("turn_meter_fill_scaled", target or "self", None, None, chance, sentence)

        for match in re.finditer(r"decrease(?:s)? the cooldowns? of ([^.]+?) by (\d+) turns?", sentence, re.IGNORECASE):
            append_effect(
                "cooldown_reduce",
                normalize_effect_target(match.group(1)),
                float(match.group(2)),
                None,
                chance,
                sentence,
            )

        for match in re.finditer(r"increase(?:s)? the cooldowns? of ([^.]+?) by (\d+) turns?", sentence, re.IGNORECASE):
            append_effect(
                "cooldown_increase",
                normalize_effect_target(match.group(1)),
                float(match.group(2)),
                None,
                chance,
                sentence,
            )

        if re.search(r"extra turn", sentence, re.IGNORECASE):
            append_effect("extra_turn", target or "self", 1.0, None, chance, sentence)

        if re.search(r"reset(?:s)? .*cooldown", sentence, re.IGNORECASE):
            append_effect("cooldown_reset", target or "self", None, None, chance, sentence)

        if re.search(r"remove(?:s)? all buffs", sentence, re.IGNORECASE):
            append_effect("remove_buffs", target or "enemy", None, None, chance, sentence)

        if re.search(r"steal(?:s)? all buffs", sentence, re.IGNORECASE):
            append_effect("steal_buffs", target or "enemy", None, None, chance, sentence)

        if re.search(r"revive(?:s)?", sentence, re.IGNORECASE):
            append_effect("revive", target or "ally", None, None, chance, sentence)

    return rows


def load_target_champions(
    conn: sqlite3.Connection,
    champion_names: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
) -> List[str]:
    if champion_names:
        return [str(name).strip() for name in champion_names if str(name).strip()]

    rows = conn.execute(
        """
        SELECT champion_name
        FROM registry_targets
        ORDER BY priority DESC, champion_name ASC
        """
    ).fetchall()
    names = [str(row[0]) for row in rows]
    return names[:limit] if limit else names


def load_existing_skill_rows(conn: sqlite3.Connection, champion_name: str) -> List[Tuple[str, int]]:
    rows = conn.execute(
        """
        SELECT slot, skill_order
        FROM champion_skills
        WHERE champion_name = ?
        ORDER BY skill_order ASC
        """,
        (champion_name,),
    ).fetchall()
    return [(str(row[0]), int(row[1])) for row in rows]


def reconcile_skill_rows(
    conn: sqlite3.Connection,
    champion_name: str,
    existing_rows: List[Tuple[str, int]],
    remote_skill_count: int,
) -> List[Tuple[str, int]]:
    if len(existing_rows) > remote_skill_count:
        for slot, skill_order in existing_rows[remote_skill_count:]:
            conn.execute(
                """
                DELETE FROM champion_skills
                WHERE champion_name = ? AND slot = ? AND skill_order = ?
                """,
                (champion_name, slot, skill_order),
            )
        existing_rows = existing_rows[:remote_skill_count]
    elif len(existing_rows) < remote_skill_count:
        for skill_order in range(len(existing_rows) + 1, remote_skill_count + 1):
            slot = f"A{skill_order}"
            conn.execute(
                """
                INSERT INTO champion_skills (
                    champion_name, slot, skill_order, skill_id, skill_name,
                    cooldown, booked_cooldown, description, skill_type, description_clean, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    champion_name,
                    slot,
                    skill_order,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                    None,
                ),
            )
            existing_rows.append((slot, skill_order))
    return existing_rows


def enrich_registry_from_hellhades(
    db_path: Path = DB_PATH,
    champion_names: Optional[Sequence[str]] = None,
    limit: Optional[int] = None,
) -> Dict[str, Any]:
    ensure_schema(db_path)
    started_at = now_utc_iso()

    summary: Dict[str, Any] = {
        "database": str(db_path),
        "started_at": started_at,
        "requested": 0,
        "matched": 0,
        "updated": 0,
        "effect_rows_written": 0,
        "not_found": [],
        "skill_count_mismatches": [],
    }

    with sqlite3.connect(db_path) as conn:
        targets = load_target_champions(conn, champion_names=champion_names, limit=limit)
        summary["requested"] = len(targets)

        for champion_name in targets:
            existing_rows = load_existing_skill_rows(conn, champion_name)
            if not existing_rows:
                summary["not_found"].append(f"{champion_name}:missing_local_skills")
                continue

            try:
                match = resolve_champion_match(champion_name)
            except Exception as exc:  # pragma: no cover - network failure path
                summary["not_found"].append(f"{champion_name}:search_error:{exc}")
                continue

            if match is None:
                summary["not_found"].append(champion_name)
                continue

            summary["matched"] += 1

            try:
                remote_skills = fetch_champion_skills(match.post_id)
            except Exception as exc:  # pragma: no cover - network failure path
                summary["not_found"].append(f"{champion_name}:skills_error:{exc}")
                continue

            if not remote_skills:
                summary["not_found"].append(f"{champion_name}:empty_remote_skills")
                continue

            if len(existing_rows) != len(remote_skills):
                summary["skill_count_mismatches"].append(
                    {
                        "champion_name": champion_name,
                        "local_skill_rows": len(existing_rows),
                        "remote_skill_rows": len(remote_skills),
                    }
                )

            existing_rows = reconcile_skill_rows(conn, champion_name, existing_rows, len(remote_skills))
            aligned_rows = list(zip(existing_rows, remote_skills))
            if not aligned_rows:
                continue

            conn.execute("DELETE FROM champion_skill_effects WHERE champion_name = ?", (champion_name,))
            effect_order = 1

            for (slot, skill_order), remote_skill in aligned_rows:
                skill_name = normalize_space(str(remote_skill.get("name") or "")) or None
                skill_type = normalize_space(str(remote_skill.get("type") or "")) or None
                description_full, description_clean, book_lines = split_description(html_to_text(remote_skill.get("description")))

                base_cooldown = nullable_int(remote_skill.get("cooldown"))
                booked_cooldown = infer_booked_cooldown(base_cooldown, book_lines, remote_skill.get("books"))

                conn.execute(
                    """
                    UPDATE champion_skills
                    SET
                        skill_name = ?,
                        cooldown = ?,
                        booked_cooldown = ?,
                        description = ?,
                        skill_type = ?,
                        description_clean = ?,
                        source = ?
                    WHERE champion_name = ? AND slot = ? AND skill_order = ?
                    """,
                    (
                        skill_name,
                        base_cooldown,
                        booked_cooldown,
                        description_full or None,
                        skill_type,
                        description_clean or None,
                        "hellhades",
                        champion_name,
                        slot,
                        skill_order,
                    ),
                )

                for effect_row in extract_effect_rows(description_clean):
                    conn.execute(
                        """
                        INSERT INTO champion_skill_effects (
                            champion_name, slot, effect_order, effect_type, target,
                            effect_value, duration, chance, condition_text
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            champion_name,
                            slot,
                            effect_order,
                            effect_row["effect_type"],
                            effect_row["target"],
                            effect_row["effect_value"],
                            effect_row["duration"],
                            effect_row["chance"],
                            effect_row["condition_text"],
                        ),
                    )
                    effect_order += 1
                    summary["effect_rows_written"] += 1

            conn.execute(
                """
                UPDATE champion_catalog
                SET hellhades_post_id = ?, hellhades_url = ?, last_enriched_at = ?
                WHERE champion_name = ?
                """,
                (match.post_id, match.url, started_at, champion_name),
            )
            summary["updated"] += 1

        conn.commit()

    save_app_state(
        {
            "hellhades_last_enrich_utc": started_at,
            "hellhades_last_enrich_requested": summary["requested"],
            "hellhades_last_enrich_updated": summary["updated"],
            "hellhades_last_enrich_missing": summary["not_found"],
        },
        db_path,
    )
    return summary


def nullable_int(value: Any) -> Optional[int]:
    if value is None or value == "":
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enrich champion skills from HellHades into SQLite.")
    parser.add_argument("--db-path", type=Path, default=DB_PATH)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--champion", action="append", dest="champions", default=None)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = enrich_registry_from_hellhades(
        db_path=args.db_path,
        champion_names=args.champions,
        limit=args.limit,
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
