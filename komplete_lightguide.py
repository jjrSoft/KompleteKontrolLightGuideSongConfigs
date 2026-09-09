#!/usr/bin/env/python3

from pathlib import Path
from logging import debug
import sys
import time
import yaml
import hid
import mido
import re
import threading
import tkinter as tk
from tkinter import messagebox
from enum import Enum
import traceback

dbg = False

if getattr(sys, 'frozen', False):
    # Running as PyInstaller executable
    APPDIR = Path(sys.executable).parent
else:
    # Running from source
    APPDIR = Path(__file__).resolve().parent

colorsYaml = APPDIR / "colors.yaml"
songColorsYaml = APPDIR / "song_colors.yaml"

NATIVE_INSTRUMENTS = 0x17cc

KEYBOARDS = {
    0x1620: {"name": "Komplete Kontrol S61 MK2", "mode": "MK2", "keys": 61, "offset": -36, "first_note": "C1"},
    0x1630: {"name": "Komplete Kontrol S88 MK2", "mode": "MK2", "keys": 88, "offset": -21, "first_note": "A0"},
    0x1610: {"name": "Komplete Kontrol S49 MK2", "mode": "MK2", "keys": 49, "offset": -36, "first_note": "C1"},
    0x1360: {"name": "Komplete Kontrol S61 MK1", "mode": "MK1", "keys": 61, "offset": -36, "first_note": "C1"},
    0x1410: {"name": "Komplete Kontrol S88 MK1", "mode": "MK1", "keys": 88, "offset": -21, "first_note": "A0"},
    0x1350: {"name": "Komplete Kontrol S49 MK1", "mode": "MK1", "keys": 49, "offset": -36, "first_note": "C1"},
    0x1340: {"name": "Komplete Kontrol S25 MK1", "mode": "MK1", "keys": 25, "offset": -21, "first_note": "C1"},
}

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



class ColorTable:
    def __init__(self, colorsFile):
        with open(colorsFile, "r") as f:
            colors = yaml.safe_load(f)

        self.colors = {
            k.lower(): v
            for k, v in colors.items()
        }

    def color_to_rgb(self, color):
        value = self.colors.get(color.lower()) if isinstance(color, str) else color

        if value is None and isinstance(color, str):
            hex_value = color.lstrip("#")
            if len(hex_value) != 6:
                raise ValueError(f"Invalid RGB color: {color}")
            try:
                value = int(hex_value, 16)
            except ValueError as ex:
                raise ValueError(f"Invalid RGB color: {color}") from ex

        if isinstance(value, list):
            if (len(value) != 3
                    or any(not isinstance(channel, int)
                           or isinstance(channel, bool)
                           or not 0 <= channel <= 255
                           for channel in value)):
                raise ValueError(f"Invalid RGB color: {color}")
            return value

        if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= 0xFFFFFF:
            raise ValueError(f"Invalid RGB color: {color}")

        return [
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ]


class SongColorsValidator:
    def __init__(self, color_table):
        self.color_table = color_table
        self.middle_c = "C4"

    def validate(self, data):
        errors = []
        if not isinstance(data, dict):
            return ["Top level YAML structure must be a mapping"]

        self.middle_c = data.get("middleC", "C4")
        self._validate_song_metadata(data, errors)
        self._validate_banks(data.get("banks"), errors)
        return errors

    def _validate_song_metadata(self, data, errors):
        if "banks" not in data:
            errors.append("Missing required top-level key: banks")

        middle_c = data.get("middleC")
        if middle_c is not None and not self._valid_note(middle_c):
            errors.append("'middleC' must be a valid note, such as C4")
            self.middle_c = "C4"

    def _validate_banks(self, banks, errors):
        if not isinstance(banks, list):
            errors.append("'banks' must be a list")
            return

        definitions = set()
        for bank_idx, bank in enumerate(banks, start=1):
            self._validate_bank(bank, bank_idx, errors, definitions)

    def _validate_bank(self, bank, bank_idx, errors, definitions):
        if not isinstance(bank, dict):
            errors.append(f"Bank #{bank_idx} must be a mapping")
            return

        bank_name = bank.get("bank", f"#{bank_idx}")
        if not isinstance(bank_name, str) or not bank_name.strip():
            errors.append(f"Bank #{bank_idx} 'bank' must be a non-empty string")
            bank_name = f"#{bank_idx}"

        msb = bank.get("msb")
        if not self._valid_midi_value(msb):
            errors.append(f"Bank {bank_name} 'msb' must be an integer from 0 to 127")

        songs = bank.get("songs")
        if not isinstance(songs, list):
            errors.append(f"Bank {bank_name} 'songs' must be a list")
            return

        for song_idx, song in enumerate(songs, start=1):
            self._validate_song(song, bank_name, song_idx, errors, msb, definitions)

    def _validate_song(self, song, bank_name, song_idx, errors, msb, definitions):
        if not isinstance(song, dict):
            errors.append(f"Bank {bank_name} song #{song_idx} must be a mapping")
            return

        title = song.get("title", f"#{song_idx}")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"Bank {bank_name} song #{song_idx} 'title' must be a non-empty string")
            title = f"#{song_idx}"

        pc = song.get("pc")
        if not self._valid_midi_value(pc):
            errors.append(f"Bank {bank_name} song {title} 'pc' must be an integer from 0 to 127")
        elif self._definition_seen(msb, pc, definitions):
            errors.append(f"Duplicate song definition for bank MSB {msb}, PC {pc}")

        lights = song.get("lights")
        if not isinstance(lights, dict):
            errors.append(f"Bank {bank_name} PC {pc} 'lights' must be a mapping")
            return

        light_ranges = []
        for note_range, color in lights.items():
            self._validate_light(
                note_range,
                color,
                bank_name,
                pc,
                errors,
                light_ranges
            )

    def _validate_light(self, note_range, color, bank_name, pc, errors, light_ranges):
        range_pattern = r'^([A-G][#b]?-?\d+)\s*-\s*([A-G][#b]?-?\d+)$'
        match = re.match(range_pattern, note_range) if isinstance(note_range, str) else None
        if not match:
            errors.append(f"Bank {bank_name} PC {pc} has an invalid note range: {note_range}")
            return

        for note in match.groups():
            if not self._valid_note(note):
                errors.append(f"Bank {bank_name} PC {pc} has an invalid note: {note}")

        if not all(self._valid_note(note) for note in match.groups()):
            return

        start_midi = self._note_to_midi(match.group(1))
        end_midi = self._note_to_midi(match.group(2))
        if start_midi < 0:
            errors.append(
                f"Bank {bank_name} PC {pc} bottom note {match.group(1)} "
                f"is MIDI {start_midi}; use {self._midi_to_note(0)} or higher"
            )
        if end_midi > 127:
            errors.append(
                f"Bank {bank_name} PC {pc} top note {match.group(2)} "
                f"is MIDI {end_midi}; use {self._midi_to_note(127)} or lower"
            )
        if start_midi < 0 or end_midi > 127:
            return

        if start_midi > end_midi:
            errors.append(f"Bank {bank_name} PC {pc} has a reversed note range: {note_range}")
            return

        for previous_start, previous_end, previous_range in light_ranges:
            if start_midi <= previous_end and end_midi >= previous_start:
                errors.append(
                    f"Bank {bank_name} PC {pc} has overlapping light ranges: "
                    f"{previous_range} and {note_range}"
                )
        light_ranges.append((start_midi, end_midi, note_range))

        if not self._valid_color(color):
            errors.append(f"Bank {bank_name} PC {pc} has an invalid color: {color}")

    def _definition_seen(self, msb, pc, definitions):
        definition = (msb, pc)
        if definition in definitions:
            return True
        definitions.add(definition)
        return False

    def _note_to_midi(self, note):
        match = re.fullmatch(r'([A-G][#b]?)(-?\d+)', note)
        reference = re.fullmatch(r'([A-G][#b]?)(-?\d+)', self.middle_c)
        reference_midi = (int(reference.group(2)) + 1) * 12 + NOTES[reference.group(1)]
        note_midi = (int(match.group(2)) + 1) * 12 + NOTES[match.group(1)]
        return 60 + note_midi - reference_midi

    def _midi_to_note(self, midi):
        reference = re.fullmatch(r'([A-G][#b]?)(-?\d+)', self.middle_c)
        reference_midi = (int(reference.group(2)) + 1) * 12 + NOTES[reference.group(1)]
        absolute_midi = reference_midi + midi - 60
        note_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        octave, semitone = divmod(absolute_midi, 12)
        return f"{note_names[semitone]}{octave - 1}"

    def _valid_note(self, note):
        match = re.fullmatch(r'[A-G][#b]?(-?\d+)', note) if isinstance(note, str) else None
        return match is not None and -2 <= int(match.group(1)) <= 9

    def _valid_midi_value(self, value):
        return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= 127

    def _valid_color(self, color):
        if isinstance(color, str):
            if color.lower() in self.color_table.colors:
                return True
            try:
                return len(color.lstrip("#")) == 6 and int(color.lstrip("#"), 16) >= 0
            except ValueError:
                return False
        if isinstance(color, int):
            return 0 <= color <= 0xFFFFFF
        return (isinstance(color, list)
                and len(color) == 3
                and all(isinstance(channel, int) and not isinstance(channel, bool)
                        and 0 <= channel <= 255 for channel in color))


class LightGuide:
    hid_device = None
    configuration_valid =   False

    def __init__(self, song_colors_file, set_status, set_validation_errors,
                 set_device_available):
        self.song_colors_file = song_colors_file
        self.set_status = set_status
        self.set_validation_errors = set_validation_errors
        self.set_device_available = set_device_available
        self.songColorsByPC, self.songLookup = None, None
        self.validation_errors = []
        self.configuration_valid = False
        self.device_available = False
        self.middle_c = "C4"
        self.keyboard = None
        self.keycount = 0
        self.note_offset = 24
        self.mode = "MK1"

        try:
            self.colorTable = ColorTable(colorsYaml)
        except Exception as ex:
            self.set_status(
                Status.ERROR,
                f"Cannot load color configuration: {colorsYaml.name}",
                str(colorsYaml),
                "Show full path"
            )
            return

        self.device_available = self.connect()
        self.load_song_colors()
        if not self.device_available:
            self.set_status(Status.ERROR, "Komplete Kontrol keyboard unavailable.", None, "")

    def load_song_colors(self):
        try:
            with open(self.song_colors_file, "r") as f:
                song_colors_text = f.read()
        except OSError:
            self.songColorsByPC, self.songLookup = None, None
            self.configuration_valid = False
            self.validation_errors = []
            self.set_validation_errors([])
            self.set_status(
                Status.ERROR,
                f"Cannot read song colors file: {Path(self.song_colors_file).name}",
                str(Path(self.song_colors_file).resolve()),
                "Show full path"
            )
            return

        try:
            self.songColors = yaml.safe_load(song_colors_text)
        except yaml.YAMLError as ex:
            self.songColorsByPC, self.songLookup = None, None
            self.configuration_valid = False
            self.validation_errors = []
            self.set_validation_errors([])
            location = ""
            if getattr(ex, "problem_mark", None) is not None:
                mark = ex.problem_mark
                location = f" at line {mark.line + 1}, column {mark.column + 1}"
            details = str(Path(self.song_colors_file).resolve())
            if getattr(ex, "problem_mark", None) is not None:
                line_number = ex.problem_mark.line + 1
                source_lines = song_colors_text.splitlines()
                if 0 < line_number <= len(source_lines):
                    first_context_line = max(1, line_number - 2)
                    last_context_line = min(len(source_lines), line_number + 1)
                    details += "\nYAML context:"
                    for context_line in range(first_context_line, last_context_line + 1):
                        marker = ">" if context_line == line_number else " "
                        details += f"\n{marker} {context_line}: {source_lines[context_line - 1]}"
                    details += (
                        f"\n  {' ' * (len(str(line_number)) + 2 + ex.problem_mark.column)}^"
                        "\nThe parser may identify the line where the structure becomes "
                        "invalid; check the surrounding lines for a missing key or ':'"
                    )
            if str(ex):
                details += f"\n{ex}"
            self.set_status(
                Status.ERROR,
                f"Invalid YAML in song colors file: {Path(self.song_colors_file).name}",
                details,
                "Details"
            )
            return

        try:
            errors = SongColorsValidator(self.colorTable).validate(self.songColors)
        except Exception:
            self.songColorsByPC, self.songLookup = None, None
            self.configuration_valid = False
            self.validation_errors = []
            self.set_validation_errors([])
            self.set_status(
                Status.ERROR,
                f"Cannot validate song colors file: {Path(self.song_colors_file).name}",
                str(Path(self.song_colors_file).resolve()),
                "Show full path"
            )
            return

        self.validation_errors = errors
        self.set_validation_errors(errors)
        if errors:
            self.songColorsByPC, self.songLookup = None, None
            self.configuration_valid = False
            self.set_status(
                Status.ERROR,
                "Errors found in song colors config.",
                None,
                "View Validation Errors"
            )
            return

        self.middle_c = self.songColors.get("middleC", "C4")
        if self.keyboard is not None:
            self.note_offset = self.note_to_midi(self.keyboard["first_note"])

        try:
            self.songColorsByPC, self.songLookup = self.create_lookup_tables(self.songColors)
        except Exception as ex:
            self.songColorsByPC, self.songLookup = None, None
            self.configuration_valid = False
            self.validation_errors = []
            self.set_validation_errors([])
            self.set_status(
                Status.ERROR,
                f"Cannot build song colors file: {Path(self.song_colors_file).name}",
                str(Path(self.song_colors_file).resolve()),
                "Show full path"
            )
            return

        self.configuration_valid = True
        self.set_status(Status.OK, "OK", None, "")

    def create_lookup_tables(self, songColors):
        preset_lookup = {}
        song_lookup = {}

        for bank in songColors["banks"]:
            bank_msb = int(bank["msb"])
            bank_lsb = 0    # unused for now

            for song in bank["songs"]:
                program = int(song["pc"])
                preset_lookup[(bank_msb, bank_lsb, program)] = self.parse_light_map(
                    song["lights"],
                    numkeys=self.keycount,
                    offset=self.note_offset
                )
                song_lookup[(bank_msb, bank_lsb, program)] = song["title"]

        return preset_lookup, song_lookup

    def get_song_title(self, bank_msb, bank_lsb, program):
        return self.songLookup.get((bank_msb, bank_lsb, program), "Unknown Song")

    def init_rainbow(self, h):
        def wheel(pos):
            pos %= 768

            if pos < 256:
                return [255-pos, pos, 0]      # red -> yellow -> green

            elif pos < 512:
                pos -= 256
                return [0, 255-pos, pos]      # green -> cyan -> blue

            else:
                pos -= 512
                return [pos, 0, 255-pos]      # blue -> magenta -> red

        # for phase in range(256):    #768):
        #     color = wheel(phase)
        #     r, g, b = color
        #     h.write([0x82] + [r, g, b] * self.keycount)
        #     time.sleep(0.0001)

        if self.mode == "MK2":
            self._write_hid([0x81] + [0] * self.keycount)
        else:
            self._write_hid([0x82] + [60, 60, 255] * self.keycount)

    def connect(self):
        try:
            devices = [
                device for device in hid.enumerate(NATIVE_INSTRUMENTS)
                if device.get("product_id") in KEYBOARDS
            ]
            if not devices:
                self.set_device_available(False)
                self.set_status(
                    Status.ERROR,
                    "Komplete Kontrol keyboard not found.",
                    None,
                    ""
                )
                return False

            product_id = devices[0]["product_id"]
            self.keyboard = KEYBOARDS[product_id]
            self.keycount = self.keyboard["keys"]
            self.note_offset = self.note_to_midi(self.keyboard["first_note"])
            self.mode = self.keyboard["mode"]

            if dbg:
                print("Found Komplete Kontrol device!")
                print(self.keyboard["name"])

            self.hid_device = hid.device()
            self.hid_device.open(NATIVE_INSTRUMENTS, product_id)

            # initialize device
            self._write_hid([0xa0, 0x00, 0x00])
            self.init_rainbow(self.hid_device)
            return True
        except Exception as ex:
            self.hid_device = None
            self.set_device_available(False)
            self.set_status(
                Status.ERROR,
                f"Cannot connect to Komplete Kontrol keyboard: {ex}",
                None,
                ""
            )
            return False

    def note_to_midi(self, note):
        """
        With the default Scientific Pitch convention:
        C4 -> 60
        A4 -> 69

        The configured middle_c value selects the octave convention, for
        example VSTLive uses C3 for MIDI note 60:
        midi = (octave + 1) * 12 + semitone
        """

        m = re.match(r'^([A-G][#b]?)(-?\d+)$', note)
        if not m:
            raise ValueError(f"Invalid note: {note}")

        name = m.group(1)
        octave = int(m.group(2))

        middle_c_match = re.match(r'^([A-G][#b]?)(-?\d+)$', self.middle_c)
        middle_c_midi = ((int(middle_c_match.group(2)) + 1) * 12
                 + NOTES[middle_c_match.group(1)])
        note_midi = (octave + 1) * 12 + NOTES[name]
        result = 60 + note_midi - middle_c_midi
        if dbg: print(f"  note_to_midi: {note} -> {result}")
        return result

    def parse_light_map(self, note_map, numkeys=88, offset=21):
        """
        note_map:
        {
            'C1-C#2': 'yellow',
            'D2-C#3': 'orange',
            'D3-G3': 1245028,
            'G#3-A4': '00FF14',
            'Bb4-C5': '1264FF',
            'C#5-E5': 'red'
        }

        returns RGB array suitable for command 0x82
        """

        colors = [0] * (numkeys * 3)

        if dbg: print(f"parse_light_map: note_map = {note_map}")
        for note_range, color_spec in note_map.items():

            m = re.match(
                r'^([A-G][#b]?-?\d+)\s*-\s*([A-G][#b]?-?\d+)$',
                note_range
            )
            if not m:
                messagebox.showerror(
                    "Error",
                    f"Invalid range: {note_range}"
                )
                return None

            start_note = m.group(1)
            end_note = m.group(2)
            if dbg: print(f"  {start_note} - {end_note} = {color_spec}")

            r, g, b = self.colorTable.color_to_rgb(color_spec)
            if dbg: print(f"  color: {color_spec} -> {hex(r)}, {hex(g)}, {hex(b)}")

            start_midi = self.note_to_midi(start_note.strip())
            end_midi   = self.note_to_midi(end_note.strip())

            for midi in range(start_midi, end_midi + 1):
                key = midi - offset
                if 0 <= key < numkeys:
                    pos = key * 3
                    colors[pos:pos + 3] = [r, g, b]

        return colors

    def send_colors(self, bankMsb, bankLsb, pc):
        if dbg: print(f"send_colors({bankMsb}, {bankLsb}, {pc})")
        if bankMsb is None or bankLsb is None:
            self.set_status(Status.WARNING, "MIDI bank selection is incomplete.", None, "")
            return False

        key = (bankMsb, bankLsb, pc)
        if self.songColorsByPC is None:
            self.set_status(Status.ERROR, "Song colors configuration is unavailable.", None, "")
            return False
        colors = self.songColorsByPC.get(key)
        if colors is None:
            self.set_status(
                Status.WARNING,
                f"Unknown song: bank {bankMsb}:{bankLsb} — PC {pc}",
                None,
                ""
            )
            return False

        if self.hid_device is None:
            if not self.connect():
                return False

        try:
            if self.mode == "MK2":
                packet = [0x81] + self._to_mk2_colors(colors)
            else:
                packet = [0x82] + colors
            self._write_hid(packet)
        except Exception as ex:
            self.hid_device = None
            self.device_available = False
            self.set_device_available(False)
            self.set_status(Status.ERROR, f"Cannot send colors to keyboard: {ex}", None, "")
            return False

        self.set_status(Status.OK, "OK", None, "")
        return True

    def _write_hid(self, packet):
        written = self.hid_device.write(packet)
        if written != len(packet):
            raise OSError(
                f"keyboard accepted {written} of {len(packet)} bytes"
            )

    def _to_mk2_colors(self, colors):
        palette = {
            (0, 0, 0): 0x00,
            (255, 0, 0): 0x0D,
            (0, 255, 0): 0x1D,
            (0, 0, 255): 0x2D,
            (255, 255, 255): 0x3D,
        }
        result = []
        for position in range(0, len(colors), 3):
            rgb = tuple(colors[position:position + 3])
            if rgb in palette:
                result.append(palette[rgb])
            else:
                result.append(0x00 if rgb == (0, 0, 0) else 0x2D)
        return result

class MidiMonitor:
    port_name = "IAC Driver KompleteLightGuide"
    bank_msb = None
    bank_lsb = None
    pc = None

    def __init__(self, lightGuide, setSongCallback, set_status):
        self.lightGuide = lightGuide
        self.setSongCallback = setSongCallback
        self.set_status = set_status
        self.available = True
        if dbg: print(f"Listening for MIDI messages on {self.port_name}...")

    def handle_message(self, msg):
        if dbg: print(f"Received MIDI message: {msg}")
        if msg.type == "control_change":
            if msg.control == 0:
                self.bank_msb = msg.value
            elif msg.control == 32:
                self.bank_lsb = msg.value
        elif msg.type == "program_change":
            if not self.lightGuide.send_colors(self.bank_msb, self.bank_lsb, msg.program):
                return

            self.pc = msg.program
            self.setSongCallback(self.bank_msb, self.bank_lsb, msg.program,
                                 self.lightGuide.get_song_title(self.bank_msb, self.bank_lsb, msg.program))

    def get_current_data(self):
        if self.bank_msb is None or self.bank_lsb is None or self.pc is None:
            return (None, None, None, "No song loaded")
        return (self.bank_msb, self.bank_lsb, self.pc,
                self.lightGuide.get_song_title(self.bank_msb, self.bank_lsb, self.pc))

    def run(self):
        try:
            with mido.open_input(self.port_name) as port:
                if dbg: print(f"Listening on {self.port_name}")
                while True:
                    msg = port.poll()
                    if msg is not None:
                        self.handle_message(msg)
                    time.sleep(0.01)
        except KeyboardInterrupt:
            if dbg: print("\nExiting...")
            sys.exit(0)
        except Exception as ex:
            self.available = False
            self.set_status(Status.ERROR, f"Cannot open MIDI input: {ex}", None, "")


class Status(Enum):
    NONE = 0
    OK = 1
    WARNING = 2
    ERROR = 3

STATUS_COLORS = {
    Status.NONE:    "#d0d0d0",  # grey
    Status.OK:      "#90ee90",  # green
    Status.WARNING: "#ffd700",  # yellow
    Status.ERROR:   "#ff6b6b",  # red
}

class LightGuideGuiApp:
    def __init__(self):
        self.root = tk.Tk()
        self.validation_errors = []
        self.error_window = None
        self.error_log = None
        self.status_details = []
        self.status_details_label = "Show full path"

        # Widgets are added here
        self.root.minsize(500, 120)
        self.root.maxsize(500, 120)
        self.root.geometry("500x120+50+50")
        self.root.title("Komplete Kontrol LightGuide Manager GUI")

        self.currentPatch = tk.Label(self.root, text="No patch")
        self.currentPatch.pack()
        self.currentSongLabel = tk.Label(self.root, text="No song loaded", font=("Helvetica", 16, "bold"))
        self.currentSongLabel.pack()

        self.reloadButton = tk.Button(self.root, text="Reload Color Definitions", command=self.reload_colors)
        self.reloadButton.pack()

        self.statusVar = tk.StringVar(value="Initializing")
        self.footer = tk.Frame(self.root)
        self.footer.pack(side="bottom", fill="x")

        self.statusLabel = tk.Label(
            self.footer,
            textvariable=self.statusVar,
            anchor="w",
            justify="left",
            #relief="sunken",
            bg=STATUS_COLORS[Status.NONE]
        )

        self.statusLabel.pack(side="left", fill="x", expand=True)
        self.errorButton = tk.Label(
            self.footer,
            text="View Validation Errors",
            font=("Helvetica", 10, "underline"),
            fg="#0645AD",
            bg=STATUS_COLORS[Status.NONE],
            cursor="hand2",
            padx=4,
            pady=2
        )
        self.errorButton.bind("<Button-1>", lambda event: self.show_validation_errors())
        self.errorButton.pack_forget()
        self.set_status(Status.NONE, "Loading...", None, "")

        self.lightGuide = LightGuide(
            songColorsYaml,
            self.set_status,
            self.set_validation_errors,
            self.set_device_available
        )
        self.set_device_available(self.lightGuide.device_available)
        if self.lightGuide.device_available and self.lightGuide.configuration_valid:
            self.midiMonitor = MidiMonitor(
                self.lightGuide,
                self.set_song,
                self.set_status
            )
            self.midi_thread = threading.Thread(
                target=self.midiMonitor.run,
                daemon=True
            )
            self.midi_thread.start()
        else:
            self.midiMonitor = None

        self.root.mainloop()

    def set_device_available(self, available):
        self.reloadButton.config(state=tk.NORMAL if available else tk.DISABLED)

    def set_status(self, status: Status, message: str, details, link_text):
        self.status_details = [details] if details else []
        self.status_details_label = link_text

        def update():
            self.statusVar.set(message)
            self.statusLabel.config(
                bg=STATUS_COLORS[status]
            )
            self.footer.config(
                bg=STATUS_COLORS[status]
            )
            self.errorButton.config(
                bg=STATUS_COLORS[status],
                fg="#0645AD",
                text=self.status_details_label
            )

            if self.status_details and not self.errorButton.winfo_manager():
                self.errorButton.pack(side="right", padx=4, pady=2)
            elif not self.status_details and not self.validation_errors:
                self.errorButton.pack_forget()

            if self.error_log is not None and self.error_log.winfo_exists():
                self.error_log.config(state="normal")
                self.error_log.delete("1.0", "end")
                log_entries = self.status_details + self.validation_errors
                self.error_log.insert("1.0", "\n".join(log_entries))
                self.error_log.config(state="disabled")

        self.root.after(0, update)

    def set_validation_errors(self, errors):
        self.validation_errors = list(errors)
        if self.validation_errors:
            self.status_details = []
            self.errorButton.config(text="View Validation Errors")
            if not self.errorButton.winfo_manager():
                self.errorButton.pack(side="right", padx=4, pady=2)
        elif not self.status_details:
            self.errorButton.pack_forget()

        if self.error_log is not None and self.error_log.winfo_exists():
            self.error_log.config(state="normal")
            self.error_log.delete("1.0", "end")
            log_entries = self.status_details + self.validation_errors
            self.error_log.insert("1.0", "\n".join(log_entries))
            self.error_log.config(state="disabled")

    def show_validation_errors(self):
        if self.error_window is not None and self.error_window.winfo_exists():
            self.error_window.deiconify()
            self.error_window.lift()
            return

        self.error_window = tk.Toplevel(self.root)
        self.error_window.title("Validation Errors")
        self.error_window.geometry("640x360")
        self.error_window.protocol("WM_DELETE_WINDOW", self.close_validation_errors)

        log_frame = tk.Frame(self.error_window)
        log_frame.pack(fill="both", expand=True, padx=8, pady=8)

        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side="right", fill="y")

        self.error_log = tk.Text(log_frame, wrap="word", yscrollcommand=scrollbar.set)
        self.error_log.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.error_log.yview)

        log_entries = self.status_details + self.validation_errors
        self.error_log.insert("1.0", "\n".join(log_entries))
        self.error_log.config(state="disabled")

    def close_validation_errors(self):
        if self.error_window is not None:
            self.error_window.destroy()
            self.error_window = None
            self.error_log = None

    def update_labels(self, bankMsb, bankLsb, pc, title):
        self.currentPatch.config(
                text=f"Bank {bankMsb}:{bankLsb} — PC {pc}"
            )
        self.currentSongLabel.config(
                text=f"{title}"
            )


    def set_song(self, bankMsb, bankLsb, pc, title):
        self.root.after(
            0,
            lambda: self.update_labels(bankMsb, bankLsb, pc, title)
        )

    def reload_colors(self):
        current_data = self.midiMonitor.get_current_data() if self.midiMonitor else None
        self.lightGuide.load_song_colors()
        if not self.lightGuide.configuration_valid:
            return

        if self.midiMonitor is None and self.lightGuide.device_available:
            self.midiMonitor = MidiMonitor(
                self.lightGuide,
                self.set_song,
                self.set_status
            )
            self.midi_thread = threading.Thread(
                target=self.midiMonitor.run,
                daemon=True
            )
            self.midi_thread.start()

        if current_data is None:
            current_data = self.midiMonitor.get_current_data()

        bank_msb, bank_lsb, pc, title = current_data
        if pc is not None:
            # we have a song loaded, so we need to re-send the colors for it
            self.set_song(bank_msb, bank_lsb, pc, title)
            self.lightGuide.send_colors(bank_msb, bank_lsb, pc)



try:
    LightGuideGuiApp()
except Exception:
    traceback.print_exc()


