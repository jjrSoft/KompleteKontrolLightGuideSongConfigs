# KompleteLightGuide

A lightweight macOS utility for controlling the Native Instruments Komplete Kontrol MK1 Light Guide independently of the Komplete Kontrol software.

The application listens for MIDI Bank Select and Program Change messages, then updates the keyboard Light Guide according to song definitions stored in a YAML configuration file.

Designed for live performance use with applications such as VST Live.

## Features

- Direct HID communication with Komplete Kontrol MK1 keyboards
- No Komplete Kontrol software required
- MIDI-driven song selection
- YAML-based song and color definitions
- Supports named colors, RGB hex values and integer RGB values
- Fast lookup using precompiled `(bankMSB, program)` mappings
- Ideal for setlist-based live performances

## Supported Hardware

Currently tested with:

- Komplete Kontrol S61 MK1

Should also work with other MK1 models after adjusting:

- key count
- MIDI offset

## How It Works

```text
VST Live
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
Komplete Kontrol MK1
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

Example:

```yaml
banks:

  - bankMSB: 0
    name: Main Set

    songs:

      - program: 1
        name: Song A

        lights:
          C1-C#2: yellow
          D2-C#3: orange
          D3-G3: 1245028
          G#3-A4: 00FF14
          Bb4-C5: 1264FF
          C#5-E5: red

      - program: 2
        name: Song B

        lights:
          C1-B2: blue
          C3-B4: green
          C5: red
```

## Supported Color Formats

### Named Colors

```yaml
C3-C4: red
D4-E4: yellow
F4-G4: blue
```

### Hex Strings

```yaml
C3-C4: FF0000
D4-E4: 00FF00
F4-G4: 0000FF
```

### Integer RGB Values

```yaml
C3-C4: 16711680
```

Equivalent to:

```text
FF0000
```

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
| orange | FF8000 |
| purple | 8000FF |
| pink | FF40A0 |
| lime | 80FF00 |
| teal | 00FF80 |
| sky | 40C0FF |
| violet | C040FF |
| dimred | 400000 |
| dimgreen | 004000 |
| dimblue | 000040 |
| dimwhite | 202020 |

## MIDI Mapping

Song lookup uses:

```python
(bankMSB, program)
```

Example:

```text
CC0 = 0
PC  = 1
```

matches:

```yaml
bankMSB: 0
program: 1
```

## Running

```bash
python komplete_lightguide.py songs.yaml
```

Example output:

```text
Listening on IAC Driver KompleteLightGuide

Bank=0
Program=1

Loading: Song A
```

## Building a Standalone Executable

Install PyInstaller:

```bash
pip install pyinstaller
```

Build:

```bash
pyinstaller \
    --onefile \
    --hidden-import=mido.backends.rtmidi \
    komplete_lightguide.py
```

Executable will be found in:

```text
dist/
```

At this stage, the yaml files will need to be in the same place as the executable.

## Install Standalone Executable

Copy the executable andn the yaml files to ```~/Applications/KompleteLightGuide```.

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

- anykey
- jasonbrent
- OlivierJ
- simonalveteg

This project extends those discoveries with song-based Light Guide control for live performance workflows.

## License

MIT License