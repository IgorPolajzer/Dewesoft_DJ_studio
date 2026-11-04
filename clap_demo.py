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
import sys
import threading
import time
from ctypes import byref, c_double, c_size_t, c_void_p

import numpy as np
import sounddevice as sd
import soundfile as sf

from main import (DEFAULT_CHANNEL, DEFAULT_CMD_PORT, DEFAULT_DATA_PORT,
                  DEFAULT_HOST, DSX_CONNECTION_TYPE_NET, DSX_NET_BUFFER_OVERWRITTEN,
                  DSX_NO_ERROR, check_net_server, find_dll, list_channels, load)

CLAP_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         r"zanderjaz-downloads-20261104-084726\33-Drums\33-Drums\33_Clap_1.aif")

THRESHOLD_MV = 50.0     # trigger when |value| >= 50 mV
HOLDOFF_S = 0.25        # ignore further crossings for this long after a trigger
POLL_INTERVAL_S = 0.001 # NET read loop period
BUFFER_SECONDS = 2.0


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
    dll = load(find_dll())
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

        data = (c_double * capacity)()
        stamps = (c_double * capacity)()
        data_np = np.frombuffer(data, dtype=np.float64)
        stamps_np = np.frombuffer(stamps, dtype=np.float64)
        holdoff_until = -1.0  # in DewesoftX sample time
        taps = 0

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
    finally:
        if ch.value:
            dll.dsconFreeChannelInstance(ch)
        dll.dsconDisconnect(inst)
        dll.dsconDestroyInstance(inst)


if __name__ == "__main__":
    args = sys.argv[1:]
    main(args[0] if len(args) > 0 else DEFAULT_HOST,
         args[1] if len(args) > 1 else DEFAULT_CMD_PORT,
         args[2] if len(args) > 2 else DEFAULT_DATA_PORT,
         args[3] if len(args) > 3 else DEFAULT_CHANNEL)
