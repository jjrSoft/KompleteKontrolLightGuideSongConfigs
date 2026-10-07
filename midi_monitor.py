import sys
import time

import mido

from status import Status



class MidiMonitor:
    port_name = "IAC Driver KompleteKontrolLightGuide"
    bank_msb = None
    bank_lsb = None
    pc = None
    last_received = None

    def __init__(self, light_guide, set_song_callback, set_status):
        self.light_guide = light_guide
        self.set_song_callback = set_song_callback
        self.set_status = set_status
        self.available = True
    def handle_message(self, msg):
        if msg.type == "control_change":
            if msg.control == 0:
                self.bank_msb = msg.value
            elif msg.control == 32:
                self.bank_lsb = msg.value
        elif msg.type == "program_change":
            self.last_received = (self.bank_msb, self.bank_lsb, msg.program)
            if not self.light_guide.send_colors(self.bank_msb, self.bank_lsb, msg.program):
                return

            self.pc = msg.program
            self.set_song_callback(self.bank_msb, self.bank_lsb, msg.program,
                                   self.light_guide.get_song_title(self.bank_msb, self.bank_lsb, msg.program))

    def get_current_data(self):
        if self.bank_msb is None or self.bank_lsb is None or self.pc is None:
            return (None, None, None, "No song loaded")
        return (self.bank_msb, self.bank_lsb, self.pc,
                self.light_guide.get_song_title(self.bank_msb, self.bank_lsb, self.pc))

    def run(self):
        try:
            with mido.open_input(self.port_name) as port:
                while True:
                    msg = port.poll()
                    if msg is not None:
                        self.handle_message(msg)
                    time.sleep(0.01)
        except KeyboardInterrupt:
            sys.exit(0)
        except Exception as ex:
            self.available = False
            self.set_status(Status.ERROR, f"Cannot open MIDI input: {ex}", None, "")
