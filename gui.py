import os
from pathlib import Path
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

from app_config import (
    KEYBOARDS,
    TITLE,
    VERSION,
    connected_keyboards,
    keyboard_product_id,
    load_app_settings,
    save_app_settings,
    song_colors_yaml,
)
from light_guide import LightGuide
from midi_monitor import MidiMonitor
from status import STATUS_COLORS, Status



class LightGuideGuiApp:
    def __init__(self):
        self.root = tk.Tk()
        self.validation_errors = []
        self.error_window = None
        self.error_log = None
        self.status_details = []
        self.status_details_label = "Show full path"
        self.app_settings = load_app_settings()
        if "editor" not in self.app_settings:
            self.app_settings["editor"] = "default"
            save_app_settings(self.app_settings)

        self._build_widgets()

        self.light_guide = LightGuide(
            song_colors_yaml,
            self.set_status,
            self.set_validation_errors,
            self.set_device_available
        )
        self.set_device_available(self.light_guide.device_available)
        self.refresh_synth_rows()
        self._start_midi_monitor()
        self._schedule_synth_row_refresh()
        self.root.mainloop()

    def _build_widgets(self):
        self.root.minsize(500, 120)
        self.root.geometry("500x120+50+50")
        self.root.title(TITLE + " " + VERSION)

        self.current_patch = tk.Label(self.root, text="No patch")
        self.current_patch.pack()
        self.current_song_label = tk.Label(self.root, text="No song loaded", font=("Helvetica", 16, "bold"))
        self.current_song_label.pack()

        self.reload_frame = tk.Frame(self.root)
        self.reload_frame.pack()

        self.load_button = tk.Button(self.reload_frame, text="Load", command=self.load_song_colors_file)
        self.load_button.pack(side="left", padx=(0, 4))

        self.song_colors_file_label = tk.Label(
            self.reload_frame,
            text=Path(song_colors_yaml).name
        )
        self.song_colors_file_label.pack(side="left", padx=(0, 4))

        self.reload_button = tk.Button(self.reload_frame, text="Reload", command=self.reload_colors)
        self.reload_button.pack(side="left", padx=(0, 4))

        self.edit_button = tk.Button(self.reload_frame, text="Edit", command=self.edit_song_colors_file)
        self.edit_button.pack(side="left")

        self.copyright_label = tk.Label(
            self.root,
            text="© jjrSoft 2026",
            font=("Helvetica", 8),
            fg="#666666"
        )
        self.copyright_label.pack()

        self.synth_rows = tk.Frame(self.root)
        self.synth_rows.pack(fill="x", padx=4, pady=(0, 4))

        self.status_var = tk.StringVar(value="Initializing")
        self.footer = tk.Frame(self.root)
        self.footer.pack(side="bottom", fill="x")

        self.status_label = tk.Label(
            self.footer,
            textvariable=self.status_var,
            anchor="w",
            justify="left",
            #relief="sunken",
            bg=STATUS_COLORS[Status.NONE]
        )

        self.status_label.pack(side="left", fill="x", expand=True)
        self.error_button = tk.Label(
            self.footer,
            text="View Validation Errors",
            font=("Helvetica", 10, "underline"),
            fg="#0645AD",
            bg=STATUS_COLORS[Status.NONE],
            cursor="hand2",
            padx=4,
            pady=2
        )
        self.error_button.bind("<Button-1>", lambda event: self.show_validation_errors())
        self.error_button.pack_forget()
        self.set_status(Status.NONE, "Loading...", None, "")

    def _schedule_synth_row_refresh(self):
        self.refresh_synth_rows()
        self.root.after(1000, self._schedule_synth_row_refresh)

    def refresh_synth_rows(self):
        for row in self.synth_rows.winfo_children():
            row.destroy()
        try:
            devices = connected_keyboards()
        except Exception as ex:
            devices = []

        for device in sorted(
            devices,
            key=lambda item: (
                KEYBOARDS[item["product_id"]]["name"],
                item.get("serial_number") or ""
            )):
            keyboard = KEYBOARDS[device["product_id"]]
            model_name = keyboard["name"].replace("Komplete Kontrol ", "")
            serial_number = device.get("serial_number") or "serial unavailable"
            definition_exists = (
                hasattr(self, "light_guide")
                and self.light_guide.has_definition_for_device(device)
            )
            row = tk.Frame(self.synth_rows, bg=STATUS_COLORS[Status.NONE])
            row.pack(fill="x", pady=1)
            tk.Label(
                row,
                text=f"{model_name} (serial {serial_number})",
                anchor="w",
                background=STATUS_COLORS[Status.NONE],
                padx=8,
                pady=4
            ).pack(side="left", fill="x", expand=True)
            tk.Label(
                row,
                text="OK" if definition_exists else "No keyboard-specific definition",
                background=STATUS_COLORS[
                    Status.OK if definition_exists else Status.WARNING
                ],
                padx=8,
                pady=4
            ).pack(side="right")

        if hasattr(self, "light_guide"):
            for definition in self._disconnected_keyboard_definitions(devices):
                model = definition["model"]
                serial_number = definition.get("serial")
                label = (
                    f"{model} (serial {serial_number})"
                    if serial_number else f"{model} (serial unspecified)"
                )
                row = tk.Frame(self.synth_rows, bg=STATUS_COLORS[Status.NONE])
                row.pack(fill="x", pady=1)
                tk.Label(
                    row,
                    text=label,
                    anchor="w",
                    background=STATUS_COLORS[Status.NONE],
                    padx=8,
                    pady=4
                ).pack(side="left", fill="x", expand=True)
                tk.Label(
                    row,
                    text="Not connected",
                    background=STATUS_COLORS[Status.ERROR],
                    padx=8,
                    pady=4
                ).pack(side="right")

        self.root.update_idletasks()
        self.root.geometry(f"500x{max(120, self.root.winfo_reqheight())}")

    def _disconnected_keyboard_definitions(self, devices):
        if not self.light_guide.configuration_valid:
            return []

        disconnected = []
        seen = set()
        for bank in self.light_guide.song_colors.get("banks", []):
            for song in bank.get("songs") or []:
                for definition in song.get("keyboards", []):
                    product_id = keyboard_product_id(definition.get("model"))
                    serial_number = definition.get("serial")
                    if product_id is None or (product_id, serial_number) in seen:
                        continue
                    seen.add((product_id, serial_number))
                    if any(
                            device["product_id"] == product_id
                            and (serial_number is None
                                 or device.get("serial_number") == serial_number)
                            for device in devices):
                        continue
                    disconnected.append(definition)
        return disconnected

    def _start_midi_monitor(self):
        if self.light_guide.device_available and self.light_guide.configuration_valid:
            self.midi_monitor = MidiMonitor(
                self.light_guide,
                self.set_song,
                self.set_status
            )
            self.midi_thread = threading.Thread(
                target=self.midi_monitor.run,
                daemon=True
            )
            self.midi_thread.start()
        else:
            self.midi_monitor = None

    def set_device_available(self, available):
        self.device_available = available

    def set_status(self, status: Status, message: str, details, link_text):
        self.status_details = [details] if details else []
        self.status_details_label = link_text

        def update():
            self.status_var.set(message)
            self.status_label.config(
                bg=STATUS_COLORS[status]
            )
            self.footer.config(
                bg=STATUS_COLORS[status]
            )
            self.error_button.config(
                bg=STATUS_COLORS[status],
                fg="#0645AD",
                text=self.status_details_label
            )

            if self.status_details and not self.error_button.winfo_manager():
                self.error_button.pack(side="right", padx=4, pady=2)
            elif not self.status_details and not self.validation_errors:
                self.error_button.pack_forget()

            if self.error_log is not None and self.error_log.winfo_exists():
                self.error_log.config(state="normal")
                self.error_log.delete("1.0", "end")
                log_entries = self.status_details + self.validation_errors
                self.error_log.insert("1.0", "\n".join(log_entries))
                self.error_log.config(state="disabled")

        self.root.after(0, update)

    def set_validation_errors(self, errors):
        self.validation_errors = list(errors)
        if self.validation_errors:
            self.status_details = []
            self.error_button.config(text="View Validation Errors")
            if not self.error_button.winfo_manager():
                self.error_button.pack(side="right", padx=4, pady=2)
        elif not self.status_details:
            self.error_button.pack_forget()

        if self.error_log is not None and self.error_log.winfo_exists():
            self.error_log.config(state="normal")
            self.error_log.delete("1.0", "end")
            log_entries = self.status_details + self.validation_errors
            self.error_log.insert("1.0", "\n".join(log_entries))
            self.error_log.config(state="disabled")

    def show_validation_errors(self):
        if self.error_window is not None and self.error_window.winfo_exists():
            self.error_window.deiconify()
            self.error_window.lift()
            return

        self.error_window = tk.Toplevel(self.root)
        self.error_window.title("Errors")
        self.error_window.geometry("640x360")
        self.error_window.protocol("WM_DELETE_WINDOW", self.close_validation_errors)

        log_frame = tk.Frame(self.error_window)
        log_frame.pack(fill="both", expand=True, padx=8, pady=8)

        scrollbar = tk.Scrollbar(log_frame)
        scrollbar.pack(side="right", fill="y")

        self.error_log = tk.Text(log_frame, wrap="word", yscrollcommand=scrollbar.set)
        self.error_log.pack(side="left", fill="both", expand=True)
        scrollbar.config(command=self.error_log.yview)

        log_entries = self.status_details + self.validation_errors
        self.error_log.insert("1.0", "\n".join(log_entries))
        self.error_log.config(state="disabled")

    def close_validation_errors(self):
        if self.error_window is not None:
            self.error_window.destroy()
            self.error_window = None
            self.error_log = None

    def update_labels(self, bank_msb, bank_lsb, pc, title):
        self.current_patch.config(
                text=f"Bank {bank_msb}:{bank_lsb} — PC {pc}"
            )
        self.current_song_label.config(
                text=f"{title}"
            )

    def set_song(self, bank_msb, bank_lsb, pc, title):
        self.root.after(
            0,
            lambda: self.update_labels(bank_msb, bank_lsb, pc, title)
        )

    def load_song_colors_file(self):
        initial_dir = self.app_settings.get("last_song_colors_dir") or str(Path(song_colors_yaml).parent)
        selected_file = filedialog.askopenfilename(
            title="Load Song Colors",
            initialdir=initial_dir,
            filetypes=[("YAML files", "*.yaml *.yml"), ("All files", "*.*")]
        )
        if not selected_file:
            return

        self.light_guide.song_colors_file = selected_file
        self.song_colors_file_label.config(text=Path(selected_file).name)
        self.app_settings["last_song_colors_dir"] = str(Path(selected_file).parent)
        save_app_settings(self.app_settings)
        self.reload_colors()

    def edit_song_colors_file(self):
        song_colors_file = str(self.light_guide.song_colors_file)
        editor = self.app_settings.get("editor")
        try:
            if editor and str(editor).strip().lower() != "default":
                # On macOS the editor may be an application name or .app path.
                command = ["open", "-a", editor, song_colors_file] if sys.platform == "darwin" else [editor, song_colors_file]
                subprocess.Popen(command)
            elif sys.platform == "darwin":
                subprocess.Popen(["open", song_colors_file])
            elif sys.platform == "win32":
                os.startfile(song_colors_file)
            else:
                subprocess.Popen(["xdg-open", song_colors_file])
        except OSError as e:
            messagebox.showerror("Edit", f"Could not open {song_colors_file} for editing:\n{e}")

    def reload_colors(self):
        if not self.light_guide.load_color_table():
            return

        self.light_guide.load_song_colors()
        if not self.light_guide.configuration_valid:
            return

        if self.light_guide.device_available:
            if not self.light_guide.build_song_colors():
                return
        else:
            return

        self.refresh_synth_rows()

        if self.midi_monitor is None and self.light_guide.device_available:
            self.midi_monitor = MidiMonitor(
                self.light_guide,
                self.set_song,
                self.set_status
            )
            self.midi_thread = threading.Thread(
                target=self.midi_monitor.run,
                daemon=True
            )
            self.midi_thread.start()

        # Retry the latest received bank/PC, including one that did not match before.
        last_received = self.midi_monitor.last_received
        if last_received is None:
            return

        bank_msb, bank_lsb, pc = last_received
        matched = self.light_guide.send_colors(bank_msb, bank_lsb, pc)
        if matched or self.midi_monitor.pc is not None:
            self.midi_monitor.pc = pc if matched else None
            self.set_song(bank_msb, bank_lsb, pc,
                          self.light_guide.get_song_title(bank_msb, bank_lsb, pc))
