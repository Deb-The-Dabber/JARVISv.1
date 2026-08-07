import os

import pytest

import file_sandbox as fs


@pytest.fixture(autouse=True)
def _cleanup():
    fs.clear_pending()
    yield
    fs.clear_pending()


def test_enabled_by_default():
    assert fs.enabled()


def test_simulate_create_file(tmp_path):
    sim = fs.simulate("create_file", {"filename": "a.txt", "path": str(tmp_path), "content": "hello"})
    assert sim == (os.path.realpath(tmp_path / "a.txt"), "", "hello")


def test_simulate_write_file_overwrites(tmp_path):
    p = tmp_path / "b.txt"
    p.write_text("old")
    sim = fs.simulate("write_file", {"path": str(p), "content": "new"})
    assert sim == (str(p), "old", "new")


def test_simulate_append_file(tmp_path):
    p = tmp_path / "c.txt"
    p.write_text("base")
    sim = fs.simulate("append_file", {"path": str(p), "content": "+more"})
    assert sim[1] == "base"
    assert sim[2] == "base+more"


def test_simulate_ignores_non_write_tools():
    assert fs.simulate("get_weather", {}) is None


def test_make_diff():
    diff = fs.make_diff("/tmp/x.py", "line1\nline2\n", "line1\nCHANGED\n")
    assert "-line2" in diff
    assert "+CHANGED" in diff


def test_make_diff_noop():
    assert fs.make_diff("/tmp/x.py", "same", "same") == ""


def test_counts():
    diff = fs.make_diff("/tmp/x.py", "a\nb\nc\n", "a\nCHANGED\nc\nNEW\n")
    ins, dels = fs.counts(diff)
    assert ins == 2
    assert dels == 1


def test_stage_and_pending(tmp_path):
    fs.stage("write_file", {"path": "/tmp/x"}, "/tmp/x", "old", "new", "diff")
    pending = fs.get_pending()
    assert pending["tool"] == "write_file"
    assert pending["path"] == "/tmp/x"
    assert pending["diff"] == "diff"
    assert fs.has_pending()
    fs.clear_pending()
    assert not fs.has_pending()
    assert fs.get_pending() is None
