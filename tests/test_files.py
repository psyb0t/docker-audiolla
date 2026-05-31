"""Unit tests for audiolla.files — path sanitisation + atomic writes."""

from __future__ import annotations

from pathlib import Path

import pytest

from audiolla.files import (
    FilePathError,
    list_files,
    prune_empty_parents,
    resolve_under,
    sanitize_path,
    write_atomic,
    ensure_base,
)


# ── sanitize_path ────────────────────────────────────────────────────────────

def test_sanitize_path_simple():
    assert str(sanitize_path("foo/bar.txt")) == "foo/bar.txt"


def test_sanitize_path_strips_leading_slashes():
    # Repeated leading slashes get stripped, then re-validated.
    assert str(sanitize_path("/foo.txt")) == "foo.txt"


def test_sanitize_path_rejects_empty():
    with pytest.raises(FilePathError, match="empty"):
        sanitize_path("")


def test_sanitize_path_rejects_null_byte():
    with pytest.raises(FilePathError, match="null byte"):
        sanitize_path("foo\0bar.txt")


def test_sanitize_path_rejects_backslash():
    with pytest.raises(FilePathError, match="backslash"):
        sanitize_path("foo\\bar.txt")


def test_sanitize_path_rejects_double_dot():
    with pytest.raises(FilePathError, match="forbidden segment"):
        sanitize_path("foo/../bar.txt")


def test_sanitize_path_rejects_only_slashes():
    with pytest.raises(FilePathError, match="empty after"):
        sanitize_path("////")


def test_sanitize_path_rejects_double_slash():
    with pytest.raises(FilePathError, match="empty segment|double slash"):
        sanitize_path("foo//bar.txt")


def test_sanitize_path_rejects_dot_segment():
    with pytest.raises(FilePathError, match="forbidden segment"):
        sanitize_path("foo/./bar.txt")


# ── resolve_under ────────────────────────────────────────────────────────────

def test_resolve_under_simple(tmp_path: Path):
    rel = sanitize_path("a/b/c.txt")
    out = resolve_under(tmp_path, rel)
    assert out == tmp_path / "a" / "b" / "c.txt"


def test_resolve_under_rejects_traversal(tmp_path: Path):
    # `..` is caught earlier by sanitize_path; resolve_under is the
    # second line of defense (symlink shenanigans). Symlink-out test:
    base = tmp_path / "base"
    base.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("nope")
    (base / "link").symlink_to(outside)
    with pytest.raises(FilePathError, match="escapes|outside|symlink"):
        resolve_under(base, sanitize_path("link"))


# ── write_atomic + list_files + prune_empty_parents ──────────────────────────

def test_write_atomic_creates_file(tmp_path: Path):
    target = tmp_path / "sub" / "file.txt"
    write_atomic(target, b"hello")
    assert target.read_bytes() == b"hello"


def test_write_atomic_overwrites(tmp_path: Path):
    target = tmp_path / "f.txt"
    write_atomic(target, b"first")
    write_atomic(target, b"second")
    assert target.read_bytes() == b"second"


def test_list_files_returns_dicts(tmp_path: Path):
    (tmp_path / "a.txt").write_text("aaa")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "b.bin").write_bytes(b"bbbbbb")
    out = list_files(tmp_path)
    assert len(out) == 2
    paths = {e["path"] for e in out}
    assert paths == {"a.txt", "sub/b.bin"}
    for entry in out:
        assert "size" in entry and "modified" in entry


def test_list_files_empty(tmp_path: Path):
    assert list_files(tmp_path) == []


def test_prune_empty_parents(tmp_path: Path):
    deep = tmp_path / "a" / "b" / "c.txt"
    deep.parent.mkdir(parents=True)
    deep.write_text("x")
    deep.unlink()
    prune_empty_parents(deep, tmp_path)
    # All empty parent dirs up to (but not including) tmp_path removed.
    assert not (tmp_path / "a").exists()
    assert tmp_path.exists()


def test_ensure_base_creates_dir(tmp_path: Path):
    target = tmp_path / "fresh"
    ensure_base(target)
    assert target.is_dir()
