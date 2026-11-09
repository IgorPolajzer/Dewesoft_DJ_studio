from ctypes import byref, c_size_t, c_void_p

from src.ds_remote_constants import DSX_CONNECTION_TYPE_NET, DSX_NO_ERROR
from src.dsremote import DLL_PATH, check_net_server, list_channels, load_dll

# Process exit codes for the caller.
EXIT_OK = 0
EXIT_NOT_OK = 1


class DJStudioApp:
    def __init__(self, host, cmd_port, data_port):
        self.host = host
        self.cmd_port = cmd_port
        self.data_port = data_port

    def run(self):
        dll = load_dll(DLL_PATH)
        check_net_server(self.host, self.cmd_port)

        # Create a new DSX instance.
        inst = c_void_p()
        rc = dll.dsconCreateInstance(byref(inst), DSX_CONNECTION_TYPE_NET)
        if rc != DSX_NO_ERROR:
            raise RuntimeError("dsconCreateInstance failed, rc=%d" % rc)

        channels = []
        try:
            # Connect.
            connection_string = ("%s:%s:%s" % (self.host, self.cmd_port, self.data_port)).encode()
            if dll.dsconConnect(inst, connection_string) != DSX_NO_ERROR:
                raise RuntimeError("dsconConnect(%s) failed" % connection_string.decode())

            count = c_size_t()
            rc = dll.dsconGetChannelCount(inst, byref(count))
            if rc != DSX_NO_ERROR or count.value == 0:
                raise RuntimeError("No channels available (rc=%d, count=%d)" % (rc, count.value))

            channels = list_channels(dll, inst)

            # Switch to Track overview screen
            pass

        finally:
            # Clean up.
            for _, _, ch in channels:
                dll.dsconFreeChannelInstance(ch)

            dll.dsconDisconnect(inst)
            dll.dsconDestroyInstance(inst)

        return EXIT_OK
