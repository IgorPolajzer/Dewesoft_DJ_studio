import os
import socket
from ctypes import *

from src.ds_remote_constants import rc_name
from src.utils.util import PROJECT_ROOT

# File paths.
DLL_NAME = "DSRemoteConnect64.dll"
DLL_PATH = os.path.join(PROJECT_ROOT, DLL_NAME)

# Dewesoft NET connection settings.
NET_HOST = "localhost"
NET_CMD_PORT = "8999"
NET_DATA_PORT = "8001"

# A timestamp step larger than this many sample periods counts as a gap (lost samples).
GAP_FACTOR = 1.5


def load_dll(path):
    dll = WinDLL(path)

    # Type aliases matching examples/Cpp/include/DSRemoteConnect.h and DSXInstance.h
    handle = c_void_p  # DSXInstanceHandle, ChannelInstanceHandle
    handle_out = POINTER(c_void_p)  # ...Handle* (the DLL writes a handle)
    channel_id = c_char_p  # ChannelID      = char*
    channel_id_list_out = POINTER(POINTER(c_char_p))  # ChannelIdList* = char***

    # All 38 exports, in the same order as DSRemoteConnect.h; every function returns int.
    sig = {
        # Version / buffer
        "dsconGetVersion": [c_char_p, c_size_t],
        "dsconSetBufferSize": [handle, c_int],
        # Instance and connection
        "dsconCreateInstance": [handle_out, c_int],
        "dsconConnect": [handle, c_char_p],
        "dsconDestroyInstance": [handle],
        "dsconDisconnect": [handle],
        "dsconGetChannelCount": [handle, POINTER(c_size_t)],
        "dsconChannelGetName": [handle, c_char_p, c_size_t],
        "dsconChannelGetNameUtf8": [handle, c_char_p, c_size_t, POINTER(c_size_t)],
        "dsconSetAppWindowVisible": [handle, c_bool],
        "dsconChannelSetTransferred": [handle, c_bool],
        # Setup, acquisition and storing
        "dsconLoadSetup": [handle, c_char_p],
        "dsconIsInAqusition": [handle, POINTER(c_bool)],
        "dsconGetState": [handle, POINTER(c_int)],
        "dsconStartMeasurement": [handle],
        "dsconStartStoring": [handle, c_char_p],
        "dsconStopStoring": [handle],
        "dsconStopStoringEx": [handle, POINTER(c_int)],
        "dsconStopMeasurement": [handle],
        # Reading data
        "dsconBeginRead": [handle, POINTER(c_double), POINTER(c_double)],
        "dsconChannelReadScalarData": [handle, POINTER(POINTER(c_double)), POINTER(POINTER(c_double)),
                                       POINTER(c_size_t)],
        "dsconChannelReadScalarData_2": [handle, POINTER(c_double), POINTER(c_double), POINTER(c_size_t)],
        "dsconChannelReadScalarData_2abs": [handle, POINTER(c_double), POINTER(c_double), POINTER(c_size_t)],
        "dsconEndRead": [handle],
        "dsconControlChannelWriteData": [handle, c_double],
        # Channel properties
        "dsconGetSampleRate": [handle, POINTER(c_double)],
        "dsconGetChannelType": [handle, POINTER(c_int)],
        "dsconIsChannelControl": [handle, POINTER(c_bool)],
        "dsconGetChUnit": [handle, c_char_p, c_size_t],
        # Channel enumeration and instances
        "dsconEnumerateChannels": [handle, channel_id_list_out, POINTER(c_size_t)],
        "dsconFreeEnumerateChannels": [handle, channel_id_list_out],
        "dsconCreateChannelInstance": [handle, channel_id, handle_out],
        "dsconCreateChannelInstanceByName": [handle, c_char_p, handle_out],
        "dsconCreateChannelInstanceByNameUtf8": [handle, c_char_p, handle_out],
        "dsconFreeChannelInstance": [handle],
        "dsconInitChannelIdEnum": [handle],
        "dsconGetNextChannelId": [handle, channel_id],
        "dsconGetNextChannelIdSize": [handle, POINTER(c_int)],
    }
    for name, argtypes in sig.items():
        fn = getattr(dll, name)
        fn.argtypes, fn.restype = argtypes, c_int
    return dll


def check_net_server(host, port, timeout=2.0):
    # dsconConnect returns 0 even when nothing is listening, so check the command port ourselves.
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            pass
    except OSError as e:
        raise RuntimeError("Cannot reach the Dewesoft NET server at %s:%s (%s).\n" % (host, port, e))


class DSRemoteError(RuntimeError):
    def __init__(self, fn, rc, detail=""):
        self.fn = fn
        self.rc = rc
        msg = "%s failed: %s (%d)" % (fn, rc_name(rc), rc)
        super().__init__(msg + (" - " + detail if detail else ""))


def check(rc, fn):
    if rc < 0:
        raise DSRemoteError(fn, rc)
    return rc
