#!/usr/bin/env/python3
#
# Keyboard profiles and Light Guide protocol details were informed by:
# Olivier Jacques, Synthesia Kontrol
# https://github.com/ojacques/SynthesiaKontrol/blob/master/SynthesiaKontrol.py

import hid
import traceback

from app_config import (
    APPDIR,
    KEYBOARDS,
    NOTES,
    NATIVE_INSTRUMENTS,
    TITLE,
    VERSION,
    colors_yaml,
    connected_keyboards,
    keyboard_product_id,
    load_app_settings,
    save_app_settings,
    settings_file,
    song_colors_yaml,
)
from color_table import ColorTable
from light_guide import LightGuide
from gui import LightGuideGuiApp
from midi_monitor import MidiMonitor
from song_colors_validator import SongColorsValidator
from status import STATUS_COLORS, Status


if __name__ == "__main__":
    try:
        LightGuideGuiApp()
    except Exception:
        traceback.print_exc()
