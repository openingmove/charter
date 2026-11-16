"""`schemacheck.conforms` may only say yes when `jsonschema` would find nothing wrong; it may say no freely."""

import copy
import datetime
import math
import random
from pathlib import Path

import jsonschema
import pytest
import yaml

from charter import schemacheck, yamlsource
from charter.checks.external import _RESPONSE_SCHEMA
from charter.checks.protected_region import ProtectedRegionCheck
from charter.checks.updated_date import UpdatedDateCheck
from charter.contract import _CHECKS_SCHEMA, CONTRACT_SCHEMA
from charter.lock import LOCK_SCHEMA
from charter.plugin import MANIFEST_SCHEMA

ROOT = Path(__file__).resolve().parent.parent
_SAMPLES = [None, True, False, 0, 1, -1, 2, 1.0, 1.5, "", "x", "string", "error", "kind", [], [1], ["a"], ["a", "a"], {}, {"a": 1}, datetime.date(2026, 1, 1),
    math.nan, math.inf, 10**30, -(10**30), "\U0001f600" * 3, "x" * 1000, [1, True, 1.0], [0, False], [1, 1.0], [math.nan]]


def _contracts():
    found = []
    for folder in ("tests/fixtures", "examples", "skills"):
        for path in sorted((ROOT / folder).rglob("charter*.yaml")):
            try:
                data, _ = yamlsource.parse(path.read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, yamlsource.YamlSyntaxError):
                continue
            if isinstance(data, dict):
                found.append(pytest.param(data, id=path.relative_to(ROOT).as_posix()))
    return found


def _valid(schema, data):
    return not list(jsonschema.Draft202012Validator(schema).iter_errors(data))


def _paths(node, prefix=()):
    yield prefix
    children = node.items() if isinstance(node, dict) else enumerate(node) if isinstance(node, list) else ()
    for key, child in children:
        yield from _paths(child, (*prefix, key))


def _mutated(data, rng):
    copy_of = copy.deepcopy(data)
    where = rng.choice(list(_paths(copy_of)))
    if not where:
        return rng.choice(_SAMPLES)
    parent = copy_of
    for step in where[:-1]:
        parent = parent[step]
    action = rng.choice(["replace", "replace", "delete", "add"])
    if action == "delete":
        del parent[where[-1]]
    elif action == "add" and isinstance(parent[where[-1]], dict):
        parent[where[-1]][rng.choice(["extra", "kind", "type"])] = rng.choice(_SAMPLES)
    else:
        parent[where[-1]] = rng.choice(_SAMPLES)
    return copy_of


@pytest.mark.parametrize("data", _contracts())
def test_a_contract_that_is_valid_conforms(data):
    if _valid(CONTRACT_SCHEMA, data):
        assert schemacheck.conforms(CONTRACT_SCHEMA, data)


@pytest.mark.parametrize("data", _contracts())
def test_conforms_never_says_yes_to_a_contract_jsonschema_rejects(data):
    rng = random.Random(88)
    for _ in range(300):
        mutant = _mutated(data, rng)
        if schemacheck.conforms(CONTRACT_SCHEMA, mutant):
            assert _valid(CONTRACT_SCHEMA, mutant), mutant


_LOCK = {
    "charter_lock": 1,
    "plugins": {"p": {"version": "1", "source": {"git": "g", "ref": "r", "commit": "c"}, "sha256": "abc"}},
}
_RESPONSE = {
    "protocol": "charter-plugin/1",
    "diagnostics": [
        {"path": "a.md", "line": 3, "severity": "error", "code": "x/y", "message": "m", "hint": None},
        {"path": "b.md", "severity": "warning", "code": "x/z", "message": "m"},
    ],
}
_CHECKS = {"schema": {"enabled": False, "severity": "warning"}, "p": {"source": "tools/p", "with": {"a": 1}}}
_MANIFEST = yaml.safe_load((ROOT / "tests/fixtures/plugins/banned-words/charter-plugin.yaml").read_text(encoding="utf-8"))
_OTHER_SCHEMAS = {
    "lock": (LOCK_SCHEMA, _LOCK),
    "manifest": (MANIFEST_SCHEMA, _MANIFEST),
    "response": (_RESPONSE_SCHEMA, _RESPONSE),
    "checks": (_CHECKS_SCHEMA, _CHECKS),
    "updated-date": (UpdatedDateCheck.params_schema, {"field": "updated"}),
    "protected-region": (ProtectedRegionCheck.params_schema, {"kinds": ["decision"], "marker": "## Amendments"}),
}


@pytest.mark.parametrize("name", _OTHER_SCHEMAS)
def test_conforms_never_says_yes_to_other_data_jsonschema_rejects(name):
    schema, seed = _OTHER_SCHEMAS[name]
    assert _valid(schema, seed)
    assert schemacheck.conforms(schema, seed)
    rng = random.Random(88)
    for _ in range(500):
        mutant = _mutated(seed, rng)
        if schemacheck.conforms(schema, mutant):
            assert _valid(schema, mutant), mutant


def test_a_malformed_schema_is_left_to_jsonschema():
    for schema, instance in (
        ({"properties": []}, {"a": 1}),
        ({"type": ["string", "bogus"]}, "x"),
        ({"required": 5}, {"a": 1}),
        ({"minLength": "x"}, "x"),
    ):
        assert not schemacheck.conforms(schema, instance)
    # jsonschema's own failure surfaces, so the real error is reported, not a silent yes.
    with pytest.raises(AttributeError):
        schemacheck.errors({"properties": []}, {"a": 1})


@pytest.mark.parametrize(
    ("schema", "instance"),
    [
        ({"const": 1}, True),
        ({"const": True}, 1),
        ({"enum": [1, 2]}, True),
        ({"type": "integer"}, True),
        ({"type": "number"}, False),
        ({"type": "integer"}, 1.5),
        ({"minimum": 1}, 0),
        ({"minLength": 2}, "x"),
        ({"propertyNames": {"minLength": 2}}, {"a": 1}),
        ({"additionalProperties": False, "properties": {"a": {}}}, {"b": 1}),
        ({"required": ["a"]}, {}),
        ({"if": {"type": "array"}, "then": {"minItems": 1}, "else": {"type": "object"}}, []),
        ({"if": {"type": "array"}, "then": {"minItems": 1}, "else": {"type": "object"}}, "x"),
    ],
)
def test_json_distinctions_are_kept(schema, instance):
    assert not schemacheck.conforms(schema, instance)
    assert not _valid(schema, instance)


@pytest.mark.parametrize(
    ("schema", "instance"),
    [
        ({"type": "integer"}, 1.0),
        ({"type": ["string", "null"]}, None),
        ({"uniqueItems": True}, [1, 2, 3]),
        ({"if": {"type": "array"}, "then": {"minItems": 1}, "else": {"type": "object"}}, [1]),
        ({"if": {"type": "array"}, "then": {"minItems": 1}, "else": {"type": "object"}}, {}),
        ({"propertyNames": {"pattern": "[^/]"}}, {"a": 1}),
    ],
)
def test_plain_valid_data_conforms(schema, instance):
    assert _valid(schema, instance)
    assert schemacheck.conforms(schema, instance)


@pytest.mark.parametrize(
    "schema",
    [{"anyOf": [{"type": "string"}]}, {"$ref": "#/$defs/x"}, {"pattern": "("}, {"patternProperties": {"a": {}}}],
)
def test_what_it_cannot_judge_is_left_to_jsonschema(schema):
    assert not schemacheck.conforms(schema, "x")


def test_mixed_items_are_left_to_jsonschema():
    assert not schemacheck.conforms({"uniqueItems": True}, [1, True])


def test_errors_are_jsonschemas_own():
    schema = {"type": "object", "properties": {"a": {"type": "string"}}}

    problems = schemacheck.errors(schema, {"a": 1})

    assert [problem.message for problem in problems] == ["1 is not of type 'string'"]
    assert schemacheck.errors(schema, {"a": "x"}) == []
