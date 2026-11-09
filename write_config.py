import json
import os
import sys

import numpy as np
import soundfile as sf

from src.util import CONFIG_PATH, EXIT_NOT_OK, EXIT_OK, MODES, PROJECT_ROOT

SONG_DIR = os.path.join(PROJECT_ROOT, "song_files")
SONG_FILES = (os.path.join(SONG_DIR, "first_song.txt"), os.path.join(SONG_DIR, "second_song.txt"))

# Fixed DewesoftX channel names.
MASTER_CHANNEL = "Master"
SLIDER_CHANNEL = "Slider"

USAGE = "Usage: write_config.py <mode> [first_song_path] [second_song_path]"


def save_state(path, state):
    # Create the folder if needed; the file itself is created by open() + os.replace().
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

    os.replace(tmp, path)


def save_song_samples(src, dst):
    # Write the song as mono ASCII samples (one value per line) at its own sample rate.
    samples, rate = sf.read(src, dtype="float32", always_2d=True)
    mono = samples.mean(axis=1) # Stereo to mono.

    # Write to a temp file first so the C++ Script never reads a half-written file.
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    tmp = dst + ".tmp"
    np.savetxt(tmp, mono, fmt="%.7g")
    os.replace(tmp, dst)
    return rate


def clean(arg):
    return arg.strip().strip('"')


def main(args):
    if not 1 <= len(args) <= 3:
        print(USAGE, file=sys.stderr)
        return EXIT_NOT_OK

    # Mode is mandatory.
    mode = clean(args[0])
    if mode not in MODES:
        print("Application mode must be one of: %s" % ", ".join(MODES), file=sys.stderr)
        return EXIT_NOT_OK

    # Store optional song paths.
    songs = []
    for arg in args[1:]:
        path = clean(arg)
        if not path:
            songs.append(None)
            continue

        path = os.path.abspath(path)
        if not os.path.isfile(path):
            print("File not found: %s" % path, file=sys.stderr)
            return EXIT_NOT_OK

        songs.append(path)

    songs += [None] * (2 - len(songs)) # Fill songs with None if they werent provided.
    first, second = songs

    rates = [None, None]
    if mode == "music_mix":
        # Convert songs to csv files.
        if first is None or second is None:
            print("music_mix needs both songs.\n" + USAGE, file=sys.stderr)
            return EXIT_NOT_OK

        for i, (src, dst) in enumerate(zip((first, second), SONG_FILES)):
            try:
                rates[i] = save_song_samples(src, dst)
            except (OSError, RuntimeError) as e:
                print("Could not convert %s: %s" % (src, e), file=sys.stderr)
                return EXIT_NOT_OK

            print("Saved %s (%d Hz, mono)" % (dst, rates[i]))

    state = {
        "mode": mode,
        "master_channel": MASTER_CHANNEL,
        "slider_channel": SLIDER_CHANNEL,
        "first_song": {"path": first, "sample_rate": rates[0]},
        "second_song": {"path": second, "sample_rate": rates[1]},
    }

    try:
        save_state(CONFIG_PATH, state)
    except OSError as e:
        print("Could not write %s: %s" % (CONFIG_PATH, e), file=sys.stderr)
        return EXIT_NOT_OK

    print("Saved state to %s" % CONFIG_PATH)
    return EXIT_OK


if "__main__" == __name__:
    sys.exit(main(sys.argv[1:]))
