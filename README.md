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
- Configuration is loaded and validated before device-sized song lookup tables are built
- `Reload Song Colors` reloads both `colors.yaml` and `song_colors.yaml`
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

__Note:__ Only S61 MK1 tested in real life. Other configurations based on https://github.com/ojacques/SynthesiaKontrol/blob/master/SynthesiaKontrol.py.

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
# VSTLive convention: MIDI note 60 is C3 unlike the typical C4.
# C4 is omitted if this entry does not exist.
middleC: C3

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

`pc` and `msb` values are zero-based MIDI values from `0` to `127`. `middleC` defines the octave convention used when converting note names to MIDI numbers. The sample uses VSTLive's convention, where MIDI note 60 is `C3`; use `C4` instead for Scientific Pitch Notation. Light ranges must resolve to MIDI `0` through `127`; the lower and upper endpoints are inclusive.

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
| teal | 00B0A0 |
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

Unknown MIDI patches are non-fatal: the current song and lights remain unchanged and the status bar shows a warning.

Invalid configuration, MIDI input failures, and keyboard failures show an error status. `Reload Song Colors` remains enabled regardless of keyboard availability so configuration can be corrected and retried.

## Running

Place `colors.yaml` and `song_colors.yaml` beside `komplete_lightguide.py` before running from source. The application loads both files from that directory.

```bash
python komplete_lightguide.py
```

For a bundled macOS application, place both YAML files beside the generated `.app` bundle or executable as described below.

## Building a Standalone Executable

Install PyInstaller:

```bash
pip install pyinstaller
```

Build:

```bash
pyinstaller komplete_lightguide.spec
```

Executable will be found in:

```text
dist/
```

The generated app uses `komplete_lightguide.icns` for its macOS icon. Place `colors.yaml` and `song_colors.yaml` beside the generated application or executable; they are external configuration files and are not embedded in the bundle.

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

The generated PyInstaller app bundle includes the icon. If an Automator launcher wraps the executable, set the same icon on the outer Automator `.app` as well, because macOS displays the launcher's icon in Launchpad and the Dock.

1. Open the Automator application in Finder and press ⌘I.
2. Click the small icon in the upper-left corner of the Info window.
3. Paste the icon or assign `komplete_lightguide.icns` to the launcher bundle.

The app immediately gets the new icon.

For a more polished macOS look, convert your image to a square 512×512 or 1024×1024 PNG first.

One caveat: if you later recreate the Automator application, the icon may revert and you'll need to paste it again. For a permanent custom icon, you'd eventually embed an .icns file inside a real app bundle, but for a personal utility the Finder method is by far the quickest.

## Credits

Based on previous reverse engineering work by members of the Native Instruments community including:

- jasonbrent https://github.com/jasonbrent/SynthesiaKomplete
- Olivier Jacques https://github.com/ojacques/SynthesiaKontrol
- Simon Alveteg https://github.com/simonalveteg/KompleteKontrolLightGuide

This project extends those discoveries with song-based Light Guide control for live performance workflows.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE).