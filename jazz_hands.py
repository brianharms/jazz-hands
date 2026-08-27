"""Jazz Hands — every keystroke is a drum hit / a note.

Menu bar app (🥁). Global key listener plays an 808 kit and a lofi
pentatonic EP system-wide.

Modes:
  Pattern       — letters advance a 16-step groove loop.
  Kit           — each key is its own fixed drum.
  Melody        — lofi EP notes, keyboard rows = registers.
  Melody + Beat — notes layered over the groove.

Listening features:
  Typing-speed sensing — rolling average of recent keystroke gaps picks the
    note length (slow = long pads, fast = short quiet plucks drifting
    up-register) and how busy the drums are (ghost notes only when fast).
  Chord gravity — a slow I-vi-IV-V-ish progression advances as you type;
    notes are gently nudged toward the current chord so extended typing
    sounds composed. Enter advances the chord.

Hotkeys: ctrl+alt+d mute/unmute, ctrl+alt+m cycle mode.
Keystrokes with Cmd or Ctrl held are ignored (shortcuts shouldn't drum).
"""
import os
import random
import threading
import time
from collections import deque
from pathlib import Path

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"

import pygame
import rumps
from pynput import keyboard

import synth

APP_DIR = Path(__file__).parent

# 16-step groove for pattern mode: the original 8-step spine on even steps,
# quiet ghost hats interleaved so double-speed typing sounds like the same beat
PATTERN = [
    "kick", "ghost", "chat", "ghost", "snare", "ghost", "chat", "ghost",
    "kick", "ghost", "kick", "ghost", "snare", "ghost", "ohat", "ghost",
]

# kit mode: per-key mapping (home row = core kit, spread outward)
KEYMAP = {
    "a": "kick", "s": "snare", "d": "chat", "f": "ohat", "g": "tom",
    "h": "tom", "j": "clap", "k": "rim", "l": "cowbell",
    "q": "kick", "w": "chat", "e": "snare", "r": "chat", "t": "kick",
    "y": "tom", "u": "clap", "i": "chat", "o": "cowbell", "p": "crash",
    "z": "kick", "x": "chat", "c": "snare", "v": "chat", "b": "kick",
    "n": "clap", "m": "rim",
    "1": "kick", "2": "snare", "3": "chat", "4": "ohat", "5": "clap",
    "6": "rim", "7": "cowbell", "8": "tom", "9": "crash", "0": "kick",
}

VOLUMES = {"Low": 0.35, "Medium": 0.7, "High": 1.0}

MODES = ["Pattern", "Kit", "Melody", "Melody + Beat"]

# melody: keyboard rows = registers (bottom row low, top row high),
# left-to-right ascends the pentatonic scale. All in-scale, all consonant.
MELODY_KEYMAP = {}
for _row, _base in (("zxcvbnm,./", 0), ("asdfghjkl;'", 5), ("qwertyuiop", 10),
                    ("1234567890", 12)):
    for _col, _ch in enumerate(_row):
        MELODY_KEYMAP[_ch] = min(_base + _col, 19)

# chord gravity: chords as sets of pentatonic degree classes (0-4).
# first element = chord root. A lofi I-vi-ii-V-ish cycle; every chord is a
# subset of the scale, so gravity can only make things MORE consonant.
CHORDS = [(0, 2, 3), (4, 0, 2), (1, 3, 0), (3, 0, 1)]
CHORD_ADVANCE_EVERY = 16  # melodic keystrokes per chord

# typing-speed bands (keys/sec)
SLOW_BELOW = 2.5
FAST_ABOVE = 5.5

# feel: Auto follows typing speed; the rest force one response style
FEELS = {
    "Auto": None,
    "Ambient (pads)": "slow",
    "Standard": "medium",
    "Sparkle (plucks)": "fast",
}


class Sounds:
    def __init__(self):
        pygame.mixer.pre_init(synth.SR, -16, 2, 256)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(48)
        synth.ensure_samples()
        self.sounds = {
            name: pygame.mixer.Sound(str(synth.SAMPLES_DIR / f"{name}.wav"))
            for name in synth.KIT
        }
        # ghost = a much quieter closed hat, used for off-beat filler steps
        self.sounds["ghost"] = pygame.mixer.Sound(str(synth.SAMPLES_DIR / "chat.wav"))
        self.notes = {}
        self.load_melody()
        self.volume = VOLUMES["Medium"]
        self.set_volume(self.volume)

    def load_melody(self):
        notes = {
            v: [
                pygame.mixer.Sound(str(synth.SAMPLES_DIR / f"note_{i:02d}_{v}.wav"))
                for i in range(synth.N_NOTES)
            ]
            for v in synth.VARIANTS
        }
        notes["bass"] = pygame.mixer.Sound(str(synth.SAMPLES_DIR / "bass.wav"))
        self.notes = notes  # atomic swap so key changes are glitch-free
        if getattr(self, "volume", None):
            self.set_volume(self.volume)

    def set_volume(self, vol):
        self.volume = vol
        for name, s in self.sounds.items():
            s.set_volume(vol * 0.3 if name == "ghost" else vol)
        for v, group in self.notes.items():
            if v == "bass":
                group.set_volume(vol * 0.9)
            else:
                for s in group:
                    s.set_volume(vol)

    def play(self, name, scale=None):
        snd = self.sounds.get(name)
        if snd:
            ch = snd.play()
            if ch and scale is not None:
                ch.set_volume(scale)

    def play_note(self, idx, variant="m", scale=None):
        group = self.notes.get(variant)
        if not group or not 0 <= idx < len(group):
            return
        ch = group[idx].play()
        if ch:
            ch.set_volume(scale if scale is not None else random.uniform(0.7, 1.0))

    def play_bass(self):
        snd = self.notes.get("bass")
        if snd:
            snd.play()


class JazzHands(rumps.App):
    def __init__(self):
        super().__init__("🥁", quit_button=rumps.MenuItem("Quit Jazz Hands"))
        self.sounds = Sounds()
        self.enabled = True
        self.mode = "Pattern"
        self.step = 0
        self.mods = set()

        # typing-speed sensing
        self.times = deque(maxlen=12)
        self.rate = 0.0  # keys/sec, rolling

        # feel override (None = Auto)
        self.feel = "Auto"
        self.last_idx = None   # previous melodic note, for contour smoothing
        self.last_full = 0.0   # time of last full-volume calm note

        # chord gravity
        self.gravity = True
        self.chord_i = 0
        self.note_count = 0

        # key/scale
        self.key_name = "C"
        self.scale_name = "Bright (major pent)"
        self.regenerating = False

        self.item_enabled = rumps.MenuItem("Enabled", callback=self.toggle_enabled)
        self.item_enabled.state = 1
        self.item_speed = rumps.MenuItem("Typing: —")
        self.item_speed.set_callback(None)
        self.mode_items = {
            m: rumps.MenuItem(m, callback=self.pick_mode) for m in MODES
        }
        self.mode_items["Pattern"].state = 1
        self.key_items = {
            k: rumps.MenuItem(k, callback=self.pick_key) for k in synth.KEYS
        }
        self.key_items["C"].state = 1
        self.scale_items = {
            s: rumps.MenuItem(s, callback=self.pick_scale) for s in synth.SCALES
        }
        self.scale_items[self.scale_name].state = 1
        self.feel_items = {
            f: rumps.MenuItem(f, callback=self.pick_feel) for f in FEELS
        }
        self.feel_items["Auto"].state = 1
        self.item_gravity = rumps.MenuItem("Chord Gravity", callback=self.toggle_gravity)
        self.item_gravity.state = 1
        self.vol_items = {
            v: rumps.MenuItem(v, callback=self.pick_volume) for v in VOLUMES
        }
        self.vol_items["Medium"].state = 1
        self.menu = [
            self.item_enabled,
            self.item_speed,
            None,
            ["Mode", list(self.mode_items.values())],
            ["Key", list(self.key_items.values())],
            ["Scale", list(self.scale_items.values())],
            ["Feel", list(self.feel_items.values())],
            self.item_gravity,
            ["Volume", list(self.vol_items.values())],
            None,
        ]

        # speed readout updated on the main thread (rumps.Timer), never from
        # the pynput thread — AppKit UI is main-thread-only
        self.speed_timer = rumps.Timer(self.update_speed_item, 1)
        self.speed_timer.start()

        self.listener = keyboard.Listener(
            on_press=self.on_press, on_release=self.on_release
        )
        self.listener.start()

    # ---- menu callbacks ----
    def toggle_enabled(self, sender):
        self.enabled = not self.enabled
        sender.state = 1 if self.enabled else 0
        self.title = "🥁" if self.enabled else "🔇"

    def pick_mode(self, sender):
        self.mode = sender.title
        for name, item in self.mode_items.items():
            item.state = 1 if name == self.mode else 0
        self.step = 0

    def pick_key(self, sender):
        self.key_name = sender.title
        for name, item in self.key_items.items():
            item.state = 1 if name == self.key_name else 0
        self.regen_melody()

    def pick_scale(self, sender):
        self.scale_name = sender.title
        for name, item in self.scale_items.items():
            item.state = 1 if name == self.scale_name else 0
        self.regen_melody()

    def pick_feel(self, sender):
        self.feel = sender.title
        for name, item in self.feel_items.items():
            item.state = 1 if name == self.feel else 0

    def toggle_gravity(self, sender):
        self.gravity = not self.gravity
        sender.state = 1 if self.gravity else 0

    def pick_volume(self, sender):
        self.sounds.set_volume(VOLUMES[sender.title])
        for name, item in self.vol_items.items():
            item.state = 1 if name == sender.title else 0

    def regen_melody(self):
        if self.regenerating:
            return
        self.regenerating = True
        self.title = "⏳"

        def work():
            synth.generate_melody(
                synth.KEYS[self.key_name], synth.SCALES[self.scale_name]
            )
            self.sounds.load_melody()
            self.regenerating = False
            self.title = "🥁" if self.enabled else "🔇"

        threading.Thread(target=work, daemon=True).start()

    def update_speed_item(self, _timer):
        now = time.monotonic()
        if not self.times or now - self.times[-1] > 2.0:
            self.rate = 0.0
            self.item_speed.title = "Typing: —"
        else:
            band = self.band()
            tag = f"{band} (forced)" if FEELS.get(self.feel) else band
            self.item_speed.title = f"Typing: {self.rate:.1f} keys/s · {tag}"

    # ---- speed sensing ----
    def sense(self):
        """Record a keystroke timestamp and update the rolling rate."""
        now = time.monotonic()
        if self.times and now - self.times[-1] > 2.0:
            self.times.clear()  # a pause resets the window
        self.times.append(now)
        if len(self.times) >= 4:
            span = self.times[-1] - self.times[0]
            self.rate = (len(self.times) - 1) / span if span > 0 else 0.0
        else:
            self.rate = 0.0

    def band(self):
        forced = FEELS.get(self.feel)
        if forced:
            return forced
        if self.rate <= 0:
            return "idle"
        if self.rate < SLOW_BELOW:
            return "slow"
        if self.rate < FAST_ABOVE:
            return "medium"
        return "fast"

    # ---- chord gravity ----
    def gravitate(self, idx):
        if not self.gravity:
            return idx
        chord = CHORDS[self.chord_i]
        if idx % 5 in chord:
            return idx
        if random.random() < 0.6:
            for d in (1, -1, 2, -2):
                j = idx + d
                if 0 <= j < synth.N_NOTES and j % 5 in chord:
                    return j
        return idx

    def advance_chord(self):
        self.chord_i = (self.chord_i + 1) % len(CHORDS)
        self.note_count = 0

    def chord_tone_idxs(self, octave=1):
        """The current chord's note indexes in a given octave (0-3)."""
        base = octave * 5
        return [base + c for c in CHORDS[self.chord_i]]

    # ---- key handling (pynput thread) ----
    MOD_KEYS = {
        keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r,
        keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
        keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r,
    }

    def on_release(self, key):
        self.mods.discard(key)

    def on_press(self, key):
        if key in self.MOD_KEYS:
            self.mods.add(key)
            return

        ctrl = any(k in self.mods for k in (
            keyboard.Key.ctrl, keyboard.Key.ctrl_l, keyboard.Key.ctrl_r))
        alt = any(k in self.mods for k in (
            keyboard.Key.alt, keyboard.Key.alt_l, keyboard.Key.alt_r))
        cmd = any(k in self.mods for k in (
            keyboard.Key.cmd, keyboard.Key.cmd_l, keyboard.Key.cmd_r))

        # hotkeys
        if ctrl and alt:
            char = getattr(key, "char", None) or getattr(key, "vk", None)
            if char in ("d", "\x04") or getattr(key, "vk", None) == 2:
                self._hotkey_toggle()
                return
            if char in ("m", "\r") or getattr(key, "vk", None) == 46:
                self._hotkey_mode()
                return

        if not self.enabled or cmd or ctrl:
            return

        melodic = self.mode in ("Melody", "Melody + Beat")
        drums = self.mode in ("Pattern", "Kit", "Melody + Beat")

        # accent keys
        if key == keyboard.Key.space:
            if melodic:
                self.sounds.play_bass()
                # low chord-root note under the sub for harmonic movement
                self.sounds.play_note(CHORDS[self.chord_i][0], "l", scale=0.8)
            if drums:
                self.sounds.play("ohat")
            return
        if key == keyboard.Key.enter:
            if melodic:
                self.advance_chord()
                for idx in self.chord_tone_idxs(octave=1):
                    self.sounds.play_note(idx, "l", scale=0.85)
            if drums:
                self.sounds.play("crash")
                self.sounds.play("kick")
            self.step = 0
            return
        if key == keyboard.Key.backspace:
            if melodic:
                self.sounds.play_bass()
            else:
                self.sounds.play("rim")
            return
        if key in (keyboard.Key.shift, keyboard.Key.shift_l, keyboard.Key.shift_r,
                   keyboard.Key.caps_lock, keyboard.Key.tab, keyboard.Key.esc):
            return

        char = getattr(key, "char", None)
        self.sense()
        band = self.band()

        if melodic:
            idx = MELODY_KEYMAP.get((char or "").lower())
            idx = self.gravitate(idx if idx is not None else 7)

            if band == "slow" or band == "idle":
                variant = "l"
                # contour smoothing: step at most 2 scale-steps from the
                # previous note, so fast bursts become smooth lines
                if self.last_idx is not None and abs(idx - self.last_idx) > 2:
                    idx = self.last_idx + (2 if idx > self.last_idx else -2)
                    idx = max(0, min(idx, synth.N_NOTES - 1))
                # felt-tempo cap: full notes bloom at most ~every 300ms;
                # keystrokes in between still sound as soft grace notes,
                # so fast typing stays calm but perfectly 1:1 timed
                now = time.monotonic()
                if now - self.last_full < 0.30:
                    vol = random.uniform(0.22, 0.38)
                else:
                    vol = random.uniform(0.75, 1.0)
                    self.last_full = now
                    # occasionally add a second chord tone below — a soft dyad
                    if random.random() < 0.25:
                        lower = [i for i in self.chord_tone_idxs(max(idx // 5 - 1, 0))
                                 if i < idx]
                        if lower:
                            self.sounds.play_note(lower[-1], "l", scale=0.5)
            elif band == "medium":
                variant, vol = "m", random.uniform(0.7, 1.0)
            else:  # fast: shorter, quieter, drifting up-register
                variant = "p"
                vol = max(0.45, 0.9 - (self.rate - FAST_ABOVE) * 0.06)
                if self.rate > 7 and random.random() < 0.5:
                    idx = min(idx + 5, synth.N_NOTES - 1)
            self.sounds.play_note(idx, variant, scale=vol)
            self.last_idx = idx

            self.note_count += 1
            if self.note_count >= CHORD_ADVANCE_EVERY:
                self.advance_chord()

        if self.mode in ("Pattern", "Melody + Beat"):
            entry = PATTERN[self.step % len(PATTERN)]
            # slow typing = spine only; ghosts fill in as you speed up
            if not (entry == "ghost" and band in ("slow", "idle")):
                self.sounds.play(entry)
            self.step += 1
        elif self.mode == "Kit":
            name = KEYMAP.get((char or "").lower())
            self.sounds.play(name or "chat")

    def _hotkey_toggle(self):
        self.enabled = not self.enabled
        self.item_enabled.state = 1 if self.enabled else 0
        self.title = "🥁" if self.enabled else "🔇"

    def _hotkey_mode(self):
        self.mode = MODES[(MODES.index(self.mode) + 1) % len(MODES)]
        for name, item in self.mode_items.items():
            item.state = 1 if name == self.mode else 0
        self.step = 0


def kill_other_instances():
    """Single-instance takeover: any older Jazz Hands process is terminated."""
    import subprocess
    me = os.getpid()
    out = subprocess.run(["pgrep", "-f", "jazz_hands.py"], capture_output=True, text=True)
    for line in out.stdout.split():
        pid = int(line)
        if pid != me:
            try:
                os.kill(pid, 9)
            except ProcessLookupError:
                pass


if __name__ == "__main__":
    kill_other_instances()
    JazzHands().run()
