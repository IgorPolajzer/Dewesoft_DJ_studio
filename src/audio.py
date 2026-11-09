import numpy as np
import sounddevice as sd
import soundfile as sf


def find_wasapi_output():
    """Default WASAPI output device. Returns (device_index, sample_rate, name, max_output_channels)."""
    wasapi = next(i for i, h in enumerate(sd.query_hostapis()) if "WASAPI" in h["name"])
    device = sd.query_hostapis(wasapi)["default_output_device"]
    info = sd.query_devices(device)
    return device, int(info["default_samplerate"]), info["name"], info["max_output_channels"]


def load_sample(path, rate, channels):
    """Load an audio file as float32 (frames, channels), resampled to `rate`
    (WASAPI shared mode needs the device rate)."""
    clip, clip_rate = sf.read(path, dtype="float32", always_2d=True)
    if clip_rate != rate:
        n_out = int(len(clip) * rate / clip_rate)
        t_in = np.arange(len(clip)) / clip_rate
        t_out = np.arange(n_out) / rate
        clip = np.stack([np.interp(t_out, t_in, clip[:, c])
                         for c in range(clip.shape[1])], axis=1).astype(np.float32)

    if clip.shape[1] < channels:
        clip = np.repeat(clip, channels, axis=1)
    return clip[:, :channels]
