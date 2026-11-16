"""Every YAML the tool writes carries each value literally: no anchors, no aliases."""

import datetime

from charter import yamlsource
from charter.lock import DevSource, GitSource, Locked, write_lock

CONTRACT = """\
charter: 1
root: docs
kinds:
  entry:
    path: "Entries/{title}.md"
    fields:
      kind: {type: string, required: true}
      title: {type: string, required: true}
      created: {type: date, required: true, auto: today}
      updated: {type: date, required: true, auto: today}
      tags: {type: list, of: string, default: [coast]}
      labels: {type: list, of: string, default: [coast]}
"""


def test_charter_new_writes_two_equal_dates_literally(charter, make_kb):
    kb = make_kb({"charter.yaml": CONTRACT, "docs/.keep": ""})
    before = datetime.date.today().isoformat()

    result = charter("new", "entry", "Lighthouse", "--format", "agent", cwd=kb)

    days = {before, datetime.date.today().isoformat()}
    assert result.exit_code == 0, result.stdout
    text = (kb / "docs/Entries/Lighthouse.md").read_text(encoding="utf-8")
    assert "&" not in text and "*" not in text
    assert any(f"created: {day}\nupdated: {day}\n" in text for day in days)
    assert "tags:\n- coast\nlabels:\n- coast\n" in text


def test_dump_writes_shared_and_nested_mappings_literally():
    shared = {"a": ["x"]}

    assert yamlsource.dump({"one": shared, "two": {"inner": shared}}) == (
        "one:\n  a:\n  - x\ntwo:\n  inner:\n    a:\n    - x\n"
    )


def test_the_lock_is_written_without_aliases_for_shared_lock_entries(tmp_path):
    """At `write_lock` level: the lock writer is only reachable through `plugin add`, which never shares objects."""
    source = GitSource("https://example.com/p.git", "main", "abc")
    entry = Locked("1.0.0", source, "0" * 64)
    plugins = {"a": entry, "b": entry, "c": Locked("1.0.0", DevSource(), "0" * 64)}

    write_lock(tmp_path, plugins)

    text = (tmp_path / "charter.lock").read_text(encoding="utf-8")
    assert "&" not in text and "*" not in text
    assert text.count("git: https://example.com/p.git\n") == 2
