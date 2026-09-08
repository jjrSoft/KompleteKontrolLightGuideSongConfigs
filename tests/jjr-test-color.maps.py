#!/usr/bin/env/python3
import time
import hid

VID = 0x17cc
PID = 0x1360

keycount = 61

light_map = """
C1-C#2: yellow
D2-C#3: orange
D3-G3: 0x12FF64
G#3-A4: 00FF14
Bb4-C5: 1264FF
C#5-E5: red
"""

COLOR_TABLE = {
    "black":   0x000000,
    "white":   0xFFFFFF,
    "red":     0xFF0000,
    "green":   0x00FF00,
    "blue":    0x0000FF,
    "yellow":  0xFFFF00,
    "cyan":    0x00FFFF,
    "magenta": 0xFF00FF,
    "orange":  0xFFb000,
    "purple":  0x8000FF,
    "pink":    0xFF40A0,
    "lime":    0x80FF00,
    "teal":    0x00FF80,
    "sky":     0x40C0FF,
    "violet":  0xC040FF,

    # dim variants that may look nicer on stage
    "dimred":    0x400000,
    "dimgreen":  0x004000,
    "dimblue":   0x000040,
    "dimwhite":  0x202020,
}

def color_to_rgb(color):
    """
    Accepts:
        "red" (color names from table)
        
        "#ff0000"
        "ff0000"
        (255,0,0)
        [255,0,0]
    Returns:
        [R,G,B]
    """

    if isinstance(color, (tuple, list)):
        return list(color)

    if isinstance(color, str):

        if color.lower() in COLOR_TABLE:
            value = COLOR_TABLE[color.lower()]
        else:
            value = int(color.lstrip("#"), 16)

        return [
            (value >> 16) & 0xFF,
            (value >> 8) & 0xFF,
            value & 0xFF
        ]

    raise ValueError(f"Unsupported color: {color}")


import re

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

def note_to_midi(note):
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

    return (octave + 1) * 12 + NOTES[name]


def parse_light_map(text, numkeys=88, offset=21):
    """
    offset=21 for S88 MK1
    returns RGB array suitable for command 0x82
    """

    colors = [0] * (numkeys * 3)

    for line in text.splitlines():
        line = line.strip()

        if not line or ':' not in line:
            continue

        rng, rgb = line.split(':', 1)

        start_note, end_note = rng.strip().split('-')

        #r, g, b = [int(x, 16) for x in rgb.strip().split()]
        r, g, b = color_to_rgb(rgb.strip())

        start_midi = note_to_midi(start_note)
        end_midi   = note_to_midi(end_note)

        for midi in range(start_midi, end_midi + 1):

            key = midi - offset

            if 0 <= key < numkeys:
                pos = key * 3
                colors[pos:pos+3] = [r, g, b]

    return colors

#-------

def color_sample():
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

    for phase in range(768):
        color = wheel(phase)
        r, g, b = color
        h.write([0x82] + [r, g, b]*(keycount))
        time.sleep(0.01)

def color_sample1():
    for red in range(0, 256, 16):
        for green in range(0, 256, 16):
            for blue in range(0, 256, 16):
                #print("Setting color: ", red, green, blue)
                h.write([0x82] + [red, green, blue]*(keycount))
                time.sleep(0.1)    



#--------------

for d in hid.enumerate():
    if d['vendor_id'] == VID:
        print("Found Komplete Kontrol device!")
        print(d)

h = hid.device()
h.open(VID, PID) # 6092, 4960 = 0x1360. // was 0x1410

h.write([0xa0, 0x00, 0x00])
# h.write([0x82] + [0x72,0xff, 0x23]*(keycount))


#color_array = parse_light_map(light_map, numkeys=keycount, offset=24)
color_array = parse_light_map(light_map, numkeys=keycount, offset=24)
h.write([0x82] + color_array)


h.close()

#for d in hid.enumerate():
#    print(d)