# Dewesoft DJ Studio

**Dewesoft DJ Studio** is a fun, interactive way for the general public to explore sensors and DAQ equipment. With this project, I aimed to demonstrate the theoretical principles of signal behaviour, specifically how signals are generated and combined, through a DJ studio simulated inside DewesoftX. It also lets users get hands-on experience with basic sensors and measurement equipment by using them as musical instruments.

The project lets users upload two songs of their choice and manipulate them by mixing them together with an equal-power crossfade and adjusting their volume. Users can also add different instrument sounds played with basic sensors:
- **Accelerometer:** drums, where the volume of each hit depends on how hard the sensor is struck.
- **Encoder:** BPM control or note playing. A note plays every 90° of rotation, and each rotation direction plays a different note. This shows that an encoder detects both the angle and the direction of rotation.
- **Tuning fork:** plays its natural frequency when struck. This helps users grasp the idea that every object has a natural frequency (resonance).

While producing music, or later in Analysis mode, users can see how the different songs and instruments are combined into a single master output stream, which makes signal behaviour intuitive to understand.

The DewesoftX C++ Scripts that process the sensor signals are in a separate repository:
**[Dewesoft_DJ_studio_cpp_scripts](https://github.com/IgorPolajzer/Dewesoft_DJ_studio_cpp_scripts)**

## Project structure

```
├── main.py                  Entry point: reads channels from DewesoftX and plays the audio
├── write_config.py          Called by the DewesoftX sequence: stores the selected songs in config.json
├── config.json              Channel names and the selected songs (path, sample rate, BPM)
├── requirements.txt
├── dewesoft_files/
│   ├── Dewesoft_DJ_Booth.dxs    DewesoftX setup (channels, C++ Scripts, displays)
│   └── Dewesoft_DJ_Booth.dxt    DewesoftX sequence (song selection, starts the app)
├── assets/
│   ├── drums/               Drum samples (clap, hat, kick, shaker)
│   ├── note/                Encoder notes (forward, backwards)
│   └── songs/               Example songs
└── src/
    ├── app.py               Main loop: reads the channels and controls the sound player
    ├── sound_player.py      Audio output: song mixing, drums, notes, tuning fork
    ├── config.py            Reads and writes config.json; converts songs for the C++ Scripts
    ├── dsremote.py          DSRemote session: connect, open channels, read data
    ├── ds_remote_constants.py   DSRemote return codes and enums
    ├── encoder_mode.py      Encoder modes (NOTE, BPM)
    └── utils/
        ├── util.py          Shared paths and exit codes
        ├── dsremote_util.py DLL loading and Dewesoft NET settings
        └── dcom_util.py     DewesoftX DCOM control (storing, screen switching)
```

`write_config.py` also creates `song_files/` (the selected songs as raw float32 files read by the C++ Scripts). It is generated and not part of the repository.

## Requirements

- Windows with DewesoftX
- 64-bit Python 3
- Dewesoft hardware with the sensors connected, and the sound card output connected to the analog input used for the `Master` channel

## Setup

1. **Install the Python dependencies**

   ```
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```

2. **Add the DSRemoteConnect DLL**

   Download the DSRemoteConnect library from [Dewesoft Developer downloads](https://dewesoft.com/download/developer-downloads) ([direct link, v1.1.3.26](https://downloads.dewesoft.com/developers/DSRemoteConnect-1.1.3.26.zip)) and copy `lib\x64\DSRemoteConnect64.dll` into the project root, next to `main.py`.

3. **Set up the C++ Scripts**

   Follow the setup in the [C++ Scripts repository](https://github.com/IgorPolajzer/Dewesoft_DJ_studio_cpp_scripts): install DSMinGW, set the project path in the scripts and point the C++ Script channels in `Dewesoft_DJ_Booth.dxs` to the script files.

4. **Adjust the paths in the DewesoftX files**

   The setup and sequence contain absolute paths that must match your system:

   - `Dewesoft_DJ_Booth.dxs`: in each C++ Script channel, the paths to the C++ source files.
   - `Dewesoft_DJ_Booth.dxt`: the two *Execute* steps (*Saving your song selection* and *DJ Studio loading...*) run `write_config.py` and `main.py`. In both steps:
     - set the **Python interpreter** path to `.venv\Scripts\pythonw.exe` in your project folder (the virtual environment from step 1, which has the dependencies installed);
     - set the script path in the parameters to your project folder.

     The *Load setup* step loads `C:\Users\Public\Documents\Dewesoft\Setups\Dewesoft_DJ_Booth.dxs`. Copy the setup there or change the step.

5. **Enable Dewesoft NET** in DewesoftX. The app connects to `localhost` on ports 8999 (commands) and 8001 (data), set in `src/utils/dsremote_util.py`.

## Running

Start the sequence `Dewesoft_DJ_Booth.dxt` in DewesoftX:

1. Select two songs (WAV, MP3, FLAC, OGG or M4A).
2. The sequence runs `write_config.py`, which converts the songs and detects their BPM.
3. It loads the setup and runs `main.py`, which starts the measurement and storing and plays the audio.

Stop the app with Ctrl+C.

To run without the sequence, with the setup loaded in DewesoftX:

```
.venv\Scripts\python.exe write_config.py "<first song>" "<second song>"
.venv\Scripts\python.exe main.py
```

## Troubleshooting

The sequence runs the scripts with `pythonw.exe`, so errors are not shown; the sequence only reports *Something went wrong*. Run `main.py` (or `write_config.py`) from a terminal as shown above to see the error message.

### config.json

`config.json` is written by `write_config.py` and read by both the Python app and the C++ song script.

| Key | Default | Meaning |
|-----|---------|---------|
| `master_channel` | `Master` | Analog input fed by the sound card output |
| `mixer_slider_channel` | `Mixer_slider` | Crossfade between the two songs (0–100) |
| `volume_slider_channel` | `Volume_slider` | Master volume (0–100) |
| `drum_selection_channel` | `Drum_selection` | Selected drum: 0 Clap, 1 Hat, 2 Kick, 3 Shaker |
| `drum_channel` | `Drum trigger` | Hit strength from the drum script (1–10, 0 = no hit) |
| `encoder_mode_channel` | `Encoder_mode` | Encoder mode: 0 NOTE, 1 BPM |
| `encoder_channel` | `Encoder output` | Output of the encoder script (±1 note steps or RPM) |
| `tuning_fork_channel` | `Tuning fork sound` | Output of the tuning fork script |
| `first_song`, `second_song` | – | `path` (source file), `sample_rate` (Hz), `bpm` (detected tempo) |

**Channel names do not match the setup.** If a channel is renamed in DewesoftX, `main.py` stops with `channels not found (names are case sensitive): ...`. Names must match exactly, including case and spaces. The defaults are defined in `src/config.py` and written to `config.json` on every `write_config.py` run, so change them there, not only in `config.json`.

**Missing or invalid config.json.** `main.py` reports that the file cannot be read or that a key is missing. Run `write_config.py` with two songs to create it again.

**Wrong song speed in BPM mode.** `bpm` is detected from the song by `write_config.py`. The detection detection can return half or double the real tempo; correct `bpm` in `config.json` by hand if needed (it is overwritten the next time songs are selected).
