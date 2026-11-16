import errno
import io
import os
import shlex
import stat
import struct
import sys
import zipfile
import zlib

import pytest

from charter import snapshot as snapshot_module
from conftest import write_files
from hostile_names import NAMES, can_create, zip_with_raw_name

KB = {
    "index.md": "---\nkind: note\n---\nHello\r\nthere\n",
    "Notes/deep/one.md": "one\n",
    ".obsidian/app.json": '{"a": 1}',
    ".git/HEAD": "ref: refs/heads/main\n",
    ".hidden": "dot\n",
    "blob.bin": bytes(range(256)),
    "spaced name/é ü.md": "unicode\n",
}


@pytest.fixture
def kb(tmp_path):
    """A small knowledge base with dotfiles, binary content and empty folders, inside its own parent folder."""
    folder = tmp_path / "work" / "kb"
    write_files(folder, KB)
    (folder / "empty").mkdir()
    (folder / "Notes" / "also empty" / "nested").mkdir(parents=True)
    return folder


def tree(folder):
    """Every path under `folder` with its bytes (None for a folder)."""
    return {
        path.relative_to(folder).as_posix(): path.read_bytes() if path.is_file() else None
        for path in sorted(folder.rglob("*"))
    }


def zips(directory):
    return sorted(directory.glob("*.zip"))


def printed_command(result):
    line = [line for line in result.stdout.splitlines() if line.startswith("  ")][0].strip()
    words = shlex.split(line, posix=os.name != "nt")
    return [word.strip('"') if os.name == "nt" else word for word in words]


def test_round_trip_is_byte_identical_including_empty_folders_and_dotfiles(charter, kb):
    before = tree(kb)

    taken = charter("snapshot", str(kb), cwd=kb.parent)

    assert taken.exit_code == 0
    assert taken.stderr == ""
    archive = zips(kb.parent)[0]
    restored_into = kb.parent / "copy"
    result = charter("snapshot", "restore", str(archive), "--to", str(restored_into), cwd=kb.parent)

    assert result.exit_code == 0
    assert tree(restored_into) == before
    assert "empty" in before and before["empty"] is None
    assert ".git/HEAD" in before and ".hidden" in before


def test_default_snapshot_sits_beside_the_folder_under_a_colonless_utc_name(charter, kb):
    result = charter("snapshot", str(kb), cwd=kb.parent)

    (archive,) = zips(kb.parent)
    assert archive.name.startswith("kb-") and archive.name.endswith("Z.zip")
    assert ":" not in archive.name
    assert not list(kb.rglob("*.zip"))
    assert str(archive) in result.stdout


def test_entries_are_posix_relative_and_add_nothing_to_the_tree(charter, kb):
    charter("snapshot", str(kb), cwd=kb.parent)

    with zipfile.ZipFile(zips(kb.parent)[0]) as bundle:
        names = bundle.namelist()
    assert all("\\" not in name and not name.startswith("/") for name in names)
    assert sorted(name.rstrip("/") for name in names) == sorted(tree(kb))


def test_to_chooses_a_zip_path_and_creates_missing_parents(charter, kb, tmp_path):
    target = tmp_path / "backups" / "mine.zip"

    result = charter("snapshot", str(kb), "--to", str(target), cwd=tmp_path)

    assert result.exit_code == 0
    assert target.is_file()
    assert zips(kb.parent) == []


def test_to_an_existing_folder_puts_the_default_name_in_it(charter, kb, tmp_path):
    out = tmp_path / "out"
    out.mkdir()

    result = charter("snapshot", str(kb), "--to", str(out), cwd=tmp_path)

    assert result.exit_code == 0
    assert len(zips(out)) == 1


def test_an_explicit_target_that_exists_is_never_overwritten(charter, kb, tmp_path):
    target = tmp_path / "mine.zip"
    target.write_bytes(b"precious")

    result = charter("snapshot", str(kb), "--to", str(target), cwd=tmp_path)

    assert result.exit_code == 1
    assert "snapshot/exists" in result.stdout
    assert target.read_bytes() == b"precious"


def test_snapshots_in_the_same_second_get_distinct_names(charter, kb):
    for _ in range(4):
        assert charter("snapshot", str(kb), cwd=kb.parent).exit_code == 0

    assert len(zips(kb.parent)) == 4


@pytest.mark.parametrize("spelling", ["inside.zip", "empty/inside.zip", "empty/../inside.zip", "empty"])
def test_writing_inside_the_folder_is_refused(charter, kb, spelling):
    before = tree(kb)

    result = charter("snapshot", str(kb), "--to", str(kb / spelling), cwd=kb.parent)

    assert result.exit_code == 2
    assert "usage/snapshot-inside-folder" in result.stdout
    assert tree(kb) == before


def test_dotdot_back_into_the_folder_is_refused(charter, kb):
    result = charter("snapshot", str(kb), "--to", "../x.zip", cwd=kb / "empty")

    assert result.exit_code == 2
    assert not (kb / "x.zip").exists()


def test_a_symlink_into_the_folder_does_not_hide_the_destination(charter, kb, tmp_path):
    link = tmp_path / "link"
    try:
        link.symlink_to(kb / "empty", target_is_directory=True)
    except OSError:
        pytest.skip("symlinks are not available here")

    result = charter("snapshot", str(kb), "--to", str(link / "x.zip"), cwd=tmp_path)

    assert result.exit_code == 2
    assert not (kb / "empty" / "x.zip").exists()


def test_a_symlink_inside_the_folder_is_refused_and_nothing_is_written(charter, kb):
    try:
        (kb / "alias").symlink_to(kb / "index.md")
    except OSError:
        pytest.skip("symlinks are not available here")

    result = charter("snapshot", str(kb), cwd=kb.parent)

    assert result.exit_code == 1
    assert "snapshot/unsupported-entry" in result.stdout and "alias" in result.stdout
    assert zips(kb.parent) == []


def test_missing_folder_and_a_file_are_usage_errors(charter, kb):
    missing = charter("snapshot", "nope", cwd=kb.parent)
    a_file = charter("snapshot", str(kb / "index.md"), cwd=kb.parent)

    assert missing.exit_code == a_file.exit_code == 2
    assert "usage/folder-not-found" in missing.stdout


def test_the_printed_command_restores_the_folder_when_run(charter, kb):
    before = tree(kb)
    result = charter("snapshot", str(kb), cwd=kb.parent)
    command = printed_command(result)
    assert command[:3] == ["charter", "snapshot", "restore"] and "--to" in command
    (kb / "index.md").write_text("ruined", encoding="utf-8")
    (kb / "extra.md").write_text("new", encoding="utf-8")

    rerun = charter(*command[1:], cwd=kb.parent)

    assert rerun.exit_code == 0
    assert tree(kb) == before
    assert [p.name for p in kb.parent.iterdir() if p.name.startswith(".kb.")] == []


def test_the_printed_command_quotes_paths_with_spaces(charter, tmp_path):
    folder = tmp_path / "my notes (v2)" / "kb one"
    write_files(folder, {"a.md": "a\n"})
    before = tree(folder)

    result = charter("snapshot", str(folder), cwd=tmp_path)
    command = printed_command(result)
    (folder / "a.md").write_text("changed", encoding="utf-8")

    assert charter(*command[1:], cwd=tmp_path).exit_code == 0
    assert tree(folder) == before


def test_restore_without_to_uses_the_recorded_name_beside_the_zip(charter, kb, tmp_path):
    charter("snapshot", str(kb), cwd=kb.parent)
    archive = zips(kb.parent)[0]
    moved = tmp_path / "elsewhere" / archive.name
    moved.parent.mkdir()
    archive.rename(moved)

    result = charter("snapshot", "restore", str(moved), cwd=tmp_path)

    assert result.exit_code == 0
    assert tree(moved.parent / "kb") == tree(kb)


def test_restore_into_a_non_empty_target_is_refused_untouched(charter, kb):
    charter("snapshot", str(kb), cwd=kb.parent)
    archive = zips(kb.parent)[0]
    (kb / "mine.md").write_text("keep", encoding="utf-8")
    before = tree(kb)

    result = charter("snapshot", "restore", str(archive), "--to", str(kb), cwd=kb.parent)

    assert result.exit_code == 1
    assert "snapshot/target-not-empty" in result.stdout
    assert tree(kb) == before


def test_restore_into_an_empty_existing_folder_is_allowed(charter, kb, tmp_path):
    charter("snapshot", str(kb), cwd=kb.parent)
    target = tmp_path / "blank"
    target.mkdir()

    result = charter("snapshot", "restore", str(zips(kb.parent)[0]), "--to", str(target), cwd=tmp_path)

    assert result.exit_code == 0
    assert tree(target) == tree(kb)


def test_restore_into_a_missing_target_creates_it_and_its_parents(charter, kb, tmp_path):
    charter("snapshot", str(kb), cwd=kb.parent)
    target = tmp_path / "a" / "b" / "c"

    result = charter("snapshot", "restore", str(zips(kb.parent)[0]), "--to", str(target), cwd=tmp_path)

    assert result.exit_code == 0
    assert tree(target) == tree(kb)


def test_replace_swaps_the_target_and_leaves_no_leftovers(charter, kb):
    before = tree(kb)
    charter("snapshot", str(kb), cwd=kb.parent)
    (kb / "extra.md").write_text("new", encoding="utf-8")
    (kb / "Notes" / "deep" / "one.md").write_text("changed", encoding="utf-8")

    result = charter(
        "snapshot", "restore", str(zips(kb.parent)[0]), "--to", str(kb), "--replace", cwd=kb.parent
    )

    assert result.exit_code == 0
    assert tree(kb) == before
    assert sorted(p.name for p in kb.parent.iterdir()) == sorted(["kb", zips(kb.parent)[0].name])


def test_a_restore_that_fails_midway_leaves_the_replaced_target_intact(charter, kb, monkeypatch):
    charter("snapshot", str(kb), cwd=kb.parent)
    archive = zips(kb.parent)[0]
    (kb / "extra.md").write_text("new", encoding="utf-8")
    after_edit = tree(kb)
    # A member whose data no longer matches its checksum fails during extraction, after earlier members were written.
    data = bytearray(archive.read_bytes())
    with zipfile.ZipFile(archive) as bundle:
        info = bundle.getinfo("blob.bin")
    extra = int.from_bytes(data[info.header_offset + 28 : info.header_offset + 30], "little")
    data[info.header_offset + 30 + len(info.filename.encode()) + extra + 5] ^= 0xFF
    archive.write_bytes(bytes(data))

    result = charter("snapshot", "restore", str(archive), "--to", str(kb), "--replace", cwd=kb.parent)

    assert result.exit_code == 2
    assert tree(kb) == after_edit
    assert [p.name for p in kb.parent.iterdir() if p.name.startswith(".kb.")] == []


def test_replace_refuses_a_target_that_holds_the_zip(charter, kb):
    inner = kb / "empty" / "snap.zip"
    charter("snapshot", str(kb), "--to", str(kb.parent / "outer.zip"), cwd=kb.parent)
    (kb / "empty").joinpath("snap.zip").write_bytes((kb.parent / "outer.zip").read_bytes())

    result = charter("snapshot", "restore", str(inner), "--to", str(kb), "--replace", cwd=kb.parent)

    assert result.exit_code == 1
    assert "snapshot/target-holds-input" in result.stdout
    assert inner.is_file()


def hand_built(path, names, comment=None):
    with zipfile.ZipFile(path, "w") as bundle:
        bundle.writestr("good.md", "good\n")
        for name in names:
            # ZipInfo(name) would rewrite backslashes (on Windows) and cut at a NUL; assigning `filename` after
            # construction stores the name as given, as an archive from another tool can.
            info = zipfile.ZipInfo("placeholder")
            info.filename = name
            bundle.writestr(info, "evil\n")
        if comment is not None:
            bundle.comment = comment
    return path


@pytest.mark.parametrize(
    "bad",
    ["../evil", "sub/../../evil", "/abs/evil", "C:/evil", "C:evil", "dir\\evil", "..\\evil", "./dot", "dir/e\0vil"],
    ids=["dotdot", "nested-dotdot", "absolute", "drive", "drive-relative", "backslash", "backslash-dotdot", "dot", "nul"],
)
def test_a_malicious_archive_is_refused_whole_with_nothing_extracted(charter, tmp_path, bad):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    archive = hand_built(tmp_path / "evil.zip", [bad])
    target = sandbox / "out"

    result = charter("snapshot", "restore", str(archive), "--to", str(target), cwd=sandbox)

    assert result.exit_code == 2
    assert "snapshot/unsafe-archive" in result.stdout
    assert sorted(p.name for p in tmp_path.iterdir()) == ["evil.zip", "sandbox"]
    assert list(sandbox.iterdir()) == []


def test_every_unsafe_entry_is_refused_together(charter, tmp_path):
    archive = hand_built(tmp_path / "evil.zip", ["../evil", "/abs", "a\\b"])

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2
    assert "3 unsafe entries" in result.stdout
    assert not (tmp_path / "out").exists() and not (tmp_path / "evil").exists()


def test_backslash_separators_are_rejected_not_normalised(charter, tmp_path):
    # An archive built by a tool that writes Windows separators: restoring it under a guessed layout could
    # land files anywhere, so charter refuses it (snapshots never contain backslashes).
    archive = hand_built(tmp_path / "win.zip", ["Notes\\one.md"])

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2
    assert not (tmp_path / "out").exists()


def with_unicode_path(path, entries):
    """A zip whose entries are (header name, Unicode Path extra field name or None): the field (id 0x7075) is
    what Info-ZIP writes for a non-ASCII name, and Python 3.12+ reads it as the entry's `filename`."""
    with zipfile.ZipFile(path, "w") as bundle:
        for header, unicode_name in entries:
            info = zipfile.ZipInfo(header)
            if unicode_name is not None:
                name = unicode_name.encode("utf-8")
                info.extra = struct.pack("<HHBL", 0x7075, 5 + len(name), 1, zlib.crc32(header.encode("ascii"))) + name
            bundle.writestr(info, "payload\n")
    return path


def listing(root):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*"))


ZIPFILE_READS_UNICODE_PATH = sys.version_info >= (3, 12)

# Each: the name the extra field gives, and a second plain entry it may duplicate.
UNICODE_PATH_ATTACKS = {
    "dotdot": ("../x", []),
    "nested-dotdot": ("a/../../x", []),
    "absolute": ("/abs/x", []),
    "backslash": ("dir\\x", []),
    "drive": ("C:/x", []),
    "duplicate": ("other.md", [("other.md", None)]),
}


@pytest.mark.parametrize("attack", UNICODE_PATH_ATTACKS)
def test_a_unicode_path_extra_field_cannot_smuggle_an_unsafe_name(charter, tmp_path, attack):
    named, others = UNICODE_PATH_ATTACKS[attack]
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    archive = with_unicode_path(tmp_path / "evil.zip", [*others, ("ok.md", named)])
    # zipfile turns a backslash into a slash on Windows, in the field's name as in the header's.
    read_as = named.replace("\\", "/") if os.sep == "\\" else named
    with zipfile.ZipFile(archive) as bundle:
        smuggled = [info.filename for info in bundle.infolist()].count(read_as) > len(others)
    # Pinned per version so that a zipfile which starts or stops reading the field cannot pass unnoticed.
    assert smuggled == ZIPFILE_READS_UNICODE_PATH
    before = listing(tmp_path)

    result = charter("snapshot", "restore", str(archive), "--to", str(sandbox / "out"), cwd=sandbox)

    # Where zipfile reads the field (3.12+), the entry is the unsafe name and must be refused; where it ignores
    # the field the entry is the harmless header name. Either way nothing may land outside the target.
    if smuggled:
        assert result.exit_code == 2
        assert "snapshot/unsafe-archive" in result.stdout
        assert listing(tmp_path) == before
    else:
        assert result.exit_code == 0
    assert [p for p in listing(tmp_path) if not p.startswith("sandbox/out") and p not in before] == []


@pytest.mark.skipif(not ZIPFILE_READS_UNICODE_PATH, reason="this zipfile ignores the Unicode Path extra field")
def test_the_extra_field_is_judged_as_written_not_as_zipfile_rewrites_it(tmp_path):
    archive = with_unicode_path(tmp_path / "evil.zip", [("ok.md", "dir\\x")])
    with zipfile.ZipFile(archive) as bundle:
        info = bundle.infolist()[0]
    # What zipfile makes of the field on Windows, where the backslash is a separator.
    info.filename = "dir/x"

    assert snapshot_module._unsafe(info, windows=False) == (
        "backslash in the path; its Unicode path extra field names 'dir\\\\x'"
    )


def test_the_refusal_names_the_stored_spelling_and_what_the_extra_field_said(charter, tmp_path):
    archive = with_unicode_path(tmp_path / "evil.zip", [("ok.md", "../x")])
    with zipfile.ZipFile(archive) as bundle:
        if bundle.infolist()[0].filename == "ok.md":
            pytest.skip("this zipfile ignores the Unicode Path extra field")

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert "'ok.md'" in result.stdout and "'../x'" in result.stdout


def test_a_legitimate_unicode_path_extra_field_restores(charter, tmp_path):
    accented = f"caf{chr(0xE9)}.md"
    archive = with_unicode_path(tmp_path / "ok.zip", [("cafe.md", accented), ("plain.md", None)])

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 0, result.stdout
    # The restored name is the extra field's where zipfile reads it, the header's elsewhere.
    restored = accented if ZIPFILE_READS_UNICODE_PATH else "cafe.md"
    assert sorted(p.name for p in (tmp_path / "out").iterdir()) == sorted([restored, "plain.md"])


def _info(stored, filename=None):
    info = zipfile.ZipInfo("placeholder")
    info.orig_filename = stored
    info.filename = stored if filename is None else filename
    return info


def test_the_refusal_message_shows_the_stored_spelling(tmp_path):
    with pytest.raises(snapshot_module.Refused) as refused:
        snapshot_module._vet([_info("dir\\evil", "dir/evil")], tmp_path / "a.zip")

    assert "'dir\\\\evil'" in str(refused.value.diagnostics[0].message)


@pytest.mark.parametrize(
    "first, second",
    [
        (_info("Dup.md"), _info("dup.md")),  # stored spellings differ in case only
        (_info("caf\u00e9.md"), _info("cafe\u0301.md")),  # NFC against NFD
        (_info("one.md", "Same.md"), _info("two.md", "same.md")),  # only the rewritten names collide
        (_info("Same.md", "one.md"), _info("same.md", "two.md")),  # only the stored names collide
        (_info("same.md"), _info("one.md", "same.md")),  # one entry's stored name against another's rewrite
        (_info("same.md"), _info("same.md")),
    ],
)
def test_collisions_are_found_on_either_spelling_whatever_the_volume(first, second, tmp_path):
    with pytest.raises(snapshot_module.Refused):
        snapshot_module._vet([first, second], tmp_path / "a.zip")


def test_the_same_name_twice_is_called_listed_twice_not_a_case_difference(tmp_path):
    with pytest.raises(snapshot_module.Refused) as twice:
        snapshot_module._vet([_info("same.md"), _info("same.md")], tmp_path / "a.zip")
    with pytest.raises(snapshot_module.Refused) as cased:
        snapshot_module._vet([_info("Same.md"), _info("same.md")], tmp_path / "a.zip")

    assert "listed twice" in twice.value.diagnostics[0].message
    assert "listed twice" not in cased.value.diagnostics[0].message


@pytest.mark.parametrize("order", [("a/", "a"), ("a", "a/")], ids=["folder-first", "file-first"])
def test_a_folder_and_a_file_of_one_name_are_caught_by_the_vetting_before_extraction(charter, tmp_path, order):
    archive = tmp_path / "clash.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for name in order:
            bundle.writestr(name, "" if name.endswith("/") else "data")

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2
    assert "snapshot/unsafe-archive" in result.stdout
    assert "listed twice" in result.stdout
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("offset", [0xFFFFFFFF, "past-the-end"], ids=["0xFFFFFFFF", "beyond-the-file"])
def test_an_end_record_offset_that_points_nowhere_is_corrupt_not_a_traceback(charter, tmp_path, offset):
    archive = tmp_path / "bad-offset.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("a.md", "data")
    data = bytearray(archive.read_bytes())
    if offset == "past-the-end":
        offset = len(data) + 1000
    # The end-of-central-directory record keeps the central directory's offset 16 bytes in.
    struct.pack_into("<I", data, data.rindex(b"PK\x05\x06") + 16, offset)
    archive.write_bytes(data)

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2
    assert "snapshot/corrupt" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("stored", ["dir\\evil", "dir/e\0vil"], ids=["backslash", "nul"])
def test_the_stored_name_is_judged_not_zipfiles_rewrite_of_it(stored):
    # zipfile keeps the archive's spelling in `orig_filename` and a rewritten, harmless-looking `filename`
    # (backslash to slash on Windows, cut at the NUL everywhere); the refusal must follow the former.
    info = zipfile.ZipInfo("dir/evil")
    info.orig_filename = stored

    assert snapshot_module._unsafe(info, windows=False) is not None


@pytest.mark.parametrize("name", NAMES)
def test_an_entry_with_a_hostile_name_gives_a_clean_outcome_not_a_traceback(charter, tmp_path, name):
    archive = zip_with_raw_name(tmp_path / "hostile.zip", name.encode())

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert "Traceback" not in result.stdout + result.stderr
    # Without the UTF-8 flag the header bytes read as cp437, so a non-ASCII name comes back as another name.
    if result.exit_code == 0:
        assert len(list((tmp_path / "out").iterdir())) == 1
    else:
        assert "snapshot/" in result.stdout
        assert not (tmp_path / "out").exists()


def test_a_symlink_entry_is_refused(charter, tmp_path):
    archive = tmp_path / "link.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        info = zipfile.ZipInfo("link")
        info.create_system = 3
        info.external_attr = 0o120777 << 16
        bundle.writestr(info, "/etc/passwd")

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2
    assert not (tmp_path / "out").exists()


def test_a_duplicate_entry_is_refused(charter, tmp_path):
    archive = tmp_path / "dup.zip"
    with pytest.warns(UserWarning), zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("a.md", "1")
        bundle.writestr("a.md", "2")

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2
    assert not (tmp_path / "out").exists()


def test_windows_forbidden_characters_fail_clearly_before_extracting(charter, tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot_module, "_ON_WINDOWS", True)
    archive = hand_built(tmp_path / "w.zip", ["ab:c.md"])

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2
    assert "Windows" in result.stdout
    assert not (tmp_path / "out").exists()


@pytest.mark.parametrize("name", ["NUL", "notes/aux.md", "COM1/a.md", "con .md"])
def test_windows_reserved_names_fail_clearly_before_extracting(charter, tmp_path, monkeypatch, name):
    # Windows sends a write to `NUL` to the device, so the note would vanish while restore reports success.
    monkeypatch.setattr(snapshot_module, "_ON_WINDOWS", True)
    archive = hand_built(tmp_path / "w.zip", [name])

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2
    assert "Windows reserves" in result.stdout
    assert not (tmp_path / "out").exists()


def test_a_corrupt_or_non_zip_file_is_a_usage_error_not_a_traceback(charter, tmp_path):
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"this is not a zip")

    result = charter("snapshot", "restore", str(junk), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2
    assert "snapshot/corrupt" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
    assert not (tmp_path / "out").exists()


def test_a_truncated_snapshot_is_corrupt(charter, kb, tmp_path):
    charter("snapshot", str(kb), cwd=kb.parent)
    archive = zips(kb.parent)[0]
    archive.write_bytes(archive.read_bytes()[: archive.stat().st_size // 2])

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2
    assert not (tmp_path / "out").exists()


def test_restoring_a_missing_zip_is_a_usage_error(charter, tmp_path):
    result = charter("snapshot", "restore", "missing.zip", "--to", "out", cwd=tmp_path)

    assert result.exit_code == 2
    assert "usage/file-not-found" in result.stdout


def test_a_foreign_zip_needs_to(charter, tmp_path):
    archive = hand_built(tmp_path / "plain.zip", [])

    refused = charter("snapshot", "restore", str(archive), cwd=tmp_path)
    allowed = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert refused.exit_code == 2 and "usage/no-recorded-folder" in refused.stdout
    assert allowed.exit_code == 0 and (tmp_path / "out" / "good.md").read_text() == "good\n"


def test_a_comment_naming_a_path_is_not_trusted_as_the_target(charter, tmp_path):
    archive = hand_built(
        tmp_path / "t.zip", [], comment=b'{"format": "charter-snapshot/1", "folder": "../escape"}'
    )

    result = charter("snapshot", "restore", str(archive), cwd=tmp_path)

    assert result.exit_code == 2
    assert not (tmp_path.parent / "escape").exists()


def test_a_folder_named_restore_needs_dot_slash(charter, tmp_path):
    folder = tmp_path / "restore"
    write_files(folder, {"a.md": "a\n"})

    bare = charter("snapshot", "restore", cwd=tmp_path)
    explicit = charter("snapshot", "./restore", cwd=tmp_path)

    assert bare.exit_code == 2
    assert "./restore" in bare.stdout
    assert explicit.exit_code == 0
    assert [p.name for p in tmp_path.glob("restore-*.zip")] != []


def test_argument_mistakes_are_usage_errors(charter, kb):
    assert charter("snapshot", cwd=kb.parent).exit_code == 2
    assert charter("snapshot", "a", "b", cwd=kb.parent).exit_code == 2
    assert charter("snapshot", str(kb), "--replace", cwd=kb.parent).exit_code == 2
    assert charter("snapshot", "restore", "a.zip", "b.zip", cwd=kb.parent).exit_code == 2


def test_snapshot_works_with_no_contract_and_ignores_one_if_present(charter, kb, tmp_path):
    # Nothing above kb is a contract, so a run that went looking for one would fail.
    assert charter("snapshot", str(kb), cwd=kb).exit_code == 0

    write_files(tmp_path / "work", {"charter.yaml": "this: [is not a valid contract"})
    write_files(kb, {"charter.yaml": "also: [broken"})
    archive = tmp_path / "with-contract.zip"
    result = charter("snapshot", str(kb), "--to", str(archive), cwd=kb)
    assert result.exit_code == 0
    restored = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "back"), cwd=kb)

    assert restored.exit_code == 0
    assert (tmp_path / "back" / "charter.yaml").read_text() == "also: [broken"


def test_executable_bit_and_modification_times_survive(charter, kb, tmp_path):
    if os.name == "nt":
        pytest.skip("no executable bit")
    script = kb / "run.sh"
    script.write_text("#!/bin/sh\n")
    script.chmod(0o755)
    os.utime(script, (1_700_000_000, 1_700_000_000))
    (kb / "plain.md").write_text("x")
    (kb / "plain.md").chmod(0o644)
    charter("snapshot", str(kb), cwd=kb.parent)

    charter("snapshot", "restore", str(zips(kb.parent)[0]), "--to", str(tmp_path / "back"), cwd=tmp_path)

    restored = tmp_path / "back"
    assert os.access(restored / "run.sh", os.X_OK)
    assert not os.access(restored / "plain.md", os.X_OK)
    assert abs((restored / "run.sh").stat().st_mtime - 1_700_000_000) <= 2


# --- review round 1 ---


def test_names_restore_would_refuse_are_refused_up_front(charter, kb, tmp_path):
    if not (can_create("we\\ird.md", tmp_path) and can_create("C:note.md", tmp_path)):
        pytest.skip("this file system cannot hold these names")
    write_files(kb, {"we\\ird.md": "x", "C:note.md": "y"})

    result = charter("snapshot", str(kb), cwd=kb.parent)

    assert result.exit_code == 1
    assert "snapshot/unsupported-entry" in result.stdout
    assert "we\\\\ird.md" in result.stdout and "C:note.md" in result.stdout
    assert "Rename" in result.stdout
    assert zips(kb.parent) == []


def test_a_name_that_is_not_valid_utf8_is_refused_not_a_traceback(charter, kb, tmp_path):
    # Windows names are UTF-16, where the same problem is a lone surrogate; elsewhere it is a stray byte.
    name = "bad\ud800.md" if os.name == "nt" else b"bad\xff.md"
    if not can_create(name, tmp_path):
        pytest.skip("this filesystem rejects names that are not UTF-8")
    raw = os.fsencode(str(kb)) + os.sep.encode() + os.fsencode(name)
    with open(raw, "wb") as handle:
        handle.write(b"x")

    result = charter("snapshot", str(kb), cwd=kb.parent)

    assert result.exit_code == 1
    assert "not valid UTF-8" in result.stdout
    assert zips(kb.parent) == []


def test_names_differing_only_in_case_are_refused_both_ways(charter, kb, tmp_path):
    write_files(kb, {"a.md": "1", "A.md": "2"})
    if len([p for p in kb.iterdir() if p.name.lower() == "a.md"]) < 2:
        pytest.skip("case-insensitive volume")
    taken = charter("snapshot", str(kb), cwd=kb.parent)
    archive = hand_built(tmp_path / "case.zip", ["Good.md"])
    restored = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert taken.exit_code == 1 and "letter case" in taken.stdout
    assert restored.exit_code == 2 and "snapshot/unsafe-archive" in restored.stdout
    assert not (tmp_path / "out").exists()


def test_an_unreadable_subfolder_is_refused_not_a_traceback(charter, kb):
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("permissions cannot block this user")
    locked = kb / "Notes" / "deep"
    locked.chmod(0)
    try:
        result = charter("snapshot", str(kb), cwd=kb.parent)
    finally:
        locked.chmod(0o755)

    assert result.exit_code == 1
    assert "snapshot/unreadable" in result.stdout and "deep" in result.stdout
    assert zips(kb.parent) == []


def test_an_unreadable_file_leaves_no_partial_zip(charter, kb):
    if os.name == "nt" or os.geteuid() == 0:
        pytest.skip("permissions cannot block this user")
    secret = kb / "secret.md"
    secret.write_text("x")
    secret.chmod(0)
    try:
        result = charter("snapshot", str(kb), cwd=kb.parent)
    finally:
        secret.chmod(0o644)

    assert result.exit_code == 1
    assert zips(kb.parent) == []


def _break_renames(monkeypatch, *, into_place, back):
    """Make renaming the staged folder into place fail, and optionally the rollback too."""
    real = snapshot_module.Path.rename

    def rename(self, target):
        if into_place and "charter-restore-" in self.name:
            raise into_place
        if back and "charter-old-" in self.name:
            raise OSError("rollback blocked")
        return real(self, target)

    monkeypatch.setattr(snapshot_module.Path, "rename", rename)


def test_a_failed_swap_puts_the_old_target_back(charter, kb, monkeypatch):
    charter("snapshot", str(kb), cwd=kb.parent)
    archive = zips(kb.parent)[0]
    (kb / "extra.md").write_text("mine")
    after_edit = tree(kb)
    _break_renames(monkeypatch, into_place=OSError("disk says no"), back=False)

    result = charter("snapshot", "restore", str(archive), "--to", str(kb), "--replace", cwd=kb.parent)

    assert result.exit_code == 1
    assert "left as it was" in result.stdout
    assert tree(kb) == after_edit


def test_an_interrupt_during_the_swap_puts_the_old_target_back(charter, kb, monkeypatch):
    charter("snapshot", str(kb), cwd=kb.parent)
    archive = zips(kb.parent)[0]
    (kb / "extra.md").write_text("mine")
    after_edit = tree(kb)
    _break_renames(monkeypatch, into_place=KeyboardInterrupt(), back=False)

    with pytest.raises(KeyboardInterrupt):
        charter("snapshot", "restore", str(archive), "--to", str(kb), "--replace", cwd=kb.parent)

    assert tree(kb) == after_edit


def test_a_failed_rollback_names_where_the_old_content_is(charter, kb, monkeypatch):
    charter("snapshot", str(kb), cwd=kb.parent)
    archive = zips(kb.parent)[0]
    (kb / "extra.md").write_text("mine")
    _break_renames(monkeypatch, into_place=OSError("disk says no"), back=True)

    result = charter("snapshot", "restore", str(archive), "--to", str(kb), "--replace", cwd=kb.parent)

    assert result.exit_code == 1
    assert "left as it was" not in result.stdout
    (aside,) = [p for p in kb.parent.iterdir() if ".charter-old-" in p.name]
    assert aside.as_posix() in result.stdout
    assert (aside / "extra.md").read_text() == "mine"


def test_a_trailing_separator_means_folder_and_is_created(charter, kb, tmp_path):
    result = charter("snapshot", str(kb), "--to", str(tmp_path / "out") + "/", cwd=tmp_path)

    assert result.exit_code == 0
    (archive,) = zips(tmp_path / "out")
    assert archive.name.startswith("kb-")


def test_the_printed_command_is_absolute_even_for_a_relative_to(charter, kb, tmp_path):
    before = tree(kb)
    result = charter("snapshot", str(kb), "--to", "rel/snap.zip", cwd=tmp_path)
    command = printed_command(result)
    (kb / "index.md").write_text("ruined")
    elsewhere = tmp_path / "somewhere"
    elsewhere.mkdir()

    assert os.path.isabs(command[3]) and os.path.isabs(command[5])
    assert charter(*command[1:], cwd=elsewhere).exit_code == 0
    assert tree(kb) == before


def test_inside_check_is_not_fooled_by_letter_case(charter, kb):
    if not (kb.parent / "KB").exists():
        pytest.skip("case-sensitive volume")

    result = charter("snapshot", str(kb), "--to", str(kb.parent / "KB" / "x.zip"), cwd=kb.parent)

    assert result.exit_code == 2
    assert not (kb / "x.zip").exists()


def test_the_success_message_only_claims_a_replacement_when_there_was_one(charter, kb, tmp_path):
    charter("snapshot", str(kb), cwd=kb.parent)
    archive = str(zips(kb.parent)[0])
    empty = tmp_path / "blank"
    empty.mkdir()

    into_missing = charter("snapshot", "restore", archive, "--to", str(tmp_path / "new"), cwd=tmp_path)
    into_empty = charter("snapshot", "restore", archive, "--to", str(empty), cwd=tmp_path)
    over_content = charter("snapshot", "restore", archive, "--to", str(kb), "--replace", cwd=tmp_path)

    assert "replacing" not in into_missing.stdout
    assert "replacing" not in into_empty.stdout
    assert "replacing" in over_content.stdout


def _stuck_cleanup(monkeypatch, marker):
    """Make every folder whose name holds `marker` one that cannot be deleted: the cleanup reports it as still
    there, as it does for a file another program holds open."""
    real = snapshot_module.remove_tree

    def remove_tree(path):
        return [path] if marker in path.name else real(path)

    monkeypatch.setattr(snapshot_module, "remove_tree", remove_tree)


@pytest.mark.parametrize("marker", [".charter-old-", ".charter-restore-"])
def test_a_folder_that_cannot_be_deleted_after_a_restore_is_a_warning_and_the_exit_code_stays_zero(
    charter, kb, monkeypatch, marker
):
    charter("snapshot", str(kb), cwd=kb.parent)
    archive = zips(kb.parent)[0]
    _stuck_cleanup(monkeypatch, marker)

    result = charter("snapshot", "restore", str(archive), "--to", str(kb), "--replace", cwd=kb.parent)

    assert result.exit_code == 0
    assert result.stdout.startswith("Restored ")
    assert "warning" in result.stderr
    assert "files/leftover" in result.stderr
    assert f"{kb.parent.as_posix()}/.kb{marker}" in result.stderr


def test_a_failed_restore_names_the_folder_it_could_not_delete_in_its_hint(charter, kb, monkeypatch):
    charter("snapshot", str(kb), cwd=kb.parent)
    archive = zips(kb.parent)[0]
    _break_renames(monkeypatch, into_place=OSError("disk says no"), back=False)
    _stuck_cleanup(monkeypatch, ".charter-restore-")

    result = charter("snapshot", "restore", str(archive), "--to", str(kb), "--replace", cwd=kb.parent)

    assert result.exit_code == 1
    assert "snapshot/restore-failed" in result.stdout
    assert "left as it was; also remove" in result.stdout
    assert f"{kb.parent.as_posix()}/.kb.charter-restore-" in result.stdout


def test_replacing_a_folder_that_holds_read_only_files_leaves_no_old_folder(charter, kb):
    charter("snapshot", str(kb), cwd=kb.parent)
    archive = zips(kb.parent)[0]
    (kb / "locked").mkdir()
    (kb / "locked" / "inner.txt").write_text("x", encoding="utf-8")
    (kb / "locked" / "inner.txt").chmod(stat.S_IREAD)
    # On POSIX a read-only folder is what blocks deleting the files in it.
    (kb / "locked").chmod(stat.S_IREAD | stat.S_IEXEC)
    (kb / "top.txt").write_text("x", encoding="utf-8")
    (kb / "top.txt").chmod(stat.S_IREAD)

    result = charter("snapshot", "restore", str(archive), "--to", str(kb), "--replace", cwd=kb.parent)

    assert result.exit_code == 0
    assert result.stderr == ""
    assert [p.name for p in kb.parent.iterdir() if p.name.startswith(".kb.")] == []


def assert_clean_refusal(result):
    assert result.exit_code == 1
    assert "snapshot/restore-failed" in result.stdout
    assert "left as it was" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr


needs_user_permissions = pytest.mark.skipif(
    os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
    reason="needs POSIX permissions that bind the current user",
)


@pytest.fixture
def read_only_parent(tmp_path):
    """A writable folder; tests call `lock(parent)` once it is filled. Permissions are restored on teardown."""
    parent = tmp_path / "ro"
    parent.mkdir()
    yield parent
    parent.chmod(0o755)


def lock(parent):
    parent.chmod(0o555)


@needs_user_permissions
@pytest.mark.parametrize("below", ["x", "a/x"], ids=["missing-target", "missing-parents-too"])
def test_restore_into_a_read_only_parent_is_refused_cleanly(charter, kb, tmp_path, read_only_parent, below):
    charter("snapshot", str(kb), cwd=kb.parent)
    lock(read_only_parent)

    result = charter("snapshot", "restore", str(zips(kb.parent)[0]), "--to", str(read_only_parent / below),
                     cwd=tmp_path)

    assert_clean_refusal(result)
    assert list(read_only_parent.iterdir()) == []


@needs_user_permissions
@pytest.mark.parametrize("content", [{}, {"mine.md": "keep"}], ids=["empty-target", "occupied-target"])
def test_restore_over_an_existing_target_in_a_read_only_parent_leaves_it_intact(
    charter, kb, tmp_path, read_only_parent, content
):
    charter("snapshot", str(kb), cwd=kb.parent)
    target = read_only_parent / "x"
    write_files(target, content)
    target.mkdir(exist_ok=True)
    before = tree(target)
    lock(read_only_parent)

    result = charter("snapshot", "restore", str(zips(kb.parent)[0]), "--to", str(target), "--replace",
                     cwd=tmp_path)

    assert_clean_refusal(result)
    assert tree(target) == before
    assert [p.name for p in read_only_parent.iterdir()] == ["x"]


def test_restore_whose_parent_path_is_a_file_is_refused_cleanly(charter, kb, tmp_path):
    charter("snapshot", str(kb), cwd=kb.parent)
    blocker = tmp_path / "blocker"
    blocker.write_text("not a folder", encoding="utf-8")

    result = charter("snapshot", "restore", str(zips(kb.parent)[0]), "--to", str(blocker / "x"), cwd=tmp_path)

    assert_clean_refusal(result)
    assert blocker.read_text(encoding="utf-8") == "not a folder"


# --- archives zipfile cannot read: a clean refusal, never a traceback ---


def zip_bytes(name="a.md", method=zipfile.ZIP_DEFLATED, comment=b""):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", method) as bundle:
        bundle.writestr(name, "hello world " * 50)
        bundle.comment = comment
    return buffer.getvalue()


def flagged_utf8_but_not_utf8():
    # 'bé.md' is stored with the UTF-8 flag; swapping the two bytes of é breaks the encoding everywhere.
    return zip_bytes("bé.md").replace(b"\xc3\xa9", b"\xff\xfe")


def bad_compressed_stream(method):
    data = zip_bytes(method=method)
    start = data.index(b"a.md") + 4
    return data[: start + 12] + b"\xff" * 8 + data[start + 20 :]


def bad_deflate_stream():
    data = zip_bytes()
    start = data.index(b"a.md") + 4
    return data[: start + 3] + b"\xff" * 4 + data[start + 7 :]


def unknown_compression_method():
    return zip_bytes().replace(b"\x08\x00", b"\x63\x00")


def cut_stream(method):
    """An entry whose compressed stream ends early while the directory is intact: both headers claim half the
    real compressed size, so the decompressor runs out of input (EOFError)."""
    data = bytearray(zip_bytes(method=method))
    central = data.index(b"PK\x01\x02")
    size = struct.unpack_from("<I", data, central + 20)[0]
    struct.pack_into("<I", data, central + 20, size // 2)
    struct.pack_into("<I", data, data.index(b"PK\x03\x04") + 18, size // 2)
    return bytes(data)


def header_offset_field(value, extra=b""):
    """A valid archive whose central directory entry claims `value` as its local header offset (a zip64 `extra`
    field may carry the real number)."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as bundle:
        info = zipfile.ZipInfo("a.md")
        info.extra = extra
        bundle.writestr(info, "hello\n")
    data = bytearray(buffer.getvalue())
    struct.pack_into("<I", data, data.index(b"PK\x01\x02") + 42, value)
    return bytes(data)


def zip64_offset_too_big():
    return header_offset_field(0xFFFFFFFF, struct.pack("<HHQ", 1, 8, 2**63))


def offset_beyond_the_file():
    return header_offset_field(len(header_offset_field(0)) + 5000)


def offset_all_ones():
    return header_offset_field(0xFFFFFFFF)


def offset_lies_about_the_entry():
    return header_offset_field(7)


MALFORMED = {
    "name-flagged-utf8-but-not-utf8": flagged_utf8_but_not_utf8,
    "unknown-compression-method": unknown_compression_method,
    "corrupt-deflate-stream": bad_deflate_stream,
    "corrupt-bzip2-stream": lambda: bad_compressed_stream(zipfile.ZIP_BZIP2),
    "corrupt-lzma-stream": lambda: bad_compressed_stream(zipfile.ZIP_LZMA),
    "truncated-deflate-stream": lambda: cut_stream(zipfile.ZIP_DEFLATED),
    "truncated-bzip2-stream": lambda: cut_stream(zipfile.ZIP_BZIP2),
    "zip64-header-offset-too-big": zip64_offset_too_big,
    "header-offset-beyond-the-file": offset_beyond_the_file,
    "header-offset-all-ones": offset_all_ones,
    "header-offset-lies": offset_lies_about_the_entry,
}


@pytest.mark.parametrize("case", MALFORMED)
def test_a_malformed_archive_is_refused_as_corrupt_with_nothing_extracted(charter, tmp_path, case):
    sandbox = tmp_path / "sandbox"
    sandbox.mkdir()
    archive = tmp_path / "bad.zip"
    archive.write_bytes(MALFORMED[case]())
    before = archive.read_bytes()

    result = charter("snapshot", "restore", str(archive), "--to", str(sandbox / "out"), cwd=sandbox)

    assert result.exit_code == 2, result.stdout + result.stderr
    assert "snapshot/corrupt" in result.stdout
    assert "left as it was" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
    assert list(sandbox.iterdir()) == []
    assert archive.read_bytes() == before


def test_a_malformed_archive_leaves_an_existing_target_as_it_was(charter, tmp_path):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(flagged_utf8_but_not_utf8())
    target = tmp_path / "out"
    write_files(target, {"mine.md": "keep"})
    before = tree(target)

    result = charter("snapshot", "restore", str(archive), "--to", str(target), "--replace", cwd=tmp_path)

    assert result.exit_code == 2
    assert "snapshot/corrupt" in result.stdout
    assert tree(target) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bad.zip", "out"]


def test_the_refusal_for_a_non_utf8_name_says_so(charter, tmp_path):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(flagged_utf8_but_not_utf8())

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert "not valid UTF-8" in result.stdout


def test_an_archive_that_cannot_be_opened_is_refused_cleanly(charter, tmp_path, monkeypatch):
    archive = tmp_path / "locked.zip"
    archive.write_bytes(zip_bytes())

    def refuse_to_open(*args, **kwargs):
        raise PermissionError(13, "Permission denied", str(archive))

    monkeypatch.setattr(zipfile, "ZipFile", refuse_to_open)

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 1, result.stdout + result.stderr
    assert "snapshot/unreadable" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
    assert not (tmp_path / "out").exists()


class NewDecompressorError(Exception):
    """Stands for an error class a future Python's decompressor adds (as compression.zstd.ZstdError once did)."""


def test_any_error_class_a_decompressor_raises_is_a_corrupt_archive(charter, tmp_path, monkeypatch):
    archive = tmp_path / "bad.zip"
    archive.write_bytes(zip_bytes())

    def explode(self, *args, **kwargs):
        raise NewDecompressorError("stream damaged")

    monkeypatch.setattr(zipfile.ZipExtFile, "read", explode)

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2, result.stdout + result.stderr
    assert "snapshot/corrupt" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
    assert not (tmp_path / "out").exists()
    assert [p.name for p in tmp_path.iterdir()] == ["bad.zip"]


@pytest.mark.parametrize("code", [errno.EINVAL, errno.EOVERFLOW, None], ids=["einval", "eoverflow", "no-errno"])
def test_an_os_error_that_only_a_bad_archive_causes_is_corrupt(charter, tmp_path, monkeypatch, code):
    # A seek to a garbage header offset fails with EINVAL or EOVERFLOW (the platform decides which, so it is
    # simulated); bzip2 reports a damaged stream as an OSError with no errno at all.
    archive = tmp_path / "bad.zip"
    archive.write_bytes(zip_bytes())

    def fail(self, *args, **kwargs):
        raise OSError(code, "Invalid argument") if code is not None else OSError("Invalid data stream")

    monkeypatch.setattr(zipfile.ZipFile, "open", fail)

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2, result.stdout + result.stderr
    assert "snapshot/corrupt" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
    assert [p.name for p in tmp_path.iterdir()] == ["bad.zip"]


def test_a_real_read_failure_on_an_entry_is_unreadable_not_corrupt(charter, tmp_path, monkeypatch):
    archive = tmp_path / "ok.zip"
    archive.write_bytes(zip_bytes())

    def fail(self, *args, **kwargs):
        raise OSError(errno.EIO, "Input/output error")

    monkeypatch.setattr(zipfile.ZipExtFile, "read", fail)

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 1, result.stdout + result.stderr
    assert "snapshot/unreadable" in result.stdout
    assert "Input/output error" in result.stdout
    assert "snapshot/corrupt" not in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
    assert [p.name for p in tmp_path.iterdir()] == ["ok.zip"]


def test_a_damaged_zstd_stream_is_a_corrupt_archive(charter, tmp_path):
    pytest.importorskip("compression.zstd", reason="zstd support in zipfile arrives with Python 3.14")
    archive = tmp_path / "bad.zip"
    archive.write_bytes(bad_compressed_stream(zipfile.ZIP_ZSTANDARD))

    result = charter("snapshot", "restore", str(archive), "--to", str(tmp_path / "out"), cwd=tmp_path)

    assert result.exit_code == 2, result.stdout + result.stderr
    assert "snapshot/corrupt" in result.stdout
    assert "Traceback" not in result.stdout + result.stderr
    assert not (tmp_path / "out").exists()
