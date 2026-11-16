import os
import shutil
import unicodedata

import pytest
import yaml
from conftest import FIXTURES, commit_files, run_git, write_files

CONTRACT = "charter: 1\nroot: notes\nkinds:\n  entry: {}\nchecks:\n  agents-include: {enabled: false}\n"
NOTES = {
    "notes/a.md": "---\nkind: entry\n---\n# TODO plans\n",
    "notes/b.md": "---\nkind: entry\n---\n# Done\n",
}
INSTALLED = ".charter/plugins/todo-free"
# The todo-free fixture's content hash. Pinned so that a change to how the hash is computed, or a checkout
# that changes line endings, shows up here on every OS.
TODO_FREE_SHA256 = "68f78f6fafd9119b4812edb8015ebfe8921c5cc49425847b7206dd05686281c4"
TODO_FOUND = [("notes/a.md", 4, "error", "todo-free/todo")]


@pytest.fixture
def kb(make_kb):
    def make(contract=CONTRACT, notes=None):
        return make_kb({"charter.yaml": contract, **(NOTES if notes is None else notes)})

    return make


def _from(repo, ref="v1.2.0"):
    return f"{repo.as_posix()}@{ref}"


def _lock(base):
    return yaml.safe_load((base / "charter.lock").read_text(encoding="utf-8"))


def _diagnostics(result):
    return [(d["path"], d["line"], d["severity"], d["code"]) for d in result.json()["diagnostics"]]


def _contract_data(base):
    return yaml.safe_load((base / "charter.yaml").read_text(encoding="utf-8"))


# --- adding from git ---


def test_add_vendors_the_plugin_enables_it_and_locks_it(charter, kb, plugin_repo):
    base, repo = kb(), plugin_repo()
    commit = run_git(repo, "rev-parse", "HEAD")

    result = charter("plugin", "add", "--from", _from(repo), cwd=base)

    assert result.exit_code == 0, result.stdout
    installed = base / INSTALLED
    assert sorted(p.name for p in installed.iterdir()) == ["charter-plugin.yaml", "check.py"]
    assert (installed / "check.py").read_bytes() == (repo / "check.py").read_bytes()
    assert _contract_data(base)["checks"]["todo-free"] == {"source": INSTALLED}
    assert _lock(base) == {
        "charter_lock": 1,
        "plugins": {
            "todo-free": {
                "version": "1.2.0",
                "source": {"git": repo.as_posix(), "ref": "v1.2.0", "commit": commit},
                "sha256": TODO_FREE_SHA256,
            }
        },
    }
    assert f"`{INSTALLED}`" in result.stdout


def test_added_plugin_runs_on_validate(charter, kb, plugin_repo):
    base = kb()
    charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, _diagnostics(result)) == (1, TODO_FOUND)


def test_add_keeps_the_rest_of_the_contract_as_written(charter, kb, plugin_repo):
    contract = (
        "# My contract\ncharter: 1\nroot: notes   # the notes\nkinds:\n  entry: {}\n"
        "checks:\n  agents-include: {enabled: false}  # no rulebook here\n\n# Profiles follow\n"
        "profiles:\n  review: {schema: warning}\n"
    )
    base = kb(contract)

    charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)

    assert (base / "charter.yaml").read_text(encoding="utf-8") == (
        "# My contract\ncharter: 1\nroot: notes   # the notes\nkinds:\n  entry: {}\n"
        "checks:\n  agents-include: {enabled: false}  # no rulebook here\n"
        f"  todo-free:\n    source: {INSTALLED}\n\n# Profiles follow\n"
        "profiles:\n  review: {schema: warning}\n"
    )


@pytest.mark.parametrize(
    ("contract", "expected"),
    [
        (
            "charter: 1\nroot: notes\nkinds:\n  entry: {}\nchecks: {agents-include: {enabled: false}}\n",
            "charter: 1\nroot: notes\nkinds:\n  entry: {}\n"
            f"checks: {{agents-include: {{enabled: false}}, todo-free: {{source: {INSTALLED}}}}}\n",
        ),
        (
            "charter: 1\nroot: notes\nkinds:\n  entry: {}\nchecks: {}\n",
            f"charter: 1\nroot: notes\nkinds:\n  entry: {{}}\nchecks: {{todo-free: {{source: {INSTALLED}}}}}\n",
        ),
        (
            "charter: 1\nroot: notes\nkinds:\n  entry: {}",
            f"charter: 1\nroot: notes\nkinds:\n  entry: {{}}\nchecks:\n  todo-free:\n    source: {INSTALLED}\n",
        ),
        (
            "charter: 1\r\nroot: notes\r\nkinds:\r\n  entry: {}\r\nchecks:\r\n    agents-include: {enabled: false}\r\n",
            "charter: 1\r\nroot: notes\r\nkinds:\r\n  entry: {}\r\nchecks:\r\n    agents-include: {enabled: false}\r\n"
            f"    todo-free:\r\n      source: {INSTALLED}\r\n",
        ),
    ],
    ids=["flow", "empty-flow", "no-checks", "crlf-and-indent"],
)
def test_add_writes_the_checks_entry_in_the_contracts_own_style(charter, make_kb, plugin_repo, contract, expected):
    base = make_kb({"charter.yaml": contract, **NOTES}, agents_include=True)

    result = charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)

    assert result.exit_code == 0, result.stdout
    assert (base / "charter.yaml").read_bytes().decode("utf-8") == expected


def test_mixed_line_endings_keep_their_own(charter, make_kb, plugin_repo):
    contract = "charter: 1\r\nroot: notes\nkinds:\r\n  entry: {}\nchecks:\n  agents-include: {enabled: false}\r\n"
    base = make_kb({"charter.yaml": contract, **NOTES}, agents_include=True)

    charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)

    assert (base / "charter.yaml").read_bytes().decode("utf-8") == (
        f"{contract}  todo-free:\r\n    source: {INSTALLED}\r\n"
    )


def test_an_id_yaml_would_read_as_another_type_is_quoted(charter, kb, plugin_repo):
    base = kb()
    repo = plugin_repo({"charter-plugin.yaml": "charter_plugin: 1\nid: 'yes'\nversion: '1'\nrun: [python, x.py]\n"})

    result = charter("plugin", "add", "--from", _from(repo), cwd=base)

    assert result.exit_code == 0, result.stdout
    assert (base / "charter.yaml").read_text(encoding="utf-8").endswith(
        '  "yes":\n    source: .charter/plugins/yes\n'
    )


def test_add_refuses_when_the_checks_entry_cannot_be_added_cleanly(charter, kb, plugin_repo):
    contract = (
        CONTRACT + "  drafts:\n    source: tools/drafts\n    enabled: false\n    with:\n      intro: |\n"
        "        first\n        # part of the text, not a comment\n"
    )
    base = kb(contract)

    result = charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)

    assert result.exit_code == 1
    assert "plugin/write-failed" in result.stdout
    assert "`checks.todo-free` could not be added to `charter.yaml`" in result.stdout
    assert (base / "charter.yaml").read_text(encoding="utf-8") == contract
    assert not (base / ".charter").exists()
    assert not (base / "charter.lock").exists()


@pytest.mark.parametrize("ref", ["main", "feature/next", "commit"])
def test_add_takes_a_branch_or_commit_as_the_ref(charter, kb, plugin_repo, ref):
    base, repo = kb(), plugin_repo()
    run_git(repo, "checkout", "-q", "-b", "feature/next")
    commit = commit_files(repo, {"NOTES.txt": "next\n"})
    run_git(repo, "checkout", "-q", "main")
    if ref == "commit":
        ref = commit
    elif ref == "main":
        commit = run_git(repo, "rev-parse", "main")

    result = charter("plugin", "add", "--from", _from(repo, ref), cwd=base)

    assert result.exit_code == 0, result.stdout
    assert _lock(base)["plugins"]["todo-free"]["source"] == {"git": repo.as_posix(), "ref": ref, "commit": commit}
    assert (base / INSTALLED / "NOTES.txt").exists() == (ref != "main")


def test_adding_a_locked_plugin_again_replaces_it(charter, kb, plugin_repo):
    base, repo = kb(), plugin_repo()
    charter("plugin", "add", "--from", _from(repo), cwd=base)
    manifest = (repo / "charter-plugin.yaml").read_text(encoding="utf-8").replace("1.2.0", "1.3.0")
    commit_files(repo, {"charter-plugin.yaml": manifest, "extra.txt": "x\n"})
    run_git(repo, "tag", "v1.3.0")
    contract = (base / "charter.yaml").read_text(encoding="utf-8")

    result = charter("plugin", "add", "--from", _from(repo, "v1.3.0"), cwd=base)

    assert result.exit_code == 0, result.stdout
    entry = _lock(base)["plugins"]["todo-free"]
    assert (entry["version"], entry["source"]["ref"]) == ("1.3.0", "v1.3.0")
    assert (base / INSTALLED / "extra.txt").exists()
    assert (base / "charter.yaml").read_text(encoding="utf-8") == contract
    assert charter("validate", "--format", "json", cwd=base).exit_code == 1


def test_add_keeps_other_locked_plugins(charter, kb, plugin_repo):
    base = kb()
    charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)
    other = plugin_repo({
        "charter-plugin.yaml": "charter_plugin: 1\nid: other\nversion: 0.1.0\nrun: [python, x.py]\n",
        "x.py": "",
    })

    charter("plugin", "add", "--from", _from(other), cwd=base)

    assert sorted(_lock(base)["plugins"]) == ["other", "todo-free"]


def test_add_reports_parameters_the_contract_must_still_give(charter, kb, plugin_repo):
    base = kb()
    fixture = FIXTURES / "plugins" / "banned-words"
    repo = plugin_repo({path.name: path.read_bytes() for path in fixture.iterdir()})

    result = charter("plugin", "add", "--from", _from(repo), cwd=base)

    assert result.exit_code == 1
    assert "checks.banned-words.with: missing required key `words`." in result.stdout
    assert _lock(base)["plugins"]["banned-words"]["version"] == "0.1.0"


# --- refusals ---


@pytest.mark.parametrize(
    "given",
    [
        "https://example.com/plugin.git",
        "git@example.com:org/plugin.git",
        "https://user@example.com/plugin.git",
        "ssh://git@example.com/plugin.git",
        "https://example.com/@v1",
        "@v1",
        "repo@",
        "repo@-v1",
    ],
)
def test_from_needs_a_url_and_a_ref(charter, kb, given):
    base = kb()

    result = charter("plugin", "add", "--from", given, cwd=base)

    assert result.exit_code == 2
    assert "usage/invalid-source" in result.stdout
    assert not (base / ".charter").exists()


def test_add_needs_from_or_dev(charter, kb):
    assert charter("plugin", "add", cwd=kb()).exit_code == 2


def test_unknown_ref_is_a_fetch_failure_and_writes_nothing(charter, kb, plugin_repo):
    base = kb()

    result = charter("plugin", "add", "--from", _from(plugin_repo(), "v9"), cwd=base)

    assert result.exit_code == 1
    assert "plugin/fetch-failed" in result.stdout
    assert "`v9`" in result.stdout
    assert not (base / ".charter").exists()
    assert not (base / "charter.lock").exists()


def test_unreachable_repository_is_a_fetch_failure(charter, kb, tmp_path_factory):
    missing = tmp_path_factory.mktemp("nothing") / "no-repo"

    result = charter("plugin", "add", "--from", _from(missing), cwd=kb())

    assert result.exit_code == 1
    assert "plugin/fetch-failed" in result.stdout


def test_url_starting_with_a_dash_is_a_repository_not_a_git_option(charter, kb):
    base = kb()

    result = charter("plugin", "add", "--from=--upload-pack=touch@v1", cwd=base)

    assert result.exit_code == 1
    assert "plugin/fetch-failed" in result.stdout
    assert "--upload-pack=touch" in result.stdout
    assert not (base / ".charter").exists()


def test_url_with_user_and_ref_takes_the_ref_after_the_path(charter, kb):
    result = charter("plugin", "add", "--from", "ssh://nobody@localhost:1/plugin.git@v1", cwd=kb())

    assert result.exit_code == 1
    assert "git could not clone `ssh://nobody@localhost:1/plugin.git`" in result.stdout


def _symlink(link, target):
    try:
        os.symlink(target, link)
    except (OSError, NotImplementedError):
        pytest.skip("this machine cannot create symbolic links")


def test_plugin_holding_a_symlink_is_refused(charter, kb, tmp_path_factory):
    working = tmp_path_factory.mktemp("work") / "todo-free"
    shutil.copytree(FIXTURES / "plugins" / "todo-free", working)
    (working / "lib").mkdir()
    _symlink(working / "lib" / "shared.py", "../check.py")
    base = kb()

    result = charter("plugin", "add", "--dev", str(working), cwd=base)

    assert result.exit_code == 1
    assert "plugin/symlink" in result.stdout
    assert "`lib/shared.py`" in result.stdout
    assert not (base / ".charter").exists()


def test_plugin_from_git_holding_a_symlink_is_refused(charter, kb, plugin_repo):
    repo = plugin_repo(tag=None)
    _symlink(repo / "elsewhere", "/etc")
    commit_files(repo, {})
    run_git(repo, "tag", "v1.2.0")

    result = charter("plugin", "add", "--from", _from(repo), cwd=kb())

    assert result.exit_code == 1
    assert "`elsewhere`" in result.stdout and "plugin/symlink" in result.stdout


@pytest.mark.parametrize(
    ("files", "fragment"),
    [
        ({"README.md": "no manifest\n"}, "could not be read"),
        ({"charter-plugin.yaml": "charter_plugin: 1\nid: x\nversion: 1\nrun: check.sh\n"}, "shell"),
        ({"charter-plugin.yaml": "charter_plugin: 1\nid: x\nrun: [python, x.py]\n"}, "`version`"),
        ({"charter-plugin.yaml": "charter_plugin: 1\nid: ../x\nversion: '1'\nrun: [python, x.py]\n"}, "`../x`"),
        ({"charter-plugin.yaml": "charter_plugin: 1\nid: schema\nversion: '1'\nrun: [python, x.py]\n"}, "built-in"),
        ({"charter-plugin.yaml": "charter_plugin: 1\nid: plugin\nversion: '1'\nrun: [python, x.py]\n"}, "reserved"),
    ],
    ids=["no-manifest", "shell", "invalid", "unsafe-id", "builtin-id", "reserved-id"],
)
def test_plugin_with_a_bad_manifest_is_refused(charter, kb, plugin_repo, files, fragment):
    base = kb()

    result = charter("plugin", "add", "--from", _from(plugin_repo(files)), cwd=base)

    assert result.exit_code == 1
    assert "plugin/invalid-manifest" in result.stdout
    assert fragment in result.stdout
    assert not (base / ".charter").exists()


def test_add_refuses_a_check_the_contract_already_has(charter, kb, plugin_repo):
    contract = CONTRACT + "  todo-free:\n    source: tools/todo-free\n    enabled: false\n"
    base = kb(contract)

    result = charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)

    assert result.exit_code == 1
    assert "plugin/exists" in result.stdout
    assert (base / "charter.yaml").read_text(encoding="utf-8") == contract
    assert not (base / "charter.lock").exists()


def test_add_refuses_to_overwrite_an_unlocked_directory(charter, kb, plugin_repo):
    base = kb()
    (base / INSTALLED).mkdir(parents=True)
    (base / INSTALLED / "mine.txt").write_text("keep\n", encoding="utf-8")

    result = charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)

    assert result.exit_code == 1
    assert "plugin/exists" in result.stdout
    assert (base / INSTALLED / "mine.txt").exists()


def test_add_on_an_invalid_contract_is_a_usage_error(charter, make_kb, plugin_repo):
    base = make_kb({"charter.yaml": "charter: 1\n"})

    result = charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)

    assert result.exit_code == 2
    assert not (base / ".charter").exists()


# --- the lock and the content hash ---


def test_content_hash_ignores_line_endings_but_not_content(charter, kb, plugin_repo):
    crlf = {
        name: (FIXTURES / "plugins" / "todo-free" / name).read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        for name in ("charter-plugin.yaml", "check.py")
    }
    base = kb()

    charter("plugin", "add", "--from", _from(plugin_repo(crlf)), cwd=base)

    assert _lock(base)["plugins"]["todo-free"]["sha256"] == TODO_FREE_SHA256


def test_validate_runs_a_plugin_checked_out_with_other_line_endings(charter, kb, plugin_repo):
    base = kb()
    charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)
    check = base / INSTALLED / "check.py"
    # Normalise first: a Windows checkout may already hold CRLF, and \r\r\n is a real change.
    check.write_bytes(check.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, _diagnostics(result)) == (1, TODO_FOUND)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: (d / "check.py").write_text("raise SystemExit(0)\n", encoding="utf-8"),
        lambda d: (d / "helper.py").write_text("", encoding="utf-8"),
        lambda d: (d / "check.py").unlink(),
        lambda d: (d / "check.py").rename(d / "main.py"),
    ],
    ids=["edited", "added", "deleted", "renamed"],
)
def test_validate_refuses_to_run_a_modified_locked_plugin(charter, kb, plugin_repo, change):
    base = kb()
    charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)
    change(base / INSTALLED)

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, _diagnostics(result)) == (3, [("charter.yaml", 7, "error", "plugin/modified")])
    message = result.json()["diagnostics"][0]["message"]
    assert f"`{INSTALLED}`" in message and "`charter.lock`" in message


def test_plugin_run_refuses_a_modified_locked_plugin(charter, kb, plugin_repo):
    base = kb()
    charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)
    (base / INSTALLED / "helper.py").write_text("", encoding="utf-8")

    result = charter("plugin", "run", "todo-free", "--format", "json", cwd=base)

    assert (result.exit_code, _diagnostics(result)) == (3, [("charter.yaml", 7, "error", "plugin/modified")])


def test_severity_settings_cannot_soften_a_modified_plugin(charter, kb, plugin_repo):
    base = kb()
    charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)
    contract = base / "charter.yaml"
    contract.write_text(contract.read_text(encoding="utf-8") + "    severity: info\n", encoding="utf-8")
    (base / INSTALLED / "helper.py").write_text("", encoding="utf-8")

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, _diagnostics(result)) == (3, [("charter.yaml", 7, "error", "plugin/modified")])


def test_bytecode_beside_a_locked_plugin_is_not_a_modification(charter, kb, plugin_repo):
    base = kb()
    charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)
    (base / INSTALLED / "__pycache__").mkdir()
    (base / INSTALLED / "__pycache__" / "check.cpython-313.pyc").write_bytes(b"\0bytecode")

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, _diagnostics(result)) == (1, TODO_FOUND)


def test_symlink_in_an_installed_plugin_is_a_modification(charter, kb, plugin_repo):
    base = kb()
    charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)
    _symlink(base / INSTALLED / "link.py", "check.py")

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, _diagnostics(result)) == (3, [("charter.yaml", 7, "error", "plugin/modified")])


def test_unlocked_plugin_runs_whatever_its_contents(charter, kb):
    base = kb(CONTRACT + "  todo-free:\n    source: tools/todo-free\n")
    shutil.copytree(FIXTURES / "plugins" / "todo-free", base / "tools" / "todo-free")
    (base / "tools" / "todo-free" / "helper.py").write_text("", encoding="utf-8")

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, _diagnostics(result)) == (1, TODO_FOUND)


def test_lock_does_not_cover_a_plugin_used_from_a_local_path(charter, kb):
    base = kb(CONTRACT + "  todo-free:\n    source: tools/todo-free\n")
    shutil.copytree(FIXTURES / "plugins" / "todo-free", base / "tools" / "todo-free")
    (base / "charter.lock").write_text(
        f"charter_lock: 1\nplugins:\n  todo-free: {{version: 1.2.0, source: {{dev: true}}, sha256: '{'0' * 64}'}}\n",
        encoding="utf-8",
    )

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, _diagnostics(result)) == (1, TODO_FOUND)


def test_lock_in_the_specs_form_and_with_keys_from_later_charters_loads(charter, kb, plugin_repo):
    base = kb()
    charter("plugin", "add", "--from", _from(plugin_repo()), cwd=base)
    (base / "charter.lock").write_text(
        "charter_lock: 1\ncatalog: {url: https://example.com/index.json}\nplugins:\n  todo-free:\n"
        "    version: 1.2.0\n    source: {git: 'https://example.com/todo-free', ref: v1.2.0, mirror: x}\n"
        f"    sha256: \"{TODO_FREE_SHA256}\"\n    signed_by: someone\n",
        encoding="utf-8",
    )

    result = charter("validate", "--format", "json", cwd=base)

    assert (result.exit_code, _diagnostics(result)) == (1, TODO_FOUND)


@pytest.mark.parametrize(
    ("lock", "line", "message"),
    [
        ("charter_lock: 2\nplugins: {}\n", 1, "charter_lock: must be `1`, got `2`."),
        (
            "charter_lock: 1\nplugins:\n  x: {version: '1', sha256: abc, source: {dev: true}}\n",
            3,
            "plugins.x.sha256: expected 64 lowercase hexadecimal digits, got `abc`.",
        ),
        (
            "charter_lock: 1\nplugins:\n  x: {version: '1', sha256: '" + "0" * 64 + "', source: {svn: x}}\n",
            3,
            "plugins.x.source: needs `git` and `ref` for a plugin from git, or `dev: true` for a working copy.",
        ),
        (
            "charter_lock: 1\nplugins:\n  x: {version: '1', sha256: '" + "0" * 64 + "', source: {dev: yes please}}\n",
            3,
            "plugins.x.source.dev: must be `true`, got `yes please`.",
        ),
        ("charter_lock: 1\nplugins:\n  x: {version: '1'}\n", 3, "plugins.x: missing required key `source`, `sha256`."),
        ("charter_lock: 1\nplugins: [\n", None, "Invalid YAML"),
    ],
)
def test_invalid_lock_is_a_contract_error(charter, kb, lock, line, message):
    base = kb()
    (base / "charter.lock").write_text(lock, encoding="utf-8")

    result = charter("validate", "--format", "json", cwd=base)

    assert result.exit_code == 2
    diagnostic = result.json()["diagnostics"][0]
    assert (diagnostic["path"], diagnostic["code"]) == ("charter.lock", "contract/invalid" if line else "contract/yaml")
    if line:
        assert (diagnostic["line"], diagnostic["message"]) == (line, message)
    else:
        assert diagnostic["message"].startswith(message)


def _dev_hash(charter, make_kb, tmp_path_factory, monkeypatch, files):
    working = tmp_path_factory.mktemp("work") / "todo-free"
    shutil.copytree(FIXTURES / "plugins" / "todo-free", working)
    write_files(working, files)
    base = make_kb({"charter.yaml": CONTRACT, **NOTES})
    charter("plugin", "add", "--dev", str(working), cwd=base)
    sha256 = _lock(base)["plugins"]["todo-free"]["sha256"]
    monkeypatch.chdir(base.parent)  # Windows refuses to delete the working directory, which `charter` set to base
    shutil.rmtree(base)
    return sha256


@pytest.mark.parametrize(("lines_before_nul", "same"), [(900, True), (700, False)])
def test_only_a_nul_byte_in_the_first_8000_makes_a_file_binary(
    charter, make_kb, tmp_path_factory, monkeypatch, lines_before_nul, same
):
    # With LF or CRLF, the NUL lands past byte 8000 after 900 lines and within it after 700.
    def data(newline):
        line = b"x" * 8 + newline
        return line * lines_before_nul + b"\0" + line * 100

    lf = _dev_hash(charter, make_kb, tmp_path_factory, monkeypatch, {"data.bin": data(b"\n")})
    crlf = _dev_hash(charter, make_kb, tmp_path_factory, monkeypatch, {"data.bin": data(b"\r\n")})

    assert (lf == crlf) is same


def test_content_hash_compares_file_names_in_one_unicode_form(charter, make_kb, tmp_path_factory, monkeypatch):
    hashes = []
    for form in ("NFC", "NFD"):
        working = tmp_path_factory.mktemp(form) / "todo-free"
        shutil.copytree(FIXTURES / "plugins" / "todo-free", working)
        (working / unicodedata.normalize(form, "café.txt")).write_text("menu\n", encoding="utf-8")
        base = make_kb({"charter.yaml": CONTRACT, **NOTES})
        charter("plugin", "add", "--dev", str(working), cwd=base)
        hashes.append(_lock(base)["plugins"]["todo-free"]["sha256"])
        monkeypatch.chdir(base.parent)  # Windows refuses to delete the working directory
        shutil.rmtree(base)

    assert hashes[0] == hashes[1] != TODO_FREE_SHA256


# --- --dev ---


def test_dev_installs_a_working_copy_and_refreshes_it_when_added_again(charter, kb, tmp_path_factory):
    working = tmp_path_factory.mktemp("work") / "todo-free"
    shutil.copytree(FIXTURES / "plugins" / "todo-free", working)
    write_files(working, {".git/HEAD": "ref: refs/heads/main\n", "__pycache__/x.pyc": b"\0"})
    base = kb()

    first = charter("plugin", "add", "--dev", str(working), cwd=base)

    assert first.exit_code == 0, first.stdout
    assert sorted(p.name for p in (base / INSTALLED).iterdir()) == ["charter-plugin.yaml", "check.py"]
    assert _lock(base)["plugins"]["todo-free"] == {
        "version": "1.2.0",
        "source": {"dev": True},
        "sha256": TODO_FREE_SHA256,
    }
    assert charter("validate", "--format", "json", cwd=base).exit_code == 1

    (working / "check.py").write_text(
        "import json, sys\nsys.stdout.write(json.dumps({'protocol': 'charter-plugin/1', 'diagnostics': []}))\n",
        encoding="utf-8",
    )
    second = charter("plugin", "add", "--dev", str(working), cwd=base)

    assert second.exit_code == 0, second.stdout
    assert _lock(base)["plugins"]["todo-free"]["sha256"] != TODO_FREE_SHA256
    assert charter("validate", "--format", "json", cwd=base).exit_code == 0


def test_dev_path_must_be_a_directory(charter, kb, tmp_path_factory):
    missing = tmp_path_factory.mktemp("work") / "nothing"

    result = charter("plugin", "add", "--dev", str(missing), cwd=kb())

    assert result.exit_code == 2
    assert "usage/invalid-source" in result.stdout
