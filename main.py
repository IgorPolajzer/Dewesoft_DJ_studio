import sys
from time import sleep

from src.app import DJStudioApp
from src.config import Config
from src.utils.dsremote_util import NET_CMD_PORT, NET_DATA_PORT, NET_HOST
from src.utils.util import EXIT_NOT_OK


if "__main__" == __name__:
    try:
        config = Config()
        config.read()
        exit_code = DJStudioApp(config, NET_HOST, NET_CMD_PORT, NET_DATA_PORT).run()
    except KeyboardInterrupt:
        print("\nInterrupted during setup.", file=sys.stderr)
        exit_code = EXIT_NOT_OK
    except Exception as e:
        print("ERROR: %s" % e, file=sys.stderr)
        exit_code = EXIT_NOT_OK


    # sleep(10)
    sys.exit(exit_code)
