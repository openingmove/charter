"""Establish offers the contract guard once, as an optional step after the contract is installed or handed off,
and states the guard's limits in plain words."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ESTABLISH = ROOT / "skills" / "establish"
GUARD = ESTABLISH / "guard.md"


def _text(path):
    return path.read_text(encoding="utf-8")


def _step(number):
    text = _text(ESTABLISH / "SKILL.md")
    match = re.search(rf"^## {number}\. .*?(?=^## )", text, re.M | re.S)
    return match.group(0)


def test_establish_offers_the_guard_after_the_install_and_before_the_hand_off():
    install, hand_off = _step(12), _step(13)

    assert "[guard.md](guard.md)" in install
    assert install.index("charter init <folder>") < install.index("guard.md") < install.index("make the commit")
    assert "[guard.md](guard.md)" in hand_off
    assert hand_off.index("guard.md") < hand_off.index("Tell the human to run `/charter:migrate`")


def test_the_offer_is_optional_and_made_once():
    guard = _text(GUARD)

    assert "Offer the guard once" in guard
    assert "optional" in guard
    assert "On a no, change nothing" in guard


def test_the_offer_sets_the_opt_in_key_and_regenerates_the_rulebook():
    guard = _text(GUARD)

    assert "guard: true" in guard
    assert "charter docs --config <folder>/charter.yaml" in guard
    assert "charter docs --config <folder>/charter.yaml --check" in guard
    assert "charter-hook --help" in guard


def test_the_offer_states_the_limits_in_plain_words():
    guard = _text(GUARD)

    assert "for the rest of that session" in guard
    assert "writes a marker itself" in guard
    assert "Claude Code only" in guard
    assert "rely on the rulebook's rule" in guard
    assert "`charter.yaml` only" in guard


def test_the_guard_needs_the_agent_layer():
    guard = _text(GUARD)

    assert "no `agents:` section" in guard
    # Adding `agents:` to switch the guard on would switch the whole agent layer on with it.
    assert "agents: {guard: true}" not in guard
    before_offering = guard[guard.index("## Before offering") : guard.index("## On a yes")]
    assert "step 12" in before_offering
    assert "step 13" in before_offering
