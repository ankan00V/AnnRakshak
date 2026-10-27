# Fonts bundled with the report

The data report (`app/report.py`) is a PDF, and a PDF carries its own fonts or
it renders nothing. A container has no Indic fonts installed, so these ship
with the app rather than being looked up on the host.

Noto Sans, one family per script, from Google Fonts. Licensed under the SIL
Open Font License 1.1 (`OFL.txt`), which permits redistribution with the
software. Source: https://fonts.google.com/noto

  Devanagari   Marathi and Hindi — also carries the Latin, digits and ₹ used
               by the English report, so it is the primary face
  Bengali, Gujarati, Gurmukhi, Kannada, Malayalam, Tamil, Telugu
               the remaining seven languages the app speaks, registered as
               per-glyph fallbacks

Devanagari ships in two weights because the report sets headings in bold; the
fallbacks are regular only, which is what a fallback is asked for.
