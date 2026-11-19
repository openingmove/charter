"""Helpers the plugin tests share: a knowledge base with sample plugins copied in, and the `probe` plugin set up over a
small linked set of notes."""

import shutil

from conftest import FIXTURES

KINDS = "kinds:\n  entry: {}\n"
NOTE = "---\nkind: entry\n---\n# Plans\n\n## A secret step\n\nSee [[b]].\n"
OTHER = "---\nkind: entry\n---\n# Secret notes\n"

PROBE = "  probe:\n    source: tools/probe\n"
KINDS_TWO = "kinds:\n  entry: {}\n  place: {}\n"
LINKED = {
    "a.md": NOTE,
    "b.md": OTHER,
    "c.md": "---\nkind: entry\n---\n# Unrelated\n",
    "d.md": "---\nkind: entry\n---\nBack to [[a]].\n",
    "Places/Town.md": "---\nkind: place\n---\n# Town\n",
}


def plugin_kb(make_kb):
    """A factory for a knowledge base under `notes/` whose contract ends with `checks`, and the named sample plugins in
    `tools/`. A test module returns it from its own `kb` fixture."""

    def make(checks, plugins=(), notes=None, top="", kinds=KINDS):
        notes = notes if notes is not None else {"a.md": NOTE, "b.md": OTHER}
        base = make_kb({
            "charter.yaml": f"charter: 1\nroot: notes\n{top}{kinds}checks:\n  agents-include: {{enabled: false}}\n{checks}",
            **{f"notes/{path}": text for path, text in notes.items()},
        })
        for name in plugins:
            shutil.copytree(FIXTURES / "plugins" / name, base / "tools" / name)
        return base

    return make


def rewrite_manifest(directory, **changes):
    """Set each manifest key to its value; a falsy value removes the key."""
    manifest = directory / "charter-plugin.yaml"
    lines = manifest.read_text(encoding="utf-8").splitlines()
    for key, value in changes.items():
        lines = [line for line in lines if not line.startswith(f"{key}:")] + ([f"{key}: {value}"] if value else [])
    manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")


def probe(kb, notes=None, **manifest):
    """The `probe` plugin enabled over `LINKED` (or `notes`), its manifest changed by `manifest`."""
    base = kb(PROBE, ["probe"], notes=notes if notes is not None else LINKED, kinds=KINDS_TWO)
    rewrite_manifest(base / "tools" / "probe", **manifest)
    return base
