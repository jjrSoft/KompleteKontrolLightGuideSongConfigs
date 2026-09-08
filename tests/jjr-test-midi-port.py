#!/usr/bin/env python3

import mido

print(mido.backend)
print("INPUTS:")
for p in mido.get_input_names():
    print(" ", p)

print("\nOUTPUTS:")
for p in mido.get_output_names():
    print(" ", p)

PORT_NAME = "LightGuide Control"

with mido.open_input(PORT_NAME, virtual=True) as port:
    print(f"Listening on '{PORT_NAME}'")

    print("INPUTS after open:")
    for p in mido.get_input_names():
        print(" ", p)

    print("\nOUTPUTS after open:")
    for p in mido.get_output_names():
        print(" ", p)

    print("Send Program Changes from VST Live...\n")

    for msg in port:
        print(msg)

        if msg.type == "program_change":
            print(f"Song preset = {msg.program}")