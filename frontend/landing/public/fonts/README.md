# Web fonts, served from this origin

`index.html` used to fetch twelve families from `fonts.googleapis.com`. That
told Google the IP address of every visitor on first paint — a farmer, an
officer, a judge — for files that are Open Font Licence and could always have
been served from here. Now they are.

Noto Sans and Noto Serif, Inter and Instrument Serif, under the SIL Open Font
Licence 1.1 (`OFL.txt`). Source: https://fonts.google.com

## What is here, and what is deliberately not

`fonts.css` is generated, not written by hand. Each `@font-face` keeps the
`unicode-range` Google published for it, and that is load-bearing: a farmer
reading Marathi fetches the Devanagari pieces and leaves Tamil, Bengali and
the rest alone. Concatenating everything into one file would be slower on the
weak connection this app is for, not faster.

Two sets of subsets were dropped, because no screen can ever render them:

  Cyrillic, Greek and Vietnamese — no language here uses them.
  Latin on the Noto families — `tailwind.config.js` puts Inter and Instrument
  Serif first in every stack, so Latin never reaches a Noto face. Keeping
  those would have been about 2.5 MB of glyphs no browser would request.

## Changing the set

Fetch Google's stylesheet with a modern browser User-Agent (an old one gets
TTF and no `unicode-range`), then rewrite each `src:` to a local path and save
the file beside this note. The two rules above are the whole of the pruning.
