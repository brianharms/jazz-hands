# Jazz Hands 🥁

**Every keystroke you type becomes music — system-wide, in any app.**

Jazz Hands is a tiny macOS menu bar app that turns your keyboard into an
instrument. Type an email and hear a lofi beat. Write code and play soft
pentatonic keys. It listens to *how* you type — speed, pauses, bursts — and
shapes the music to match, while staying perfectly 1:1 with your fingers.

Everything is synthesized locally at first launch (an 808-style drum kit and
a warm electric-piano voice). No sample packs, no network, no accounts.

## Modes

| Mode | What typing does |
|---|---|
| **Pattern** | Each keystroke advances a 16-step drum groove — steady typing builds a beat |
| **Kit** | Every key is its own drum (home row = core kit; there is a cowbell) |
| **Melody** | Keys play a pentatonic electric piano — keyboard rows are registers, so words become melodies |
| **Melody + Beat** | Both at once: you are the drummer and the keys player |

In every mode: **space** = open hat / sub bass, **enter** = crash or chord
resolution, **backspace** = rimshot. Keystrokes with ⌘ or ⌃ held are silent,
so shortcuts never drum.

## The instrument listens

- **Typing-speed sensing** — a rolling average of your recent keystroke gaps
  drives the sound: slow thoughtful typing gets long ambient pads, fast
  bursts get short quiet plucks that drift up-register into sparkle.
- **Chord gravity** — a slow lofi chord progression advances as you type, and
  each note is gently nudged toward the current chord, so extended typing
  sounds composed instead of random. Hitting enter resolves the harmony.
- **Felt tempo** — in the calm feel, fast typing stays calm: full notes bloom
  at a relaxed pulse while in-between keystrokes land as soft grace notes,
  and the melody moves in smooth steps instead of leaps.
- **Can't-sound-bad guarantee** — all melody notes come from a pentatonic
  scale, which contains no dissonant intervals. Mash freely.

## Menu controls

- **Typing** — live readout of your current speed
- **Mode** — the four modes above
- **Key** (C/D/F/G/A) and **Scale** (Bright major / Moody minor pentatonic) —
  the instrument regenerates in ~¼ second
- **Feel** — Auto (follows your speed) or force Ambient / Standard / Sparkle
- **Chord Gravity** — toggle the harmony-nudging
- **Volume** — Low / Medium / High

Hotkeys: `ctrl+alt+d` mute/unmute · `ctrl+alt+m` cycle modes.

## Install & run

Requires macOS and Python 3.12.

```bash
git clone https://github.com/brianharms/jazz-hands.git
cd jazz-hands
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python jazz_hands.py
```

A 🥁 appears in your menu bar. The first launch synthesizes the full
instrument into `samples/` (about a second). macOS will ask for **Input
Monitoring** permission for your terminal — that's the global key listener;
grant it and relaunch if needed.

Launching Jazz Hands again replaces any running copy, so "restart" is just
running it again. Quit from the menu.

## Make it yours

- Drop your own WAVs into `samples/` (same filenames) to replace any drum.
- The groove lives in `PATTERN` in `jazz_hands.py`; the per-key drum map in
  `KEYMAP`; the chord cycle in `CHORDS`.
- All synthesis knobs (tails, attacks, scales, keys) are at the top of
  `synth.py`.

## License

MIT
