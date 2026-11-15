"""The launch video's soundtrack, written to the video's own grid.

100 BPM, 4/4: a beat is 0.6 s, a bar 2.4 s; the bar count comes from the
timeline. D major, I–V–vi–IV (D, A, Bm, G). Warm pad, sub bass, a soft kick
and shaker, a plucked marimba-like line; a tick on every tap the video makes,
a low impact on the big turns, a breath of air into each new scene, and a
breakdown on the turn to the district office. Everything is on the one grid,
counted from the first sample, and the effects sit under the music.

    python music.py out/timeline.json out/music.wav
"""
import json
import sys
import wave
import numpy as np
from scipy.signal import butter, sosfilt, fftconvolve

SR = 48000
BPM = 100
BEAT = 60 / BPM
BAR = 4 * BEAT
TL = json.load(open(sys.argv[1]))
OUT = sys.argv[2]
BARS = TL['bars']
TURN = TL['turn_bar']
DUR = BARS * BAR
N = int(DUR * SR) + SR  # a second of tail, trimmed at the end

rng = np.random.default_rng(7)
t_all = np.arange(N) / SR


def midi(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def at(sec):
    return int(round(sec * SR))


def env_adsr(n, a, d, s, r, sus_len):
    a, d, r = int(a * SR), int(d * SR), int(r * SR)
    sus = max(0, int(sus_len * SR))
    e = np.concatenate([np.linspace(0, 1, max(a, 1), endpoint=False), np.linspace(1, s, max(d, 1), endpoint=False),
                        np.full(sus, s), np.linspace(s, 0, max(r, 1))])
    return e[:n] if len(e) >= n else np.pad(e, (0, n - len(e)))


def lp(x, f, order=2):
    return sosfilt(butter(order, f, 'low', fs=SR, output='sos'), x)


def hp(x, f, order=2):
    return sosfilt(butter(order, f, 'high', fs=SR, output='sos'), x)


def bp(x, lo, hi, order=2):
    return sosfilt(butter(order, [lo, hi], 'band', fs=SR, output='sos'), x)


def add(bus, sig, start):
    i = at(start)
    if i >= len(bus):
        return
    j = min(len(bus), i + len(sig))
    bus[i:j] += sig[: j - i]


def bars(*ranges):
    s = set()
    for r in ranges:
        a, b = r if isinstance(r, tuple) else (r, r)
        s.update(range(a, b + 1))
    return s


PAD = bars((1, BARS))
BASS = bars((3, TURN - 1), (TURN + 1, BARS - 2))
KICK = bars((5, TURN - 1), (TURN + 1, BARS - 3))
SHAKER = KICK
PLUCK = bars((1, 2), (5, TURN - 1), (TURN + 1, BARS - 1))
CHORDS = [[62, 66, 69, 74], [61, 64, 69, 73], [59, 62, 66, 71], [59, 62, 67, 71]]  # D, A/C#, Bm, G/B
ROOTS = [38, 33, 35, 31]

pad = np.zeros(N); bass = np.zeros(N); drums = np.zeros(N); pluck = np.zeros(N); sfx = np.zeros(N)

for b in range(1, BARS + 1):          # pad: detuned soft saws, low-passed, a swell per bar
    if b not in PAD:
        continue
    ch = CHORDS[(b - 1) % 4]
    n = int(BAR * SR * 1.25)
    t = np.arange(n) / SR
    s = np.zeros(n)
    for note in ch:
        for det in (-0.07, 0.0, 0.07):
            ph = 2 * np.pi * midi(note) * (1 + det / 100) * t + rng.uniform(0, 6.28)
            s += (2 * ((ph / (2 * np.pi)) % 1) - 1) * 0.5 + np.sin(ph) * 0.5
    s = lp(s, 1400 if b in KICK else 900, 2)
    add(pad, s * env_adsr(n, 0.5, 0.6, 0.85, 0.9, BAR * 1.25 - 2.0) * (0.032 if b == TURN else 0.022), (b - 1) * BAR)

for b in range(1, BARS + 1):          # sub bass on 1 and 3, an octave on the and-of-4
    if b not in BASS:
        continue
    r = ROOTS[(b - 1) % 4]
    for beat, note, ln in ((0, r, 1.6), (2, r, 1.2), (3.5, r + 12, 0.45)):
        n = int(ln * SR)
        t = np.arange(n) / SR
        s = np.tanh(np.sin(2 * np.pi * midi(note) * t) * 1.6) * 0.6
        add(bass, lp(s * env_adsr(n, 0.008, 0.25, 0.6, 0.25, ln - 0.6), 380) * 0.16, (b - 1) * BAR + beat * BEAT)


def kick():
    n = int(0.42 * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * np.cumsum(46 + 74 * np.exp(-t * 28)) / SR) * np.exp(-t * 9)
    return (s + hp(rng.standard_normal(n), 2500) * np.exp(-t * 300) * 0.05) * 0.42


def shaker(level):
    n = int(0.09 * SR)
    t = np.arange(n) / SR
    return bp(rng.standard_normal(n), 5000, 11000) * np.exp(-t * 55) * level


K = kick()
for b in range(1, BARS + 1):
    base = (b - 1) * BAR
    if b in KICK:
        for beat in (0, 2):
            add(drums, K, base + beat * BEAT)
    if b in SHAKER:
        for e8 in range(8):
            add(drums, shaker(0.05 if e8 % 2 else 0.03), base + e8 * BEAT / 2)


def pluck_note(note, ln=0.5, vel=1.0):
    n = int(ln * SR)
    t = np.arange(n) / SR
    f = midi(note)
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 4 * t) * np.exp(-t * 40) + 0.15 * np.sin(2 * np.pi * f * 2 * t)
    return s * np.exp(-t * 7.5) * vel


PATTERNS = [[0, None, 2, 1, None, 3, 2, None], [0, 2, None, 3, 1, None, 2, 1]]
for b in range(1, BARS + 1):
    if b not in PLUCK:
        continue
    ch = [n + 12 for n in CHORDS[(b - 1) % 4]]
    pat = PATTERNS[(b - 1) % 2] if b not in bars(1, 2, BARS - 1) else [0, None, None, 2, None, None, 1, None]
    for i, k in enumerate(pat):
        if k is not None:
            add(pluck, pluck_note(ch[k], 0.6, 0.9 if i % 2 == 0 else 0.6) * 0.05, (b - 1) * BAR + i * BEAT / 2)


def tick():
    n = int(0.14 * SR)
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * midi(86) * t) * np.exp(-t * 60) + 0.4 * np.sin(2 * np.pi * midi(93) * t) * np.exp(-t * 90)) * 0.05


def whoosh(ln=0.9):
    n = int(ln * SR)
    t = np.arange(n) / SR
    noise = rng.standard_normal(n)
    sweep = np.zeros(n)
    for k in range(0, n, 2048):
        f = 400 + 5000 * (k / n) ** 1.5
        seg = bp(noise[k:k + 2048], max(200, f * 0.7), min(18000, f * 1.3))
        sweep[k:k + len(seg)] = seg
    return sweep * np.sin(np.pi * np.clip(t / ln, 0, 1)) ** 2 * 0.018


def impact():
    n = int(2.2 * SR)
    t = np.arange(n) / SR
    s = np.sin(2 * np.pi * (38 + 30 * np.exp(-t * 6)) * t) * np.exp(-t * 2.2)
    return (s + lp(rng.standard_normal(n), 900) * np.exp(-t * 4) * 0.25) * 0.32


for tp in TL['taps']:
    add(sfx, tick(), tp)
for c in TL['cuts']:
    add(sfx, whoosh(0.9), c - 0.85)
for h in TL['impacts']:
    add(sfx, impact(), h)


def room(x, secs=1.8, wet=0.18):
    n = int(secs * SR)
    t = np.arange(n) / SR
    ir = lp(rng.standard_normal(n) * np.exp(-t * 3.2), 6000)
    ir /= np.sqrt(np.sum(ir ** 2))
    return x + fftconvolve(x, ir)[: len(x)] * wet


mix = room(pad + pluck, 2.4, 0.35) + bass + drums + room(sfx, 1.4, 0.25)
mix = mix * np.clip(t_all / 0.4, 0, 1) * np.clip((DUR - t_all) / 2.2, 0, 1)
mix = np.tanh(mix[: int(DUR * SR)] * 1.2) / 1.2
st = np.stack([mix, mix], axis=1)
wide = room(pluck, 0.6, 0.2)[: len(mix)] * 0.15
st[:, 0] += wide
st[:, 1] += np.roll(wide, int(0.012 * SR))
st /= max(1e-9, np.max(np.abs(st))) / 0.8
with wave.open(OUT, 'wb') as w:
    w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR)
    w.writeframes((st * 32767).astype('<i2').tobytes())
print('wrote', OUT, f'{DUR:.1f}s')
