"""Unprintable control characters are a diagnostic on the file that holds them, not a traceback.

The characters are built from code points here: typed literally they would be invisible in review."""

import pytest

from charter import yamlsource

# C0 (not tab, LF, CR), DEL, C1 (not NEL), U+FFFE
CHARS = [0x00, 0x01, 0x07, 0x1B, 0x1F, 0x7F, 0x80, 0x9F, 0xFFFE]
CONTRACT = "charter: 1\nkinds:\n  entry: {}\n"
GOOD = "---\nkind: entry\n---\n"


def _note(char: str) -> str:
    return f"---\nkind: entry\ntitle: Ada{char}\n---\n"


@pytest.fixture(params=["python", None], ids=["pure-python", "default-loader"])
def loader(request, monkeypatch):
    if request.param:
        monkeypatch.setenv(yamlsource.LOADER_ENV, request.param)
    else:
        monkeypatch.delenv(yamlsource.LOADER_ENV, raising=False)


def _diagnostics(result):
    return [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]]


@pytest.mark.parametrize("code_point", CHARS, ids=lambda c: f"U+{c:04X}")
def test_validate_reports_the_note_and_checks_the_others(charter, make_kb, loader, code_point):
    kb = make_kb({"charter.yaml": CONTRACT, "a.md": _note(chr(code_point)), "b.md": GOOD, "c.md": "---\n---\n"})

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 1
    found = [d for d in _diagnostics(result) if d[0] == "a.md"]
    assert found == [("a.md", 3, "index/invalid-frontmatter")]
    assert [d for d in _diagnostics(result) if d[0] == "b.md"] == []
    assert any(d[0] == "c.md" for d in _diagnostics(result))  # c.md has no kind: it was still validated


@pytest.mark.parametrize("code_point", [0x07, 0x7F, 0x86, 0xFFFE], ids=lambda c: f"U+{c:04X}")
def test_validate_file_reports_the_note(charter, make_kb, loader, code_point):
    kb = make_kb({"charter.yaml": CONTRACT, "a.md": _note(chr(code_point)), "b.md": GOOD})

    result = charter("validate", "--file", "a.md", "--format", "json", cwd=kb)

    assert result.exit_code == 1
    assert _diagnostics(result) == [("a.md", 3, "index/invalid-frontmatter")]


def test_the_line_counts_every_line_break_before_the_character(loader):
    # The scanner reads CRLF as one break, and NEL, LS and PS as breaks too.
    text = "a: 1\r\nb: 2\u2028c: 3\u0085d: 4\re: x" + chr(7) + "\n"

    with pytest.raises(yamlsource.YamlSyntaxError) as raised:
        yamlsource.parse(text)

    assert raised.value.line == 5


@pytest.mark.parametrize("code_point", CHARS, ids=lambda c: f"U+{c:04X}")
def test_the_contract_gives_a_clean_error(charter, make_kb, loader, code_point):
    kb = make_kb({"charter.yaml": CONTRACT + f"title: Ada{chr(code_point)}\n", "a.md": GOOD})

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert _diagnostics(result) == [("charter.yaml", 4, "contract/yaml")]
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("code_point", CHARS, ids=lambda c: f"U+{c:04X}")
def test_parse_raises_the_projects_error_with_a_line(loader, code_point):
    with pytest.raises(yamlsource.YamlSyntaxError) as raised:
        yamlsource.parse(f"a: 1\nb: x{chr(code_point)}\n")

    assert raised.value.line == 2
    assert raised.value.message.startswith(f"unacceptable character #x{code_point:04x}:")


def test_the_lock_gives_a_clean_error(charter, make_kb, loader):
    kb = make_kb({"charter.yaml": CONTRACT, "charter.lock": "charter_lock: 1\nplugins: {}\nx: " + chr(7) + "\n"})

    result = charter("validate", "--format", "json", cwd=kb)

    assert result.exit_code == 2
    assert _diagnostics(result) == [("charter.lock", 3, "contract/yaml")]


def test_survey_reports_the_note_and_reads_the_others(charter, make_kb, loader):
    kb = make_kb({"notes/bad.md": _note(chr(7)), "notes/good.md": GOOD})

    survey = charter("survey", str(kb), "--format", "json", cwd=kb.parent).json()

    files = {file["path"]: file for file in survey["files"]}
    assert files["notes/bad.md"]["frontmatter_error"].startswith("Invalid YAML in frontmatter")
    assert files["notes/good.md"]["frontmatter_error"] is None


ACCEPTED = [
    (0x7E, "tilde, just below DEL"),
    (0xA0, "no-break space, just above the C1 range"),
    (0xA1, "inverted exclamation mark"),
    (0xFFFD, "replacement character, just below the noncharacters"),
]


@pytest.mark.parametrize(("code_point", "why"), ACCEPTED, ids=[why for _, why in ACCEPTED])
def test_characters_next_to_the_rejected_ranges_still_parse(loader, code_point, why):
    assert yamlsource.parse(f"a: x{chr(code_point)}y\n")[0] == {"a": f"x{chr(code_point)}y"}
