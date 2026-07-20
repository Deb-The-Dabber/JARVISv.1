import importlib.util
import os
import shutil
import subprocess
import tempfile
import threading

import yaml

from tools import TOOL_DEFINITIONS, TOOL_REGISTRY

PLUGIN_DIR = os.path.expanduser("~/.jarvis/plugins")
PLUGIN_LOCK = threading.Lock()

_loaded_plugins = {}
_plugin_providers = []


def _ensure_dir():
    os.makedirs(PLUGIN_DIR, exist_ok=True)


def _discover() -> list[dict]:
    _ensure_dir()
    plugins = []
    if not os.path.isdir(PLUGIN_DIR):
        return plugins
    for name in sorted(os.listdir(PLUGIN_DIR)):
        plugin_path = os.path.join(PLUGIN_DIR, name)
        manifest_path = os.path.join(plugin_path, "manifest.yaml")
        if not os.path.isdir(plugin_path) or not os.path.isfile(manifest_path):
            continue
        try:
            with open(manifest_path) as f:
                manifest = yaml.safe_load(f) or {}
            manifest.setdefault("name", name)
            manifest.setdefault("version", "0.1")
            manifest.setdefault("description", "")
            manifest.setdefault("type", "tool")
            manifest.setdefault("entry", "plugin.py")
            manifest["_path"] = plugin_path
            plugins.append(manifest)
        except Exception as e:
            print(f"  [Plugin] Failed to load manifest for {name}: {e}")
    return plugins


def _load_plugin_module(manifest: dict):
    name = manifest["name"]
    entry = manifest["entry"]
    plugin_path = manifest["_path"]
    mod_path = os.path.join(plugin_path, entry)
    if not os.path.isfile(mod_path):
        raise FileNotFoundError(f"Entry module not found: {mod_path}")
    spec = importlib.util.spec_from_file_location(f"jarvis_plugin_{name}", mod_path)
    if not spec or not spec.loader:
        raise ImportError(f"Could not load spec for {mod_path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "register"):
        raise AttributeError(f"Plugin {name} has no register() function")
    return mod.register()


def _merge_tool_plugin(name: str, tools: list[dict]):
    for t in tools:
        fn_name = t.get("name", "")
        handler = t.get("handler")
        description = t.get("description", "")
        parameters = t.get("parameters", {"type": "object", "properties": {}})
        if not fn_name or not handler:
            print(f"  [Plugin] Skipping tool entry in {name}: missing name or handler")
            continue
        with PLUGIN_LOCK:
            if fn_name in TOOL_REGISTRY:
                print(f"  [Plugin] Tool '{fn_name}' already registered — skipping")
                continue
            TOOL_REGISTRY[fn_name] = handler
            TOOL_DEFINITIONS.append(
                {
                    "type": "function",
                    "function": {
                        "name": fn_name,
                        "description": description,
                        "parameters": parameters,
                    },
                }
            )
            print(f"  [Plugin] Registered tool: {fn_name}")


def _merge_provider_plugin(name: str, providers: list[dict]):
    for p in providers:
        p_name = p.get("name", "")
        handler = p.get("handler")
        priority = p.get("priority", 6)
        if not p_name or not handler:
            print(f"  [Plugin] Skipping provider entry in {name}: missing name or handler")
            continue
        with PLUGIN_LOCK:
            _plugin_providers.append(
                {
                    "name": p_name,
                    "handler": handler,
                    "priority": priority,
                    "plugin": name,
                }
            )
            _plugin_providers.sort(key=lambda x: x["priority"], reverse=True)
            print(f"  [Plugin] Registered provider: {p_name} (priority {priority})")


def load_plugin(name: str) -> dict:
    _ensure_dir()
    plugin_path = os.path.join(PLUGIN_DIR, name)
    manifest_path = os.path.join(plugin_path, "manifest.yaml")
    if not os.path.isfile(manifest_path):
        return {"ok": False, "error": f"No manifest.yaml in {plugin_path}"}
    try:
        with open(manifest_path) as f:
            manifest = yaml.safe_load(f) or {}
        manifest.setdefault("name", name)
        manifest.setdefault("entry", "plugin.py")
        manifest["_path"] = plugin_path
        registrations = _load_plugin_module(manifest)
    except Exception as e:
        return {"ok": False, "error": str(e)}
    if not isinstance(registrations, dict):
        return {"ok": False, "error": "register() must return a dict"}
    tools = registrations.get("tools", [])
    providers = registrations.get("providers", [])
    if tools:
        _merge_tool_plugin(name, tools)
    if providers:
        _merge_provider_plugin(name, providers)
    _loaded_plugins[name] = manifest
    return {"ok": True, "tools": len(tools), "providers": len(providers)}


def load_all_plugins() -> list[dict]:
    results = []
    for manifest in _discover():
        name = manifest["name"]
        if manifest.get("disabled"):
            continue
        result = load_plugin(name)
        if not result["ok"]:
            print(f"  [Plugin] Failed to load '{name}': {result['error']}")
        results.append({"name": name, **result})
    return results


def reload_plugins():
    _ensure_dir()
    with PLUGIN_LOCK:
        # Remove plugin tools from registries
        # (We can't easily remove individual items w/o tracking, so re-init)
        pass
    # For now: load all (non-destructive, skips already-registered names)
    return load_all_plugins()


def get_loaded_plugins() -> list[dict]:
    return [
        {
            "name": name,
            "version": m.get("version", ""),
            "description": m.get("description", ""),
            "type": m.get("type", ""),
        }
        for name, m in _loaded_plugins.items()
    ]


def get_plugin_providers() -> list[dict]:
    with PLUGIN_LOCK:
        return list(_plugin_providers)


def install_plugin(source: str) -> dict:
    _ensure_dir()
    if source.startswith("http"):
        return _install_from_url(source)
    if source.startswith("git@") or source.endswith(".git"):
        return _install_from_git(source)
    if os.path.isdir(source):
        return _install_from_local(source)
    return {"ok": False, "error": f"Unknown source type: {source}"}


def _install_from_git(url: str) -> dict:
    name = url.rstrip(".git").rsplit("/", 1)[-1]
    dest = os.path.join(PLUGIN_DIR, name)
    if os.path.exists(dest):
        return {"ok": False, "error": f"Plugin '{name}' already installed"}
    try:
        subprocess.run(["git", "clone", url, dest], capture_output=True, text=True, check=True, timeout=60)
        return {"ok": True, "name": name, "action": "cloned"}
    except subprocess.CalledProcessError as e:
        return {"ok": False, "error": f"git clone failed: {e.stderr[:200]}"}
    except FileNotFoundError:
        return {"ok": False, "error": "git not found on system"}


def _install_from_url(url: str) -> dict:
    import requests

    name = url.rstrip("/").rsplit("/", 1)[-1].replace(".tar.gz", "").replace(".zip", "")
    dest = os.path.join(PLUGIN_DIR, name)
    if os.path.exists(dest):
        return {"ok": False, "error": f"Plugin '{name}' already installed"}
    try:
        resp = requests.get(url, stream=True, timeout=30)
        resp.raise_for_status()
        with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as f:
            f.write(resp.content)
            tmp = f.name
        shutil.unpack_archive(tmp, dest)
        os.remove(tmp)
        return {"ok": True, "name": name, "action": "downloaded"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _install_from_local(path: str) -> dict:
    name = os.path.basename(os.path.normpath(path))
    dest = os.path.join(PLUGIN_DIR, name)
    if os.path.exists(dest):
        return {"ok": False, "error": f"Plugin '{name}' already installed at {dest}"}
    shutil.copytree(path, dest)
    return {"ok": True, "name": name, "action": "copied"}


def list_available_plugins() -> list[dict]:
    _ensure_dir()
    results = []
    for name in sorted(os.listdir(PLUGIN_DIR)):
        plugin_path = os.path.join(PLUGIN_DIR, name)
        manifest_path = os.path.join(plugin_path, "manifest.yaml")
        if not os.path.isdir(plugin_path):
            continue
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path) as f:
                    m = yaml.safe_load(f) or {}
                results.append(
                    {
                        "name": name,
                        "version": m.get("version", "?"),
                        "description": m.get("description", ""),
                        "type": m.get("type", "unknown"),
                        "loaded": name in _loaded_plugins,
                    }
                )
            except Exception:
                results.append({"name": name, "error": "bad manifest"})
        else:
            results.append({"name": name, "error": "no manifest.yaml"})
    return results


def print_plugin_status():
    plugins = list_available_plugins()
    if not plugins:
        print("  No plugins found in ~/.jarvis/plugins/")
        return
    print(f"  Plugins ({len(plugins)}):")
    for p in plugins:
        status = "loaded" if p.get("loaded") else "available"
        tag = "OK" if p.get("loaded") else "  -"
        extra = p.get("type", "")
        desc = p.get("description", "")
        line = f"    [{tag}] {p['name']}  ({extra}, {status})"
        if desc:
            line += f" — {desc}"
        print(line)
