import re

from app_config import KEYBOARDS, NOTES, keyboard_product_id



class SongColorsValidator:
    def __init__(self, color_table):
        self.color_table = color_table
        self.middle_c = "C4"
        self.bank_base = 0
        self.program_base = 0

    def validate(self, data):
        errors = []
        if not isinstance(data, dict):
            return ["Top level YAML structure must be a mapping"]

        self.middle_c = data.get("middleC", "C4")
        self.bank_base = 1 if data.get("oneBasedBanks") is True else 0
        self.program_base = 1 if data.get("oneBasedPrograms") is True else 0
        self._validate_song_metadata(data, errors)
        if "banks" in data:
            self._validate_banks(data["banks"], errors)
        return errors

    def _validate_song_metadata(self, data, errors):
        self._validate_unknown_keys(
            data,
            {"middleC", "oneBasedBanks", "oneBasedPrograms", "banks"},
            "Top level",
            errors
        )
        if "banks" not in data:
            errors.append("Missing required top-level key: banks")

        for key in ("oneBasedBanks", "oneBasedPrograms"):
            if key in data and not isinstance(data[key], bool):
                errors.append(f"'{key}' must be true or false")

        middle_c = data.get("middleC")
        if middle_c is not None and not self._valid_note(middle_c):
            errors.append("'middleC' must be a valid note, such as C4")
            self.middle_c = "C4"

    def _validate_banks(self, banks, errors, context=""):
        if not isinstance(banks, list):
            errors.append(f"{context}'banks' must be a list")
            return
        if not banks:
            errors.append(f"{context}'banks' must not be empty")
            return

        definitions = set()
        for bank_idx, bank in enumerate(banks, start=1):
            self._validate_bank(bank, bank_idx, errors, definitions)

    def _validate_bank(self, bank, bank_idx, errors, definitions):
        if not isinstance(bank, dict):
            errors.append(f"Bank #{bank_idx} must be a mapping")
            return

        self._validate_unknown_keys(
            bank,
            {"bank", "msb", "songs"},
            f"Bank #{bank_idx}",
            errors
        )

        bank_name = bank.get("bank", f"#{bank_idx}")
        if not isinstance(bank_name, str) or not bank_name.strip():
            errors.append(f"Bank #{bank_idx} 'bank' must be a non-empty string")
            bank_name = f"#{bank_idx}"

        msb = bank.get("msb")
        if not self._valid_midi_value(msb, self.bank_base):
            errors.append(
                f"Bank {bank_name} 'msb' must be an integer from "
                f"{self.bank_base} to {127 + self.bank_base}"
            )

        songs = bank.get("songs", [])
        if not isinstance(songs, list):
            if songs is None:
                errors.append(
                    f"Bank {bank_name} 'songs' has no value; use 'songs: []' "
                    "or omit 'songs'"
                )
            else:
                errors.append(f"Bank {bank_name} 'songs' must be a list")
            return

        for song_idx, song in enumerate(songs, start=1):
            self._validate_song(song, bank_name, song_idx, errors, msb, definitions)

    def _validate_song(self, song, bank_name, song_idx, errors, msb, definitions):
        if not isinstance(song, dict):
            errors.append(f"Bank {bank_name} song #{song_idx} must be a mapping")
            return

        self._validate_unknown_keys(
            song,
            {"title", "pc", "lights", "keyboards"},
            f"Bank {bank_name} song #{song_idx}",
            errors
        )

        title = song.get("title")
        if not isinstance(title, str) or not title.strip():
            errors.append(f"Bank {bank_name} song #{song_idx} 'title' must be a non-empty string")
            title = f"#{song_idx}"

        pc = song.get("pc")
        if not self._valid_midi_value(pc, self.program_base):
            errors.append(
                f"Bank {bank_name} song {title} 'pc' must be an integer from "
                f"{self.program_base} to {127 + self.program_base}"
            )
        elif self._definition_seen(msb, pc, definitions):
            errors.append(f"Duplicate song definition for bank MSB {msb}, PC {pc}")

        has_keyboard_maps = "keyboards" in song
        if "lights" not in song and not has_keyboard_maps:
            errors.append(f"Bank {bank_name} PC {pc} requires 'lights' or 'keyboards'")
        elif "lights" in song:
            lights = song["lights"]
            if not isinstance(lights, dict):
                errors.append(f"Bank {bank_name} PC {pc} 'lights' must be a mapping")
            elif not lights:
                errors.append(f"Bank {bank_name} PC {pc} 'lights' must not be empty")
            else:
                self._validate_light_map(lights, bank_name, pc, errors)

        if has_keyboard_maps:
            self._validate_song_keyboard_lights(
                song["keyboards"],
                bank_name,
                pc,
                errors
            )

    def _validate_song_keyboard_lights(self, keyboard_lights, bank_name, pc, errors):
        if not isinstance(keyboard_lights, list) or not keyboard_lights:
            errors.append(
                f"Bank {bank_name} PC {pc} 'keyboards' must be a non-empty list"
            )
            return

        definitions = {}
        for keyboard_idx, definition in enumerate(keyboard_lights, start=1):
            context = f"Bank {bank_name} PC {pc} keyboard #{keyboard_idx}"
            if not isinstance(definition, dict):
                errors.append(f"{context} must be a mapping")
                continue

            self._validate_unknown_keys(
                definition,
                {"model", "serial", "lights"},
                context,
                errors
            )

            model = definition.get("model")
            product_id = keyboard_product_id(model)
            if product_id not in KEYBOARDS:
                errors.append(f"{context} 'model' must be a recognized keyboard model")
                product_id = None

            serial = definition.get("serial")
            if serial is not None and (
                    not isinstance(serial, str) or not serial.strip()):
                errors.append(f"{context} 'serial' must be a non-empty string")
                serial = None

            if product_id is not None:
                definitions.setdefault(product_id, []).append(serial)

            lights = definition.get("lights")
            if not isinstance(lights, dict):
                errors.append(f"{context} 'lights' must be a mapping")
            elif not lights:
                errors.append(f"{context} 'lights' must not be empty")
            else:
                self._validate_light_map(lights, bank_name, pc, errors)

        for product_id, serials in definitions.items():
            if len(serials) > 1 and any(serial is None for serial in serials):
                errors.append(
                    f"Bank {bank_name} PC {pc} multiple "
                    f"{KEYBOARDS[product_id]['name']} entries require serials"
                )
            configured_serials = [serial for serial in serials if serial is not None]
            if len(configured_serials) != len(set(configured_serials)):
                errors.append(
                    f"Bank {bank_name} PC {pc} has duplicate serial entries for "
                    f"{KEYBOARDS[product_id]['name']}"
                )

    def _validate_light_map(self, lights, bank_name, pc, errors):
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

    def _validate_unknown_keys(self, data, allowed_keys, context, errors):
        for key in data.keys() - allowed_keys:
            errors.append(f"{context} has an unknown key: {key}")

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

    def _valid_midi_value(self, value, base=0):
        return (isinstance(value, int) and not isinstance(value, bool)
                and base <= value <= 127 + base)

    def _valid_color(self, color):
        if isinstance(color, str):
            if color.lower() in self.color_table.colors:
                return True
            try:
                return len(color.lstrip("#")) == 6 and int(color.lstrip("#"), 16) >= 0
            except ValueError:
                return False
        if isinstance(color, int) and not isinstance(color, bool):
            return 0 <= color <= 0xFFFFFF
        return (isinstance(color, list)
                and len(color) == 3
                and all(isinstance(channel, int) and not isinstance(channel, bool)
                        and 0 <= channel <= 255 for channel in color))
