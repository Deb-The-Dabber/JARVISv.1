
filepath = "/Users/debasishbeura/Jarvis/tools/computer_tools.py"
with open(filepath, "r") as f:
    content = f.read()

# Old block to replace
old = """    if "ps aux --sort=-%mem" in command:
        command = "ps axm -o pid,%mem,%cpu,comm | sort -nrk2 | head -20"
        _debug(f"[Rewrite] Linux ps -> macOS compat: {original_command[:60]}...")"""

# New block - robust macOS rewrite
new = """    # Robust macOS rewrite: case-insensitive regex for Linux ps patterns
    ps_rewrites = [
        (r"ps\\s+aux\\s+--sort=-%mem", "ps axm -o pid,%mem,%cpu,comm | sort -nrk2 | head -20"),
        (r"ps\\s+-ef", "ps -ax"),
        (r"ps\\s+aux", "ps ax"),
        (r"ps\\s+--sort", "ps axm | sort -nrk2"),
    ]
    for pattern, replacement in ps_rewrites:
        if re.search(pattern, command, re.IGNORECASE):
            command = re.sub(pattern, replacement, command, flags=re.IGNORECASE)
            _debug(f"[Rewrite] Linux ps -> macOS: {original_command[:60]}...")
            break"""

if old in content:
    content = content.replace(old, new)
    with open(filepath, "w") as f:
        f.write(content)
    print("Fixed macOS ps rewrite in computer_tools.py")
else:
    print("Pattern not found - may already be fixed")
