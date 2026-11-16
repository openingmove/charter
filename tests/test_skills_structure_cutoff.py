"""The skills propose, date and respect a kind's structure cutoff.

Skills are instruction text that an agent follows, so there is no harness that runs them. These tests do the
two things that can be checked: they read the skill and plan-format files for what the instructions must say,
and they walk the instructions' own steps by hand against the real CLI, running the exact commands the skills
print (extracted from the files, never retyped here) on small invented knowledge bases, with the interpreter
chosen the way the skill says (the first of python3, python and py -3), not by borrowing pytest's own.
"""

import datetime
import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import run_git

ROOT = Path(__file__).resolve().parent.parent
SKILLS = ROOT / "skills"
SPARSE = ROOT / "examples" / "sparse-history"
MIGRATE_DATES = SKILLS / "migrate" / "dates.md"
EVOLVE_DATES = SKILLS / "evolve" / "dates.md"
PLAN_FORMAT = SKILLS / "establish" / "migration-plan.md"
EVOLVE_PLAN = SKILLS / "evolve" / "plan.md"

# Read once, so a run that crosses midnight sees one day; no test reads the clock again.
TODAY = datetime.date.today()
YESTERDAY = TODAY - datetime.timedelta(days=1)


def _text(path):
    return re.sub(r"\s+", " ", path.read_text("utf-8"))


# --- no skill offers to move a cutoff ---

# A cutoff is part of the contract: skills never move it, offer to, or list moving it as a way to spare
# notes. The pattern catches an offer in any wording, negated or not, so skill text avoids the
# phrasing altogether and says only that the cutoff stays and a human edits the contract by hand.
OFFERS = re.compile(
    r"\b(?:move|moves|moving|change|changes|changing|raise|raises|raising|push|pushing|bump|bumping|"
    r"adjust|adjusting|postpone|postponing|delay|delaying|extend|extending|shift|shifting)\s+"
    r"(?:the|a|an|this|that|its|any|their|your)\s+(?:(?:structure\s+)?cutoff|date\s+of\s+the\s+cutoff)"
    r"|\b(?:later|newer|different|another|alternative)\s+(?:structure\s+)?cutoff\b"
    r"|\bcutoff\s+(?:later|forward)\b",
    re.IGNORECASE,
)


def _skill_files():
    return sorted(p for p in SKILLS.rglob("*") if p.is_file() and "kinds" not in p.relative_to(SKILLS).parts)


@pytest.mark.parametrize(
    "offer",
    [
        "Offer to move the cutoff later.",
        "You could change the structure cutoff to spare these notes.",
        "Raising the cutoff avoids touching the notes.",
        "pick a later cutoff",
        "Never move the cutoff.",  # even a negation: skill text avoids the phrasing altogether
    ],
)
def test_the_offer_detector_catches_offers(offer):
    assert OFFERS.search(offer)


@pytest.mark.parametrize(
    "fine",
    [
        "A human who wants a different date edits the contract by hand.",
        "The cutoff stays exactly as the draft has it.",
        "Move the content, then check links. The cutoff is fixed.",
        "Editing a legacy note would move it past the cutoff.",
        "A note edited on the day of this change, which is the cutoff day, is judged.",
        "When the change sets a cutoff, find a date for each note.",
    ],
)
def test_the_offer_detector_leaves_ordinary_text_alone(fine):
    assert not OFFERS.search(fine)


def test_no_skill_text_offers_to_move_a_cutoff():
    found = [
        f"{path.relative_to(ROOT)}: {match.group(0)!r}"
        for path in _skill_files()
        for match in OFFERS.finditer(_text(path))
    ]

    assert not found, (
        "A skill file words something as moving, changing or choosing another cutoff. A structure cutoff is "
        "part of the contract and no skill moves it or offers to; say instead that it stays and "
        "that a human who wants another date edits the contract by hand.\n" + "\n".join(found)
    )


@pytest.mark.parametrize("skill", ["establish", "migrate", "evolve"])
def test_each_skill_leaves_the_cutoff_to_a_human_editing_the_contract(skill):
    assert "edits the contract by hand" in _text(SKILLS / skill / "SKILL.md")


# --- what each skill's instructions must say ---


def test_establish_proposes_a_cutoff_with_a_required_date_field():
    text = _text(SKILLS / "establish" / "SKILL.md")

    assert "structure_cutoff: {field: FIELD, date: DAY}" in text
    assert "template and existing notes" in text
    assert "migration day" in text and "unquoted" in text
    assert "`type: date` and `required: true`" in text
    assert "never an update date" in text
    assert "before approval" in text  # the human may give another date first


def test_establish_writes_the_cutoff_into_the_plan_it_hands_to_migrate():
    assert "`Dates` section" in _text(SKILLS / "establish" / "SKILL.md")


def test_migrate_dates_each_undated_note_and_shows_the_dates_first():
    skill = _text(SKILLS / "migrate" / "SKILL.md")
    rules = _text(MIGRATE_DATES)

    assert "[dates.md](dates.md)" in skill
    assert skill.index("`Dates` section") < skill.index("`Folders` states")  # walked through first
    assert "before any note is written or edited" in rules
    for source in ("first-commit author date", "modified time", "one date", "day before the cutoff"):
        assert source in rules


def test_migrate_creates_notes_already_dated_and_has_a_line_for_dating_existing_ones():
    moving = _text(SKILLS / "migrate" / "moving.md")

    assert "--set FIELD=DATE" in moving
    assert "## `Date NOTE: DATE`" in (SKILLS / "migrate" / "moving.md").read_text("utf-8")


def test_evolve_sets_a_cutoff_only_with_a_kinds_first_template():
    skill = _text(SKILLS / "evolve" / "SKILL.md")
    rules = _text(EVOLVE_DATES)

    assert "adds a kind's first template to a kind that already has notes" in skill
    assert "In no other case set one" in skill
    assert "date field is part of that change" in rules
    assert "`type: date` and `required: true`" in rules


def test_evolve_fallout_needs_no_special_case_for_legacy_notes():
    assert "needs no special case" in _text(SKILLS / "evolve" / "fallout.md")


# --- the plan format says where dates go ---


def _template(path):
    return re.search(r"````markdown\n(.*?)````", path.read_text("utf-8"), re.DOTALL).group(1)


def _sections(markdown):
    parts = re.split(r"^## (.+)$", markdown, flags=re.MULTILINE)
    return dict(zip(parts[1::2], parts[2::2], strict=True))


@pytest.mark.parametrize("plan", [PLAN_FORMAT, EVOLVE_PLAN], ids=["migrate", "evolve"])
def test_the_plan_template_shows_dates_right_after_folders_with_none_past_the_cutoff(plan):
    sections = _sections(_template(plan))
    names = list(sections)

    assert names.index("Dates") == names.index("Folders") + 1
    kind = re.search(r"cutoff `([\d-]+)`, latest `([\d-]+)`", sections["Dates"])
    cutoff, latest = (datetime.date.fromisoformat(value) for value in kind.groups())
    assert latest == cutoff - datetime.timedelta(days=1)
    notes = re.findall(r"^- `([^`]+\.md)`: `([\d-]+)` \((first commit|modified|given)", sections["Dates"], re.M)
    assert notes
    assert all(datetime.date.fromisoformat(day) <= latest for _, day, _ in notes)


@pytest.mark.parametrize("plan", [PLAN_FORMAT, EVOLVE_PLAN], ids=["migrate", "evolve"])
def test_every_existing_note_in_dates_has_its_date_line_and_dating_comes_first(plan):
    sections = _sections(_template(plan))
    progress = [line for line in sections["Progress"].splitlines() if line.startswith("- [ ]")]
    created = set(re.findall(r"- \[ \] Created `([^`]+)`", sections["Progress"]))
    matches = (re.match(r"- \[ \] Date `([^`]+)`: `([\d-]+)`$", line) for line in progress)
    dated = [(m.group(1), m.group(2)) for m in matches if m]

    bullets = re.findall(r"^- `([^`]+\.md)`: `([\d-]+)` \((first commit|modified|given)", sections["Dates"], re.M)
    for note, day, _ in bullets:
        assert (note in created) != ((note, day) in dated), f"{note}: exactly one of a Created line or a Date line"
    dates_at = [n for n, line in enumerate(progress) if " Date `" in line]
    # A fix that adds frontmatter comes before the dates: a note needs its block before it can hold a date.
    work_at = [n for n, line in enumerate(progress) if re.match(r"- \[ \] (Created|Source|Fix) ", line) and ": add frontmatter " not in line]
    assert dates_at and max(dates_at) < min(work_at)


def test_the_plan_format_documents_the_note_bullet_and_the_clamped_form():
    text = _text(PLAN_FORMAT)

    for phrase in ("first commit", "modified", "given", "clamped from", "never later than `LATEST`"):
        assert phrase in text
    assert "Dates` is present only when a kind in the draft has a `structure_cutoff`" in text


# --- walking the instructions against the real CLI ---

TEMPLATE = "# {{title}}\n\n## Summary\n\n## Details\n"


def _contract(cutoff, template=True, field="created: {type: date, required: true}"):
    return (
        "charter: 1\nroot: .\n"
        "paths:\n  'Templates/**': {ignore: true}\n  'README.md': {ignore: true}\n"
        "kinds:\n  story:\n    description: A story.\n"
        + ("    template: Templates/Story.md\n" if template else "")
        + '    path: "stories/{title}.md"\n'
        + (f"    structure_cutoff: {{field: created, date: {cutoff}}}\n" if cutoff else "")
        + "    fields:\n      kind: {type: string, required: true}\n"
        "      title: {type: string, required: true, matches_filename: true}\n"
        f"      {field}\n"
    )


def test_establish_walkthrough_a_sparse_kb_gets_a_cutoff_and_a_required_date_field(charter, tmp_path):
    kb = tmp_path / "sparse-history"
    shutil.copytree(SPARSE, kb)
    survey = charter("survey", str(kb), "--format", "json", cwd=tmp_path).json()
    assert survey["totals"]["with_frontmatter"] == 0  # sparse: existing notes, none of them dated
    (kb / "Templates").mkdir()
    (kb / "Templates" / "Story.md").write_text(TEMPLATE, encoding="utf-8")
    # The draft Establish writes for a `story` kind with a template and existing notes (SKILL.md step 9).
    draft = kb / "charter.draft.yaml"
    draft.write_text(_contract(TODAY.isoformat()), encoding="utf-8")

    result = charter("describe", "--config", str(draft), "--format", "json", cwd=kb)

    assert result.exit_code == 0, result.stdout
    declared = yaml.safe_load(draft.read_text("utf-8"))["kinds"]["story"]
    assert declared["structure_cutoff"] == {"field": "created", "date": TODAY}  # an unquoted date: the migration day
    assert declared["fields"]["created"] == {"type": "date", "required": True}


@pytest.mark.parametrize(
    ("contract", "complaint"),
    [
        (_contract(TODAY.isoformat(), field="created: {type: date}"), "required"),
        (_contract(TODAY.isoformat(), field="created: {type: string, required: true}"), "date"),
        (_contract(f"'{TODAY.isoformat()}'"), "date"),
        (_contract(TODAY.isoformat(), template=False), "template"),
    ],
    ids=["not-required", "not-a-date-field", "quoted-date", "no-template"],
)
def test_establish_must_get_each_condition_right_or_the_contract_does_not_load(charter, tmp_path, contract, complaint):
    (tmp_path / "Templates").mkdir()
    (tmp_path / "Templates" / "Story.md").write_text(TEMPLATE, encoding="utf-8")
    (tmp_path / "charter.draft.yaml").write_text(contract, encoding="utf-8")

    result = charter("describe", "--config", "charter.draft.yaml", cwd=tmp_path)

    assert result.exit_code == 2
    assert complaint in result.stdout


def _blocks(path):
    """The fenced one-line commands of a skill file, as written."""
    text = path.read_text("utf-8")
    return [m.group(2).strip() for m in re.finditer(r"^( *)```\n(.*?)\n\1```$", text, re.M | re.S)]


INTERPRETERS = (["python3"], ["python"], ["py", "-3"])  # the order dates.md tells the agent to try
PLACEHOLDERS = {"FILE"}  # the argument the agent fills in


def _commands(path):
    """The commands as argv lists (placeholders dropped), the interpreter still spelled as the skill spells it.

    `shlex.split` checks POSIX quoting only; the Windows quoting (double quotes around the path) is checked by
    reading the text.
    """
    return [[word for word in shlex.split(block) if word not in PLACEHOLDERS] for block in _blocks(path)]


def _interpreter():
    """The first of the skill's three interpreter names that works here, never `sys.executable`."""
    for candidate in INTERPRETERS:
        if not shutil.which(candidate[0]):
            continue
        if subprocess.run([*candidate, "-c", "pass"], capture_output=True).returncode == 0:
            return candidate
    pytest.skip("none of python3, python or py -3 runs here, so the skill's own commands cannot be run")


def _run(command, *args, cwd=None):
    argv = [*_interpreter(), *command[1:]] if command[0] in {"python3", "python", "py"} else list(command)
    return subprocess.run([*argv, *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _command(containing):
    return next(c for c in _commands(MIGRATE_DATES) if any(containing in word for word in c))


def test_every_documented_command_names_an_allowed_tool_and_quotes_the_path():
    blocks = _blocks(MIGRATE_DATES)
    text = _text(MIGRATE_DATES)

    assert blocks
    for block in blocks:
        assert block.split()[0] in {"python3", "git"}, block
        assert '"FILE"' in block, block  # note names hold spaces
    assert "`python3`, `python` and `py -3`" in text
    assert "needs version 2.25 or newer" in text
    assert "ask the human for one date for each folder" in text


def test_the_two_dates_files_share_their_rules():
    # Skills install independently, so each carries its own copy; the shared rules must not drift.
    def shared(path):
        text = path.read_text("utf-8")
        return text[text.index("## Commands") : text.index("## Show before writing")]

    assert shared(MIGRATE_DATES) == shared(EVOLVE_DATES)


def _modified_day(file):
    return datetime.date.fromisoformat(_run(_command("os.stat"), str(file)).strip())


def _clamp(day, cutoff):
    # The skill states the clamp as plain arithmetic for the agent to do, not as a command.
    return min(day, cutoff - datetime.timedelta(days=1))


def _first_commit_day(repo, file):
    lines = _run(_command("--follow"), str(file), cwd=repo).split()
    return datetime.date.fromisoformat(lines[-1]) if lines else None


def _write_note(path, title, created=None, body="# {t}\n"):
    front = f"---\nkind: story\ntitle: {title}\n" + (f"created: {created}\n" if created else "") + "---\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(front + "\n" + body.format(t=title), encoding="utf-8")


def _set_modified(path, moment):
    os.utime(path, (moment.timestamp(), moment.timestamp()))


def _findings(charter, kb):
    result = charter("validate", "--profile", "ci", "--format", "json", cwd=kb)
    return sorted((d["path"], d["code"]) for d in result.json()["diagnostics"])


def _migrate_kb(tmp_path, today=TODAY):
    kb = tmp_path / "kb"
    (kb / "Templates").mkdir(parents=True)
    (kb / "Templates" / "Story.md").write_text(TEMPLATE, encoding="utf-8")
    contract = _contract(today.isoformat()) + "checks: {agents-include: {enabled: false}}\n"
    (kb / "charter.yaml").write_text(contract, encoding="utf-8")
    return kb


# The second day is one the real clock has already left, as after a run crosses midnight: the walkthrough must
# derive every date from the day it is given, never from the clock.
@pytest.mark.parametrize("today", [TODAY, TODAY - datetime.timedelta(days=1)], ids=["captured-today", "a-day-earlier"])
def test_migrate_walkthrough_modified_times_give_dates_all_before_the_cutoff(charter, tmp_path, today):
    kb = _migrate_kb(tmp_path, today)
    cutoff = today
    yesterday = today - datetime.timedelta(days=1)
    now = datetime.datetime.combine(today, datetime.time(12, 0))
    modified = {
        "Old tale": datetime.datetime(2020, 3, 4, 12, 0),
        "Edited on migration day": now,
        "Late tonight": datetime.datetime.combine(today, datetime.time(23, 59)),
        "From the future": now + datetime.timedelta(days=3),
    }
    for title, moment in modified.items():
        _write_note(kb / "stories" / f"{title}.md", title)
        _set_modified(kb / "stories" / f"{title}.md", moment)
    # Before dating, every note lacks the required field: that is why Migrate must date them.
    assert {code for _, code in _findings(charter, kb)} >= {"schema/required"}

    proposed = {}
    for title in modified:
        found = _modified_day(kb / "stories" / f"{title}.md")
        proposed[title] = _clamp(found, cutoff)
    assert proposed["Old tale"] == datetime.date(2020, 3, 4)
    assert _modified_day(kb / "stories" / "Edited on migration day.md") == today  # the local day, not the UTC day
    assert proposed["Edited on migration day"] == yesterday
    assert all(day < cutoff for day in proposed.values())

    for title, day in proposed.items():
        _write_note(kb / "stories" / f"{title}.md", title, created=day.isoformat())
    assert _findings(charter, kb) == []  # dated before the cutoff: legacy, no structure findings


def test_migrate_walkthrough_a_note_dated_on_the_cutoff_is_judged(charter, tmp_path):
    kb = _migrate_kb(tmp_path)
    _write_note(kb / "stories" / "Legacy.md", "Legacy", created=YESTERDAY.isoformat())
    _write_note(kb / "stories" / "Judged.md", "Judged", created=TODAY.isoformat())

    found = _findings(charter, kb)

    assert [path for path, code in found if code.startswith("structure/")] == ["stories/Judged.md"] * 2


def test_migrate_walkthrough_under_git_the_first_commit_author_date_is_used(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-q", "--initial-branch=main")
    note = repo / "stories" / "Old tale.md"
    _write_note(note, "Old tale")
    os.environ["GIT_AUTHOR_DATE"] = "2021-06-01T12:00:00+00:00"  # run_git passes the environment through
    try:
        run_git(repo, "add", "-A")
        run_git(repo, "commit", "-q", "-m", "first")
    finally:
        del os.environ["GIT_AUTHOR_DATE"]
    note.write_text(note.read_text("utf-8") + "\nLater edit.\n", encoding="utf-8")
    run_git(repo, "commit", "-q", "-am", "edit")
    untracked = repo / "stories" / "New.md"
    _write_note(untracked, "New")

    assert _first_commit_day(repo, note) == datetime.date(2021, 6, 1)  # not the later edit
    assert _first_commit_day(repo, untracked) is None  # never committed: the skill falls back to modified time
    assert _clamp(_first_commit_day(repo, note), TODAY) == datetime.date(2021, 6, 1)


def _same_finding(d):
    return (d["path"], d.get("line"), d["code"], d["message"])


def _fallout(charter, kb):
    options = ("--profile", "ci", "--format", "json")
    current = charter("validate", *options, cwd=kb).json()["diagnostics"]
    draft = charter("validate", "--config", "charter.draft.yaml", *options, cwd=kb).json()["diagnostics"]
    known = {_same_finding(d) for d in current}
    return [d for d in draft if _same_finding(d) not in known]


def test_evolve_walkthrough_a_first_template_sets_a_cutoff_and_old_notes_are_not_fallout(charter, tmp_path):
    kb = tmp_path / "kb"
    (kb / "Templates").mkdir(parents=True)
    (kb / "Templates" / "Story.md").write_text(TEMPLATE, encoding="utf-8")
    off = "checks: {agents-include: {enabled: false}}\n"
    # The current contract has the kind but no template and no date field.
    (kb / "charter.yaml").write_text(
        _contract(None, template=False, field="summary: {type: string}") + off,
        encoding="utf-8",
    )
    titles = ["First", "Second", "Third"]
    for title in titles:
        _write_note(kb / "stories" / f"{title}.md", title)
    # The draft adds the first template, the required date field and the cutoff together (evolve/dates.md).
    (kb / "charter.draft.yaml").write_text(_contract(TODAY.isoformat()) + off, encoding="utf-8")

    before = _fallout(charter, kb)
    # An undated note is not legacy: until the Dates section is applied it fails schema and structure.
    assert {d["code"] for d in before} == {"schema/required", "structure/missing-heading"}
    assert {d["path"] for d in before} == {f"stories/{t}.md" for t in titles}

    for title in titles:  # the plan's Dates section, applied
        _write_note(kb / "stories" / f"{title}.md", title, created=YESTERDAY.isoformat())
    after = charter("validate", "--config", "charter.draft.yaml", "--profile", "ci", "--format", "json", cwd=kb)

    assert after.exit_code == 0
    assert after.json()["diagnostics"] == []


def test_evolve_walkthrough_without_the_cutoff_the_first_template_fails_every_old_note(charter, tmp_path):
    kb = tmp_path / "kb"
    (kb / "Templates").mkdir(parents=True)
    (kb / "Templates" / "Story.md").write_text(TEMPLATE, encoding="utf-8")
    off = "checks: {agents-include: {enabled: false}}\n"
    (kb / "charter.yaml").write_text(_contract(None, template=False) + off, encoding="utf-8")
    _write_note(kb / "stories" / "First.md", "First", created=YESTERDAY.isoformat())
    (kb / "charter.draft.yaml").write_text(_contract(None) + off, encoding="utf-8")

    assert {d["code"] for d in _fallout(charter, kb)} >= {"structure/missing-heading"}
