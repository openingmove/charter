"""`charter plugin list` and `info`: each plugin of the knowledge base, where it comes from, and its manifest."""

import json
from typing import Any

from charter.contract import PluginSettings
from charter.files import contract_relative
from charter.lock import DevSource, GitSource, content_hash, is_vendored, vendored_directory
from charter.plugin import DEFAULT_TIMEOUT_MS, MANIFEST_FILENAME, manifest_of

FORMATS = ("text", "json")


def listing(settings: PluginSettings) -> list[dict[str, Any]]:
    return [_described(settings, plugin_id, detailed=False) for plugin_id in settings.plugin_ids]


def details(settings: PluginSettings, plugin_id: str) -> dict[str, Any]:
    return _described(settings, plugin_id, detailed=True)


def to_json(described: Any) -> str:
    return json.dumps(described, indent=2, ensure_ascii=False) + "\n"


def listing_text(plugins: list[dict[str, Any]], contract_file: str) -> str:
    if not plugins:
        return f"No plugins: no `checks.<id>` in `{contract_file}` has a `source`.\n"
    rows = [
        (p["id"], p["version"] or "?", "enabled" if p["enabled"] else "disabled", _source_text(p["source"]))
        for p in plugins
    ]
    widths = [max(len(row[column]) for row in rows) for column in range(3)]
    lines = ("  ".join(cell.ljust(width) for cell, width in zip(row, [*widths, 0])).rstrip() for row in rows)
    return "".join(f"{line}\n" for line in lines)


def details_text(plugin: dict[str, Any]) -> str:
    lines = [f"{plugin['id']} {plugin['version'] or '(version unknown)'}"]
    if plugin.get("description"):
        lines.append(plugin["description"])
    lines.append("")
    fields = [
        ("enabled", "yes" if plugin["enabled"] else "no"),
        ("source", _source_text(plugin["source"], with_commit=True)),
        ("directory", plugin["directory"] or "(outside the directory holding charter.yaml)"),
    ]
    if "sha256" in plugin:
        state = "no longer matches the directory, so charter will not run it" if plugin["modified"] else "matches"
        fields.append(("sha256", f"{plugin['sha256']} ({state})"))
    if manifest := plugin.get("manifest"):
        triggers = manifest["triggers"]
        fields += [
            ("run", " ".join(manifest["run"])),
            ("scope", manifest["scope"]),
            ("needs", ", ".join(manifest["needs"]) or "-"),
            ("triggers", _triggers_text(triggers) if triggers is not None else "none: it runs on every run"),
            ("hook", "yes" if manifest["hook"] else "no: left out of per-edit runs"),
            ("timeout", f"{manifest['timeout_ms']} ms"),
        ]
        if "requires" in manifest:
            fields.append(("requires", f"charter {manifest['requires']}"))
        if "docs" in manifest:
            fields.append(("docs", manifest["docs"]))
    fields += [("problem", problem) for problem in plugin.get("problems", [])]
    width = max(len(name) for name, _ in fields) + 1
    lines += [f"{f'{name}:'.ljust(width)} {value}" for name, value in fields]
    return "\n".join(lines) + "\n"


def _described(settings: PluginSettings, plugin_id: str, *, detailed: bool) -> dict[str, Any]:
    config = settings.check_config(plugin_id)
    locked = settings.locked.get(plugin_id)
    given = config.source
    vendored = is_vendored(plugin_id, given, settings.locked)
    directory = vendored_directory(plugin_id) if vendored else contract_relative(given)
    manifest = manifest_of(settings.base_dir / directory) if directory is not None else None
    readable = isinstance(manifest, dict)
    described: dict[str, Any] = {
        "id": plugin_id,
        "version": locked.version if vendored else manifest["version"] if readable else None,
        "enabled": given is not None and config.enabled,
        "source": _source_data(locked.source) if vendored else {"path": given},
        "directory": directory,
    }
    if not detailed:
        return described
    if readable:
        described["description"] = manifest.get("description")
    if vendored:
        described["sha256"] = locked.sha256
        described["modified"] = content_hash(settings.base_dir / directory) != locked.sha256
    if readable:
        described["manifest"] = {
            "run": manifest["run"],
            "scope": manifest.get("scope", "vault"),
            "needs": manifest.get("needs", []),
            "triggers": manifest.get("triggers"),
            "hook": manifest.get("hook", True),
            "timeout_ms": manifest.get("timeout_ms", DEFAULT_TIMEOUT_MS),
            **({"requires": manifest["requires"]["charter"]} if "charter" in manifest.get("requires", {}) else {}),
            **({"docs": manifest["docs"]} if "docs" in manifest else {}),
        }
    elif manifest is not None:
        described["problems"] = [f"`{MANIFEST_FILENAME}`: {message}" for message, _ in manifest]
    return described


def _source_data(source: GitSource | DevSource) -> dict[str, Any]:
    if isinstance(source, DevSource):
        return {"dev": True}
    return {"git": source.git, "ref": source.ref, "commit": source.commit}


def _source_text(source: dict[str, Any], *, with_commit: bool = False) -> str:
    if "git" in source:
        commit = f" (commit {source['commit']})" if with_commit and source["commit"] else ""
        return f"git {source['git']}@{source['ref']}{commit}"
    if "dev" in source:
        return "a working copy, installed with --dev"
    return f"used in place from {source['path']}"


def _triggers_text(triggers: dict[str, list[str]]) -> str:
    parts = [f"{name} {', '.join(triggers[name])}" for name in ("kinds", "globs") if triggers.get(name)]
    return "; ".join(parts)
