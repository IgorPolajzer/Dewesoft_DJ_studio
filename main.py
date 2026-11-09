import sys

from src.app import EXIT_NOT_OK, DJStudioApp
from src.dsremote_util import NET_CMD_PORT, NET_DATA_PORT, NET_HOST


if "__main__" == __name__:
    try:
        exit_code = DJStudioApp(NET_HOST, NET_CMD_PORT, NET_DATA_PORT).run()
    except KeyboardInterrupt:
        print("\nInterrupted during setup.", file=sys.stderr)
        exit_code = EXIT_NOT_OK
    except Exception as e:
        print("ERROR: %s" % e, file=sys.stderr)
        exit_code = EXIT_NOT_OK

    sys.exit(exit_code)
