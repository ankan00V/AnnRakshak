"""The farmer's own record, as a document they can read.

The Act calls it the right to access. A farmer calls it wanting to see what an
app knows about them — and what they get back has to be readable by the person
who asked, not by a parser. This renders `erasure.export_account` as a PDF in
the farmer's own language, with the app's stamp on it, so it can be kept,
printed, or handed to somebody at a Krishi Vigyan Kendra.

Two things make that harder than it sounds, and both are handled here.

**Script.** Marathi and Hindi need Devanagari, and the other seven languages
need their own scripts. A PDF carries its own fonts or it renders nothing, and
a container has no Indic fonts installed, so Noto Sans ships with the app
(`assets/fonts`). Devanagari is the primary face — it also carries the Latin,
digits and ₹ the English report uses — and the rest are registered as
per-glyph fallbacks.

**Shaping.** Devanagari is not written in the order it is typed: the ि in
शिवार is stored after the श and drawn before it, and क + ् + ष becomes the
single conjunct क्ष. Without shaping the text comes out as detached pieces,
which is worse than English because it looks like a bug in the farmer's own
language. `set_text_shaping` turns HarfBuzz on for every line here.
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from fpdf import FPDF
from fpdf.enums import Align, XPos, YPos

from app.kb import tr

ASSETS = Path(__file__).parent / "assets"
FONTS = ASSETS / "fonts"
EMBLEM = ASSETS / "emblem-512.png"

PRIMARY = "noto"
"""Devanagari + Latin: hi, mr and en all render from this one face."""

FALLBACKS = {
    "bn": "NotoSansBengali-Regular.ttf",
    "gu": "NotoSansGujarati-Regular.ttf",
    "pa": "NotoSansGurmukhi-Regular.ttf",
    "kn": "NotoSansKannada-Regular.ttf",
    "ml": "NotoSansMalayalam-Regular.ttf",
    "ta": "NotoSansTamil-Regular.ttf",
    "te": "NotoSansTelugu-Regular.ttf",
}

INK = (31, 41, 36)
MUTED = (110, 120, 114)
LEAF = (47, 93, 63)
RULE = (214, 220, 214)

# Every word the report says, authored in the three languages this project
# writes by hand. tr() takes the other seven from the reviewed translation
# memory and falls back to English rather than to another language's text.
L = {
    "title": {"en": "Your data", "hi": "आपका डेटा", "mr": "तुमची माहिती"},
    "subtitle": {"en": "Everything AnnRakshak holds about you",
                 "hi": "AnnRakshak आपके बारे में जो कुछ रखता है",
                 "mr": "AnnRakshak तुमच्याबद्दल जे काही ठेवते"},
    "prepared_for": {"en": "Prepared for", "hi": "किसके लिए", "mr": "कोणासाठी"},
    "prepared_on": {"en": "Prepared on", "hi": "कब बनाया", "mr": "कधी तयार केले"},
    "account": {"en": "Your account", "hi": "आपका खाता", "mr": "तुमचे खाते"},
    "name": {"en": "Name", "hi": "नाम", "mr": "नाव"},
    "phone": {"en": "Mobile", "hi": "मोबाइल", "mr": "मोबाइल"},
    "email": {"en": "Email", "hi": "ईमेल", "mr": "ईमेल"},
    "language": {"en": "Language", "hi": "भाषा", "mr": "भाषा"},
    "joined": {"en": "Joined", "hi": "कब जुड़े", "mr": "कधी जोडले"},
    "place": {"en": "Your place", "hi": "आपकी जगह", "mr": "तुमचे ठिकाण"},
    "district": {"en": "District", "hi": "ज़िला", "mr": "जिल्हा"},
    "taluka": {"en": "Taluka", "hi": "तालुका", "mr": "तालुका"},
    "village": {"en": "Village", "hi": "गाँव", "mr": "गाव"},
    "land": {"en": "Total land", "hi": "कुल ज़मीन", "mr": "एकूण जमीन"},
    "consent": {"en": "You agreed on", "hi": "आपने सहमति दी", "mr": "तुम्ही संमती दिली"},
    "farms": {"en": "Your fields", "hi": "आपके खेत", "mr": "तुमची शेते"},
    "crop": {"en": "Crop", "hi": "फसल", "mr": "पीक"},
    "problem": {"en": "Problem", "hi": "समस्या", "mr": "समस्या"},
    "variety": {"en": "Variety", "hi": "किस्म", "mr": "वाण"},
    "area": {"en": "Area", "hi": "क्षेत्र", "mr": "क्षेत्र"},
    "sown": {"en": "Sown", "hi": "बुवाई", "mr": "पेरणी"},
    "where": {"en": "Where", "hi": "कहाँ", "mr": "कुठे"},
    "problems": {"en": "Problems you reported", "hi": "आपने बताई समस्याएँ",
                 "mr": "तुम्ही सांगितलेल्या समस्या"},
    "opened": {"en": "Opened", "hi": "कब खुली", "mr": "कधी उघडली"},
    "status": {"en": "Status", "hi": "स्थिति", "mr": "स्थिती"},
    "photographs": {"en": "Your photographs", "hi": "आपके फ़ोटो", "mr": "तुमचे फोटो"},
    "what_said": {"en": "What the app said", "hi": "ऐप ने क्या कहा", "mr": "ॲपने काय सांगितले"},
    "why": {"en": "Why", "hi": "क्यों", "mr": "का"},
    "alerts": {"en": "Alerts we sent you", "hi": "हमने भेजी चेतावनियाँ",
               "mr": "आम्ही पाठवलेले इशारे"},
    "level": {"en": "Level", "hi": "स्तर", "mr": "पातळी"},
    "issued": {"en": "Sent on", "hi": "कब भेजी", "mr": "कधी पाठवले"},
    "found": {"en": "What you found", "hi": "आपको क्या मिला", "mr": "तुम्हाला काय आढळले"},
    "sprays": {"en": "Sprays you recorded", "hi": "आपने दर्ज किए छिड़काव",
               "mr": "तुम्ही नोंदवलेली फवारणी"},
    "product": {"en": "Product", "hi": "उत्पाद", "mr": "उत्पादन"},
    "at": {"en": "When", "hi": "कब", "mr": "कधी"},
    "emails": {"en": "Emails we sent you", "hi": "हमने भेजे ईमेल", "mr": "आम्ही पाठवलेले ईमेल"},
    "subject": {"en": "Subject", "hi": "विषय", "mr": "विषय"},
    "kind": {"en": "Kind", "hi": "प्रकार", "mr": "प्रकार"},
    "nothing": {"en": "Nothing here yet.", "hi": "अभी यहाँ कुछ नहीं।", "mr": "इथे अजून काही नाही."},
    "page": {"en": "Page", "hi": "पृष्ठ", "mr": "पृष्ठ"},
    "of": {"en": "of", "hi": "में से", "mr": "पैकी"},
    "footer_note": {
        "en": "This is your copy. If you delete your account, everything named here goes "
              "with it — including the photographs as files, not only as rows.",
        "hi": "यह आपकी प्रति है। यदि आप अपना खाता हटाते हैं, तो यहाँ लिखा सब कुछ चला जाएगा — "
              "फ़ोटो भी, फ़ाइलों के रूप में, केवल पंक्तियों के रूप में नहीं।",
        "mr": "ही तुमची प्रत आहे. तुम्ही खाते हटवल्यास इथे लिहिलेले सर्व काही जाईल — "
              "फोटोसुद्धा, फाइल म्हणून, फक्त ओळी म्हणून नाही."},
    "stamp_line": {"en": "Issued by AnnRakshak", "hi": "AnnRakshak द्वारा जारी",
                   "mr": "AnnRakshak कडून जारी"},
    "ps": {"en": "Smart India Hackathon 2026 · PS 26131 · Government of Maharashtra",
           "hi": "Smart India Hackathon 2026 · PS 26131 · महाराष्ट्र शासन",
           "mr": "Smart India Hackathon 2026 · PS 26131 · महाराष्ट्र शासन"},
}


def _t(key: str, lang: str) -> str:
    return tr(L[key], lang)


def _day(value: str | None) -> str:
    """An ISO timestamp as a farmer reads a date, not as a machine writes one."""
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%d %b %Y")
    except ValueError:
        return value


class _Report(FPDF):
    """The page furniture: a rule and a wordmark at the top, the page number
    and the promise about deletion at the foot."""

    def __init__(self, lang: str):
        super().__init__(format="A4", unit="mm")
        self.lang = lang
        self.set_auto_page_break(auto=True, margin=22)
        self.set_margins(18, 18, 18)
        self.add_font(PRIMARY, "", str(FONTS / "NotoSansDevanagari-Regular.ttf"))
        self.add_font(PRIMARY, "B", str(FONTS / "NotoSansDevanagari-Bold.ttf"))
        names = []
        for code, filename in FALLBACKS.items():
            path = FONTS / filename
            if path.exists():
                self.add_font(f"noto_{code}", "", str(path))
                names.append(f"noto_{code}")
        self.set_fallback_fonts(names)
        # Devanagari is not drawn in the order it is typed; without this the
        # farmer's own language comes out as detached pieces.
        self.set_text_shaping(True)

    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font(PRIMARY, "B", 9)
        self.set_text_color(*MUTED)
        self.cell(0, 6, "AnnRakshak", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*RULE)
        self.line(self.l_margin, self.get_y() + 1, self.w - self.r_margin, self.get_y() + 1)
        self.ln(5)

    def footer(self) -> None:
        self.set_y(-18)
        self.set_font(PRIMARY, "", 7)
        self.set_text_color(*MUTED)
        self.multi_cell(0, 3.4, _t("footer_note", self.lang), align=Align.L)
        self.set_y(-9)
        self.cell(0, 5, f"{_t('page', self.lang)} {self.page_no()} {_t('of', self.lang)} {{nb}}",
                  align=Align.R)


def _stamp(pdf: _Report, lang: str, when: date) -> None:
    """The mark that says this came from the app, and when.

    A farmer may hand this to somebody at a KVK or an office, so it should
    look issued rather than printed off a web page."""
    x, y, w, h = pdf.w - pdf.r_margin - 54, 18, 54, 26
    pdf.set_draw_color(*LEAF)
    pdf.set_line_width(0.5)
    pdf.rect(x, y, w, h, round_corners=True, corner_radius=3)
    if EMBLEM.exists():
        pdf.image(str(EMBLEM), x=x + 4, y=y + 5.5, w=11, h=11)
    pdf.set_xy(x + 17, y + 5)
    pdf.set_font(PRIMARY, "B", 8)
    pdf.set_text_color(*LEAF)
    pdf.cell(w - 20, 4.5, "AnnRakshak", new_x=XPos.LEFT, new_y=YPos.NEXT)
    pdf.set_x(x + 17)
    pdf.set_font(PRIMARY, "", 6)
    pdf.set_text_color(*MUTED)
    pdf.cell(w - 20, 4, _t("stamp_line", lang))
    pdf.set_xy(x + 4, y + h - 8.5)
    pdf.set_font(PRIMARY, "", 6.5)
    pdf.cell(w - 8, 4, when.strftime("%d %b %Y"), align=Align.C)
    pdf.set_line_width(0.2)


def _heading(pdf: _Report, text: str) -> None:
    pdf.ln(3)
    pdf.set_font(PRIMARY, "B", 12)
    pdf.set_text_color(*LEAF)
    pdf.cell(0, 7, text, new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_draw_color(*RULE)
    pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
    pdf.ln(2.5)


def _pair(pdf: _Report, label: str, value: str) -> None:
    """One fact: what it is, then what it says."""
    pdf.set_font(PRIMARY, "", 8.5)
    pdf.set_text_color(*MUTED)
    pdf.cell(42, 5.6, label)
    pdf.set_font(PRIMARY, "", 9.5)
    pdf.set_text_color(*INK)
    pdf.multi_cell(0, 5.6, value or "—", new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _empty(pdf: _Report, lang: str) -> None:
    pdf.set_font(PRIMARY, "", 9)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 6, _t("nothing", lang), new_x=XPos.LMARGIN, new_y=YPos.NEXT)


def _entry(pdf: _Report, pairs: list[tuple[str, str]]) -> None:
    """One field, problem, alert or spray, as a small block of its own."""
    if pdf.get_y() > pdf.h - 45:
        pdf.add_page()
    pdf.set_draw_color(*RULE)
    top = pdf.get_y()
    for label, value in pairs:
        _pair(pdf, label, value)
    pdf.line(pdf.l_margin, pdf.get_y() + 1.5, pdf.w - pdf.r_margin, pdf.get_y() + 1.5)
    pdf.ln(4)
    del top


def _table(pdf: _Report, headers: list[str], widths: list[float], rows: list[list[str]]) -> None:
    """The sections that repeat. A farmer can hold ninety-nine alerts and a
    hundred and thirty emails; as a labelled block each that is a twenty-five
    page document nobody reads. The same rows as a table are a page or two,
    and nothing is left out to get there."""
    usable = pdf.w - pdf.l_margin - pdf.r_margin
    widths = [w / sum(widths) * usable for w in widths]

    def head() -> None:
        pdf.set_font(PRIMARY, "B", 7.5)
        pdf.set_text_color(*MUTED)
        for h, w in zip(headers, widths):
            pdf.cell(w, 5, h)
        pdf.ln(5)
        pdf.set_draw_color(*RULE)
        pdf.line(pdf.l_margin, pdf.get_y(), pdf.w - pdf.r_margin, pdf.get_y())
        pdf.ln(1.5)

    head()
    for row in rows:
        if pdf.get_y() > pdf.h - 30:
            pdf.add_page()
            head()
        pdf.set_font(PRIMARY, "", 8.5)
        pdf.set_text_color(*INK)
        for value, w in zip(row, widths):
            text = value or "—"
            while text and pdf.get_string_width(text) > w - 2:   # one row stays one line
                text = text[:-1]
            if text != (value or "—"):
                text = text[:-1] + "…"
            pdf.cell(w, 5.2, text)
        pdf.ln(5.2)
    pdf.ln(2)


def render(data: dict, lang: str = "en") -> bytes:
    """`erasure.export_account`'s answer, as a document the farmer can keep."""
    lang = lang if lang else "en"
    pdf = _Report(lang)
    pdf.set_title(_t("title", lang))
    pdf.set_author("AnnRakshak")
    pdf.add_page()

    when = date.today()
    _stamp(pdf, lang, when)

    account = data.get("account") or {}
    pdf.set_xy(pdf.l_margin, 22)
    pdf.set_font(PRIMARY, "B", 24)
    pdf.set_text_color(*INK)
    pdf.cell(0, 12, _t("title", lang), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font(PRIMARY, "", 10)
    pdf.set_text_color(*MUTED)
    pdf.multi_cell(pdf.w - pdf.l_margin - pdf.r_margin - 58, 5.5, _t("subtitle", lang),
                   new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.ln(8)
    _pair(pdf, _t("prepared_for", lang), account.get("name") or "—")
    _pair(pdf, _t("prepared_on", lang), when.strftime("%d %b %Y"))

    _heading(pdf, _t("account", lang))
    _pair(pdf, _t("name", lang), account.get("name") or "—")
    _pair(pdf, _t("phone", lang), account.get("phone") or "—")
    _pair(pdf, _t("email", lang), account.get("email") or "—")
    _pair(pdf, _t("language", lang), account.get("language") or "—")
    _pair(pdf, _t("joined", lang), _day(account.get("joined")))

    profile = data.get("profile") or {}
    if profile:
        _heading(pdf, _t("place", lang))
        _pair(pdf, _t("district", lang), profile.get("district") or "—")
        _pair(pdf, _t("taluka", lang), profile.get("taluka") or "—")
        _pair(pdf, _t("village", lang), profile.get("village") or "—")
        acres = profile.get("total_land_acres")
        _pair(pdf, _t("land", lang), f"{acres} acres" if acres else "—")
        _pair(pdf, _t("consent", lang), _day(profile.get("consent_given_at")))

    _heading(pdf, _t("farms", lang))
    farms = data.get("farms") or []
    if not farms:
        _empty(pdf, lang)
    for f in farms:
        loc = f.get("location") or {}
        where = ", ".join(x for x in (f.get("village"), f.get("district")) if x) or "—"
        if loc.get("lat") is not None:
            where += f"  ({loc['lat']:.4f}, {loc['lon']:.4f})"
        _entry(pdf, [
            (_t("crop", lang), str(f.get("crop") or "—")),
            (_t("variety", lang), str(f.get("variety") or "—")),
            (_t("area", lang), f"{f.get('area_acres')} acres" if f.get("area_acres") else "—"),
            (_t("sown", lang), _day(f.get("sowing_date"))),
            (_t("where", lang), where),
        ])

    _heading(pdf, _t("problems", lang))
    problems = data.get("problems") or []
    if not problems:
        _empty(pdf, lang)
    for p in problems:
        _entry(pdf, [
            (_t("problem", lang), str(p.get("target") or "—")),
            (_t("status", lang), str(p.get("status") or "—")),
            (_t("opened", lang), _day(p.get("opened"))),
        ])

    _heading(pdf, _t("photographs", lang))
    photos = data.get("photographs") or []
    if not photos:
        _empty(pdf, lang)
    if photos:
        _table(pdf, [_t("what_said", lang), _t("why", lang)], [1, 2],
               [[str(ph.get("what_the_app_said") or ""), str(ph.get("why") or "")] for ph in photos])

    _heading(pdf, _t("alerts", lang))
    alerts = data.get("alerts") or []
    if not alerts:
        _empty(pdf, lang)
    if alerts:
        _table(pdf, [_t("problem", lang), _t("level", lang), _t("issued", lang), _t("found", lang)],
               [3, 1, 1.4, 1.6],
               [[str(a.get("target") or ""), str(a.get("level") or ""),
                 _day(a.get("issued_on")), str(a.get("what_you_found") or "")] for a in alerts])

    _heading(pdf, _t("sprays", lang))
    sprays = data.get("sprays") or []
    if not sprays:
        _empty(pdf, lang)
    if sprays:
        _table(pdf, [_t("product", lang), _t("at", lang)], [3, 1.4],
               [[str(x.get("product") or ""), _day(x.get("at"))] for x in sprays])

    _heading(pdf, _t("emails", lang))
    emails = data.get("emails_we_sent") or []
    if not emails:
        _empty(pdf, lang)
    if emails:
        _table(pdf, [_t("subject", lang), _t("kind", lang), _t("at", lang)], [4, 1, 1.4],
               [[str(e.get("subject") or ""), str(e.get("kind") or ""), _day(e.get("at"))]
                for e in emails])

    pdf.ln(4)
    pdf.set_font(PRIMARY, "", 7)
    pdf.set_text_color(*MUTED)
    pdf.cell(0, 4, _t("ps", lang), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    out = pdf.output()
    return bytes(out)
