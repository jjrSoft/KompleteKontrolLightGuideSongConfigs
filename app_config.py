from pathlib import Path
import json
import sys

import hid


VERSION = "1.1.0"
TITLE = "Komplete Kontrol LightGuide Manager GUI"


if getattr(sys, 'frozen', False):
    executable_dir = Path(sys.executable).resolve().parent
    bundle_dir = executable_dir.parent.parent
    if bundle_dir.suffix == ".app":
        # External configuration lives beside the macOS application bundle.
        APPDIR = bundle_dir.parent
    else:
        # Running as a standalone executable directory.
        APPDIR = executable_dir
else:
    # Running from source
    APPDIR = Path(__file__).resolve().parent


colors_yaml = APPDIR / "colors.yaml"
song_colors_yaml = APPDIR / "song_colors.yaml"
settings_file = APPDIR / "app_settings.json"


def load_app_settings():
    try:
        with open(settings_file, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_app_settings(settings):
    try:
        with open(settings_file, "w") as f:
            json.dump(settings, f)
    except OSError:
        pass


NATIVE_INSTRUMENTS = 0x17cc


KEYBOARDS = {
    0x1620: {"name": "Komplete Kontrol S61 MK2", "mode": "MK2", "keys": 61, "offset": -36, "first_midi": 36},
    0x1630: {"name": "Komplete Kontrol S88 MK2", "mode": "MK2", "keys": 88, "offset": -21, "first_midi": 21},
    0x1610: {"name": "Komplete Kontrol S49 MK2", "mode": "MK2", "keys": 49, "offset": -36, "first_midi": 36},
    0x1360: {"name": "Komplete Kontrol S61 MK1", "mode": "MK1", "keys": 61, "offset": -36, "first_midi": 36},
    0x1410: {"name": "Komplete Kontrol S88 MK1", "mode": "MK1", "keys": 88, "offset": -21, "first_midi": 21},
    0x1350: {"name": "Komplete Kontrol S49 MK1", "mode": "MK1", "keys": 49, "offset": -36, "first_midi": 36},
    0x1340: {"name": "Komplete Kontrol S25 MK1", "mode": "MK1", "keys": 25, "offset": -21, "first_midi": 21},
}


def connected_keyboards():
    return [
        device for device in hid.enumerate(NATIVE_INSTRUMENTS)
        if device.get("product_id") in KEYBOARDS
    ]


def keyboard_product_id(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str):
        try:
            return int(value, 0)
        except ValueError:
            model_name = " ".join(value.split()).casefold()
            for product_id, keyboard in KEYBOARDS.items():
                short_name = keyboard["name"].replace("Komplete Kontrol ", "")
                if model_name == short_name.casefold():
                    return product_id
    return None


NOTES = {
    'C': 0,
    'C#': 1, 'Db': 1,
    'D': 2,
    'D#': 3, 'Eb': 3,
    'E': 4,
    'F': 5,
    'F#': 6, 'Gb': 6,
    'G': 7,
    'G#': 8, 'Ab': 8,
    'A': 9,
    'A#': 10, 'Bb': 10,
    'B': 11,
}
