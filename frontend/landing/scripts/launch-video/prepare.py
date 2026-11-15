"""Display-sized copies of the captures, and the timeline the video and the
music share.

Phone captures are drawn about 430 px wide and laptop captures about 1,200 px,
so out/shotsv keeps them at 900 and 2,400 px: sharp, and light enough that the
renderer's page does not run out of memory over three thousand frames.

The timeline: 100 BPM, a bar is 2.4 s, every scene a whole number of bars,
every tap on the beat grid. Edit SCENES or the tap offsets here; the video
(index.html) and the music (music.py) both read out/timeline.json.
"""
import json
import os
from pathlib import Path
from PIL import Image

HERE = Path(__file__).parent
SHOTS, OUT = HERE / 'out/shots', HERE / 'out/shotsv'
OUT.mkdir(parents=True, exist_ok=True)

for f in SHOTS.glob('*.png'):
    n = f.stem
    im = Image.open(f)
    if n.startswith('p_chrome'):            # transparent bar + Krishi
        im = im.convert('RGBA')
        im.resize((900, round(im.height * 900 / im.width)), Image.LANCZOS).save(OUT / f'{n}.png')
        continue
    w = 900 if n.startswith('p_') else 2400
    im = im.convert('RGB')
    im.resize((w, round(im.height * w / im.width)), Image.LANCZOS).save(OUT / f'{n}.jpg', quality=93)

meta = json.loads((SHOTS / 'meta.json').read_text())
# "What to do" on Weather: the page title also says "what to do", and a
# capture that matched it reads 0. The section sits at 607 px on this screen.
if not meta.get('weather_todo') or meta['weather_todo'] < 100:
    meta['weather_todo'] = 607
(OUT / 'meta.json').write_text(json.dumps(meta, indent=1))

BAR = 2.4
SCENES = [('hook', 2), ('reveal', 2), ('scan', 4), ('upload', 2), ('unsure', 2), ('treat', 2), ('lang', 2),
          ('krishi', 2), ('call', 3), ('lcall', 2), ('weather', 2), ('alerts', 2), ('followup', 2), ('spray', 2),
          ('offline', 2), ('turn', 1), ('office', 3), ('decide', 1), ('map', 2), ('plan', 2), ('staff', 2),
          ('both', 1), ('logo', 2)]
t, scenes = 0.0, []
for name, bars in SCENES:
    scenes.append({'id': name, 'a': round(t, 3), 'b': round(t + bars * BAR, 3)})
    t += bars * BAR
S = {s['id']: s['a'] for s in scenes}
tap = {'hook': 0.9, 'scanNav': S['scan'] + 1.2, 'sample': S['scan'] + 3.0, 'check': S['scan'] + 4.5,
       'lcheck': S['upload'] + 1.8, 'lang': S['lang'] + 0.6, 'mr': S['lang'] + 1.8, 'krishi': S['krishi'] + 1.2,
       'start': S['call'] + 0.9, 'lvideo': S['lcall'] + 0.9, 'spray': S['spray'] + 1.5, 'review': S['office'] + 3.6}
tap = {k: round(v, 2) for k, v in tap.items()}
timeline = {
    'bpm': 100, 'bars': sum(b for _, b in SCENES), 'dur': round(t, 3), 'scenes': scenes,
    'tap': tap, 'taps': sorted(tap.values()), 'cuts': [s['a'] for s in scenes[1:]],
    'impacts': [S['reveal'], S['turn'], S['office']], 'turn_bar': int(round(S['turn'] / BAR)) + 1,
}
(HERE / 'out/timeline.json').write_text(json.dumps(timeline, indent=1))
print(f"{len(os.listdir(OUT))} shots, {timeline['bars']} bars, {timeline['dur']} s")
