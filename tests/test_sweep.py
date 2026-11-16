import pytest

CONTRACT = (
    "charter: 1\n"
    "root: notes\n"
    "common_fields: [aliases]\n"
    "kinds:\n"
    "  page: {}\n"
    "  zone:\n"
    "    fields:\n"
    "      title: {type: string}\n"
    "      parent: {type: link, to: zone}\n"
    "  thing:\n"
    "    fields:\n"
    "      id: {type: int}\n"
    "      zone: {type: link, to: zone}\n"
    "      requires: {type: list, of: link}\n"
)
CANAL = "---\nkind: zone\ntitle: Grand Canal\naliases: [The Cut]\nparent: '[[City]]'\n---\n# Canal\n"
PAGE = "---\nkind: page\n---\n"


def _kb(make_kb, notes, paths=""):
    files = {"charter.yaml": CONTRACT + paths}
    files.update({f"notes/{path}": text for path, text in notes.items()})
    return make_kb(files)


def _sweep(charter, kb, note, *extra):
    return charter("sweep", note, "--format", "json", *extra, cwd=kb)


def _linked_from(result):
    return [(entry["path"], entry["line"], entry["field"], entry["raw"]) for entry in result.json()["linked_from"]]


def _mentioned_in(result):
    return [(entry["path"], entry["line"], entry["names"]) for entry in result.json()["mentioned_in"]]


# --- notes linking to the note ---


def test_lists_notes_linking_by_field_and_body_with_lines(charter, make_kb):
    kb = _kb(make_kb, {
        "Zones/Canal.md": CANAL,
        "Zones/City.md": "---\nkind: zone\n---\n",
        "Things/Honey.md": "---\nkind: thing\nzone: '[[Canal]]'\nrequires: ['[[Zones/Canal]]', '[[City]]']\n---\n"
        "Starts by [the canal](../Zones/Canal.md).\n",
        "Index.md": PAGE + "\n- [[Canal|the canal]]\n- [[City]]\n",
    })

    result = _sweep(charter, kb, "Canal")

    assert result.exit_code == 0, result.stdout
    assert result.json()["format"] == "charter-sweep/1"
    assert result.json()["note"] == "notes/Zones/Canal.md"
    assert _linked_from(result) == [
        ("notes/Index.md", 5, None, "[[Canal|the canal]]"),
        ("notes/Things/Honey.md", 3, "zone", "[[Canal]]"),
        ("notes/Things/Honey.md", 4, "requires", "[[Zones/Canal]]"),
        ("notes/Things/Honey.md", 6, None, "[the canal](../Zones/Canal.md)"),
    ]


def test_links_in_code_and_comments_do_not_count(charter, make_kb):
    kb = _kb(make_kb, {
        "Zones/Canal.md": CANAL,
        "Index.md": PAGE + "`[[Zones/Canal]]` <!-- [[Zones/Canal]] -->\n```\n[[Zones/Canal]]\n```\n",
    })

    result = _sweep(charter, kb, "Zones/Canal")

    assert result.exit_code == 0, result.stdout
    assert _linked_from(result) == []


AMBIGUOUS_KB = {
    "Zones/Canal.md": CANAL,
    "Zones/City.md": "---\nkind: zone\n---\n",
    "Old/Canal.md": PAGE,
    "Index.md": PAGE + "[[Canal]]\n",
}


def test_an_ambiguous_link_that_may_mean_the_note_is_listed_as_ambiguous(charter, make_kb):
    kb = _kb(make_kb, AMBIGUOUS_KB)

    result = _sweep(charter, kb, "Zones/Canal")

    assert result.exit_code == 0, result.stdout
    assert result.json()["linked_from"] == [
        {"path": "notes/Index.md", "line": 4, "field": None, "raw": "[[Canal]]",
         "candidates": ["notes/Old/Canal.md", "notes/Zones/Canal.md"]},
    ]
    assert _mentioned_in(result) == []


def test_an_ambiguous_link_in_text_and_agent_output(charter, make_kb):
    kb = _kb(make_kb, AMBIGUOUS_KB)

    text = charter("sweep", "Zones/Canal", cwd=kb).stdout
    agent = charter("sweep", "Zones/Canal", "--format", "agent", cwd=kb).stdout

    assert "  notes/Index.md:4  [[Canal]] (ambiguous: notes/Old/Canal.md, notes/Zones/Canal.md)\n" in text
    assert "linked-from notes/Index.md:4 [[Canal]] (ambiguous: notes/Old/Canal.md, notes/Zones/Canal.md)\n" in agent


# --- notes mentioning the note ---


def test_lists_prose_mentions_of_title_aliases_and_filename(charter, make_kb):
    kb = _kb(make_kb, {
        "Zones/Canal.md": CANAL + "The Canal is long.\n",
        "Zones/City.md": "---\nkind: zone\n---\n",
        "Diary.md": PAGE
        + "We walked along the grand canal.\n"
        + "Nothing here: Canals, Canalside.\n"
        + "Locals call it the cut; [[Canal]] links do not count as mentions.\n"
        + "`Canal` <!-- Canal -->\n"
        + "\n"
        + "    Canal in indented code\n",
        "Map.md": "---\nkind: page\ntitle: Canal\n---\nSee [[City]] by the CANAL.\n",
    })

    result = _sweep(charter, kb, "Canal")

    assert result.exit_code == 0, result.stdout
    assert _mentioned_in(result) == [
        ("notes/Diary.md", 4, ["Grand Canal"]),
        ("notes/Diary.md", 6, ["The Cut"]),
        ("notes/Map.md", 5, ["Canal"]),
    ]


def test_text_of_links_to_other_notes_still_mentions_the_note(charter, make_kb):
    kb = _kb(make_kb, {
        "Zones/Canal.md": CANAL,
        "Zones/City.md": "---\nkind: zone\n---\n",
        "Index.md": PAGE + "[[City|by the Canal]]\n",
    })

    result = _sweep(charter, kb, "Canal")

    assert _mentioned_in(result) == [("notes/Index.md", 4, ["Canal"])]


def test_names_match_whatever_the_unicode_form_and_case(charter, make_kb):
    decomposed = "Café"
    kb = _kb(make_kb, {
        f"{decomposed}.md": "---\nkind: page\naliases: [Straße]\n---\n",
        "Diary.md": PAGE + "Coffee at the CAFÉ.\nDown the STRASSE.\n",
    })

    result = _sweep(charter, kb, "Straße")

    assert result.exit_code == 0, result.stdout
    assert _mentioned_in(result) == [("notes/Diary.md", 4, ["Caf\u00e9"]), ("notes/Diary.md", 5, ["Straße"])]


def test_a_name_may_break_across_lines_of_a_paragraph_but_not_across_items(charter, make_kb):
    kb = _kb(make_kb, {
        "Zones/Canal.md": CANAL,
        "Zones/City.md": "---\nkind: zone\n---\n",
        "Diary.md": PAGE + "We walked the Grand\nCanal at dawn.\n\n- Grand\n- Canal\n",
    })

    result = _sweep(charter, kb, "Canal")

    assert _mentioned_in(result) == [("notes/Diary.md", 4, ["Grand Canal"]), ("notes/Diary.md", 8, ["Canal"])]


@pytest.mark.parametrize(
    ("note_id", "prose", "mentioned"),
    [
        ("11", "Needs thing 11 first.", True),
        ("11", "Needs Thing #11 first.", True),
        ("11", "Needs #11 first.", True),
        ("11", "Takes 11 minutes.", False),
        ("11", "Needs thing 112 first.", False),
        ("1d", "Superseded by 1d.", True),
        ("1d", "Superseded by 1da.", False),
    ],
)
def test_an_id_counts_as_written_with_its_kind_or_hash_or_bare_when_it_holds_a_letter(
    charter, make_kb, note_id, prose, mentioned
):
    contract_id = "string" if not note_id.isdigit() else "int"
    kb = make_kb({
        "charter.yaml": "charter: 1\nkinds:\n  page: {}\n  thing:\n"
        f"    fields:\n      id: {{type: {contract_id}}}\n",
        "Honey.md": f"---\nkind: thing\nid: {note_id if note_id.isdigit() else repr(note_id)}\n---\n",
        "Diary.md": f"---\nkind: page\n---\n{prose}\n",
    })

    result = _sweep(charter, kb, "Honey")

    assert result.exit_code == 0, result.stdout
    assert bool(_mentioned_in(result)) is mentioned


# --- the note's own links ---


def test_lists_the_notes_own_outgoing_links(charter, make_kb):
    kb = _kb(make_kb, {
        "Zones/Canal.md": CANAL + "Flows past [[Mill]] and [[Nowhere]], see [[#Canal]].\n",
        "Zones/City.md": "---\nkind: zone\n---\n",
        "Mill.md": PAGE,
    })

    result = _sweep(charter, kb, "Canal")

    assert result.exit_code == 0, result.stdout
    assert result.json()["links_to"] == [
        {"line": 5, "field": "parent", "raw": "[[City]]", "target": "notes/Zones/City.md", "candidates": [
            "notes/Zones/City.md"]},
        {"line": 8, "field": None, "raw": "[[Mill]]", "target": "notes/Mill.md", "candidates": ["notes/Mill.md"]},
        {"line": 8, "field": None, "raw": "[[Nowhere]]", "target": None, "candidates": []},
    ]


# --- sweep: false ---


SWEPT_KB = {
    "Zones/Canal.md": CANAL + "Built from [[Survey]].\n",
    "Zones/City.md": "---\nkind: zone\n---\n",
    "Research/Survey.md": PAGE + "The [[Canal]] survey.\n",
    "Research/Live/Plan.md": PAGE + "The [[Canal]] plan.\n",
    "Index.md": PAGE + "[[Canal]]\n",
}


def test_notes_under_sweep_false_are_left_out_of_every_list(charter, make_kb):
    kb = _kb(make_kb, SWEPT_KB, paths='paths:\n  "Research/**": {sweep: false}\n')

    result = _sweep(charter, kb, "Canal")

    assert result.exit_code == 0, result.stdout
    assert _linked_from(result) == [("notes/Index.md", 4, None, "[[Canal]]")]
    assert _mentioned_in(result) == []
    assert [link["raw"] for link in result.json()["links_to"]] == ["[[City]]"]


def test_a_narrower_glob_can_sweep_again(charter, make_kb):
    kb = _kb(
        make_kb,
        SWEPT_KB,
        paths='paths:\n  "Research/**": {sweep: false}\n  "Research/Live/**": {sweep: true}\n',
    )

    result = _sweep(charter, kb, "Canal")

    assert [path for path, *_ in _linked_from(result)] == ["notes/Index.md", "notes/Research/Live/Plan.md"]


def test_a_note_under_sweep_false_can_itself_be_swept(charter, make_kb):
    kb = _kb(make_kb, SWEPT_KB, paths='paths:\n  "Research/**": {sweep: false}\n')

    result = _sweep(charter, kb, "Survey")

    assert result.exit_code == 0, result.stdout
    assert _linked_from(result) == [("notes/Zones/Canal.md", 8, None, "[[Survey]]")]


def test_sweep_policy_must_be_a_boolean_and_is_described(charter, make_kb):
    bad = _kb(make_kb, {"Index.md": PAGE}, paths='paths:\n  "Research/**": {sweep: no-thanks}\n')
    assert charter("validate", cwd=bad).exit_code == 2

    good = _kb(make_kb, {"Index.md": PAGE}, paths='paths:\n  "Research/**": {sweep: false}\n')
    described = charter("describe", cwd=good)
    assert "| `Research/**` | left out of `charter sweep` results |" in described.stdout


# --- naming the note ---


@pytest.mark.parametrize("named", ["Canal", "[[Canal]]", "Zones/Canal", "Zones/Canal.md", "The Cut"])
def test_the_note_is_named_as_a_wikilink_would_name_it(charter, make_kb, named):
    kb = _kb(make_kb, {"Zones/Canal.md": CANAL, "Zones/City.md": "---\nkind: zone\n---\n"})

    result = _sweep(charter, kb, named)

    assert result.exit_code == 0, result.stdout
    assert result.json()["note"] == "notes/Zones/Canal.md"


def test_the_note_may_be_a_file_path_from_the_working_directory(charter, make_kb):
    kb = _kb(make_kb, {"Zones/Canal.md": CANAL, "Zones/City.md": "---\nkind: zone\n---\n"})

    result = charter("sweep", "../Zones/Canal.md", "--config", "../../charter.yaml", "--format", "json",
                     cwd=kb / "notes" / "Zones")

    assert result.exit_code == 0, result.stdout
    assert result.json()["note"] == "notes/Zones/Canal.md"


def test_an_unknown_note_is_a_usage_error_with_a_suggestion(charter, make_kb):
    kb = _kb(make_kb, {"Zones/Canal.md": CANAL, "Zones/City.md": "---\nkind: zone\n---\n"})

    result = _sweep(charter, kb, "Canall")

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert diagnostic["code"] == "usage/unknown-note"
    assert diagnostic["hint"] == "Did you mean `Canal`?"


def test_an_ambiguous_note_is_a_usage_error_listing_the_candidates(charter, make_kb):
    kb = _kb(make_kb, {"Zones/Canal.md": CANAL, "Zones/City.md": "---\nkind: zone\n---\n", "Old/Canal.md": PAGE})

    result = _sweep(charter, kb, "Canal")

    assert result.exit_code == 2
    [diagnostic] = result.json()["diagnostics"]
    assert diagnostic["code"] == "usage/ambiguous-note"
    assert "`notes/Old/Canal.md`, `notes/Zones/Canal.md`" in diagnostic["message"]


def test_a_file_that_is_not_a_note_is_a_usage_error(charter, make_kb):
    kb = _kb(make_kb, {"map.png": "png", "Index.md": PAGE}, paths='paths:\n  "Drafts/**": {ignore: true}\n')
    (kb / "notes" / "Drafts").mkdir()
    (kb / "notes" / "Drafts" / "Idea.md").write_text(PAGE, encoding="utf-8")

    for named in ("map.png", "notes/Drafts/Idea.md"):
        result = _sweep(charter, kb, named)
        assert result.exit_code == 2
        assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/not-a-note"]


def test_an_existing_file_outside_the_knowledge_base_is_not_a_note(charter, make_kb, tmp_path_factory):
    kb = _kb(make_kb, {"Canal.md": PAGE})
    outside = tmp_path_factory.mktemp("elsewhere") / "Canal.md"
    outside.write_text(PAGE, encoding="utf-8")
    (kb / "Canal.md").write_text(PAGE, encoding="utf-8")

    for named in (str(outside), "Canal.md"):
        result = _sweep(charter, kb, named)
        assert result.exit_code == 2
        assert [d["code"] for d in result.json()["diagnostics"]] == ["usage/not-a-note"]


def test_an_invalid_contract_is_a_usage_error(charter, make_kb):
    kb = make_kb({"charter.yaml": "charter: 1\nkinds: [oops]\n"})

    assert _sweep(charter, kb, "Canal").exit_code == 2


# --- formats ---


FORMAT_KB = {
    "Zones/Canal.md": CANAL + "Next to [[City]].\n",
    "Zones/City.md": "---\nkind: zone\n---\nHome of the Grand Canal.\n",
    "Index.md": PAGE + "[[Canal]] and [[Gone]]\n",
}


def test_text_output(charter, make_kb):
    kb = _kb(make_kb, {**FORMAT_KB, "Lost.md": "---\nkind: [\n---\n"})

    result = charter("sweep", "Canal", cwd=kb)

    assert result.exit_code == 0, result.stdout
    assert result.stdout == (
        "Sweep of `notes/Zones/Canal.md`\n"
        "\n"
        "Linked from (1):\n"
        "  notes/Index.md:4  [[Canal]]\n"
        "\n"
        "Mentioned in (1):\n"
        "  notes/Zones/City.md:4  Grand Canal\n"
        "\n"
        "Links to (2):\n"
        "  5  parent: [[City]] -> notes/Zones/City.md\n"
        "  8  [[City]] -> notes/Zones/City.md\n"
        "\n"
        "Not searched, as charter could not read them (1):\n"
        "  notes/Lost.md\n"
    )


def test_text_output_with_nothing_found(charter, make_kb):
    kb = _kb(make_kb, {"Lone.md": PAGE})

    result = charter("sweep", "Lone", cwd=kb)

    assert result.stdout == (
        "Sweep of `notes/Lone.md`\n\nLinked from: none\n\nMentioned in: none\n\nLinks to: none\n"
    )


def test_agent_output(charter, make_kb):
    kb = _kb(make_kb, FORMAT_KB)

    result = charter("sweep", "Canal", "--format", "agent", cwd=kb)

    assert result.exit_code == 0, result.stdout
    assert result.stdout == (
        "linked-from notes/Index.md:4 [[Canal]]\n"
        "mentioned-in notes/Zones/City.md:4 Grand Canal\n"
        "links-to notes/Zones/City.md (line 5, parent: [[City]])\n"
        "links-to notes/Zones/City.md (line 8, [[City]])\n"
    )


def test_unresolved_and_ambiguous_outgoing_links_in_text(charter, make_kb):
    kb = _kb(make_kb, {
        "Index.md": PAGE + "[[Gone]] [[Twin]]\n",
        "A/Twin.md": PAGE,
        "B/Twin.md": PAGE,
    })

    result = charter("sweep", "Index", cwd=kb)

    assert "  4  [[Gone]] -> unresolved\n" in result.stdout
    assert "  4  [[Twin]] -> ambiguous: notes/A/Twin.md, notes/B/Twin.md\n" in result.stdout


def test_json_lists_unreadable_notes(charter, make_kb):
    kb = _kb(make_kb, {**FORMAT_KB, "Lost.md": "---\nkind: [\n---\n"})

    result = _sweep(charter, kb, "Canal")

    assert result.json()["unsearched"] == ["notes/Lost.md"]
