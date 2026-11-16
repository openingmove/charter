"""The strict and the lenient contract loader agree on which built-in checks are off unless `checks:` enables them.

Tested at the loader functions: `charter plugin` shows only checks that have a `source`, so no CLI output reveals
the lenient loader's view of a built-in check."""

import pytest
from charter.validate import contract_at, plugin_settings_at

BASE = "charter: 1\nroot: notes\nkinds:\n  entry: {}\n"
AGENTS = "agents: {file: AGENTS.md}\n"


@pytest.mark.parametrize(
    ("checks", "agents"),
    [
        ("checks:\n  updated-date: {severity: warning}\n", ""),
        ("checks:\n  protected-region: {severity: warning}\n", ""),
        ("checks:\n  updated-date: {enabled: false}\n", ""),
        ("checks:\n  agents-include: {severity: warning}\n", ""),
        ("checks:\n  agents-include: {severity: warning}\n", AGENTS),
    ],
)
def test_both_loaders_default_a_mentioned_check_alike(make_kb, checks, agents):
    kb = make_kb(
        {"charter.yaml": BASE + agents + checks, "notes/a.md": "---\nkind: entry\n---\n"}, agents_include=True
    )
    config = kb / "charter.yaml"

    strict, lenient = contract_at(config), plugin_settings_at(config)

    assert lenient.checks
    for check_id in lenient.checks:
        assert lenient.checks[check_id].enabled == strict.check_config(check_id).enabled


def test_an_optional_check_mentioned_without_enabled_stays_off(make_kb):
    kb = make_kb({"charter.yaml": BASE + "checks:\n  updated-date: {severity: warning}\n"}, agents_include=True)

    assert plugin_settings_at(kb / "charter.yaml").checks["updated-date"].enabled is False
