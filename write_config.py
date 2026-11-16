import sys
from time import sleep

from src.config import Config
from src.utils import EXIT_NOT_OK, EXIT_OK

USAGE = "Usage: write_config.py <mode> [first_song_path] [second_song_path]"


def clean(arg):
    return arg.strip().strip('"')


def main(args):
    if not 1 <= len(args) <= 3:
        print(USAGE, file=sys.stderr)
        return EXIT_NOT_OK

    # Mode is mandatory; songs are optional and an empty string means "no song".
    mode = clean(args[0])
    songs = [clean(arg) or None for arg in args[1:]]
    songs += [None] * (2 - len(songs))

    config = Config()
    try:
        config.update(mode, songs[0], songs[1])
        config.write()
    except RuntimeError as e:
        print("%s\n%s" % (e, USAGE), file=sys.stderr)
        return EXIT_NOT_OK

    print("Saved config to %s" % config.path)
    return EXIT_OK


if "__main__" == __name__:
    val = main(sys.argv[1:])
    sleep(10)
    sys.exit(val)
