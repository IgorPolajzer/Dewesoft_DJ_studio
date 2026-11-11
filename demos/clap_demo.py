"""Tap-to-clap latency demo.

Streams the first channel (or "AI 1") from DewesoftX over Dewesoft NET and
plays a clap sound as soon as the signal crosses +/- THRESHOLD_MV.

Usage:
    python clap_demo.py [host] [cmd_port] [data_port] [channel_name]

Defaults: localhost 8999 8001 "AI 1"

Latency notes:
  * Audio goes through WASAPI (~3 ms buffer) with the clap preloaded in RAM;
    a trigger only flips a flag that the audio callback picks up.
  * The NET read loop polls every POLL_INTERVAL_S. Each trigger prints how
    old the crossing sample already was when its block arrived (age in block).
  * Bluetooth output (e.g. AirPods) adds ~150-250 ms on its own. Use wired
    speakers/headphones to measure the real chain.
"""
import ctypes
import os
import socket
import sys
import threading
import time
from ctypes import *

import numpy as np
import sounddevice as sd
import soundfile as sf
import win32com.client  # pywin32: DewesoftX COM (DCOM) interface, used for screen switching

# This script lives in <project>/demos, so the project root is one level up.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

DLL_NAME = "DSRemoteConnect64.dll"
# The DLL lives in the project root, not next to this script in demos/.
DLL_PATH = os.path.join(PROJECT_ROOT, DLL_NAME)


DEFAULT_HOST = "localhost"
DEFAULT_CMD_PORT = "8999"
DEFAULT_DATA_PORT = "8001"
DEFAULT_CHANNEL = "AI 6"

DSX_END_OF_ENUM = 1
DSX_NO_ERROR = 0
DSX_NET_BUFFER_OVERWRITTEN = -21
DSX_CONNECTION_TYPE_NET = 1

# Process exit codes for the caller.
EXIT_OK = 0      # stopped normally (Ctrl+C in the tap loop)
EXIT_NOT_OK = 1  # any error: DLL, connection, channel setup, read or audio failure

CLAP_FILE = os.path.join(PROJECT_ROOT, "assets", "33-Drums", "33-Drums", "Clap.aif")

THRESHOLD_MV = 10.0     # trigger when |value| >= 50 mV
HOLDOFF_S = 0.25        # ignore further crossings for this long after a trigger
POLL_INTERVAL_S = 0.001 # NET read loop period
BUFFER_SECONDS = 2.0    # NET ring buffer depth, in seconds of signal

MEASURE_SCREEN = "Recorder"   # DewesoftX Measure-mode screen to show once measuring
SCREEN_SWITCH_TIMEOUT_S = 5.0 # DewesoftX needs a moment to enter Measure mode



def load(path):
    """Load the DLL and declare argtypes/restype."""
    dll = ctypes.WinDLL(path)

    # Type aliases matching examples/Cpp/include/DSRemoteConnect.h and DSXInstance.h
    handle = c_void_p                          # DSXInstanceHandle, ChannelInstanceHandle
    handle_out = POINTER(c_void_p)             # ...Handle* (the DLL writes a handle)
    channel_id = c_char_p                      # ChannelID      = char*
    channel_id_list_out = POINTER(POINTER(c_char_p))  # ChannelIdList* = char***

    # All 38 exports, in the same order as DSRemoteConnect.h; every function returns int.
    sig = {
        # Version / buffer
        "dsconGetVersion":                      [c_char_p, c_size_t],
        "dsconSetBufferSize":                   [handle, c_int],
        # Instance and connection
        "dsconCreateInstance":                  [handle_out, c_int],
        "dsconConnect":                         [handle, c_char_p],
        "dsconDestroyInstance":                 [handle],
        "dsconDisconnect":                      [handle],
        "dsconGetChannelCount":                 [handle, POINTER(c_size_t)],
        "dsconChannelGetName":                  [handle, c_char_p, c_size_t],
        "dsconChannelGetNameUtf8":              [handle, c_char_p, c_size_t, POINTER(c_size_t)],
        "dsconSetAppWindowVisible":             [handle, c_bool],
        "dsconChannelSetTransferred":           [handle, c_bool],
        # Setup, acquisition and storing
        "dsconLoadSetup":                       [handle, c_char_p],
        "dsconIsInAqusition":                   [handle, POINTER(c_bool)],
        "dsconGetState":                        [handle, POINTER(c_int)],
        "dsconStartMeasurement":                [handle],
        "dsconStartStoring":                    [handle, c_char_p],
        "dsconStopStoring":                     [handle],
        "dsconStopStoringEx":                   [handle, POINTER(c_int)],
        "dsconStopMeasurement":                 [handle],
        # Reading data
        "dsconBeginRead":                       [handle, POINTER(c_double), POINTER(c_double)],
        "dsconChannelReadScalarData":           [handle, POINTER(POINTER(c_double)), POINTER(POINTER(c_double)), POINTER(c_size_t)],
        "dsconChannelReadScalarData_2":         [handle, POINTER(c_double), POINTER(c_double), POINTER(c_size_t)],
        "dsconChannelReadScalarData_2abs":      [handle, POINTER(c_double), POINTER(c_double), POINTER(c_size_t)],
        "dsconEndRead":                         [handle],
        "dsconControlChannelWriteData":         [handle, c_double],
        # Channel properties
        "dsconGetSampleRate":                   [handle, POINTER(c_double)],
        "dsconGetChannelType":                  [handle, POINTER(c_int)],
        "dsconIsChannelControl":                [handle, POINTER(c_bool)],
        "dsconGetChUnit":                       [handle, c_char_p, c_size_t],
        # Channel enumeration and instances
        "dsconEnumerateChannels":               [handle, channel_id_list_out, POINTER(c_size_t)],
        "dsconFreeEnumerateChannels":           [handle, channel_id_list_out],
        "dsconCreateChannelInstance":           [handle, channel_id, handle_out],
        "dsconCreateChannelInstanceByName":     [handle, c_char_p, handle_out],
        "dsconCreateChannelInstanceByNameUtf8": [handle, c_char_p, handle_out],
        "dsconFreeChannelInstance":             [handle],
        "dsconInitChannelIdEnum":               [handle],
        "dsconGetNextChannelId":                [handle, channel_id],
        "dsconGetNextChannelIdSize":            [handle, POINTER(c_int)],
    }
    for name, argtypes in sig.items():
        fn = getattr(dll, name)
        fn.argtypes, fn.restype = argtypes, c_int
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


def show_screen(name, timeout=SCREEN_SWITCH_TIMEOUT_S):
    """Switch DewesoftX to the Measure-mode screen called `name`.

    DSRemoteConnect (NET) has no screen command, so this uses DewesoftX's COM
    interface: Dispatch("DEWESoft.App") attaches to the running DewesoftX,
    app.Screens lists the screens of the loaded setup (Item(i).Name) and
    Item(i).Show() makes one visible. Screens only become switchable once
    DewesoftX is in Measure mode, so we retry until `timeout`.
    Returns True if the screen is now shown."""
    deadline = time.perf_counter() + timeout
    names, error = [], None
    while True:
        try:
            app = win32com.client.Dispatch("DEWESoft.App")
            screens = app.Screens
            names = [screens.Item(i).Name for i in range(screens.Count)]
            if name in names:
                screen = screens.Item(names.index(name))
                screen.Show()
                if screen.IsCurrent:
                    print("Switched DewesoftX to the %r screen" % name)
                    return True
        except Exception as e:  # COM errors (pywintypes.com_error) while DewesoftX switches mode
            error = e
        if time.perf_counter() >= deadline:
            print("WARNING: could not switch to screen %r (screens in setup: %s%s)"
                  % (name, ", ".join(repr(n) for n in names) or "none",
                     "; last COM error: %s" % error if error else ""), file=sys.stderr)
            return False
        time.sleep(0.1)


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


class ClapPlayer:
    """Keeps a low-latency WASAPI output stream open and starts the clap
    from the audio callback as soon as trigger() is called."""

    def __init__(self, path):
        wasapi = next(i for i, h in enumerate(sd.query_hostapis())
                      if "WASAPI" in h["name"])
        self.device = sd.query_hostapis(wasapi)["default_output_device"]
        info = sd.query_devices(self.device)
        self.rate = int(info["default_samplerate"])

        clip, clip_rate = sf.read(path, dtype="float32", always_2d=True)
        if clip_rate != self.rate:  # WASAPI shared mode needs the device rate
            n_out = int(len(clip) * self.rate / clip_rate)
            t_in = np.arange(len(clip)) / clip_rate
            t_out = np.arange(n_out) / self.rate
            clip = np.stack([np.interp(t_out, t_in, clip[:, c])
                             for c in range(clip.shape[1])], axis=1).astype(np.float32)
        channels = min(2, info["max_output_channels"])
        if clip.shape[1] < channels:
            clip = np.repeat(clip, channels, axis=1)
        self.clip = clip[:, :channels]

        self.pos = None             # playback position, None = silent
        self.trigger_time = None
        self.lock = threading.Lock()
        self.stream = sd.OutputStream(device=self.device, samplerate=self.rate,
                                      channels=channels, dtype="float32",
                                      latency="low", callback=self._callback)
        print("Audio: %s, %d Hz, output latency %.1f ms"
              % (info["name"], self.rate, self.stream.latency * 1000))
        if "airpods" in info["name"].lower() or "bluetooth" in info["name"].lower():
            print("  WARNING: Bluetooth output adds ~150-250 ms of extra delay. "
                  "Use wired audio for latency measurements.")

    def _callback(self, out, frames, t, status):
        with self.lock:
            if self.trigger_time is not None:
                delay = (time.perf_counter() - self.trigger_time) * 1000
                print("    audio callback started %.1f ms after trigger" % delay)
                self.trigger_time = None
            pos = self.pos
        if pos is None:
            out.fill(0)
            return
        chunk = self.clip[pos:pos + frames]
        out[:len(chunk)] = chunk
        out[len(chunk):] = 0
        with self.lock:
            self.pos = None if pos + frames >= len(self.clip) else pos + frames

    def trigger(self):
        with self.lock:
            self.pos = 0  # restart the clap from the beginning
            self.trigger_time = time.perf_counter()

    def __enter__(self):
        self.stream.start()
        return self

    def __exit__(self, *exc):
        self.stream.stop()
        self.stream.close()


def main(host, cmd_port, data_port, wanted_name):
    dll = load(DLL_PATH)
    check_net_server(host, cmd_port)

    inst = c_void_p()
    rc = dll.dsconCreateInstance(byref(inst), DSX_CONNECTION_TYPE_NET)
    if rc != DSX_NO_ERROR:
        raise RuntimeError("dsconCreateInstance failed, rc=%d" % rc)

    ch = c_void_p()
    try:
        conn = ("%s:%s:%s" % (host, cmd_port, data_port)).encode()
        if dll.dsconConnect(inst, conn) != DSX_NO_ERROR:
            raise RuntimeError("dsconConnect(%s) failed" % conn.decode())
        count = c_size_t()
        rc = dll.dsconGetChannelCount(inst, byref(count))
        if rc != DSX_NO_ERROR or count.value == 0:
            raise RuntimeError("No channels available (rc=%d, count=%d)"
                               % (rc, count.value))

        channels = list_channels(dll, inst)
        selected = next((c for c in channels if c[1] == wanted_name), channels[0])
        _, name, ch = selected
        for _, _, handle in channels:
            if handle is not ch:
                dll.dsconChannelSetTransferred(handle, False)
                dll.dsconFreeChannelInstance(handle)

        rate = c_double()
        dll.dsconGetSampleRate(ch, byref(rate))
        unit_buf = ctypes.create_string_buffer(64)
        dll.dsconGetChUnit(ch, unit_buf, len(unit_buf))
        unit = unit_buf.value.decode(errors="replace").strip()

        # Express the 50 mV threshold in the channel's own unit.
        if unit.lower() == "mv":
            threshold = THRESHOLD_MV
        else:
            threshold = THRESHOLD_MV / 1000.0
            if unit.lower() != "v":
                print("WARNING: channel unit is %r, not V/mV. Using threshold "
                      "%g %s - check the channel scaling in DewesoftX."
                      % (unit, threshold, unit))
        print("Channel %r: %g Hz, unit %r, threshold +/-%g %s"
              % (name, rate.value, unit, threshold, unit))

        capacity = max(3000, int(rate.value * BUFFER_SECONDS))
        dll.dsconSetBufferSize(inst, capacity)
        if dll.dsconStartMeasurement(inst) != DSX_NO_ERROR:
            raise RuntimeError("dsconStartMeasurement failed")

        # Only cosmetic: a failed switch is a warning, the demo keeps running.
        show_screen(MEASURE_SCREEN)

        data = (c_double * capacity)()
        stamps = (c_double * capacity)()
        data_np = np.frombuffer(data, dtype=np.float64)
        stamps_np = np.frombuffer(stamps, dtype=np.float64)
        holdoff_until = -1.0  # in DewesoftX sample time
        taps = 0
        result = EXIT_OK

        with ClapPlayer(CLAP_FILE) as player:
            print("\nTap the accelerometer - Ctrl+C to stop\n")
            try:
                while True:
                    time.sleep(POLL_INTERVAL_S)
                    n = c_size_t(capacity)
                    rc = dll.dsconChannelReadScalarData_2(ch, data, stamps, byref(n))
                    if rc == DSX_NET_BUFFER_OVERWRITTEN:
                        print("WARNING: ring buffer overrun", file=sys.stderr)
                    elif rc != DSX_NO_ERROR:
                        print("Read error rc=%d" % rc, file=sys.stderr)
                        result = EXIT_NOT_OK
                        break
                    if n.value == 0:
                        continue

                    vals = data_np[:n.value]
                    ts = stamps_np[:n.value]
                    hits = np.flatnonzero((np.abs(vals) >= threshold) & (ts > holdoff_until))
                    if hits.size == 0:
                        continue

                    i = hits[0]
                    player.trigger()
                    taps += 1
                    holdoff_until = ts[i] + HOLDOFF_S
                    print("TAP %d: value %+.4f %s at t=%.4f s, block of %d samples, "
                          "age in block %.1f ms"
                          % (taps, vals[i], unit, ts[i], n.value,
                             (ts[-1] - ts[i]) * 1000))
            except KeyboardInterrupt:
                print("\nStopping...")

        dll.dsconStopMeasurement(inst)
        return result
    finally:
        if ch.value:
            dll.dsconFreeChannelInstance(ch)
        dll.dsconDisconnect(inst)
        dll.dsconDestroyInstance(inst)


if __name__ == "__main__":
    args = sys.argv[1:]
    try:
        exit_code = main(args[0] if len(args) > 0 else DEFAULT_HOST,
                         args[1] if len(args) > 1 else DEFAULT_CMD_PORT,
                         args[2] if len(args) > 2 else DEFAULT_DATA_PORT,
                         args[3] if len(args) > 3 else DEFAULT_CHANNEL)
    except KeyboardInterrupt:
        # Ctrl+C before the tap loop started: setup did not finish.
        print("\nInterrupted during setup.", file=sys.stderr)
        exit_code = EXIT_NOT_OK
    except Exception as e:
        print("ERROR: %s" % e, file=sys.stderr)
        exit_code = EXIT_NOT_OK

    sys.exit(exit_code)


