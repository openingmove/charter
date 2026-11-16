"""Helpers the link tests share: a small contract with link fields, and running `validate` over a knowledge base."""

KINDS = (
    "common_fields: [aliases]\n"
    "kinds:\n"
    "  page: {}\n"
    "  zone: {}\n"
    "  npc: {}\n"
    "  thing:\n"
    "    fields:\n"
    "      zone: {type: link, to: zone}\n"
    "      requires: {type: list, of: link, to: [thing, npc]}\n"
    "      anywhere: {type: link}\n"
)
PAGE = "---\nkind: page\n---\n"


def codes(result):
    return [(d["path"], d["line"], d["code"]) for d in result.json()["diagnostics"]]


def kb(make_kb, notes, top=""):
    files = {"charter.yaml": f"charter: 1\nroot: notes\n{top}{KINDS}"}
    files.update({f"notes/{path}": text for path, text in notes.items()})
    return make_kb(files)


def validate(charter, kb, *extra):
    return charter("validate", "--profile", "ci", "--format", "json", *extra, cwd=kb)
