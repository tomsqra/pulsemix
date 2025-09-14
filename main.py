#!/usr/bin/env python3
from blessed import Terminal
from pulsectl import Pulse
import sys, select
import time

term = Terminal()
step = 0.01       # 1% volume step
poll_interval = 0.5  # seconds


def wrap_text(text, width):
    """Wrap text on word boundaries to fit in 'width'."""
    words = text.split()
    lines = []
    current = ""
    for word in words:
        if len(current) + len(word) + (1 if current else 0) <= width:
            current += (" " if current else "") + word
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines

def hex_to_rgb(hex_color):
    """Convert #RRGGBB to (r,g,b) tuple."""
    hex_color = hex_color.lstrip("#")
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def gradient_color(hex_start, hex_end, fraction):
    """
    fraction: 0.0 (start) → 1.0 (end)
    Returns RGB tuple for this fraction along the gradient
    """
    r1, g1, b1 = hex_to_rgb(hex_start)
    r2, g2, b2 = hex_to_rgb(hex_end)
    r = int(r1 + (r2 - r1) * fraction)
    g = int(g1 + (g2 - g1) * fraction)
    b = int(b1 + (b2 - b1) * fraction)
    return r, g, b


class Mixer:
    def __init__(self):
        self.selected_index = 0
        self.items = []

    # Safe: open Pulse each time
    def get_items(self):
        with Pulse("pulsemix") as pulse:
            sinks = pulse.sink_list()
            inputs = pulse.sink_input_list()
        items = []
        for s in sinks:
            items.append(("sink", s))
        for i in inputs:
            items.append(("input", i))
        return items

    def update_if_changed(self):
        new_items = self.get_items()
        changed = False

        if len(new_items) != len(self.items):
            changed = True
        else:
            for (old_typ, old_obj), (new_typ, new_obj) in zip(self.items, new_items):
                if abs(old_obj.volume.value_flat - new_obj.volume.value_flat) > 0.001:
                    changed = True
                    break

        self.items = new_items
        if changed:
            self.draw()

    def draw_header(self):
        title = "pulsemix"
        return term.bold + title + term.normal + "\n\n"

    def draw_screen_string(self):
        screen = ""
        screen += self.draw_header()

        name_width = 24
        slider_width = 48
        gap = 3
        hex_start = "#ffac8b"  # low volume color
        hex_end = "#f971b7"    # high volume color
        hex_bg = "#f0e2e6"

        for idx, (typ, obj) in enumerate(self.items):
            vol_frac = obj.volume.value_flat
            name = obj.description if typ=="sink" else obj.proplist.get("application.name", "unknown")
            percent = int(vol_frac*100)
            blocks = int(slider_width*vol_frac)
            lines = wrap_text(name, name_width)

            for i, line in enumerate(lines):
                selector = "→" if i==0 and idx==self.selected_index else " "
                slider = ""
                if i==0:
                    for j in range(slider_width):
                        if j < blocks:
                            frac = j / max(slider_width-1,1)
                            r,g,b = gradient_color(hex_start, hex_end, frac)
                        else:
                            # subtle background for empty part
                            r, g, b = hex_to_rgb(hex_bg)
                        slider += term.color_rgb(r,g,b) + "█"
                    slider += term.normal + f"{' '*gap}{percent}%"
                screen += f"{selector} {line.ljust(name_width)}{' '*gap}{slider}\n"

            screen += "\n"  # spacing between items

        screen += term.dim + "Use ↑/↓ select, ←/→ adjust, q quit" + term.normal
        return screen

    def draw(self):
        print(term.home + self.draw_screen_string(), end="")

    # Safe: open Pulse each time
    def adjust_volume(self, delta):
        if not self.items:
            return
        typ, obj = self.items[self.selected_index]
        vol = obj.volume.value_flat + delta
        vol = max(0.0, min(vol, 1.5))
        with Pulse("pulsemix") as pulse:
            pulse.volume_set_all_chans(obj, vol)

    def run(self):
        last_poll = 0
        with term.fullscreen(), term.cbreak(), term.hidden_cursor():
            self.items = self.get_items()
            self.draw()

            while True:
                now = time.time()
                # Poll PulseAudio every poll_interval seconds
                if now - last_poll > poll_interval:
                    self.items = self.get_items()
                    self.selected_index = min(self.selected_index, len(self.items)-1)
                    self.update_if_changed()
                    last_poll = now

                # non-blocking input
                rlist, _, _ = select.select([sys.stdin], [], [], 0.1)
                if rlist:
                    key = term.inkey(timeout=0)
                    if key.name == "KEY_UP":
                        self.selected_index = max(0, self.selected_index - 1)
                        self.draw()
                    elif key.name == "KEY_DOWN":
                        self.selected_index = min(len(self.items)-1, self.selected_index +1)
                        self.draw()
                    elif key.name == "KEY_RIGHT":
                        self.adjust_volume(+step)
                        self.draw()
                    elif key.name == "KEY_LEFT":
                        self.adjust_volume(-step)
                        self.draw()
                    elif hasattr(key, "lower") and key.lower() == "q":
                        break


if __name__ == "__main__":
    Mixer().run()
