from __future__ import annotations

from providers.ayumilove_provider import (
    AYUMILOVE_SEARCH_URL_TEMPLATE,
    AYUMILOVE_URL_TEMPLATE,
    AyumiLoveSkillEnrichmentProvider,
    parse_ayumilove_skills,
    slugify_champion_name,
)


THEA_PAGE_HTML = """
<html>
  <body>
    <h1>Thea the Tomb Angel | Raid Shadow Legends</h1>
    <h2>Thea the Tomb Angel Skills</h2>
    <p>Befoulment</p>
    <p>Attacks 2 times at random. Has a 75% chance of placing a [Hex] debuff for 5 turns.</p>
    <p>Level 2: Damage +5%</p>
    <p>Level 3: Buff/Debuff Chance +5%</p>
    <p>Damage Multiplier: 2 ATK</p>
    <p>Hexreaper (Cooldown: 5 turns)</p>
    <p>Attacks all enemies.</p>
    <p>Level 2: Cooldown -1</p>
    <p>Not of This World (Cooldown: 5 turns)</p>
    <p>Places a [Perfect Veil] buff on this Champion for 3 turns. Grants an Extra Turn.</p>
    <p>Level 2: Cooldown -1</p>
    <p>Cruel Angel (Passive)</p>
    <p>Has a 50% chance of placing a [True Fear] debuff on all enemies for 1 turn.</p>
    <p>Aura</p>
    <p>Increases Ally ATK in All Battles by 30%</p>
    <h2>Thea the Tomb Angel Build Guide</h2>
  </body>
</html>
"""


def test_parse_ayumilove_skills_extracts_skill_blocks() -> None:
    skills = parse_ayumilove_skills(THEA_PAGE_HTML)

    assert [skill["name"] for skill in skills] == [
        "Befoulment",
        "Hexreaper",
        "Not of This World",
        "Cruel Angel",
        "Aura",
    ]
    assert skills[0]["type"] == "Basic"
    assert skills[0]["cooldown"] == 0
    assert skills[0]["books"] == ["Level 2: Damage +5%", "Level 3: Buff/Debuff Chance +5%"]
    assert skills[1]["cooldown"] == 5
    assert skills[1]["books"] == ["Level 2: Cooldown -1"]
    assert skills[2]["description"] == "Places a [Perfect Veil] buff on this Champion for 3 turns. Grants an Extra Turn."
    assert skills[3]["type"] == "Passive"
    assert skills[4]["type"] == "Aura"


def test_ayumilove_provider_resolves_direct_slug_without_search(monkeypatch) -> None:
    provider = AyumiLoveSkillEnrichmentProvider()
    requested_urls: list[str] = []

    def fake_fetch_text(url: str) -> str:
        requested_urls.append(url)
        if url == AYUMILOVE_URL_TEMPLATE.format(slug=slugify_champion_name("Thea the Tomb Angel")):
            return THEA_PAGE_HTML
        if url == AYUMILOVE_SEARCH_URL_TEMPLATE.format(query="Thea+the+Tomb+Angel+raid+shadow+legends"):
            return ""
        raise AssertionError(f"URL inattesa: {url}")

    monkeypatch.setattr("providers.ayumilove_provider.fetch_text", fake_fetch_text)

    match = provider.resolve_champion_match("Thea the Tomb Angel")
    assert match is not None
    assert match.source_name == "ayumilove"
    assert match.title == "Thea the Tomb Angel"
    assert match.url == AYUMILOVE_URL_TEMPLATE.format(slug="thea-the-tomb-angel")
    assert requested_urls[0] == AYUMILOVE_URL_TEMPLATE.format(slug="thea-the-tomb-angel")


def test_ayumilove_provider_uses_search_results_when_direct_slug_misses(monkeypatch) -> None:
    provider = AyumiLoveSkillEnrichmentProvider()

    search_html = """
    <html>
      <body>
        <a href="https://ayumilove.net/raid-shadow-legends-thea-the-tomb-angel-skill-mastery-equip-guide/">Thea</a>
      </body>
    </html>
    """

    def fake_fetch_text(url: str) -> str:
        if url == AYUMILOVE_URL_TEMPLATE.format(slug="thea"):
            raise AssertionError("lo slug diretto non dovrebbe essere valido per questo test")
        if url == AYUMILOVE_SEARCH_URL_TEMPLATE.format(query="Thea+raid+shadow+legends"):
            return search_html
        if url == "https://ayumilove.net/raid-shadow-legends-thea-the-tomb-angel-skill-mastery-equip-guide/":
            return THEA_PAGE_HTML
        raise AssertionError(f"URL inattesa: {url}")

    monkeypatch.setattr("providers.ayumilove_provider.fetch_text", fake_fetch_text)

    match = provider.resolve_champion_match("Thea")
    assert match is not None
    assert match.title == "Thea the Tomb Angel"
    assert match.slug == "thea-the-tomb-angel"
