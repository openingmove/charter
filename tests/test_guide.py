"""The user manual in `docs/guide/` and the README front page: every relative link resolves, anchors included.

The links are read the way GitHub renders them, so a page or heading renamed in a later change fails here, not
in front of a reader.
"""

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GUIDE = ROOT / "docs" / "guide"
PAGES = sorted(GUIDE.glob("*.md"))
WIKI = "https://github.com/openingmove/charter/wiki"
LINK = re.compile(r"(?<!!)\[[^\]]*\]\(([^)\s]+)\)")
FENCE = re.compile(r"^\s{0,3}(`{3,}|~{3,})")


def _prose(text: str) -> list[str]:
    """The lines outside fenced code, with inline code removed."""
    lines, fence = [], None
    for line in text.splitlines():
        opened = FENCE.match(line)
        if fence:
            if opened and opened.group(1)[0] == fence[0] and len(opened.group(1)) >= len(fence):
                fence = None
            continue
        if opened:
            fence = opened.group(1)
            continue
        lines.append(re.sub(r"(`+).+?\1", "", line))
    return lines


def _anchors(page: Path) -> set[str]:
    """GitHub's heading ids: lower case, punctuation dropped, spaces as hyphens, repeats numbered."""
    anchors: set[str] = set()
    seen: dict[str, int] = {}
    for line in _prose(page.read_text(encoding="utf-8").replace("`", "")):
        heading = re.match(r"^#{1,6}\s+(.*?)\s*#*\s*$", line)
        if heading:
            slug = re.sub(r"[^\w\- ]", "", heading.group(1).lower()).replace(" ", "-")
            count = seen.get(slug, 0)
            seen[slug] = count + 1
            anchors.add(slug if count == 0 else f"{slug}-{count}")
    return anchors


def _links(page: Path) -> list[str]:
    return [target for line in _prose(page.read_text(encoding="utf-8")) for target in LINK.findall(line)]


def test_the_manual_has_an_index_and_topic_pages():
    names = {page.name for page in PAGES}

    assert "README.md" in names
    assert {"Contract-syntax.md", "Commands.md", "Plugins.md", "Diagnostic-codes.md"} <= names


@pytest.mark.parametrize("page", [ROOT / "README.md", *PAGES], ids=lambda page: page.relative_to(ROOT).as_posix())
def test_every_relative_link_resolves(page):
    broken = []
    for target in _links(page):
        if re.match(r"[a-z][a-z0-9+.-]*:", target):
            continue
        path, _, anchor = target.partition("#")
        file = (page.parent / path).resolve() if path else page
        if not file.exists():
            broken.append(target)
        elif anchor and file.suffix == ".md" and anchor not in _anchors(file):
            broken.append(target)

    assert broken == []


def test_the_index_links_to_every_page():
    linked = {target.partition("#")[0] for target in _links(GUIDE / "README.md")}

    assert {page.name for page in PAGES if page.name != "README.md"} <= linked


def test_the_readme_is_a_short_front_page_that_links_to_the_manual_and_the_wiki():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")

    assert len(readme.splitlines()) <= 150
    assert "docs/guide/README.md" in _links(ROOT / "README.md")
    assert WIKI in readme


POINTING_FILES = [*(ROOT / "skills").rglob("*.md"), *(ROOT / "src").rglob("*.py")]


def test_no_skill_or_source_file_points_at_a_readme_section():
    pointers = [
        file.relative_to(ROOT).as_posix()
        for file in POINTING_FILES
        if re.search(r"README's|in the README", file.read_text("utf-8"))
    ]

    assert pointers == []


def test_the_skills_point_at_manual_pages_that_exist():
    pointer = re.compile(r"docs/guide/([\w-]+\.md)")
    named = {name for file in POINTING_FILES for name in pointer.findall(file.read_text("utf-8"))}

    assert named
    assert named <= {page.name for page in PAGES}
