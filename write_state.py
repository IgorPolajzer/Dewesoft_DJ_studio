import json
import os
import sys

from src.app import EXIT_NOT_OK, EXIT_OK

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
MODES = ("music_mix", "natural_sounds")


def save_state(path, state):
    # Create the folder if needed; the file itself is created by open() + os.replace().
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"

    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

    os.replace(tmp, path)


def clean(arg):
    return arg.strip().strip('"')


def main(args):
    if not 1 <= len(args) <= 3:
        print("Usage: write_state.py <mode> [first_song_path] [second_song_path]", file=sys.stderr)
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

    state = {"mode": mode, "first_song": first, "second_song": second}
    try:
        save_state(STATE_FILE, state)
    except OSError as e:
        print("Could not write %s: %s" % (STATE_FILE, e), file=sys.stderr)
        return EXIT_NOT_OK

    print("Saved state to %s" % STATE_FILE)
    return EXIT_OK


if "__main__" == __name__:
    sys.exit(main(sys.argv[1:]))
