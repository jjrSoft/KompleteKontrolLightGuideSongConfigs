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
            self._validate_banks(data["banks"], errors, "Default ")
        if "keyboards" in data:
            self._validate_keyboard_definitions(data["keyboards"], errors)
        elif "banks" not in data:
            self._validate_banks(data.get("banks"), errors)
        return errors

    def _validate_song_metadata(self, data, errors):
        self._validate_unknown_keys(
            data,
            {"middleC", "oneBasedBanks", "oneBasedPrograms", "banks", "keyboards"},
            "Top level",
            errors
        )
        if "banks" not in data and "keyboards" not in data:
            errors.append("Missing required top-level key: banks or keyboards")

        for key in ("oneBasedBanks", "oneBasedPrograms"):
            if key in data and not isinstance(data[key], bool):
                errors.append(f"'{key}' must be true or false")

        middle_c = data.get("middleC")
        if middle_c is not None and not self._valid_note(middle_c):
            errors.append("'middleC' must be a valid note, such as C4")
            self.middle_c = "C4"

    def _validate_keyboard_definitions(self, keyboards, errors):
        if not isinstance(keyboards, list) or not keyboards:
            errors.append("'keyboards' must be a non-empty list")
            return

        models = {}
        multiple_definitions = len(keyboards) > 1
        for keyboard_idx, definition in enumerate(keyboards, start=1):
            if not isinstance(definition, dict):
                errors.append(f"Keyboard #{keyboard_idx} definition must be a mapping")
                continue
            self._validate_unknown_keys(
                definition,
                {"model", "serial", "banks"},
                f"Keyboard #{keyboard_idx}",
                errors
            )
            model = definition.get("model")
            product_id = keyboard_product_id(model)
            if model is None:
                if multiple_definitions:
                    errors.append(
                        f"Keyboard #{keyboard_idx} requires 'model' when multiple "
                        "keyboard definitions are present"
                    )
            elif product_id not in KEYBOARDS:
                errors.append(f"Keyboard #{keyboard_idx} has an unsupported model: {model}")
            serial_number = definition.get("serial")
            if serial_number is not None and (
                    not isinstance(serial_number, str) or not serial_number.strip()):
                errors.append(f"Keyboard #{keyboard_idx} 'serial' must be a non-empty string")
            self._validate_banks(
                definition.get("banks"),
                errors,
                f"Keyboard #{keyboard_idx} ({model}) "
            )
            if product_id in KEYBOARDS:
                models.setdefault(product_id, []).append(serial_number)

        for product_id, serial_numbers in models.items():
            if len(serial_numbers) > 1 and any(serial is None for serial in serial_numbers):
                errors.append(
                    f"Multiple {KEYBOARDS[product_id]['name']} definitions require serial numbers"
                )
            configured_serials = [serial for serial in serial_numbers if serial is not None]
            if len(configured_serials) != len(set(configured_serials)):
                errors.append(
                    f"Duplicate serial definition for {KEYBOARDS[product_id]['name']}"
                )

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
            {"title", "pc", "lights"},
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

        lights = song.get("lights")
        if not isinstance(lights, dict):
            errors.append(f"Bank {bank_name} PC {pc} 'lights' must be a mapping")
            return
        if not lights:
            errors.append(f"Bank {bank_name} PC {pc} 'lights' must not be empty")
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

    def check_song_name_consistency(self, data):
        """Warn when keyboards define different song titles for the same bank/PC."""
        if not isinstance(data, dict):
            return []

        sources = []
        if isinstance(data.get("banks"), list):
            sources.append(("Default", data["banks"]))
        for keyboard_idx, definition in enumerate(data.get("keyboards") or [], start=1):
            if not isinstance(definition, dict) or not isinstance(definition.get("banks"), list):
                continue
            label = definition.get("model", f"Keyboard #{keyboard_idx}")
            if definition.get("serial"):
                label = f"{label} (serial {definition['serial']})"
            sources.append((label, definition["banks"]))

        if len(sources) < 2:
            return []

        titles_by_key = {}
        for label, banks in sources:
            for bank in banks:
                if not isinstance(bank, dict):
                    continue
                msb = bank.get("msb")
                for song in bank.get("songs") or []:
                    if not isinstance(song, dict):
                        continue
                    pc = song.get("pc")
                    title = song.get("title")
                    if msb is None or pc is None or title is None:
                        continue
                    titles_by_key.setdefault((msb, pc), []).append((label, title))

        warnings = []
        for (msb, pc), entries in sorted(titles_by_key.items(), key=lambda item: item[0]):
            if len({title for _, title in entries}) > 1:
                details = ", ".join(f"{label}: '{title}'" for label, title in entries)
                warnings.append(
                    f"Bank MSB {msb} PC {pc} has mismatched song names across keyboards: {details}"
                )
        return warnings
