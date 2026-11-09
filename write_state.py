import json
import os
import sys

EXIT_OK = 0
EXIT_NOT_OK = 1
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "program_state.json")


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
    if not mode:
        print("Application mode must be provided.", file=sys.stderr)
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
