"""The farmer's data report: a document they can read, not a dump.

"Download everything we hold" used to hand back a .json file. A farmer in
Bhandara cannot read JSON, so being answered that way is the same as not being
answered. This renders the same content as a PDF in their own language.

What these tests hold onto: it is a PDF, it is in the farmer's language with
the script actually drawn, every section of the export reaches the page, and
a farmer with hundreds of alerts still gets a document rather than a ream.
"""

from datetime import date, datetime, timedelta

import pytest

from app import erasure, report
from app.db import Base, SessionLocal, engine
from app.models import Alert, Diagnosis, Farm, FarmerProfile, Problem, User


@pytest.fixture()
def farmer():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        u = User(role="farmer", name="सुनीता भोयर", phone="+919876500001",
                 email="sunita@example.com", lang="mr")
        db.add(u)
        db.flush()
        db.add(FarmerProfile(user_id=u.id, district="Bhandara", village="Sakoli",
                             taluka="Sakoli", total_land_acres=2.5, consent_at=datetime.now()))
        farm = Farm(user_id=u.id, farmer_name="सुनीता भोयर", crop="rice",
                    sowing_date=date.today() - timedelta(days=60), district="Bhandara",
                    village="Sakoli", lat=21.17, lon=79.65, area_acres=2.5, lang="mr")
        db.add(farm)
        db.flush()
        problem = Problem(farm_id=farm.id, target="rice_brown_spot", status="open")
        db.add(problem)
        db.flush()
        db.add(Diagnosis(problem_id=problem.id, image_path="x.jpg", topk=[],
                         gate_outcome="advise", gate_reason="ABOVE_GATE", confidence=0.9,
                         model_version="test-1", is_stub=False))
        for i in range(120):   # a farmer who has been with the app a while
            db.add(Alert(farm_id=farm.id, target="rice_brown_spot", trigger="weather",
                         level="high", reason={"en": "x"}, tasks={"en": ["look"]},
                         issued_on=date.today() - timedelta(days=i)))
        db.commit()
        yield db.get(User, u.id)


def _export(user):
    with SessionLocal() as db:
        return erasure.export_account(db, db.get(User, user.id))


def test_it_is_a_pdf(farmer):
    out = report.render(_export(farmer), "mr")
    assert out[:5] == b"%PDF-", "the farmer asked for their data, not for a parser's breakfast"
    assert out.endswith(b"%%EOF\n") or b"%%EOF" in out[-32:]


def test_the_farmers_own_language_is_actually_drawn(farmer):
    """Not just passed through: the Devanagari has to reach the page as glyphs,
    which is what the bundled font and HarfBuzz are for."""
    mr = report.render(_export(farmer), "mr")
    en = report.render(_export(farmer), "en")
    assert mr != en, "the Marathi report is the English one with a different label"
    assert len(mr) > 20_000, "a PDF this small cannot be carrying an embedded font"


def test_every_section_of_the_export_reaches_the_document(farmer):
    """The promise is *everything* we hold, so a section added to the export
    and forgotten in the renderer is the failure worth catching.

    The text cannot be read back out of the PDF — an embedded subset font
    writes glyph ids, not words — so this checks it the two ways that are
    honest: every section the export produces has a heading authored for it,
    and emptying a section it holds makes the document shorter.
    """
    data = _export(farmer)
    headed = {"account", "profile", "farms", "problems", "photographs", "alerts",
              "sprays", "emails_we_sent"}
    sections = {k for k, v in data.items() if k != "exported_at"}
    assert sections <= headed, f"the export grew a section the report does not print: {sections - headed}"

    full = len(report.render(data, "en"))
    for key in ("farms", "problems", "photographs", "alerts"):
        assert data.get(key), f"fixture should populate {key}"
        shorter = len(report.render({**data, key: []}, "en"))
        assert shorter < full, f"emptying {key} changed nothing — is it being rendered at all?"


def test_a_farmer_with_a_hundred_alerts_still_gets_a_document(farmer):
    """Rendered as labelled blocks this was twenty-five pages. Nothing is left
    out to shorten it — the repeating sections are a table instead."""
    out = report.render(_export(farmer), "mr")
    pages = out.count(b"/Type /Page")
    assert 0 < pages <= 12, f"{pages} pages is a ream, not a record"


def test_a_language_with_no_devanagari_still_renders(farmer):
    """Tamil, Bengali and the rest are registered as per-glyph fallbacks; a
    missing font must not take the whole report down."""
    for lang in ("ta", "bn", "gu", "pa", "kn", "ml", "te", "hi", "en"):
        out = report.render(_export(farmer), lang)
        assert out[:5] == b"%PDF-", lang


def test_an_empty_account_is_a_short_report_not_a_crash(farmer):
    """A farmer who signed up this morning holds almost nothing."""
    out = report.render({"account": {"name": "New"}, "farms": [], "problems": [],
                         "photographs": [], "alerts": [], "sprays": [],
                         "emails_we_sent": []}, "en")
    assert out[:5] == b"%PDF-"
