# KompleteLightGuide

A lightweight macOS utility for controlling the Native Instruments Komplete Kontrol Light Guide independently of the Komplete Kontrol software.

The application listens for MIDI Bank Select and Program Change messages, then updates the keyboard Light Guide according to song definitions stored in a YAML configuration file.

Designed for live performance use with applications such as VST Live.

## Features

- Direct HID communication with supported Komplete Kontrol MK1 and MK2 keyboards
- Automatic keyboard detection with per-model key counts and Light Guide protocols
- No Komplete Kontrol software required
- MIDI-driven song selection
- YAML-based song and color definitions
- Validation of YAML structure, MIDI ranges, duplicate definitions, and overlapping light ranges
- Supports named colors, RGB hex values and integer RGB values
- Fast lookup using precompiled `(bank MSB, program)` mappings
- Ideal for setlist-based live performances

## Supported Hardware

The application detects these USB HID product IDs automatically:

| Model | Protocol | Keys | Product ID |
|---|---:|---:|---:|
| Komplete Kontrol S25 MK1 | MK1 | 25 | `0x1340` |
| Komplete Kontrol S49 MK1 | MK1 | 49 | `0x1350` |
| Komplete Kontrol S61 MK1 | MK1 | 61 | `0x1360` |
| Komplete Kontrol S88 MK1 | MK1 | 88 | `0x1410` |
| Komplete Kontrol S49 MK2 | MK2 | 49 | `0x1610` |
| Komplete Kontrol S61 MK2 | MK2 | 61 | `0x1620` |
| Komplete Kontrol S88 MK2 | MK2 | 88 | `0x1630` |

MK1 keyboards use RGB Light Guide packets. MK2 keyboards use the MK2 per-key packet protocol and the built-in color mapping.

## How It Works

```text
VST Live (or any other host where you select programs and send bank and program changes)
    │
    ├── Bank Select (CC0)
    └── Program Change
            │
            ▼
IAC Driver "KompleteLightGuide"
            │
            ▼
KompleteLightGuide
            │
            ▼
USB HID
            │
            ▼
Supported Komplete Kontrol keyboard
```

A song change in VST Live immediately updates the keyboard Light Guide.

## Installation

### Python Environment

Install dependencies:

```bash
pip install hidapi
pip install mido
pip install python-rtmidi
pip install pyyaml
```

```TkInter``` is required for the GUI.

To build the standalone executable, `pyinstaller` is needed as well.

The dependencies are listed in `requirements.txt` and can be installed with 
```bash
pip install -r requirements.txt
```

### macOS MIDI Setup

Enable the IAC Driver:

```text
Applications
    → Utilities
    → Audio MIDI Setup
    → MIDI Studio
    → IAC Driver
```

Enable:

```text
Device is online
```

Create a port named:

```text
KompleteLightGuide
```

The application listens on:

```text
IAC Driver KompleteLightGuide
```

## YAML Format

The application loads `song_colors.yaml` from the same directory as the source script or executable.

Example:

```yaml
# comments are supported
middleC: C4

banks:

  - bank: Main Set
    msb: 0

    songs:

      - title: Song A
        pc: 1

        lights:
          C1-C#2: yellow
          D2-C#3: orange
          D3-G3: 1245028
          G#3-A4: 00FF14
          Bb4-C5: 1264FF
          C#5-E5: red

      - title: Song B
        pc: 2

        lights:
          C1-B2: blue
          C3-B4: green
          C5-C5: red
```

`pc` and `msb` values are zero-based MIDI values from `0` to `127`. `middleC` defines the octave convention used when converting note names to MIDI numbers. Light ranges must resolve to MIDI `0` through `127`; the lower and upper endpoints are inclusive.

## Supported Color Formats

### Named Colors

```yaml
C3-C4: red
D4-E4: yellow
F4-G4: blue
```

### Hex Strings

```yaml
C3-C4: "#FF0000"
D4-E4: 00FF00
F4-G4: FF0000
```

Hex strings may be written without quotes. Quote values beginning with `#` because YAML treats an unquoted `#` as a comment marker.

### Integer RGB Values

```yaml
C3-C4: 0xFF0000
D4-E4: 16711680
```

Equivalent to:

```text
FF0000
```

### RGB Lists

```yaml
C3-C4: [255, 0, 0]
D4-E4: [0, 255, 0]
F4-G4: [0, 0, 255]
```

RGB list channels may be decimal or hexadecimal integers:

```yaml
C3-C4: [0xFF, 0x00, 0x00]
```

RGB list channels must each resolve to an integer from `0` to `255`.

## Built-In Colors

| Name | RGB |
|--------|--------|
| black | 000000 |
| white | FFFFFF |
| red | FF0000 |
| green | 00FF00 |
| blue | 0000FF |
| yellow | FFFF00 |
| cyan | 00FFFF |
| magenta | FF00FF |
| orange | FFB000 |
| purple | 8000FF |
| pink | FF40A0 |
| lime | 80FF00 |
| teal | 00FF80 |
| sky | 40C0FF |
| violet | FF00FF |
| dimred | 400000 |
| dimgreen | 004000 |
| dimblue | 000040 |
| dimwhite | 202020 |

## MIDI Mapping

Song lookup uses:

```text
(bank MSB, program)
```

Example:

```text
CC0 = 0
PC  = 1
```

matches:

```yaml
msb: 0
pc: 1
```

The bank LSB is currently unused and is treated as `0`.

## Runtime Errors

Unknown MIDI patches are non-fatal: the current song and lights remain unchanged and the status bar shows a warning. Invalid configuration, MIDI input failures, and keyboard failures show an error status and disable device-dependent operation.

## Running

```bash
python komplete_lightguide.py
```

The script uses the `song_colors.yaml` and `colors.yaml` files beside it. 

## Building a Standalone Executable

Install PyInstaller:

```bash
pip install pyinstaller
```

Build:

```bash
pyinstaller komplete_lightguide.spec
```

For the terminal build, use:

```bash
pyinstaller komplete_lightguide_terminal.spec
```

Executable will be found in:

```text
dist/
```

At this stage, the yaml files will need to be in the same place as the executable.

## Install Standalone Executable

Copy the executable and the yaml files to ```~/Applications/KompleteLightGuide```.

Open Automator and create:

```New → Application```

Add:

```Run Shell Script```

and use this as the script:

```
cd ~/Applications/KompleteLightGuide
./komplete_lightguide
```

This way you can start the app from Launchpad like everything else.

To change the icon, for an Automator-created .app, the easiest way is Finder's built-in icon replacement:

1. Find an image you want to use (PNG works fine).
2. Open it in Preview.
3. Press ⌘A, then ⌘C.
4. In Finder, select your ```Komplete Light Guide.app``` (in ```/Applications``` folder)
5. Press ⌘I (Get Info).
6. Click the tiny app icon in the upper-left corner of the Info window.
7. Press ⌘V.

The app immediately gets the new icon.

For a more polished macOS look, convert your image to a square 512×512 or 1024×1024 PNG first.

One caveat: if you later recreate the Automator application, the icon may revert and you'll need to paste it again. For a permanent custom icon, you'd eventually embed an .icns file inside a real app bundle, but for a personal utility the Finder method is by far the quickest.

**Missing:** The dock icon still does not show the icon we just pasted.

## Credits

Based on previous reverse engineering work by members of the Native Instruments community including:

- jasonbrent https://github.com/jasonbrent/SynthesiaKomplete
- Olivier Jacques https://github.com/ojacques/SynthesiaKontrol
- Simon Alveteg https://github.com/simonalveteg/KompleteKontrolLightGuide

This project extends those discoveries with song-based Light Guide control for live performance workflows.

## License

MIT License