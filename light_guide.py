from pathlib import Path
import re

import hid
import yaml
from tkinter import messagebox

from app_config import KEYBOARDS, NOTES, colors_yaml, connected_keyboards, keyboard_product_id
from color_table import ColorTable
from song_colors_validator import SongColorsValidator
from status import Status



class LightGuide:
    hid_device = None
    configuration_valid =   False

    def __init__(self, song_colors_file, set_status, set_validation_errors,
                 set_device_available):
        self.song_colors_file = song_colors_file
        self.set_status = set_status
        self.set_validation_errors = set_validation_errors
        self.set_device_available = set_device_available
        self.song_colors_by_pc, self.song_lookup = None, None
        self.validation_errors = []
        self.configuration_valid = False
        self.device_available = False
        self.middle_c = "C4"
        self.keyboard = None
        self.keycount = 0
        self.note_offset = 24
        self.mode = "MK1"
        self.keyboard_devices = []

        if not self.load_color_table():
            return

        self.load_song_colors()
        self.device_available = self.connect()
        if self.configuration_valid and self.device_available:
            self.build_song_colors()
        if not self.device_available:
            if self.configuration_valid:
                self.set_status(Status.ERROR, "Komplete Kontrol keyboard unavailable.", None, "")

    def load_song_colors(self):
        try:
            with open(self.song_colors_file, "r") as f:
                song_colors_text = f.read()
        except OSError:
            self._song_configuration_error(
                Status.ERROR,
                f"Cannot read song colors file: {Path(self.song_colors_file).name}",
                str(Path(self.song_colors_file).resolve()),
                "Show full path"
            )
            return

        try:
            self.song_colors = yaml.safe_load(song_colors_text)
        except yaml.YAMLError as ex:
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
            self._song_configuration_error(
                Status.ERROR,
                f"Invalid YAML in song colors file: {Path(self.song_colors_file).name}",
                details,
                "Details"
            )
            return

        try:
            errors = SongColorsValidator(self.color_table).validate(self.song_colors)
        except Exception:
            self._song_configuration_error(
                Status.ERROR,
                f"Cannot validate song colors file: {Path(self.song_colors_file).name}",
                str(Path(self.song_colors_file).resolve()),
                "Show full path"
            )
            return

        self.validation_errors = errors
        self.set_validation_errors(errors)
        if errors:
            self._song_configuration_error(
                Status.ERROR,
                "Errors found in song colors config.",
                None,
                "View Validation Errors",
                clear_validation_errors=False
            )
            return

        self.song_colors_by_pc, self.song_lookup = None, None
        self.middle_c = self.song_colors.get("middleC", "C4")

        self.configuration_valid = True
        self.set_status(Status.OK, "OK", None, "")

    def build_song_colors(self):
        try:
            self.song_colors_by_pc, self.song_lookup = None, None
            for keyboard_device in self.keyboard_devices:
                device_song_colors = self._song_colors_for_device(keyboard_device)
                if device_song_colors is None:
                    keyboard_device["song_colors_by_pc"] = None
                    keyboard_device["song_lookup"] = None
                    continue
                preset_lookup, song_lookup = self.create_lookup_tables(
                    device_song_colors,
                    keyboard_device["keycount"],
                    keyboard_device["note_offset"]
                )
                keyboard_device["song_colors_by_pc"] = preset_lookup
                keyboard_device["song_lookup"] = song_lookup
                if self.song_colors_by_pc is None:
                    self.song_colors_by_pc = preset_lookup
                    self.song_lookup = song_lookup
        except Exception as ex:
            self._song_configuration_error(
                Status.ERROR,
                f"Cannot build song colors file: {Path(self.song_colors_file).name}",
                str(Path(self.song_colors_file).resolve()),
                "Show full path"
            )
            return False

        return True

    def _song_colors_for_device(self, keyboard_device):
        return self._song_colors_with_keyboard_light_overrides(
            self.song_colors,
            keyboard_device
        )

    def _song_colors_with_keyboard_light_overrides(self, song_colors, keyboard_device):
        resolved_banks = []
        changed = False
        for bank in song_colors["banks"]:
            resolved_songs = []
            for song in bank.get("songs", []):
                keyboard_lights = song.get("keyboards")
                if keyboard_lights is None:
                    resolved_songs.append(song)
                    continue

                product_id = keyboard_device["product_id"]
                serial_number = keyboard_device.get("serial_number")
                model_lights = None
                serial_lights = None
                for definition in keyboard_lights:
                    if keyboard_product_id(definition["model"]) != product_id:
                        continue
                    if "serial" in definition:
                        if definition["serial"] == serial_number:
                            serial_lights = definition["lights"]
                    else:
                        model_lights = definition["lights"]

                lights = (
                    serial_lights
                    if serial_lights is not None
                    else model_lights
                    if model_lights is not None
                    else song.get("lights")
                )
                if lights is None:
                    changed = True
                    continue
                resolved_song = dict(song)
                resolved_song.pop("keyboards", None)
                resolved_song["lights"] = lights
                resolved_songs.append(resolved_song)
                changed = True

            resolved_bank = dict(bank)
            resolved_bank["songs"] = resolved_songs
            resolved_banks.append(resolved_bank)

        if not changed:
            return song_colors
        resolved = dict(song_colors)
        resolved["banks"] = resolved_banks
        return resolved

    def has_definition_for_device(self, device_info):
        if not self.configuration_valid:
            return False
        song_colors = self._song_colors_for_device({
            "product_id": device_info["product_id"],
            "serial_number": device_info.get("serial_number"),
        })
        return any(
            bank.get("songs")
            for bank in song_colors.get("banks", [])
        )

    def _song_configuration_error(
            self,
            status,
            message,
            details,
            link_text,
            clear_validation_errors=True):
        self.song_colors_by_pc, self.song_lookup = None, None
        self.configuration_valid = False
        if clear_validation_errors:
            self.validation_errors = []
            self.set_validation_errors([])
        self.set_status(status, message, details, link_text)

    def load_color_table(self):
        try:
            color_table = ColorTable(colors_yaml)
        except Exception:
            self.set_status(
                Status.ERROR,
                f"Cannot load color configuration: {colors_yaml.name}",
                str(colors_yaml),
                "Show full path"
            )
            return False

        self.color_table = color_table
        return True

    def create_lookup_tables(self, song_colors, keycount=None, note_offset=None):
        preset_lookup = {}
        song_lookup = {}
        keycount = self.keycount if keycount is None else keycount
        note_offset = self.note_offset if note_offset is None else note_offset

        settings = getattr(self, "song_colors", None) or {}
        bank_base = 1 if settings.get("oneBasedBanks") is True else 0
        program_base = 1 if settings.get("oneBasedPrograms") is True else 0

        for bank in song_colors["banks"]:
            bank_msb = int(bank["msb"]) - bank_base
            bank_lsb = 0    # unused for now

            for song in bank.get("songs", []):
                program = int(song["pc"]) - program_base
                preset_lookup[(bank_msb, bank_lsb, program)] = self.parse_light_map(
                    song["lights"],
                    numkeys=keycount,
                    offset=note_offset
                )
                song_lookup[(bank_msb, bank_lsb, program)] = song["title"]

        return preset_lookup, song_lookup

    def get_song_title(self, bank_msb, bank_lsb, program):
        return (self.song_lookup or {}).get(
            (bank_msb, bank_lsb, program),
            "Unknown Song"
        )

    def init_rainbow(self, hid_device, mode=None, keycount=None):
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

        mode = self.mode if mode is None else mode
        keycount = self.keycount if keycount is None else keycount
        if mode == "MK2":
            self._write_hid([0x81] + [0] * keycount, hid_device)
        else:
            self._write_hid([0x82] + [60, 60, 255] * keycount, hid_device)

    def connect(self):
        try:
            devices = connected_keyboards()
            if not devices:
                self.set_device_available(False)
                self.set_status(
                    Status.ERROR,
                    "Komplete Kontrol keyboard not found.",
                    None,
                    ""
                )
                return False

            self.keyboard_devices = []
            connection_errors = []
            for device_info in devices:
                product_id = device_info["product_id"]
                keyboard = KEYBOARDS[product_id]
                label = self._device_label(device_info, keyboard)
                hid_path = device_info.get("path")
                if hid_path is None:
                    connection_errors.append(f"{label}: HID path unavailable")
                    continue

                try:
                    hid_device = hid.device()
                    hid_device.open_path(hid_path)
                    self._write_hid([0xa0, 0x00, 0x00], hid_device)
                    self.init_rainbow(hid_device, keyboard["mode"], keyboard["keys"])
                    self.keyboard_devices.append({
                        "hid_device": hid_device,
                        "keyboard": keyboard,
                        "product_id": product_id,
                        "keycount": keyboard["keys"],
                        "note_offset": keyboard["first_midi"],
                        "mode": keyboard["mode"],
                        "label": label,
                        "serial_number": device_info.get("serial_number"),
                    })
                except Exception as ex:
                    connection_errors.append(f"{label}: {ex}")

            if not self.keyboard_devices:
                details = "\n".join(connection_errors) or None
                self.set_device_available(False)
                self.set_status(
                    Status.ERROR,
                    "Cannot connect to any Komplete Kontrol keyboard.",
                    details,
                    "Details" if details else ""
                )
                return False

            first_device = self.keyboard_devices[0]
            self.hid_device = first_device["hid_device"]
            self.keyboard = first_device["keyboard"]
            self.keycount = first_device["keycount"]
            self.note_offset = first_device["note_offset"]
            self.mode = first_device["mode"]
            self.device_available = True
            self.set_device_available(True)
            if connection_errors:
                self.set_status(
                    Status.WARNING,
                    "Some connected keyboards could not be initialized.",
                    "\n".join(connection_errors),
                    "Details"
                )
            return True
        except Exception as ex:
            self.hid_device = None
            self.keyboard_devices = []
            self.set_device_available(False)
            self.set_status(
                Status.ERROR,
                f"Cannot connect to Komplete Kontrol keyboard: {ex}",
                None,
                ""
            )
            return False

    def _device_label(self, device_info, keyboard):
        serial_number = device_info.get("serial_number")
        if serial_number:
            return f"{keyboard['name']} (serial {serial_number})"
        return keyboard["name"]

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
            r, g, b = self.color_table.color_to_rgb(color_spec)

            start_midi = self.note_to_midi(start_note.strip())
            end_midi   = self.note_to_midi(end_note.strip())

            for midi in range(start_midi, end_midi + 1):
                key = midi - offset
                if 0 <= key < numkeys:
                    pos = key * 3
                    colors[pos:pos + 3] = [r, g, b]

        return colors

    def send_colors(self, bank_msb, bank_lsb, pc):
        if bank_msb is None or bank_lsb is None:
            self.set_status(Status.WARNING, "MIDI bank selection is incomplete.", None, "")
            return False

        key = (bank_msb, bank_lsb, pc)
        if not self.keyboard_devices:
            if not self.connect():
                return False
            if not self.build_song_colors():
                return False

        targets = [
            keyboard_device
            for keyboard_device in self.keyboard_devices
            if keyboard_device["song_colors_by_pc"] is not None
            and key in keyboard_device["song_colors_by_pc"]
        ]
        if not targets:
            self.set_status(
                Status.WARNING,
                f"No keyboard definition for bank {bank_msb}:{bank_lsb} — PC {pc}",
                None,
                ""
            )
            return False

        try:
            for keyboard_device in targets:
                colors = keyboard_device["song_colors_by_pc"].get(key)
                if keyboard_device["mode"] == "MK2":
                    packet = [0x81] + self._to_mk2_colors(colors)
                else:
                    packet = [0x82] + colors
                self._write_hid(packet, keyboard_device["hid_device"])
        except Exception as ex:
            self.hid_device = None
            self.keyboard_devices = []
            self.device_available = False
            self.set_device_available(False)
            self.set_status(Status.ERROR, f"Cannot send colors to keyboard: {ex}", None, "")
            return False

        self.set_status(Status.OK, "OK", None, "")
        return True

    def _write_hid(self, packet, hid_device=None):
        hid_device = self.hid_device if hid_device is None else hid_device
        written = hid_device.write(packet)
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
