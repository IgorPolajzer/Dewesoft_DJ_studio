import json

from src.util import CONFIG_PATH, MODES


class Config:
    def __init__(self, path=CONFIG_PATH):
        self.path = path
        self.mode = None
        self.master_channel = None
        self.slider_channel = None
        self.first_song = None
        self.second_song = None

    def read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except OSError as e:
            raise RuntimeError("Cannot read %s (%s). Run write_config.py first." % (self.path, e))
        except json.JSONDecodeError as e:
            raise RuntimeError("%s is not valid JSON (%s)." % (self.path, e))

        try:
            self.mode = data["mode"]
            self.master_channel = data["master_channel"]
            self.slider_channel = data["slider_channel"]
            self.first_song = data["first_song"]
            self.second_song = data["second_song"]
        except KeyError as e:
            raise RuntimeError("%s is missing the key %s. Run write_config.py again." % (self.path, e))

        if self.mode not in MODES:
            raise RuntimeError("%s: mode %r must be one of: %s" % (self.path, self.mode, ", ".join(MODES)))
        return self
