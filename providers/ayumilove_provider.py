from __future__ import annotations

import html
import re
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import quote_plus

from enrichment_sources import ChampionSkillMatch, register_skill_enrichment_provider


AYUMILOVE_BASE_URL = "https://ayumilove.net"
AYUMILOVE_URL_TEMPLATE = AYUMILOVE_BASE_URL + "/raid-shadow-legends-{slug}-skill-mastery-equip-guide/"
AYUMILOVE_SEARCH_URL_TEMPLATE = AYUMILOVE_BASE_URL + "/?s={query}"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Referer": AYUMILOVE_BASE_URL + "/",
}
TITLE_RE = re.compile(r"^#\s+(?P<title>.+?)\s+\|\s+Raid Shadow Legends\s*$", re.IGNORECASE)
COOLDOWN_HEADER_RE = re.compile(r"^(?P<name>.+?)\s+\(Cooldown:\s*(?P<cooldown>\d+)(?:\s+turns?)?\)$", re.IGNORECASE)
PASSIVE_HEADER_RE = re.compile(r"^(?P<name>.+?)\s+\((?P<label>Passive)\)$", re.IGNORECASE)
CHAMPION_URL_RE = re.compile(
    r"https://ayumilove\.net/raid-shadow-legends-[a-z0-9\-]+-skill-mastery-equip-guide/?",
    re.IGNORECASE,
)


def normalize_lookup_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())


def slugify_champion_name(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_value = ascii_value.replace("&", " and ")
    ascii_value = re.sub(r"[^a-z0-9]+", "-", ascii_value.lower()).strip("-")
    return re.sub(r"-{2,}", "-", ascii_value)


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, headers=REQUEST_HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8-sig", errors="ignore")


def html_to_text_lines(value: str) -> List[str]:
    text = str(value or "")
    if not text.strip():
        return []

    def replace_heading(match: re.Match[str]) -> str:
        level = int(match.group(1))
        return f"\n{'#' * level} "

    text = re.sub(r"(?is)<h([1-6])[^>]*>", replace_heading, text)
    text = re.sub(r"(?is)</h[1-6]>", "\n", text)
    text = re.sub(r"(?is)<br\s*/?>", "\n", text)
    text = re.sub(r"(?is)</p>", "\n\n", text)
    text = re.sub(r"(?is)<p[^>]*>", "", text)
    text = re.sub(r"(?is)<li[^>]*>", "\n* ", text)
    text = re.sub(r"(?is)</li>", "\n", text)
    text = re.sub(r"(?is)<[^>]+>", "", text)
    text = html.unescape(text).replace("\r", "")

    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    output: List[str] = []
    previous_blank = False
    for line in lines:
        if line:
            output.append(line)
            previous_blank = False
        elif not previous_blank:
            output.append("")
            previous_blank = True
    return output


def extract_page_title(lines: Sequence[str]) -> str:
    for line in lines:
        match = TITLE_RE.match(line)
        if match:
            return str(match.group("title")).strip()
    return ""


def parse_search_candidate_urls(search_html: str) -> List[str]:
    candidates = CHAMPION_URL_RE.findall(search_html or "")
    seen: set[str] = set()
    urls: List[str] = []
    for candidate in candidates:
        normalized = candidate.rstrip("/") + "/"
        if normalized in seen:
            continue
        seen.add(normalized)
        urls.append(normalized)
    return urls


def looks_like_skill_header(line: str) -> bool:
    if not line or line.startswith("#") or line.startswith("* "):
        return False
    if line == "Aura" or COOLDOWN_HEADER_RE.match(line) or PASSIVE_HEADER_RE.match(line):
        return True
    lowered = line.lower()
    if lowered.startswith(
        (
            "attacks ",
            "places ",
            "has ",
            "increases ",
            "decreases ",
            "grants ",
            "removes ",
            "revives ",
            "heals ",
            "fills ",
            "steals ",
        )
    ):
        return False
    if ":" in line or line.endswith("."):
        return False
    words = line.split()
    return bool(words) and len(words) <= 8 and line[:1].isupper()


def parse_skill_type(name: str, skill_index: int) -> str:
    if name == "Aura":
        return "Aura"
    if "passive" in name.lower():
        return "Passive"
    if skill_index == 1:
        return "Basic"
    return "Active"


def parse_ayumilove_skills(page_html: str) -> List[Dict[str, Any]]:
    lines = html_to_text_lines(page_html)
    section_start = -1
    section_end = len(lines)

    for index, line in enumerate(lines):
        if line.startswith("## ") and line.endswith(" Skills"):
            section_start = index + 1
            continue
        if section_start >= 0 and line.startswith("## "):
            section_end = index
            break

    if section_start < 0:
        return []

    section_lines = list(lines[section_start:section_end])
    skills: List[Dict[str, Any]] = []
    current: Optional[Dict[str, Any]] = None
    skill_index = 0

    def flush_current() -> None:
        nonlocal current
        if current is None:
            return
        current["description"] = "\n".join(current.pop("_description_lines")).strip()
        current["books"] = list(current.pop("_book_lines"))
        skills.append(current)
        current = None

    for line in section_lines:
        if not line:
            continue
        if line.startswith("### ") or line.startswith("#### "):
            continue
        if line.startswith("Damage Multiplier:"):
            continue

        cooldown_match = COOLDOWN_HEADER_RE.match(line)
        passive_match = PASSIVE_HEADER_RE.match(line)
        if line == "Aura" or cooldown_match or passive_match or looks_like_skill_header(line):
            flush_current()
            skill_index += 1
            header_name = line
            cooldown: Optional[int] = None
            if cooldown_match:
                header_name = str(cooldown_match.group("name")).strip()
                cooldown = int(cooldown_match.group("cooldown"))
            elif passive_match:
                header_name = str(passive_match.group("name")).strip()
            elif line == "Aura":
                header_name = "Aura"
            current = {
                "name": header_name,
                "type": "Passive" if passive_match else parse_skill_type(header_name, skill_index),
                "cooldown": 0 if skill_index == 1 and not cooldown_match and line != "Aura" and not passive_match else cooldown,
                "_description_lines": [],
                "_book_lines": [],
            }
            continue

        if current is None:
            continue
        if re.match(r"^Level\s+\d+\s*:", line, re.IGNORECASE):
            current["_book_lines"].append(line)
            continue
        current["_description_lines"].append(line)

    flush_current()
    return [skill for skill in skills if str(skill.get("name") or "").strip()]


@dataclass(frozen=True)
class AyumiLoveChampionMatch(ChampionSkillMatch):
    slug: str

    def __init__(self, slug: str, title: str, url: str) -> None:
        normalized_slug = str(slug or "").strip()
        object.__setattr__(self, "source_name", "ayumilove")
        object.__setattr__(self, "source_ref", normalized_slug)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "slug", normalized_slug)


class AyumiLoveSkillEnrichmentProvider:
    source_name = "ayumilove"

    def resolve_champion_match(self, champion_name: str) -> Optional[AyumiLoveChampionMatch]:
        normalized_name = normalize_lookup_text(champion_name)
        slug = slugify_champion_name(champion_name)
        candidate_urls = [AYUMILOVE_URL_TEMPLATE.format(slug=slug)]

        seen: set[str] = set()
        best_match: Optional[AyumiLoveChampionMatch] = None
        best_score = -1

        def consider_urls(urls: Sequence[str]) -> None:
            nonlocal best_match, best_score
            for url in urls:
                normalized_url = url.rstrip("/") + "/"
                if normalized_url in seen:
                    continue
                seen.add(normalized_url)
                try:
                    page_html = fetch_text(normalized_url)
                except urllib.error.HTTPError:
                    continue
                except Exception:
                    continue

                title = extract_page_title(html_to_text_lines(page_html))
                if not title:
                    continue
                title_norm = normalize_lookup_text(title)
                slug_norm = normalize_lookup_text(slugify_champion_name(title))
                score = 0
                if title_norm == normalized_name:
                    score += 1000
                if slug_norm == normalized_name:
                    score += 800
                if normalized_name and normalized_name in title_norm:
                    score += 250
                if normalized_name and normalized_name in slug_norm:
                    score += 200
                if score <= 0:
                    continue

                candidate = AyumiLoveChampionMatch(slug=slugify_champion_name(title), title=title, url=normalized_url)
                if score > best_score:
                    best_score = score
                    best_match = candidate

        consider_urls(candidate_urls)
        if best_match is not None:
            return best_match

        search_query = quote_plus(f"{champion_name} raid shadow legends")
        try:
            search_html = fetch_text(AYUMILOVE_SEARCH_URL_TEMPLATE.format(query=search_query))
        except Exception:
            search_html = ""
        consider_urls(parse_search_candidate_urls(search_html))

        return best_match

    def fetch_champion_skills(self, match: ChampionSkillMatch) -> List[Dict[str, Any]]:
        page_html = fetch_text(str(match.url))
        return parse_ayumilove_skills(page_html)


register_skill_enrichment_provider(AyumiLoveSkillEnrichmentProvider())
