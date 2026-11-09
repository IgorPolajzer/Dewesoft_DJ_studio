import sys

from src.util import *
from src.ds_remote_util import *


def main(host, cmd_port, data_port):
    dll = load_dll(DLL_PATH)
    check_net_server(host, cmd_port)

    inst = c_void_p()
    rc = dll.dsconCreateInstance(byref(inst), DSX_CONNECTION_TYPE_NET)
    if rc != DSX_NO_ERROR:
        raise RuntimeError("dsconCreateInstance failed, rc=%d" % rc)

    # Connect.
    try:
        conn = ("%s:%s:%s" % (host, cmd_port, data_port)).encode()
        if dll.dsconConnect(inst, conn) != DSX_NO_ERROR:
            raise RuntimeError("dsconConnect(%s) failed" % conn.decode())

    finally:
        if ch.value:
            dll.dsconFreeChannelInstance(ch)
        dll.dsconDisconnect(inst)
        dll.dsconDestroyInstance(inst)

    # Switch to Track overview screen
    pass


if "__main__" == __name__:
    args = sys.argv[1:]
    try:
        exit_code = main(NET_HOST, NET_CMD_PORT, NET_DATA_PORT)
    except KeyboardInterrupt:
        # Ctrl+C before the tap loop started: setup did not finish.
        print("\nInterrupted during setup.", file=sys.stderr)
        exit_code = EXIT_NOT_OK
    except Exception as e:
        print("ERROR: %s" % e, file=sys.stderr)
        exit_code = EXIT_NOT_OK

    sys.exit(exit_code)