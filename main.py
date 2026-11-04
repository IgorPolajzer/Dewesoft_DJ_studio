"""Stream live samples of channel "AI 1" from DewesoftX over Dewesoft NET.

Usage:
    python main.py [host] [cmd_port] [data_port] [channel_name]

Defaults: localhost 8999 8001 "AI 1"

Connection string is <dewesoft_ip>:<net_command_port>:<data_port>.
The data port is a port on THIS machine: the DLL listens on it and DewesoftX
connects back to it.

Based on DSRemoteNET_MinimalExample.py from DSRemoteConnect 1.1.3.26
(requires 64-bit Python and DSRemoteConnect64.dll).
"""
import ctypes
import os
import socket
import sys
import time
from ctypes import POINTER, byref, c_char_p, c_double, c_int, c_size_t, c_void_p

DLL_NAME = "DSRemoteConnect64.dll"
# Look for the DLL next to this script first, then in the DSRemoteConnect examples folder.
DLL_SEARCH_PATHS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), DLL_NAME),
    os.path.join(r"C:\Users\igor.polajzer\Desktop\Dewesoft\ds_downloads\DSRemoteConnect-1.1.3.26"
                 r"\DSRemoteConnect-1.1.3.26\examples\Python", DLL_NAME),
]

DEFAULT_HOST = "localhost"
DEFAULT_CMD_PORT = "8999"
DEFAULT_DATA_PORT = "8001"
DEFAULT_CHANNEL = "AI 1"

DSX_END_OF_ENUM = 1
DSX_NO_ERROR = 0
DSX_NET_BUFFER_OVERWRITTEN = -21
DSX_CONNECTION_TYPE_NET = 1

POLL_HZ = 20.0          # how often the read loop runs
BUFFER_SECONDS = 2.0    # ring buffer depth, in seconds of signal


def find_dll():
    for path in DLL_SEARCH_PATHS:
        if os.path.isfile(path):
            return path
    raise FileNotFoundError(
        "%s not found. Copy it next to main.py. Searched:\n  %s"
        % (DLL_NAME, "\n  ".join(DLL_SEARCH_PATHS)))


def load(path):
    dll = ctypes.WinDLL(path)
    sig = {
        "dsconGetVersion":                      ([c_char_p, c_size_t], c_int),
        "dsconCreateInstance":                  ([POINTER(c_void_p), c_int], c_int),
        "dsconConnect":                         ([c_void_p, c_char_p], c_int),
        "dsconDisconnect":                      ([c_void_p], c_int),
        "dsconDestroyInstance":                 ([c_void_p], c_int),
        "dsconGetChannelCount":                 ([c_void_p, POINTER(c_size_t)], c_int),
        "dsconCreateChannelInstanceByNameUtf8": ([c_void_p, c_char_p, POINTER(c_void_p)], c_int),
        "dsconCreateChannelInstance":           ([c_void_p, c_char_p, POINTER(c_void_p)], c_int),
        "dsconInitChannelIdEnum":               ([c_void_p], c_int),
        "dsconGetNextChannelIdSize":            ([c_void_p, POINTER(c_int)], c_int),
        "dsconGetNextChannelId":                ([c_void_p, c_char_p], c_int),
        "dsconChannelGetNameUtf8":              ([c_void_p, c_char_p, c_size_t, POINTER(c_size_t)], c_int),
        "dsconChannelSetTransferred":           ([c_void_p, ctypes.c_bool], c_int),
        "dsconFreeChannelInstance":             ([c_void_p], c_int),
        "dsconGetChUnit":                       ([c_void_p, c_char_p, c_size_t], c_int),
        "dsconGetSampleRate":                   ([c_void_p, POINTER(c_double)], c_int),
        "dsconSetBufferSize":                   ([c_void_p, c_int], c_int),
        "dsconStartMeasurement":                ([c_void_p], c_int),
        "dsconStopMeasurement":                 ([c_void_p], c_int),
        "dsconChannelReadScalarData_2":         ([c_void_p, POINTER(c_double), POINTER(c_double), POINTER(c_size_t)], c_int),
    }
    for name, (argtypes, restype) in sig.items():
        fn = getattr(dll, name)
        fn.argtypes, fn.restype = argtypes, restype
    return dll


def check_net_server(host, port, timeout=2.0):
    """dsconConnect returns 0 even when nothing is listening, so check the
    Dewesoft NET command port ourselves to get a clear error message."""
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            pass
    except OSError as e:
        raise RuntimeError(
            "Cannot reach the Dewesoft NET server at %s:%s (%s).\n"
            "Enable Dewesoft NET / remote control in DewesoftX "
            "(Options -> Settings) with command port %s, then try again."
            % (host, port, e, port))


def channel_name(dll, ch):
    buf = ctypes.create_string_buffer(256)
    required = c_size_t()
    dll.dsconChannelGetNameUtf8(ch, buf, len(buf), byref(required))
    return buf.value.decode("utf-8", errors="replace")


def list_channels(dll, inst):
    """Enumerate every channel of the open setup.
    Returns a list of (channel_id, name, channel_instance_handle)."""
    channels = []
    rc = dll.dsconInitChannelIdEnum(inst)
    if rc != DSX_NO_ERROR:
        raise RuntimeError("dsconInitChannelIdEnum failed, rc=%d" % rc)
    while True:
        size = c_int(0)
        rc = dll.dsconGetNextChannelIdSize(inst, byref(size))
        if rc < 0 or size.value <= 0:
            break
        id_buf = ctypes.create_string_buffer(size.value + 1)
        rc = dll.dsconGetNextChannelId(inst, id_buf)
        if rc < 0:
            break
        # The last channel is returned together with DSX_END_OF_ENUM.
        ch = c_void_p()
        if dll.dsconCreateChannelInstance(inst, id_buf, byref(ch)) == DSX_NO_ERROR:
            channels.append((id_buf.value.decode(), channel_name(dll, ch), ch))
        if rc == DSX_END_OF_ENUM:
            break
    return channels


def main(host, cmd_port, data_port, wanted_name):
    dll = load(find_dll())

    ver = ctypes.create_string_buffer(64)
    dll.dsconGetVersion(ver, len(ver))
    print("DSRemote version:", ver.value.decode())

    check_net_server(host, cmd_port)

    inst = c_void_p()
    rc = dll.dsconCreateInstance(byref(inst), DSX_CONNECTION_TYPE_NET)
    if rc != DSX_NO_ERROR:
        raise RuntimeError("dsconCreateInstance failed, rc=%d" % rc)

    ch = c_void_p()
    try:
        conn = ("%s:%s:%s" % (host, cmd_port, data_port)).encode()
        rc = dll.dsconConnect(inst, conn)
        if rc != DSX_NO_ERROR:
            raise RuntimeError("dsconConnect(%s) failed, rc=%d" % (conn.decode(), rc))
        print("Connected to", conn.decode())

        # Parses the channel list of the open setup. Must be called BEFORE
        # creating channel instances, and not again afterwards.
        count = c_size_t()
        rc = dll.dsconGetChannelCount(inst, byref(count))
        if rc != DSX_NO_ERROR:
            raise RuntimeError("dsconGetChannelCount failed, rc=%d "
                               "(-4 = not connected to DewesoftX)" % rc)
        print("Channels in setup:", count.value)
        if count.value == 0:
            raise RuntimeError("The open DewesoftX setup has no channels. "
                               "Load a setup with at least one used channel.")

        channels = list_channels(dll, inst)
        print("\nAvailable channels:")
        for i, (cid, name, _) in enumerate(channels):
            print("  [%d] %-30s id=%s" % (i, name, cid))
        if not channels:
            raise RuntimeError("Channel enumeration returned no channels.")

        # Pick the requested channel, or fall back to the first one.
        selected = next((c for c in channels if c[1] == wanted_name), None)
        if selected is None:
            selected = channels[0]
            print("\nChannel %r not found - using first channel %r."
                  % (wanted_name, selected[1]))
        ch = selected[2]
        name = selected[1]

        # Creating an instance marks a channel as transferred; only transfer
        # the selected one.
        for cid, n, handle in channels:
            if handle is not ch:
                dll.dsconChannelSetTransferred(handle, False)
                dll.dsconFreeChannelInstance(handle)

        rate = c_double()
        dll.dsconGetSampleRate(ch, byref(rate))
        unit_buf = ctypes.create_string_buffer(64)
        dll.dsconGetChUnit(ch, unit_buf, len(unit_buf))
        unit = unit_buf.value.decode(errors="replace")
        print("\n%s: %g Hz, unit '%s'" % (name, rate.value, unit))

        # Ring buffer must be set BEFORE starting the measurement.
        capacity = max(3000, int(rate.value * BUFFER_SECONDS))
        dll.dsconSetBufferSize(inst, capacity)

        rc = dll.dsconStartMeasurement(inst)
        if rc != DSX_NO_ERROR:
            raise RuntimeError("dsconStartMeasurement failed, rc=%d" % rc)

        data = (c_double * capacity)()
        stamps = (c_double * capacity)()
        print("\nStreaming '%s' - press Ctrl+C to stop\n" % name)

        try:
            while True:
                time.sleep(1.0 / POLL_HZ)
                n = c_size_t(capacity)  # in/out: must be reset before EVERY read
                rc = dll.dsconChannelReadScalarData_2(ch, data, stamps, byref(n))

                if rc == DSX_NET_BUFFER_OVERWRITTEN:
                    print("WARNING: ring buffer overrun, samples were dropped.",
                          file=sys.stderr)
                elif rc != DSX_NO_ERROR:
                    print("Read error rc=%d" % rc, file=sys.stderr)
                    break

                if n.value:
                    print("\n".join("%.6f\t%.6f %s" % (stamps[i], data[i], unit)
                                    for i in range(n.value)))
        except KeyboardInterrupt:
            print("\nStopping...")

        dll.dsconStopMeasurement(inst)
    finally:
        if ch.value:
            dll.dsconFreeChannelInstance(ch)
        dll.dsconDisconnect(inst)
        dll.dsconDestroyInstance(inst)
        print("Disconnected.")


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args[0] if len(args) > 0 else DEFAULT_HOST,
         args[1] if len(args) > 1 else DEFAULT_CMD_PORT,
         args[2] if len(args) > 2 else DEFAULT_DATA_PORT,
         args[3] if len(args) > 3 else DEFAULT_CHANNEL)
