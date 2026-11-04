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


def main(args):
    if len(args) != 2:
        print("Usage: write_song_state.py <first_song_path> <second_song_path>", file=sys.stderr)
        return EXIT_NOT_OK

    # Split the arguments.
    first, second = (os.path.abspath(p.strip().strip('"')) for p in args)

    # Check if files exist.
    first_ok, second_ok = os.path.isfile(first), os.path.isfile(second)

    if not first_ok or not second_ok:
        return EXIT_NOT_OK

    state = {"first_song": first, "second_song": second}
    try:
        save_state(STATE_FILE, state)
    except OSError as e:
        print("Could not write %s: %s" % (STATE_FILE, e), file=sys.stderr)
        return EXIT_NOT_OK

    print("Saved songs to %s" % STATE_FILE)
    return EXIT_OK


if "__main__" == __name__:
    sys.exit(main(sys.argv[1:]))
