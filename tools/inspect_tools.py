INSPECT_DEFINITIONS = [
    {
        "name": "inspect_capabilities",
        "description": (
            "Return structured list of all available tools, grouped by category. "
            "ALWAYS call this tool FIRST when user asks about capabilities, "
            "'what's missing', setup review, gap analysis, what tools exist, "
            "or what Jarvis can do. DO NOT scan directories or read source code "
            "to figure out capabilities — this tool provides the complete inventory."
        ),
        "parameters": {"type": "object", "properties": {}},
    }
]


def inspect_capabilities() -> str:
    from tools import TOOL_REGISTRY

    by_category = {}
    for name, fn in TOOL_REGISTRY.items():
        module = fn.__module__.replace("tools.", "")
        cat = module.split(".")[0] if "." in module else module
        by_category.setdefault(cat, []).append(name)

    lines = ["JARVIS Capabilities:"]
    for cat, tools in sorted(by_category.items()):
        lines.append(f"\n  {cat.upper()} ({len(tools)}):")
        for t in sorted(tools):
            lines.append(f"    - {t}")
    lines.append(f"\nTotal: {len(TOOL_REGISTRY)} tools")
    return "\n".join(lines)


INSPECT_TOOLS = {"inspect_capabilities": inspect_capabilities}
