import os

# Project root folder.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Process exit codes for the caller.
EXIT_OK = 0
EXIT_NOT_OK = 1

# Application config.
CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.json")
MODES = ("music_mix", "natural_sounds")
