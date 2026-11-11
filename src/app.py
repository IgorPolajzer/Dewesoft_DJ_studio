import time

from src.dsremote import DSRemoteSession
from src.sound_player import SoundPlayer, mix_gains
from src.utils.util import EXIT_OK

CHANNELS = ["Mixer_slider", "Volume_slider"]

# DSRemote ring buffer per channel, in samples. The sliders send at most 100 values/s, so any size
# is far more than one 5 ms poll needs. 102400 worked with Master + one slider in tests.
BUFFER_SAMPLES = 102400
POLL_INTERVAL_S = 0.005 # 5ms.

START_MIXER = 0.0
START_VOLUME = 100.0


class DJStudioApp:
    def __init__(self, config, host, cmd_port, data_port):
        self.config = config
        self.host = host
        self.cmd_port = cmd_port
        self.data_port = data_port

    def run(self):
        mixer, volume = START_MIXER, START_VOLUME

        player = None
        if self.config.mode == "music_mix":
            player = SoundPlayer(self.config.first_song["path"], self.config.second_song["path"], *mix_gains(mixer, volume))

        try:
            with DSRemoteSession(self.host, self.cmd_port, self.data_port) as session:
                channels = session.open_channels(CHANNELS)
                session.start(BUFFER_SAMPLES)

                if player:
                    player.start()

                mixer_ch = channels["Mixer_slider"]
                volume_ch = channels["Volume_slider"]
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
                    except KeyboardInterrupt:
                        break


        finally:
            if player:
                player.stop()

        return EXIT_OK
