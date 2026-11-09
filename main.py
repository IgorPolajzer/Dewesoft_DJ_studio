import sys

from src.util import *


def main():
    dll = load(DLL_PATH)
    check_net_server(host, cmd_port)

    # Switch to Track overview screen
    pass


if "__main__" == __name__:
    args = sys.argv[1:]
    try:
        exit_code = main()
    except KeyboardInterrupt:
        # Ctrl+C before the tap loop started: setup did not finish.
        print("\nInterrupted during setup.", file=sys.stderr)
        exit_code = EXIT_NOT_OK
    except Exception as e:
        print("ERROR: %s" % e, file=sys.stderr)
        exit_code = EXIT_NOT_OK

    sys.exit(exit_code)