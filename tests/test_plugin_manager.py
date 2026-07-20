import os
import shutil
import tempfile

import pytest

from plugin_manager import (
    PLUGIN_DIR,
    TOOL_DEFINITIONS,
    TOOL_REGISTRY,
    _discover,
    _loaded_plugins,
    get_loaded_plugins,
    install_plugin,
    list_available_plugins,
    load_all_plugins,
)


@pytest.fixture(autouse=True)
def isolated_plugins():
    """Use temp dir as plugin dir to avoid contaminating user's real plugins."""
    old_dir = PLUGIN_DIR
    tmp = tempfile.mkdtemp()
    import plugin_manager as pm

    pm.PLUGIN_DIR = tmp
    _loaded_plugins.clear()
    yield tmp
    pm.PLUGIN_DIR = old_dir
    shutil.rmtree(tmp, ignore_errors=True)


def _create_plugin(base, name, manifest_overrides=None, tools=None):
    pdir = os.path.join(base, name)
    os.makedirs(pdir, exist_ok=True)
    manifest = {
        "name": name,
        "version": "1.0",
        "description": f"Test: {name}",
        "type": "tool",
        "entry": "plugin.py",
    }
    if manifest_overrides:
        manifest.update(manifest_overrides)
    with open(os.path.join(pdir, "manifest.yaml"), "w") as f:
        import yaml

        yaml.dump(manifest, f)
    if tools is None:
        tools = [
            {
                "name": f"{name}_tool",
                "description": f"A tool from {name}",
                "parameters": {"type": "object", "properties": {}},
            }
        ]
    # Build plugin.py with actual callable handlers
    lines = ["def register():"]
    lines.append("    def _h():")
    lines.append(f'        return "result from {name}"')
    lines.append("    tools = [")
    for t in tools:
        lines.append("        {")
        lines.append(f'            "name": {repr(t["name"])},')
        lines.append(f'            "description": {repr(t["description"])},')
        lines.append(f'            "parameters": {repr(t["parameters"])},')
        lines.append('            "handler": _h,')
        lines.append("        },")
    lines.append("    ]")
    lines.append("    return {'tools': tools}")
    with open(os.path.join(pdir, "plugin.py"), "w") as f:
        f.write("\n".join(lines) + "\n")


def test_discover_empty():
    assert _discover() == []


def test_discover_single(isolated_plugins):
    _create_plugin(isolated_plugins, "my_plugin")
    discovered = _discover()
    assert len(discovered) == 1
    assert discovered[0]["name"] == "my_plugin"


def test_load_single_plugin(isolated_plugins):
    _create_plugin(isolated_plugins, "my_plugin")
    results = load_all_plugins()
    assert len(results) == 1
    assert results[0]["ok"] is True
    assert results[0]["tools"] == 1
    loaded = get_loaded_plugins()
    assert len(loaded) == 1
    assert loaded[0]["name"] == "my_plugin"


def test_tool_registered(isolated_plugins):
    unique = "unique_tool_test_plugin"
    _create_plugin(isolated_plugins, unique)
    before = len(TOOL_DEFINITIONS)
    load_all_plugins()
    assert len(TOOL_DEFINITIONS) == before + 1
    assert f"{unique}_tool" in TOOL_REGISTRY


def test_multiple_tools(isolated_plugins):
    initial_count = len(TOOL_DEFINITIONS)
    _create_plugin(
        isolated_plugins,
        "p1",
        tools=[
            {"name": "tool_a", "description": "A", "parameters": {}, "handler": lambda: "a"},
            {"name": "tool_b", "description": "B", "parameters": {}, "handler": lambda: "b"},
            {"name": "tool_c", "description": "C", "parameters": {}, "handler": lambda: "c"},
        ],
    )
    load_all_plugins()
    assert len(TOOL_DEFINITIONS) == initial_count + 3


def test_two_plugins(isolated_plugins):
    initial_count = len(TOOL_DEFINITIONS)
    _create_plugin(isolated_plugins, "plugin_a")
    _create_plugin(isolated_plugins, "plugin_b")
    load_all_plugins()
    assert len(TOOL_DEFINITIONS) == initial_count + 2


def test_bad_manifest(isolated_plugins):
    pdir = os.path.join(isolated_plugins, "bad_one")
    os.makedirs(pdir, exist_ok=True)
    with open(os.path.join(pdir, "manifest.yaml"), "w") as f:
        f.write("not: valid: yaml: [")
    results = load_all_plugins()
    assert len(results) == 0  # No results from bad manifest


def test_missing_entry(isolated_plugins):
    pdir = os.path.join(isolated_plugins, "no_entry")
    os.makedirs(pdir, exist_ok=True)
    import yaml

    with open(os.path.join(pdir, "manifest.yaml"), "w") as f:
        yaml.dump({"name": "no_entry", "entry": "missing.py"}, f)
    results = load_all_plugins()
    assert len(results) == 1
    assert results[0]["ok"] is False


def test_no_register_function(isolated_plugins):
    pdir = os.path.join(isolated_plugins, "no_reg")
    os.makedirs(pdir, exist_ok=True)
    import yaml

    with open(os.path.join(pdir, "manifest.yaml"), "w") as f:
        yaml.dump({"name": "no_reg"}, f)
    with open(os.path.join(pdir, "plugin.py"), "w") as f:
        f.write("# no register function\n")
    results = load_all_plugins()
    assert len(results) == 1
    assert results[0]["ok"] is False


def test_list_available(isolated_plugins):
    _create_plugin(isolated_plugins, "visible")
    available = list_available_plugins()
    assert len(available) == 1
    assert available[0]["name"] == "visible"
    assert available[0].get("loaded") is False


def test_list_after_load(isolated_plugins):
    _create_plugin(isolated_plugins, "loaded_one")
    load_all_plugins()
    available = list_available_plugins()
    loaded = [p for p in available if p.get("loaded")]
    assert len(loaded) == 1


def test_install_from_local(isolated_plugins):
    src = tempfile.mkdtemp()
    try:
        _create_plugin(src, "local_plugin")
        src_path = os.path.join(src, "local_plugin")
        result = install_plugin(src_path)
        assert result["ok"] is True
        assert result["name"] == "local_plugin"
        # Verify it can now be loaded
        results = load_all_plugins()
        assert any(r["name"] == "local_plugin" for r in results)
    finally:
        shutil.rmtree(src, ignore_errors=True)


def test_duplicate_install(isolated_plugins):
    _create_plugin(isolated_plugins, "dup")
    src = tempfile.mkdtemp()
    try:
        _create_plugin(src, "dup")
        result = install_plugin(os.path.join(src, "dup"))
        assert result["ok"] is False
        assert "already installed" in result["error"]
    finally:
        shutil.rmtree(src, ignore_errors=True)
