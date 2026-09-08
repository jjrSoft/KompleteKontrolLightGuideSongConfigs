# VST Live
#     └─ Program Change
#            ↓
#       IAC: LightGuide [create port manually in Audio MIDI Setup]
#            ↓
#     Python daemon
#            ↓
#       HID packets
#            ↓
#    Komplete Kontrol MK1

import mido

print("INPUTS")
for p in mido.get_input_names():
    print(" ", p)

print("\nOUTPUTS")
for p in mido.get_output_names():
    print(" ", p)

PORT_NAME = "IAC Driver KompleteLightGuide"

with mido.open_input(PORT_NAME) as port:
    print(f"Listening on {PORT_NAME}")

    for msg in port:

        if msg.type == "program_change":
            print(f"Program Change {msg.program}")

            # load preset
            # update lightguide
