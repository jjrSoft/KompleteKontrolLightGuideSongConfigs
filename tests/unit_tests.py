import unittest
from pathlib import Path
import sys
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import komplete_kontrol_lightguide as lightguide_module
import light_guide as light_guide_module


class FakeHidDevice:
    def __init__(self):
        self.path = None
        self.packets = []

    def open_path(self, path):
        self.path = path

    def write(self, packet):
        self.packets.append(packet)
        return len(packet)


class MultiKeyboardTests(unittest.TestCase):
    def test_configuration_error_can_preserve_validation_errors(self):
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.song_colors_by_pc = {}
        guide.song_lookup = {}
        guide.configuration_valid = True
        guide.validation_errors = [
            "Bank Common 'songs' has no value; use 'songs: []' or omit 'songs'"
        ]
        guide.set_validation_errors = lambda errors: self.fail(
            "Validation errors should not be cleared"
        )
        guide.set_status = lambda *args: None

        guide._song_configuration_error(
            lightguide_module.Status.ERROR,
            "Errors found in song colors config.",
            None,
            "View Validation Errors",
            clear_validation_errors=False
        )

        self.assertFalse(guide.configuration_valid)
        self.assertEqual(
            guide.validation_errors,
            ["Bank Common 'songs' has no value; use 'songs: []' or omit 'songs'"]
        )

    def test_validator_rejects_unknown_keys_and_empty_lists(self):
        color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        errors = lightguide_module.SongColorsValidator(color_table).validate({
            "unknown": True,
            "banks": [],
            "keyboards": [{
                "model": "S61 MK1",
                "unknown": True,
                "banks": [{"msb": 0, "unknown": True, "songs": []}],
            }],
        })

        self.assertEqual(errors, [
            "Top level has an unknown key: unknown",
            "Default 'banks' must not be empty",
            "Keyboard #1 has an unknown key: unknown",
            "Bank #1 has an unknown key: unknown",
        ])

    def test_mismatched_song_names_across_keyboards_are_warnings(self):
        color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        song_colors = {
            "keyboards": [
                {"model": "S61 MK1", "serial": "FIRST", "banks": [{"msb": 0, "songs": [{
                    "title": "Song A", "pc": 1, "lights": {"C1-C1": "red"},
                }]}]},
                {"model": "S88 MK1", "serial": "SECOND", "banks": [{"msb": 0, "songs": [{
                    "title": "Song B", "pc": 1, "lights": {"C1-C1": "blue"},
                }]}]},
            ],
        }

        self.assertEqual(
            lightguide_module.SongColorsValidator(color_table).validate(song_colors),
            []
        )
        self.assertEqual(
            lightguide_module.SongColorsValidator(color_table)
                .check_song_name_consistency(song_colors),
            [
                "Bank MSB 0 PC 1 has mismatched song names across keyboards: "
                "S61 MK1 (serial FIRST): 'Song A', S88 MK1 (serial SECOND): 'Song B'"
            ]
        )

    def test_matching_song_names_across_keyboards_produce_no_warnings(self):
        color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        song_colors = {
            "keyboards": [
                {"model": "S61 MK1", "serial": "FIRST", "banks": [{"msb": 0, "songs": [{
                    "title": "Song A", "pc": 1, "lights": {"C1-C1": "red"},
                }]}]},
                {"model": "S88 MK1", "serial": "SECOND", "banks": [{"msb": 0, "songs": [{
                    "title": "Song A", "pc": 1, "lights": {"C1-C1": "blue"},
                }]}]},
            ],
        }

        self.assertEqual(
            lightguide_module.SongColorsValidator(color_table)
                .check_song_name_consistency(song_colors),
            []
        )

    def test_validator_allows_empty_or_omitted_song_lists(self):
        color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        empty_list_errors = lightguide_module.SongColorsValidator(color_table).validate({
            "banks": [{"msb": 0, "songs": []}],
        })
        omitted_key_errors = lightguide_module.SongColorsValidator(color_table).validate({
            "banks": [{"msb": 0}],
        })

        self.assertEqual(empty_list_errors, [])
        self.assertEqual(omitted_key_errors, [])

    def test_lookup_tables_allow_omitted_song_lists(self):
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.middle_c = "C4"
        guide.color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )

        self.assertEqual(
            guide.create_lookup_tables(
                {"banks": [{"msb": 0}]},
                keycount=61,
                note_offset=24
            ),
            ({}, {})
        )

    def test_lookup_tables_normalize_one_based_banks_and_programs(self):
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.middle_c = "C3"
        guide.color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        guide.song_colors = {
            "oneBasedBanks": True,
            "oneBasedPrograms": True,
        }

        preset_lookup, song_lookup = guide.create_lookup_tables(
            {"banks": [{"msb": 2, "songs": [{
                "title": "Song",
                "pc": 3,
                "lights": {"C3-C3": "red"},
            }]}]},
            keycount=61,
            note_offset=36
        )

        self.assertEqual(set(preset_lookup), {(1, 0, 2)})
        self.assertEqual(song_lookup, {(1, 0, 2): "Song"})
        self.assertEqual(preset_lookup[(1, 0, 2)][24 * 3:24 * 3 + 3], [255, 0, 0])

    def test_validator_rejects_incomplete_song_and_boolean_color(self):
        color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        errors = lightguide_module.SongColorsValidator(color_table).validate({
            "banks": [{"msb": 0, "songs": [
                {"pc": 0, "lights": {}},
                {"title": "Song", "pc": 1, "lights": {"C1-C1": True}},
            ]}],
        })

        self.assertEqual(errors, [
            "Bank #1 song #1 'title' must be a non-empty string",
            "Bank #1 PC 0 'lights' must not be empty",
            "Bank #1 PC 1 has an invalid color: True",
        ])

    def test_default_banks_apply_when_no_keyboard_definition_matches(self):
        banks = [{"msb": 0, "songs": [{
            "title": "Song", "pc": 0, "lights": {"C1-C1": "red"},
        }]}]
        default_definition = {"banks": banks}
        specific_definition = {"model": "S61 MK1", "serial": "SECOND", "banks": banks}
        song_colors = {
            **default_definition,
            "keyboards": [specific_definition],
        }
        color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        self.assertEqual(
            lightguide_module.SongColorsValidator(color_table).validate(song_colors),
            []
        )

        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.song_colors = song_colors
        guide.configuration_valid = True
        first_keyboard = {"product_id": 0x1360, "serial_number": "FIRST"}
        second_keyboard = {"product_id": 0x1360, "serial_number": "SECOND"}
        guide.keyboard_devices = [first_keyboard, second_keyboard]

        self.assertTrue(guide.has_definition_for_device(first_keyboard))
        self.assertTrue(guide.has_definition_for_device(second_keyboard))
        self.assertIs(guide._song_colors_for_device(first_keyboard), song_colors)
        self.assertIs(
            guide._song_colors_for_device(second_keyboard),
            specific_definition
        )

    def test_single_keyboard_definition_can_omit_model(self):
        song_colors = {
            "keyboards": [{
                "serial": "ONLY",
                "banks": [{"msb": 0, "songs": [{
                    "title": "Song", "pc": 0, "lights": {"C1-C1": "red"},
                }]}],
            }],
        }
        color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        self.assertEqual(
            lightguide_module.SongColorsValidator(color_table).validate(song_colors),
            []
        )

        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.song_colors = song_colors
        guide.keyboard_devices = [{"product_id": 0x1360, "serial_number": "ONLY"}]
        self.assertIs(
            guide._song_colors_for_device(guide.keyboard_devices[0]),
            song_colors["keyboards"][0]
        )

    def test_duplicate_connected_models_require_serial_entries(self):
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.song_colors = {
            "keyboards": [{
                "model": "S61 MK1",
                "banks": [{"msb": 0, "songs": [{
                    "title": "Song", "pc": 0, "lights": {"C1-C1": "red"},
                }]}],
            }],
        }
        guide.keyboard_devices = [
            {"product_id": 0x1360},
            {"product_id": 0x1360},
        ]
        guide.validation_errors = []
        guide.configuration_valid = True
        guide.set_validation_errors = lambda errors: None
        guide.set_status = lambda *args: None

        self.assertFalse(guide.build_song_colors())
        self.assertEqual(
            guide.validation_errors,
            [
                "Multiple connected Komplete Kontrol S61 MK1 keyboards "
                "require serial numbers in song_colors.yaml"
            ]
        )

    def test_disconnected_models_and_serials_are_allowed(self):
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.song_colors = {
            "keyboards": [
                {"model": "S88 MK1", "banks": [{"msb": 0, "songs": [{
                    "title": "Song", "pc": 0, "lights": {"C1-C1": "red"},
                }]}]},
                {"model": "S61 MK1", "serial": "WRONG", "banks": [{"msb": 0, "songs": [{
                    "title": "Song", "pc": 0, "lights": {"C1-C1": "red"},
                }]}]},
            ],
        }
        guide.keyboard_devices = [{"product_id": 0x1360, "serial_number": "RIGHT"}]

        self.assertEqual(guide._keyboard_definition_errors(), [])

    def test_identifies_configured_keyboard_that_is_not_connected(self):
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.configuration_valid = True
        guide.song_colors = {
            "keyboards": [
                {"model": "S61 MK1", "serial": "CONNECTED"},
                {"model": "S88 MK1", "serial": "DISCONNECTED"},
            ],
        }
        app = lightguide_module.LightGuideGuiApp.__new__(lightguide_module.LightGuideGuiApp)
        app.light_guide = guide

        self.assertEqual(
            app._disconnected_keyboard_definitions([
                {"product_id": 0x1360, "serial_number": "CONNECTED"},
            ]),
            [{"model": "S88 MK1", "serial": "DISCONNECTED"}]
        )

    def test_identifies_expected_serial_that_is_not_connected(self):
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.configuration_valid = True
        guide.song_colors = {
            "keyboards": [{"model": "S61 MK1", "serial": "EXPECTED"}],
        }
        app = lightguide_module.LightGuideGuiApp.__new__(lightguide_module.LightGuideGuiApp)
        app.light_guide = guide

        self.assertEqual(
            app._disconnected_keyboard_definitions([
                {"product_id": 0x1360, "serial_number": "ACTUAL"},
            ]),
            [{"model": "S61 MK1", "serial": "EXPECTED"}]
        )

    def test_same_model_keyboards_use_serial_entries(self):
        device_info = [
            {"product_id": 0x1360, "path": b"keyboard-one", "serial_number": "FIRST"},
            {"product_id": 0x1360, "path": b"keyboard-two", "serial_number": "SECOND"},
        ]
        hid_devices = []
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.middle_c = "C3"
        guide.keyboard_devices = []
        guide.hid_device = None
        guide.set_device_available = lambda available: None
        guide.set_status = lambda *args: None
        guide.color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        guide.song_colors = {
            "keyboards": [
                {"model": "S61 MK1", "serial": "FIRST", "banks": [{"msb": 0, "songs": [{
                    "pc": 1, "title": "First", "lights": {"C1-C1": "red"},
                }]}]},
                {"model": "S61 MK1", "serial": "SECOND", "banks": [{"msb": 0, "songs": [{
                    "pc": 1, "title": "Second", "lights": {"C1-C1": "blue"},
                }]}]},
            ],
        }
        self.assertEqual(
            lightguide_module.SongColorsValidator(guide.color_table).validate(
                guide.song_colors
            ),
            []
        )

        def create_hid_device():
            hid_device = FakeHidDevice()
            hid_devices.append(hid_device)
            return hid_device

        with patch.object(lightguide_module.hid, "enumerate", return_value=device_info), \
                patch.object(lightguide_module.hid, "device", side_effect=create_hid_device):
            self.assertTrue(guide.connect())

        self.assertEqual([device.path for device in hid_devices], [
            b"keyboard-one",
            b"keyboard-two",
        ])
        self.assertEqual(hid_devices[0].packets[-1], hid_devices[1].packets[-1])
        self.assertTrue(guide.build_song_colors())
        self.assertTrue(guide.send_colors(0, 0, 1))
        self.assertEqual(hid_devices[0].packets[-1][1:4], [255, 0, 0])
        self.assertEqual(hid_devices[1].packets[-1][1:4], [0, 0, 255])

    def test_different_programs_are_sent_only_to_the_matching_keyboard(self):
        hid_devices = [FakeHidDevice(), FakeHidDevice()]
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.middle_c = "C3"
        guide.color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        guide.song_colors = {
            "keyboards": [
                {"model": "S61 MK1", "serial": "FIRST", "banks": [{
                    "msb": 0, "songs": [{
                        "title": "First", "pc": 0, "lights": {"C3-C3": "red"},
                    }],
                }]},
                {"model": "S61 MK1", "serial": "SECOND", "banks": [{
                    "msb": 0, "songs": [{
                        "title": "Second", "pc": 1, "lights": {"C3-C3": "blue"},
                    }],
                }]},
            ],
        }
        guide.keyboard_devices = [
            {
                "product_id": 0x1360,
                "serial_number": serial,
                "keycount": 61,
                "note_offset": 36,
                "mode": "MK1",
                "hid_device": hid_device,
            }
            for serial, hid_device in zip(("FIRST", "SECOND"), hid_devices)
        ]
        guide.set_status = lambda *args: None

        self.assertTrue(guide.build_song_colors())
        self.assertTrue(guide.send_colors(0, 0, 0))
        self.assertEqual(len(hid_devices[0].packets), 1)
        self.assertEqual(hid_devices[0].packets[0][1 + 24 * 3:1 + 24 * 3 + 3], [255, 0, 0])
        self.assertEqual(hid_devices[1].packets, [])

        self.assertTrue(guide.send_colors(0, 0, 1))
        self.assertEqual(len(hid_devices[0].packets), 1)
        self.assertEqual(len(hid_devices[1].packets), 1)
        self.assertEqual(hid_devices[1].packets[0][1 + 24 * 3:1 + 24 * 3 + 3], [0, 0, 255])

    def test_mixed_keyboard_models_use_their_own_packet_formats(self):
        device_info = [
            {"product_id": 0x1360, "path": b"mk1", "serial_number": "MK1"},
            {"product_id": 0x1630, "path": b"mk2", "serial_number": "MK2"},
        ]
        hid_devices = []
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.middle_c = "C3"
        guide.keyboard_devices = []
        guide.hid_device = None
        guide.set_device_available = lambda available: None
        guide.set_status = lambda *args: None
        guide.color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        guide.song_colors = {
            "keyboards": [
                {"model": "S61 MK1", "serial": "MK1", "banks": [{
                    "msb": 0, "songs": [{
                        "pc": 0, "title": "Song", "lights": {"C3-C3": "red"},
                    }],
                }]},
                {"model": "S88 MK2", "serial": "MK2", "banks": [{
                    "msb": 0, "songs": [{
                        "pc": 0, "title": "Song", "lights": {"C3-C3": "red"},
                    }],
                }]},
            ],
        }

        def create_hid_device():
            hid_device = FakeHidDevice()
            hid_devices.append(hid_device)
            return hid_device

        with patch.object(lightguide_module.hid, "enumerate", return_value=device_info), \
                patch.object(lightguide_module.hid, "device", side_effect=create_hid_device):
            self.assertTrue(guide.connect())

        self.assertTrue(guide.build_song_colors())
        self.assertTrue(guide.send_colors(0, 0, 0))

        mk1_packet = hid_devices[0].packets[-1]
        mk2_packet = hid_devices[1].packets[-1]
        self.assertEqual(mk1_packet[0], 0x82)
        self.assertEqual(len(mk1_packet), 1 + 61 * 3)
        self.assertEqual(mk1_packet[1 + 24 * 3:1 + 24 * 3 + 3], [255, 0, 0])
        self.assertEqual(mk2_packet[0], 0x81)
        self.assertEqual(len(mk2_packet), 1 + 88)
        self.assertEqual(mk2_packet[1 + 39], 0x0D)

    def test_connect_reports_when_no_keyboards_are_found(self):
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        available = []
        statuses = []
        guide.set_device_available = available.append
        guide.set_status = lambda *args: statuses.append(args)

        with patch.object(light_guide_module, "connected_keyboards", return_value=[]):
            self.assertFalse(guide.connect())

        self.assertEqual(available, [False])
        self.assertEqual(statuses[0][:2], (
            lightguide_module.Status.ERROR,
            "Komplete Kontrol keyboard not found.",
        ))

    def test_connect_keeps_working_keyboard_when_another_fails(self):
        device_info = [
            {"product_id": 0x1360, "path": b"broken", "serial_number": "BROKEN"},
            {"product_id": 0x1360, "path": b"working", "serial_number": "WORKING"},
        ]
        hid_devices = []
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.keyboard_devices = []
        guide.hid_device = None
        guide.set_device_available = lambda available: None
        statuses = []
        guide.set_status = lambda *args: statuses.append(args)

        class MaybeFailingHidDevice(FakeHidDevice):
            def open_path(self, path):
                if path == b"broken":
                    raise OSError("device unavailable")
                super().open_path(path)

        def create_hid_device():
            hid_device = MaybeFailingHidDevice()
            hid_devices.append(hid_device)
            return hid_device

        with patch.object(lightguide_module.hid, "enumerate", return_value=device_info), \
                patch.object(lightguide_module.hid, "device", side_effect=create_hid_device):
            self.assertTrue(guide.connect())

        self.assertEqual(len(guide.keyboard_devices), 1)
        self.assertEqual(guide.keyboard_devices[0]["serial_number"], "WORKING")
        self.assertEqual(guide.hid_device, hid_devices[1])
        self.assertEqual(statuses[-1][0], lightguide_module.Status.WARNING)
        self.assertIn("device unavailable", statuses[-1][2])

    def test_connect_fails_when_every_keyboard_fails_to_open(self):
        device_info = [
            {"product_id": 0x1360, "path": b"broken", "serial_number": "BROKEN"},
        ]
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.keyboard_devices = []
        guide.set_device_available = lambda available: None
        statuses = []
        guide.set_status = lambda *args: statuses.append(args)

        class FailingHidDevice(FakeHidDevice):
            def open_path(self, path):
                raise OSError("device unavailable")

        with patch.object(lightguide_module.hid, "enumerate", return_value=device_info), \
                patch.object(lightguide_module.hid, "device", return_value=FailingHidDevice()):
            self.assertFalse(guide.connect())

        self.assertEqual(guide.keyboard_devices, [])
        self.assertEqual(statuses[-1][0], lightguide_module.Status.ERROR)
        self.assertEqual(
            statuses[-1][1],
            "Cannot connect to any Komplete Kontrol keyboard."
        )
        self.assertIn("device unavailable", statuses[-1][2])


if __name__ == "__main__":
    unittest.main()