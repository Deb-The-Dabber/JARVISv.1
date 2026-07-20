import subprocess


def _applescript(script):
    result = subprocess.run(["osascript", "-e", script],
                            capture_output=True, text=True)
    return result.stdout.strip(), result.stderr.strip()

def spotify_play():
    _applescript('tell application "Spotify" to play')
    return "Playing."

def spotify_pause():
    _applescript('tell application "Spotify" to pause')
    return "Paused."

def spotify_next():
    _applescript('tell application "Spotify" to next track')
    return "Skipped."

def spotify_previous():
    _applescript('tell application "Spotify" to previous track')
    return "Going back."

def spotify_volume_up():
    _applescript('tell application "Spotify" to set sound volume to (sound volume + 10)')
    return "Volume up."

def spotify_volume_down():
    _applescript('tell application "Spotify" to set sound volume to (sound volume - 10)')
    return "Volume down."

def spotify_current():
    script = '''tell application "Spotify"
        set t to name of current track
        set a to artist of current track
        return t & " by " & a
    end tell'''
    out, _ = _applescript(script)
    return f"Now playing: {out}" if out else "Nothing playing."

def spotify_play_song(song: str):
    url = f"spotify:search:{song.replace(' ','%20')}"
    subprocess.run(["open", url])
    import time; time.sleep(2)
    _applescript('tell application "Spotify" to play')
    return f"Playing '{song}' on Spotify."

SPOTIFY_TOOLS = {
    "spotify_play": spotify_play,
    "spotify_pause": spotify_pause,
    "spotify_next": spotify_next,
    "spotify_previous": spotify_previous,
    "spotify_volume_up": spotify_volume_up,
    "spotify_volume_down": spotify_volume_down,
    "spotify_current": spotify_current,
    "spotify_play_song": spotify_play_song,
}

SPOTIFY_DEFINITIONS = [
    {"type":"function","function":{"name":"spotify_play","description":"Resume Spotify playback","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"spotify_pause","description":"Pause Spotify","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"spotify_next","description":"Skip to next track","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"spotify_previous","description":"Go to previous track","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"spotify_volume_up","description":"Turn Spotify volume up","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"spotify_volume_down","description":"Turn Spotify volume down","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"spotify_current","description":"Get currently playing Spotify track","parameters":{"type":"object","properties":{},"required":[]}}},
    {"type":"function","function":{"name":"spotify_play_song","description":"Play a specific song on Spotify","parameters":{"type":"object","properties":{"song":{"type":"string"}},"required":["song"]}}},
]
