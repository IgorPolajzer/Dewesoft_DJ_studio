import time

from src.dsremote import DSRemoteSession
from src.sound_player import SoundPlayer, mix_gains
from src.utils.util import EXIT_OK

# DSRemote ring buffer per channel, in samples. The sliders send at most 100 values/s, so any size
# is far more than one 5 ms poll needs. 102400 worked with Master + one slider in tests.
BUFFER_SAMPLES = 102400
POLL_INTERVAL_S = 0.005 # 5ms.

START_MIXER = 0.0
START_VOLUME = 100.0
START_DRUM = 0.0
DRUM_VOLUME_FACTOR = 1.5


class DJStudioApp:
    def __init__(self, config, host, cmd_port, data_port):
        self.config = config
        self.host = host
        self.cmd_port = cmd_port
        self.data_port = data_port

    def run(self):
        mixer, volume, drum_selection = START_MIXER, START_VOLUME, START_DRUM

        player = None
        if self.config.mode == "music_mix":
            player = SoundPlayer(self.config.first_song["path"], self.config.second_song["path"], *mix_gains(mixer, volume))

        try:
            with DSRemoteSession(self.host, self.cmd_port, self.data_port) as session:
                mixer_name = self.config.mixer_slider_channel
                volume_name = self.config.volume_slider_channel
                drum_selection_name = self.config.drum_selection_channel
                drum_name = self.config.drum_channel

                channels = session.open_channels([mixer_name, volume_name, drum_selection_name, drum_name])
                session.start(BUFFER_SAMPLES)

                if player:
                    player.start()

                mixer_ch = channels[mixer_name]
                volume_ch = channels[volume_name]
                drum_selection_ch = channels[drum_selection_name]
                drum_ch = channels[drum_name]
                while True:
                    try:
                        time.sleep(POLL_INTERVAL_S)

                        # Mixer channel.
                        new_mixer, new_volume = mixer, volume
                        values, _ = session.read(mixer_ch)
                        if len(values):
                            new_mixer = values[-1]

                        # Volume channel.
                        values, _ = session.read(volume_ch)
                        if len(values):
                            new_volume = values[-1]

                        # Update values.
                        if (new_mixer, new_volume) != (mixer, volume):
                            mixer, volume = new_mixer, new_volume
                            gain_a, gain_b = mix_gains(mixer, volume)

                            if player:
                                player.set_gains(gain_a, gain_b)

                        # Drum selection (dropdown 0-3).
                        values, _ = session.read(drum_selection_ch)
                        if len(values):
                            drum_selection = values[-1]

                        # Drum hits (strengths 1-10).
                        values, _ = session.read(drum_ch)
                        for strength in values:
                            if strength < 1:
                                continue

                            index = int(round(drum_selection))
                            if player and 0 <= index < len(player.drums):
                                print(f"Drum hit (strength level: {strength}).")
                                player.play_drum(index, strength, (volume * DRUM_VOLUME_FACTOR))

                    except KeyboardInterrupt:
                        break


        finally:
            if player:
                player.stop()

        return EXIT_OK
