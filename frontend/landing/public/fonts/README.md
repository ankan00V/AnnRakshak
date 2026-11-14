# Web fonts, served from this origin

`index.html` used to fetch twelve families from `fonts.googleapis.com`. That
told Google the IP address of every visitor on first paint — a farmer, an
officer, a judge — for files that are Open Font Licence and could always have
been served from here. Now they are.

Noto Sans, Inter and Instrument Serif, under the SIL Open Font
Licence 1.1 (`OFL.txt`). Source: https://fonts.google.com

## What is here, and what is deliberately not

The `@font-face` rules live in `src/fonts.css` (imported from `main.tsx`, so
they ship inside the one hashed stylesheet). They are generated, not written
by hand. Each `@font-face` keeps the
`unicode-range` Google published for it, and that is load-bearing: a farmer
reading Marathi fetches the Devanagari pieces and leaves Tamil, Bengali and
the rest alone. Concatenating everything into one file would be slower on the
weak connection this app is for, not faster.

Two sets of subsets were dropped, because no screen can ever render them:

  Cyrillic, Greek and Vietnamese — no language here uses them.
  Latin on the Noto families — `tailwind.config.js` puts Inter and Instrument
  Serif first in every stack, so Latin never reaches a Noto face. Keeping
  those would have been about 2.5 MB of glyphs no browser would request.

One file per family and script. Inter and every Noto Sans family are variable
fonts: Google's stylesheet names the same file once per weight
(`Inter-400-latin`, `Inter-600-latin`, ... all byte-identical), so each face now
declares a weight range (`font-weight: 300 700`) and points at the single file.
Instrument Serif is static and has one weight.

Noto Serif Devanagari is gone: it drew one word on Home (a Hindi or Marathi
crop name) for 124 KB. Devanagari in the serif stack falls back to Noto Sans
Devanagari, which that farmer has already downloaded.

## Changing the set

Fetch Google's stylesheet with a modern browser User-Agent (an old one gets
TTF and no `unicode-range`), then rewrite each `src:` to a local path, collapse
faces whose files are byte-identical into one weight range, and save the rules
to `src/fonts.css`. The two rules above are the whole of the pruning.
