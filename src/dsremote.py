import ctypes
import sys
from ctypes import *
from dataclasses import dataclass, field

import numpy as np

from src.ds_remote_constants import (
    DSX_CONNECTION_TYPE_NET,
    DSX_NET_BUFFER_OVERWRITTEN,
    DSX_TOO_MANY_SAMPLES_AVAILABLE,
    rc_name,
)
from src.utils.dsremote_util import DLL_PATH, DSRemoteError, check, check_net_server, load_dll


@dataclass
class Channel:
    name: str
    handle: c_void_p
    rate: float
    unit: str
    ch_type: int
    is_control: bool
    values_np: np.ndarray = field(default=None, repr=False)
    stamps_np: np.ndarray = field(default=None, repr=False)


class DSRemoteSession:
    def __init__(self, host, cmd_port, data_port, dll_path=DLL_PATH):
        self.host = host
        self.cmd_port = cmd_port
        self.data_port = data_port
        self.dll_path = dll_path
        self.dll = None
        self.inst = c_void_p()
        self.channels = {}
        self.capacity = 0
        self.started = False


    def __enter__(self):
        self.dll = load_dll(self.dll_path)
        check_net_server(self.host, self.cmd_port)

        check(self.dll.dsconCreateInstance(byref(self.inst), DSX_CONNECTION_TYPE_NET), "dsconCreateInstance")
        try:
            conn = ("%s:%s:%s" % (self.host, self.cmd_port, self.data_port)).encode()
            check(self.dll.dsconConnect(self.inst, conn), "dsconConnect")

            count = c_size_t()
            check(self.dll.dsconGetChannelCount(self.inst, byref(count)), "dsconGetChannelCount")
        except BaseException:
            self._close()
            raise
        return self


    def __exit__(self, exc_type, exc, tb):
        self._close()
        return False


    def open_channels(self, names):
        if self.started:
            raise RuntimeError("open_channels() must be called before start()")

        missing = []
        for name in names:

            handle = c_void_p()
            rc = self.dll.dsconCreateChannelInstanceByNameUtf8(self.inst, name.encode("utf-8"), byref(handle))

            if rc < 0 or not handle.value:
                # Channel not found.
                missing.append(name)
                continue

            # Create channel instance.
            rate, ch_type, is_control = c_double(), c_int(), c_bool()
            unit = ctypes.create_string_buffer(64)

            check(self.dll.dsconGetSampleRate(handle, byref(rate)), "dsconGetSampleRate")
            check(self.dll.dsconGetChannelType(handle, byref(ch_type)), "dsconGetChannelType")
            check(self.dll.dsconIsChannelControl(handle, byref(is_control)), "dsconIsChannelControl")
            check(self.dll.dsconGetChUnit(handle, unit, len(unit)), "dsconGetChUnit")

            self.channels[name] = Channel(name, handle, rate.value,
                                          unit.value.decode(errors="replace").strip(),
                                          ch_type.value, is_control.value)

        if missing:
            raise DSRemoteError("dsconCreateChannelInstanceByNameUtf8", -1,
                                "channels not found (names are case sensitive): %s" % ", ".join(repr(n) for n in missing))

        return {name: self.channels[name] for name in names}


    def start(self, buffer_samples):
        # Set ring buffer size.
        check(self.dll.dsconSetBufferSize(self.inst, buffer_samples), "dsconSetBufferSize")
        self.capacity = buffer_samples

        # Allocate channel buffers.
        for ch in self.channels.values():
            ch.values_np = np.zeros(buffer_samples, dtype=np.float64)
            ch.stamps_np = np.zeros(buffer_samples, dtype=np.float64)

        # Start measurment.
        check(self.dll.dsconStartMeasurement(self.inst), "dsconStartMeasurement")
        self.started = True


    def read(self, ch):
        # Read all new samples from the channel.
        n = c_size_t(self.capacity)
        rc = self.dll.dsconChannelReadScalarData_2(ch.handle,
                                                   ch.values_np.ctypes.data_as(POINTER(c_double)),
                                                   ch.stamps_np.ctypes.data_as(POINTER(c_double)),
                                                   byref(n))

        if rc not in (DSX_NET_BUFFER_OVERWRITTEN, DSX_TOO_MANY_SAMPLES_AVAILABLE):
            check(rc, "dsconChannelReadScalarData_2")

        count = n.value
        return ch.values_np[:count], ch.stamps_np[:count]

    def stop(self):
        if self.started:
            self.started = False
            check(self.dll.dsconStopMeasurement(self.inst), "dsconStopMeasurement")


    def _close(self):
        # Clean up session state.
        close_steps = []
        if self.started:
            close_steps.append(("dsconStopMeasurement", lambda: self.dll.dsconStopMeasurement(self.inst)))
            self.started = False

        for ch in self.channels.values():
            close_steps.append(("dsconFreeChannelInstance", lambda h=ch.handle: self.dll.dsconFreeChannelInstance(h)))

        if self.inst.value:
            close_steps.append(("dsconDisconnect", lambda: self.dll.dsconDisconnect(self.inst)))
            close_steps.append(("dsconDestroyInstance", lambda: self.dll.dsconDestroyInstance(self.inst)))

        # Execute the lambdas.
        for fn, call in close_steps:
            try:
                rc = call()
                if rc < 0:
                    print("WARNING: %s failed: %s" % (fn, rc_name(rc)), file=sys.stderr)
            except Exception as e:
                print("WARNING: %s raised %s" % (fn, e), file=sys.stderr)

        self.channels = {}
        self.inst = c_void_p()
