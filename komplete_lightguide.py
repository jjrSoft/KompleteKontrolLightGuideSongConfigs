#!/usr/bin/env/python3

from logging import debug, root
import sys
import time
import yaml
import hid
import mido
import re
import threading
import tkinter as tk


dbg = False

colorsYaml = "colors.yaml"
songColorsYaml = "song_colors.yaml"

keycount = 61

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

    def color_to_rgb(self, name):
        value = self.colors[name.lower()]

        # notation [255,72,0]
        if isinstance(value, list):
            return value

        # notation #ff6600
        if isinstance(value, str):
            value = int(value.lstrip("#"), 16)

        return [
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF,
        ]


class LightGuide:
    hid_device = None

    def __init__(self, filename):

        with open(filename, "r") as f:
            self.songColors = yaml.safe_load(f)
    
        if dbg: print(self.songColors)

        self.colorTable = ColorTable(colorsYaml)
        self.songColorsByPC, self.songLookup = self.create_lookup_tables(self.songColors)
        self.connect()

    def create_lookup_tables(self, songColors):
        preset_lookup = {}
        song_lookup = {}

        for bank in songColors["banks"]:
            bank_msb = int(bank["msb"])
            bank_lsb = 0    # unused for now

            for song in bank["songs"]:
                program = int(song["pc"])
                preset_lookup[(bank_msb, bank_lsb, program)] = self.parse_light_map(song["lights"], numkeys=keycount, offset=24)
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
        #     h.write([0x82] + [r, g, b]*(keycount))
        #     time.sleep(0.0001)

        h.write([0x82] + [60, 60, 255]*(keycount))  # turn off all keys

    def connect(self):
        VID = 0x17cc
        PID = 0x1360

        for d in hid.enumerate():
            if d['vendor_id'] == VID:
                print("Found Komplete Kontrol device!")
                print(d)

        self.hid_device = hid.device()
        self.hid_device.open(VID, PID) # 6092, 4960 = 0x1360. // was 0x1410

        # initialize device
        self.hid_device.write([0xa0, 0x00, 0x00])
        self.init_rainbow(self.hid_device)

    def color_list_to_packet(self, colorList):
        return self.parse_light_map(colorList, numkeys=keycount, offset=24)
        #packet = [0x82] + color_array

        #return packet

    def note_to_midi(self, note):
        """
        C4 -> 60
        A4 -> 69

        Parameterized octave convention:
        midi = (octave + 1) * 12 + semitone
        """

        m = re.match(r'^([A-G][#b]?)(-?\d+)$', note)
        if not m:
            raise ValueError(f"Invalid note: {note}")

        name = m.group(1)
        octave = int(m.group(2))

        result = (octave + 1) * 12 + NOTES[name]
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
                raise ValueError(f"Invalid range: {note_range}")

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

        # self.print_color_map(colors, numkeys)

        return colors

    def print_color_map(self, colors, numkeys):
        for octave_start in range(0, numkeys, 12):
            octave = []
            for key in range(octave_start, min(octave_start + 12, numkeys)):

                pos = key * 3

                octave.append(
                    f"{colors[pos]:02X}"
                    f"{colors[pos+1]:02X}"
                    f"{colors[pos+2]:02X}"
                )

            print(
                f"{octave_start:02d}-{octave_start+len(octave)-1:02d}: "
                + " ".join(octave)
            )

    def send_colors(self, bankMsb, bankLsb, PC):
        if dbg: print(f"send_colors({bankMsb}, {bankLsb}, {PC})")
        self.hid_device.write([0x82] + self.songColorsByPC[(bankMsb, bankLsb, PC)])

class MidiMonitor:
    port_name = "IAC Driver KompleteLightGuide"
    bank_msb = 0
    bank_lsb = 0

    def __init__(self, lightGuide, setSongCallback):
        self.lightGuide = lightGuide
        self.setSongCallback = setSongCallback
        print(f"Listening for MIDI messages on {self.port_name}...")

    def handle_message(self, msg):
        print(f"Received MIDI message: {msg}")
        if msg.type == "control_change":
            if msg.control == 0:
                self.bank_msb = msg.value
            elif msg.control == 32:
                self.bank_lsb = msg.value
        elif msg.type == "program_change":
            self.lightGuide.send_colors(self.bank_msb, self.bank_lsb, msg.program)
            self.setSongCallback(self.bank_msb, self.bank_lsb, msg.program, 
                                 self.lightGuide.get_song_title(self.bank_msb, self.bank_lsb, msg.program))

    def run(self):
        try:
            with mido.open_input(self.port_name) as port:
                # print(f"Listening on {self.port_name}")
                while True:
                    msg = port.poll()
                    if msg is not None:
                        self.handle_message(msg)
                    time.sleep(0.01)
        except KeyboardInterrupt:
            print("\nExiting...")
            sys.exit(0)


class LightGuideGuiApp:
    def __init__(self, ):

        self.root = tk.Tk()
        self.bank_var = tk.StringVar()
        self.pc_var = tk.StringVar()
        self.song_var = tk.StringVar()

        # Widgets are added here
        self.root.minsize(500, 50)
        self.root.maxsize(500, 50)
        self.root.geometry("500x50+50+50")
        self.root.title("Komplete Kontrol LightGuide Manager GUI")

        self.currentSongLabel = tk.Label(self.root, text="No song loaded")
        self.currentSongLabel.pack()

        self.lightGuide = LightGuide(songColorsYaml)
        self.midiMonitor = MidiMonitor(self.lightGuide, self.set_song)
        self.midi_thread = threading.Thread(
            target=self.midiMonitor.run,
            daemon=True
        )

        self.midi_thread.start()
        self.root.mainloop()

    def set_song(self, bankMsb, bankLsb, pc, title):
        self.root.after(
            0,  
            lambda: self.currentSongLabel.config(
                text=f"Bank {bankMsb}:{bankLsb} PC {pc} | {title}"
            )
        )     



LightGuideGuiApp()


