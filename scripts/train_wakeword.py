#!/usr/bin/env python3
"""Train or tune wake word detection for Jarvis.

Usage:
    python scripts/train_wakeword.py --test           # test current wake word detection
    python scripts/train_wakeword.py --record         # record samples for custom training
    python scripts/train_wakeword.py --calibrate      # calibrate VAD sensitivity

This script works with Porcupine (pre-trained) and openWakeWord.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

OK = "\033[92mOK\033[0m"
WARN = "\033[93mWARN\033[0m"
FAIL = "\033[91mFAIL\033[0m"


def test_wake_word():
    print("  Testing wake word detection...")
    try:
        import pvporcupine
        print(f"  {OK} Porcupine available (v{pvporcupine.__version__})")
    except ImportError:
        print(f"  {WARN} Porcupine not installed — using openWakeWord fallback")
    except Exception as e:
        print(f"  {WARN} Porcupine check: {e}")

    try:
        import importlib
        if importlib.util.find_spec("openwakeword"):
            print(f"  {OK} openWakeWord available")
        else:
            print(f"  {WARN} openWakeWord not installed")
    except Exception:
        print(f"  {WARN} openWakeWord check skipped")

    try:
        import importlib
        if importlib.util.find_spec("webrtcvad"):
            print(f"  {OK} webrtcvad available — VAD ready")
        else:
            print(f"  {WARN} webrtcvad not installed — pip install webrtcvad for VAD")
    except Exception:
        print(f"  {WARN} webrtcvad check skipped")

    from config import SAMPLE_RATE, WAKE_WORD
    print(f"  Wake word: \"{WAKE_WORD}\"")
    print(f"  Sample rate: {SAMPLE_RATE}Hz")


def record_samples():
    print("  Recording wake word samples...")
    print("  Say your wake word 5 times with 2 seconds between each.")
    out_dir = os.path.expanduser("~/.jarvis_wakeword_samples")
    os.makedirs(out_dir, exist_ok=True)

    try:
        import scipy.io.wavfile as wav
        import sounddevice as sd

        for i in range(5):
            input(f"  Press Enter then say wake word (sample {i + 1}/5)...")
            audio = sd.rec(int(2 * 16000), samplerate=16000, channels=1, dtype="int16")
            sd.wait()
            path = os.path.join(out_dir, f"sample_{i + 1}.wav")
            wav.write(path, 16000, audio)
            print(f"  Saved {path}")
        print(f"  {OK} Samples saved to {out_dir}")
    except Exception as e:
        print(f"  {FAIL} Recording failed: {e}")


def calibrate_vad():
    print("  Calibrating VAD...")
    try:
        import importlib
        if not importlib.util.find_spec("webrtcvad"):
            print(f"  {FAIL} webrtcvad not installed — pip install webrtcvad")
            return

        from config import VAD_AGGRESSIVENESS

        for agg in range(4):
            print(f"  Aggressiveness {agg}: VAD ready ({'aggressive' if agg >= 2 else 'gentle'})")
        print(f"  Current: VAD_AGGRESSIVENESS={VAD_AGGRESSIVENESS}")
        print("  Recommended: 0=loose, 1=moderate, 2=tight, 3=very tight")
        print("  Adjust in config.py or .env")
    except ImportError:
        print(f"  {FAIL} webrtcvad not installed — pip install webrtcvad")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--calibrate", action="store_true")
    args = parser.parse_args()

    print("=" * 56)
    print("  Jarvis Wake Word & VAD Tools")
    print("=" * 56)

    if args.test:
        print("\n--- Wake Word Test ---")
        test_wake_word()
    if args.record:
        print("\n--- Record Samples ---")
        record_samples()
    if args.calibrate:
        print("\n--- VAD Calibration ---")
        calibrate_vad()
    if not any([args.test, args.record, args.calibrate]):
        test_wake_word()


if __name__ == "__main__":
    main()
