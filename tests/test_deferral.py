"""Whether a run judges the edit policies now, or leaves them to git's commit-msg stage, is one three-state choice:
judge now, defer and say so, or defer silently. Two booleans would allow a fourth, meaningless combination."""

import datetime

import pytest

from charter.profiles import Profile
from charter.validate import Deferral, contract_at, validate

CONTRACT = """\
charter: 1
root: notes
paths:
  "Archive/**": {edit: read-only}
kinds:
  entry: {}
"""
NOTE = "---\nkind: entry\n---\n"
PROFILE = Profile("ci", {}, downgrade_only=True)
TODAY = datetime.date(2026, 1, 1)


def _codes(make_kb, deferral):
    kb = make_kb({"charter.yaml": CONTRACT, "notes/Archive/old.md": NOTE})
    contract = contract_at(kb / "charter.yaml")
    return [d.code for d in validate(contract, None, PROFILE, strict=False, today=TODAY, deferral=deferral)]


def test_a_run_has_exactly_three_deferral_states():
    assert {state.name for state in Deferral} == {"JUDGE", "ANNOUNCE", "SILENT"}


@pytest.mark.parametrize(
    ("deferral", "announced"), [(Deferral.JUDGE, False), (Deferral.ANNOUNCE, True), (Deferral.SILENT, False)]
)
def test_only_an_announced_deferral_says_the_edit_policies_wait(make_kb, deferral, announced):
    assert ("paths/edit-deferred" in _codes(make_kb, deferral)) is announced


@pytest.mark.parametrize("removed", [{"overridable_checks": True}, {"announce_deferred": False}])
def test_the_two_booleans_are_gone(make_kb, removed):
    kb = make_kb({"charter.yaml": CONTRACT, "notes/Archive/old.md": NOTE})
    contract = contract_at(kb / "charter.yaml")

    with pytest.raises(TypeError):
        validate(contract, None, PROFILE, strict=False, today=TODAY, **removed)
