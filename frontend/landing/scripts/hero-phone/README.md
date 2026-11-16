# Phones on the landing page

Every phone on the landing page shows the real app, captured from the running
farmer app at iPhone 15 size (393 × 852 points at 3×) with the status bar and
home indicator where an iPhone puts them. Nothing on a screen is drawn.

| Image | Screen | How it is framed |
|---|---|---|
| `public/photos/hero-phone.webp` | Scan | set into the handset render `phone-render.png` (`compose.py`) |
| `public/photos/phone-scan.webp` | Scan | straight-on phone (`frame.py`) |
| `public/photos/phone-result.webp` | a sample's answer (False smut) | straight-on phone |
| `public/photos/phone-treat.webp` | the same answer, at what to do | straight-on phone |
| `public/photos/phone-result-mr.webp` | the answer in Marathi | straight-on phone |

Re-make them whenever those screens change. Needs Chrome, the repo's `.venv`
(numpy, scipy, Pillow), and the launch configs `backend-isolated` +
`landing-isolated` running.

```bash
npm i --no-save puppeteer-core        # or reuse ../launch-video's node_modules
node capture.mjs                      # -> out/scan.png, result.png, treat.png, result-mr.png
PY=../../../../.venv/bin/python
$PY -I compose.py phone-render.png out/scan.png ../../public/photos/hero-phone.webp
for n in scan result treat result-mr; do $PY -I frame.py out/$n.png ../../public/photos/phone-$n.webp 620; done
```

`compose.py` finds the render's screen, fits its four edges, and warps the
capture onto it; the render's frame, bezel and shadow are kept. `frame.py`
draws the bezel, titanium edge and side buttons around a capture.
