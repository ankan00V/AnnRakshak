# Launch video

A 1 min 53 s product film of AnnRakshak, rendered from the real app: every
screen is a capture of the running farmer app or officer dashboard, on a phone
and a laptop drawn in `index.html`. Nothing on a screen is mocked. The output is
`out/annrakshak-launch.mp4` (1920 × 1080, 30 fps, −16 LUFS) with its own
soundtrack written to the cut. The storyboard is in [`plan.md`](plan.md).

Made the [/brag](https://github.com/latent-spaces/brag) way: the story planned
first, the soundtrack and the picture on one beat grid (100 BPM, every cut on a
bar), every frame a pure function of time, stills checked before the full render.

## Re-render

Needs Chrome, ffmpeg, Node 22+, the repo's `.venv` (numpy, scipy, Pillow), and
the app's demo servers from `.claude/launch.json`:
`backend-isolated` + `landing-isolated` (an isolated database, SMS in outbox
mode: the flows that write — a scan, a live call, an upload — run there),
`backend` + `landing-main` (the development database's demo district, read
only), and `web-built` (the production build, for the offline shot).

```bash
npm i --no-save puppeteer-core     # drives the Chrome already installed
./make_clip.sh                     # a camera clip of ICAR photos for the live call
PHOTO=$PWD/out/clip/upload.jpg node capture.mjs   # every screen -> out/shots
../../../../.venv/bin/python prepare.py           # display-sized shots + out/timeline.json
../../../../.venv/bin/python music.py out/timeline.json out/music.wav
node render.mjs stills 3.9 26.4 50.0              # look before rendering
./run.sh                                          # -> out/annrakshak-launch.mp4
```

`capture.mjs` takes `STEP=iso,call,main,officer,offline` to re-take only part.
Change the cut in `prepare.py` (scenes and taps) and `index.html` (what each
scene shows); the music follows the timeline on its own.

## What is real and what is staged

- Every screen is the app as it renders, with the demo data. The live call ran
  for real against the backend, with a 20-second clip of ICAR test photographs
  standing in for the phone's camera. The offline screens were taken from the
  production build with the network switched off.
- The isolated database's demo farmer is given a fictional phone number so the
  SMS panel can be shown.
- Not shown: satellite greenness. The demo data has no satellite reading for the
  field, and the film does not invent one.
