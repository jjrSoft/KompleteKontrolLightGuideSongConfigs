import re
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import yaml

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
    def test_gui_lists_configured_keyboards_that_are_not_connected(self):
        import gui

        app = gui.LightGuideGuiApp.__new__(gui.LightGuideGuiApp)
        app.light_guide = type("Guide", (), {})()
        app.light_guide.configuration_valid = True
        app.light_guide.song_colors = {"banks": [
            {"msb": 0, "songs": [
                {"title": "A", "pc": 0, "keyboards": [
                    {"model": "S61 MK1", "serial": "FIRST", "lights": {}},
                    {"model": "S61 MK1", "serial": "MISSING", "lights": {}},
                    {"model": "S88 MK1", "lights": {}},
                ]},
                {"title": "B", "pc": 1, "keyboards": [
                    {"model": "S61 MK1", "serial": "MISSING", "lights": {}},
                ]},
            ]},
            {"msb": 1},
        ]}

        missing = app._disconnected_keyboard_definitions([
            {"product_id": 0x1360, "serial_number": "FIRST"},
            {"product_id": 0x1410, "serial_number": "ANY"},
        ])

        self.assertEqual(
            [(item["model"], item.get("serial")) for item in missing],
            [("S61 MK1", "MISSING")]
        )

    def test_song_colors_yaml_and_readme_examples_are_valid(self):
        repository_root = Path(lightguide_module.__file__).resolve().parent
        color_table = lightguide_module.ColorTable(repository_root / "colors.yaml")
        validator = lightguide_module.SongColorsValidator(color_table)

        song_colors = yaml.safe_load(
            (repository_root / "song_colors.yaml").read_text()
        )
        self.assertEqual(validator.validate(song_colors), [])

        readme = (repository_root / "README.md").read_text()
        yaml_blocks = re.findall(r"```yaml\s*\n(.*?)\n```", readme, re.DOTALL)
        self.assertTrue(yaml_blocks, "README should contain YAML examples")
        config_examples = []

        for index, block in enumerate(yaml_blocks, start=1):
            with self.subTest(readme_yaml_block=index):
                parsed = yaml.safe_load(block)
                if isinstance(parsed, dict) and "banks" in parsed:
                    config_examples.append(parsed)
                    self.assertEqual(validator.validate(parsed), [])

        self.assertGreaterEqual(
            len(config_examples),
            2,
            "README should contain full and multi-keyboard song config examples"
        )

    def test_load_song_colors_reports_malformed_yaml(self):
        with TemporaryDirectory() as temporary_directory:
            song_colors_file = Path(temporary_directory) / "song_colors.yaml"
            song_colors_file.write_text("banks:\n  - msb: [\n")
            statuses = []
            validation_errors = []
            guide = lightguide_module.LightGuide.__new__(
                lightguide_module.LightGuide
            )
            guide.song_colors_file = song_colors_file
            guide.configuration_valid = True
            guide.set_status = lambda *args: statuses.append(args)
            guide.set_validation_errors = lambda errors: validation_errors.append(errors)

            guide.load_song_colors()

            self.assertFalse(guide.configuration_valid)
            self.assertEqual(validation_errors, [[]])
            self.assertEqual(
                statuses[0][:2],
                (
                    lightguide_module.Status.ERROR,
                    "Invalid YAML in song colors file: song_colors.yaml",
                )
            )
            self.assertIn(str(song_colors_file.resolve()), statuses[0][2])

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
            "keyboards": [{"model": "S61 MK1", "banks": []}],
            "banks": [],
        })

        self.assertEqual(errors, [
            "Top level has an unknown key: keyboards",
            "'banks' must not be empty",
        ])

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

    def test_song_first_keyboard_light_maps_override_the_default(self):
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.middle_c = "C3"
        guide.color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        guide.song_colors = {
            "banks": [{
                "msb": 0,
                "songs": [{
                    "title": "Song",
                    "pc": 0,
                    "lights": {"C3-C3": "green"},
                    "keyboards": [
                        {
                            "model": "S61 MK1",
                            "serial": "FIRST",
                            "lights": {"C3-C3": "red"},
                        },
                        {
                            "model": "S61 MK1",
                            "serial": "SECOND",
                            "lights": {"C3-C3": "blue"},
                        },
                    ],
                }],
            }],
        }
        self.assertEqual(
            lightguide_module.SongColorsValidator(guide.color_table).validate(
                guide.song_colors
            ),
            []
        )
        guide.keyboard_devices = [
            {
                "product_id": product_id,
                "serial_number": serial,
                "keycount": keycount,
                "note_offset": note_offset,
                "mode": "MK1",
                "hid_device": FakeHidDevice(),
            }
            for product_id, serial, keycount, note_offset in (
                (0x1360, "FIRST", 61, 36),
                (0x1360, "SECOND", 61, 36),
                (0x1410, "THIRD", 88, 21),
            )
        ]
        guide.set_status = lambda *args: None

        self.assertTrue(guide.build_song_colors())
        self.assertIn(
            "keyboards",
            guide.song_colors["banks"][0]["songs"][0]
        )
        self.assertTrue(guide.send_colors(0, 0, 0))
        expected_colors = ([255, 0, 0], [0, 0, 255], [0, 255, 0])
        for keyboard, expected_color, key_index in zip(
                guide.keyboard_devices,
                expected_colors,
                (24, 24, 39)):
            packet = keyboard["hid_device"].packets[-1]
            start = 1 + key_index * 3
            self.assertEqual(packet[start:start + 3], expected_color)

    def test_song_first_keyboard_maps_reject_unknown_models(self):
        color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        errors = lightguide_module.SongColorsValidator(color_table).validate({
            "banks": [{
                "msb": 0,
                "songs": [{
                    "title": "Song",
                    "pc": 0,
                    "lights": {"C3-C3": "green"},
                    "keyboards": [{
                        "model": "Unknown Keyboard",
                        "lights": {"C3-C3": "red"},
                    }],
                }],
            }],
        })

        self.assertIn(
            "Bank #1 PC 0 keyboard #1 'model' must be a recognized keyboard model",
            errors
        )

    def test_song_without_default_lights_only_targets_listed_keyboards(self):
        guide = lightguide_module.LightGuide.__new__(lightguide_module.LightGuide)
        guide.middle_c = "C3"
        guide.color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        guide.song_colors = {
            "banks": [{
                "msb": 0,
                "songs": [{
                    "title": "S61 and S88 only",
                    "pc": 0,
                    "keyboards": [{
                        "model": "S61 MK1",
                        "lights": {"C3-C3": "red"},
                    }, {
                        "model": "S88 MK1",
                        "lights": {"C3-C3": "blue"},
                    }],
                }],
            }],
        }
        self.assertEqual(
            lightguide_module.SongColorsValidator(guide.color_table).validate(
                guide.song_colors
            ),
            []
        )
        guide.keyboard_devices = [
            {
                "product_id": product_id,
                "serial_number": None,
                "keycount": keycount,
                "note_offset": note_offset,
                "mode": "MK1",
                "hid_device": FakeHidDevice(),
            }
            for product_id, keycount, note_offset in (
                (0x1360, 61, 36),
                (0x1410, 88, 21),
                (0x1630, 88, 21),
            )
        ]
        guide.set_status = lambda *args: None

        guide.configuration_valid = True
        self.assertTrue(guide.has_definition_for_device({"product_id": 0x1360}))
        self.assertTrue(guide.has_definition_for_device({"product_id": 0x1410}))
        self.assertFalse(guide.has_definition_for_device({"product_id": 0x1630}))

        self.assertTrue(guide.build_song_colors())
        self.assertEqual(
            [device["song_colors_by_pc"] for device in guide.keyboard_devices],
            [
                {(0, 0, 0): unittest.mock.ANY},
                {(0, 0, 0): unittest.mock.ANY},
                {},
            ]
        )
        self.assertTrue(guide.send_colors(0, 0, 0))
        self.assertEqual(
            [len(device["hid_device"].packets) for device in guide.keyboard_devices],
            [1, 1, 0]
        )
        self.assertEqual(
            guide.keyboard_devices[0]["hid_device"].packets[0][1 + 24 * 3:1 + 24 * 3 + 3],
            [255, 0, 0]
        )
        self.assertEqual(
            guide.keyboard_devices[1]["hid_device"].packets[0][1 + 39 * 3:1 + 39 * 3 + 3],
            [0, 0, 255]
        )

    def test_validator_rejects_top_level_keyboard_definitions(self):
        color_table = lightguide_module.ColorTable(
            Path(lightguide_module.__file__).with_name("colors.yaml")
        )
        errors = lightguide_module.SongColorsValidator(color_table).validate({
            "banks": [{
                "msb": 0,
                "songs": [{
                    "title": "Song",
                    "pc": 0,
                    "lights": {"C3-C3": "green"},
                }],
            }],
            "keyboards": [{"model": "S88 MK1", "banks": []}],
        })

        self.assertIn(
            "Top level has an unknown key: keyboards",
            errors
        )

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
            "banks": [{"msb": 0, "songs": [{
                "pc": 1,
                "title": "Song",
                "keyboards": [
                    {"model": "S61 MK1", "serial": "FIRST", "lights": {"C1-C1": "red"}},
                    {"model": "S61 MK1", "serial": "SECOND", "lights": {"C1-C1": "blue"}},
                ],
            }]}],
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
            "banks": [{"msb": 0, "songs": [
                {
                    "title": "First",
                    "pc": 0,
                    "keyboards": [{
                        "model": "S61 MK1",
                        "serial": "FIRST",
                        "lights": {"C3-C3": "red"},
                    }],
                },
                {
                    "title": "Second",
                    "pc": 1,
                    "keyboards": [{
                        "model": "S61 MK1",
                        "serial": "SECOND",
                        "lights": {"C3-C3": "blue"},
                    }],
                },
            ]}],
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
            "banks": [{"msb": 0, "songs": [{
                "pc": 0,
                "title": "Song",
                "keyboards": [
                    {"model": "S61 MK1", "serial": "MK1", "lights": {"C3-C3": "red"}},
                    {"model": "S88 MK2", "serial": "MK2", "lights": {"C3-C3": "red"}},
                ],
            }]}],
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