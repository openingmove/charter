import shlex

import pytest

from conftest import FIXTURES

DESCRIBE = FIXTURES / "describe"

BOOK = """\
charter: 1
root: docs
kinds:
  book:
    description: "A book on the shelf."
    path: "Books/{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true, matches_filename: true, description: "As printed on the cover."}
      author: {type: link, required: true}
      pages: {type: int, range: [1, 5000]}
"""


def describe(charter, kb, *args):
    return charter("describe", *args, "--format", "json", cwd=kb)


def test_a_kind_is_described_with_its_path_fields_and_new_command(charter, make_kb):
    kb = make_kb({"charter.yaml": BOOK, "docs/.keep": ""})
    result = describe(charter, kb, "book")
    assert result.exit_code == 0
    [book] = result.json()["kinds"]
    assert book["name"] == "book"
    assert book["description"] == "A book on the shelf."
    assert book["path"] == "docs/Books/{title}.md"
    assert book["new_command"] == 'charter new book "TITLE" --set author=AUTHOR'
    fields = {field["name"]: field for field in book["fields"]}
    assert list(fields) == ["kind", "title", "author", "pages"]
    assert fields["title"]["description"] == "As printed on the cover."
    assert fields["title"]["required"] is True
    assert fields["pages"]["required"] is False
    assert fields["pages"]["expects"] == "an integer, from 1 to 5000"


def test_describing_the_whole_contract_matches_the_golden_markdown(charter, golden):
    result = charter("describe", cwd=DESCRIBE)
    assert result.exit_code == 0
    golden("describe", result.stdout, "all.md")


def test_describing_the_whole_contract_matches_the_golden_json(charter, golden):
    result = describe(charter, DESCRIBE)
    assert result.exit_code == 0
    golden("describe", result.json(), "all.json")


def test_describing_a_variant_matches_the_golden_markdown(charter, golden):
    result = charter("describe", "recipe/bread", cwd=DESCRIBE)
    assert result.exit_code == 0
    golden("describe", result.stdout, "recipe-bread.md")


def test_the_whole_contract_covers_every_kind_and_variant_with_path_policies_and_checks(charter):
    document = describe(charter, DESCRIBE).json()
    assert [shape["name"] for shape in document["kinds"]] == [
        "recipe",
        "recipe/bread",
        "pantry",
        "pantry/dry",
        "pantry/cold",
        "note",
    ]
    assert [policy["glob"] for policy in document["paths"]] == ["Templates/**", "Recipes/**", "Recipes/Drafts/**"]
    checks = {check["id"]: check for check in document["checks"]}
    assert checks["tags"]["enabled"] is False
    assert checks["links"]["severity"] == "warning"
    assert "schema/type" in checks["schema"]["codes"]


def test_a_kind_is_described_with_its_variants_only(charter):
    document = describe(charter, DESCRIBE, "pantry").json()
    assert [shape["name"] for shape in document["kinds"]] == ["pantry", "pantry/dry", "pantry/cold"]
    assert "paths" not in document
    assert "checks" not in document


def test_a_variant_has_its_own_description_template_fields_and_command(charter):
    [bread] = describe(charter, DESCRIBE, "recipe/bread").json()["kinds"]
    assert bread["description"] == "A recipe that rises."
    assert bread["selection"] == {"method": "bake"}
    assert bread["template"] == "docs/Templates/Bread.md"
    assert [(entry["level"], entry["text"], entry["repeat"]) for entry in bread["outline"]] == [
        (1, "{{title}}", False),
        (2, "Dough", False),
        (2, "Bake {{date}}", True),
    ]
    assert "proof_hours" in [field["name"] for field in bread["fields"]]
    assert bread["new_command"] == 'charter new recipe/bread "TITLE" --set proof_hours=PROOF_HOURS'


def test_a_variant_keeps_what_it_does_not_declare_from_its_kind(charter):
    [cold] = describe(charter, DESCRIBE, "pantry/cold").json()["kinds"]
    [dry] = describe(charter, DESCRIBE, "pantry/dry").json()["kinds"]
    assert cold["path"] == "docs/Fridge/{title}.md"
    assert dry["path"] == "docs/Pantry/{shelf}/{title}.md"
    assert dry["unknown_fields"] is None
    assert dry["new_command"] == 'charter new pantry/dry "TITLE"'


def test_a_variant_by_field_allows_the_variant_names(charter):
    [pantry, *_] = describe(charter, DESCRIBE, "pantry").json()["kinds"]
    shelf = next(field for field in pantry["fields"] if field["name"] == "shelf")
    assert shelf["values"] == ["dry", "cold"]
    assert pantry["new_command"] == 'charter new pantry "TITLE" --set shelf=SHELF'


def test_the_new_command_leaves_out_what_charter_new_fills_in(charter):
    [recipe, _] = describe(charter, DESCRIBE, "recipe").json()["kinds"]
    # id and added are `auto`, stage has a default, published_in is only conditionally required.
    assert recipe["new_command"] == 'charter new recipe "TITLE" --set method=METHOD'


def test_a_kind_without_a_path_has_no_new_command(charter):
    [note] = describe(charter, DESCRIBE, "note").json()["kinds"]
    assert note["path"] is None
    assert note["new_command"] is None


def test_a_date_default_is_given_as_yyyy_mm_dd(charter):
    [note] = describe(charter, DESCRIBE, "note").json()["kinds"]
    since = next(field for field in note["fields"] if field["name"] == "since")
    assert since["default"] == "2026-01-31"


@pytest.mark.parametrize("named", ["recipe", "recipe/bread", "pantry", "pantry/cold"])
def test_the_new_command_creates_a_note_once_its_values_are_filled_in(charter, make_kb, named):
    kb = make_kb({
        relative: (DESCRIBE / relative).read_text(encoding="utf-8")
        for relative in ("charter.yaml", "docs/Templates/Recipe.md", "docs/Templates/Bread.md")
    })
    [shape] = [s for s in describe(charter, kb, named).json()["kinds"] if s["name"] == named]
    filled = {"TITLE": "Soda Bread", "METHOD": "fry", "PROOF_HOURS": "2", "SHELF": "dry"}
    argv = [_fill(word, filled) for word in shlex.split(shape["new_command"])]
    assert argv[0] == "charter"
    result = charter(*argv[1:], cwd=kb)
    assert result.exit_code == 0, result.stdout


def _fill(word, values):
    name, equals, value = word.partition("=")
    return f"{name}={values[value]}" if equals else values.get(word, word)


@pytest.mark.parametrize("named, code", [("recpe", "usage/unknown-kind"), ("recipe/rye", "usage/unknown-variant")])
def test_an_unknown_kind_or_variant_is_a_usage_error(charter, named, code):
    result = describe(charter, DESCRIBE, named)
    assert result.exit_code == 2
    assert [d["code"] for d in result.json()["diagnostics"]] == [code]


def test_a_usage_error_is_reported_as_text_when_markdown_was_asked_for(charter):
    result = charter("describe", "recpe", cwd=DESCRIBE)
    assert result.exit_code == 2
    assert "usage/unknown-kind" in result.stdout
    assert "Did you mean `recipe`?" in result.stdout


@pytest.mark.parametrize(
    "replaced, location",
    [
        ('description: "A book on the shelf."', "kinds.book.description"),
        ('description: "As printed on the cover."', "kinds.book.fields.title.description"),
    ],
)
def test_a_description_must_be_text(charter, make_kb, replaced, location):
    kb = make_kb({"charter.yaml": BOOK.replace(replaced, "description: 3"), "docs/.keep": ""})
    result = describe(charter, kb)
    assert result.exit_code == 2
    [problem] = result.json()["diagnostics"]
    assert problem["message"] == f"{location}: expected text, got `3`."


@pytest.mark.parametrize(
    "replaced, written, location",
    [
        ('description: "A book on the shelf."', r'description: "A book\non the shelf."', "kinds.book.description"),
        # A folded block keeps its final line break.
        (
            'title: {type: string, required: true, matches_filename: true, description: "As printed on the cover."}',
            "title:\n        type: string\n        required: true\n        description: >\n          As printed.\n",
            "kinds.book.fields.title.description",
        ),
    ],
)
def test_a_description_is_one_line(charter, make_kb, replaced, written, location):
    kb = make_kb({"charter.yaml": BOOK.replace(replaced, written), "docs/.keep": ""})
    result = describe(charter, kb)
    assert result.exit_code == 2
    [problem] = result.json()["diagnostics"]
    assert problem["message"] == f"{location}: a description is one line."


def _field(shape, name):
    return next(field for field in shape["fields"] if field["name"] == name)


def test_the_kind_points_at_the_variant_a_value_selects(charter):
    [recipe, _] = describe(charter, DESCRIBE, "recipe").json()["kinds"]
    assert recipe["variants"] == [{"name": "recipe/bread", "selection": {"method": "bake"}}]
    assert _field(recipe, "method")["selects"] == [{"value": "bake", "variant": "recipe/bread"}]

    text = charter("describe", "recipe", cwd=DESCRIBE).stdout
    assert "  - `recipe/bread`: `method` is `bake`." in text
    assert "`bake` makes it `recipe/bread`" in text
    assert "A value that selects a variant creates that variant instead: use the variant's own command." in text


def test_a_field_the_variant_fixes_has_only_that_value(charter):
    [bread] = describe(charter, DESCRIBE, "recipe/bread").json()["kinds"]
    [cold] = describe(charter, DESCRIBE, "pantry/cold").json()["kinds"]
    assert _field(bread, "method")["fixed"] == "bake"
    assert _field(cold, "shelf")["fixed"] == "cold"
    assert _field(bread, "stage")["fixed"] is None
    text = charter("describe", "recipe/bread", cwd=DESCRIBE).stdout
    assert "| `method` | yes | always `bake`, which makes the note this variant |" in text


def test_the_discriminator_names_the_kind_even_when_undeclared(charter, make_kb):
    [recipe, _] = describe(charter, DESCRIBE, "recipe").json()["kinds"]
    assert _field(recipe, "kind")["discriminator"] is True
    assert _field(recipe, "kind")["fixed"] == "recipe"
    assert "| `kind` | yes | names the kind: always `recipe` |" in charter("describe", "recipe", cwd=DESCRIBE).stdout

    kb = make_kb({"charter.yaml": BOOK.replace("      kind: {type: string, required: true}\n", ""), "docs/.keep": ""})
    [book] = describe(charter, kb, "book").json()["kinds"]
    assert [field["name"] for field in book["fields"]][:2] == ["kind", "title"]
    assert _field(book, "kind")["fixed"] == "book"


def test_the_outline_carries_the_templates_guidance(charter):
    [recipe, bread] = describe(charter, DESCRIBE, "recipe").json()["kinds"]
    assert recipe["outline"][0] == {
        "level": 1,
        "text": "{{title}}",
        "optional": False,
        "repeat": False,
        "guide": "why it is worth cooking again",
    }
    assert recipe["outline"][3]["optional"] is True
    assert bread["lead"] == "Start from the flour you have."
    text = charter("describe", "recipe", cwd=DESCRIBE).stdout
    assert "- `# {{title}}`: why it is worth cooking again" in text
    assert "- `## Variations` (optional)" in text


def test_field_rules_are_given_as_data(charter):
    [recipe, _] = describe(charter, DESCRIBE, "recipe").json()["kinds"]
    [pantry, *_] = describe(charter, DESCRIBE, "pantry").json()["kinds"]
    assert _field(recipe, "serves")["range"] == [1, 12]
    assert _field(recipe, "code")["pattern"] == r"R\d+|X"
    assert _field(recipe, "stage")["values"] == ["idea", "tested", "published"]
    assert _field(pantry, "stocks")["to"] == ["recipe"]
