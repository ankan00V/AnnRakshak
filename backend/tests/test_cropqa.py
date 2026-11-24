"""Krishi and Darpan answer questions about pests and diseases from the
advisories (app.cropqa), and stay out of the way of questions about the app.

Every answer here is the knowledge base's own words in a template, so the
tests check two things: that the right pest is found from the way people
actually ask, and that nothing reaches the farmer that the advisory does not
say — no chemical in an organic answer, no diagnosis from a description.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app import cropqa, darpan, geo, krishi
from app.db import Base, SessionLocal, engine
from app.engine import advisory, labelcheck
from app.kb import get_kb, tr
from app.main import app
from app.models import Alert, Farm, Problem

kb = get_kb()


def ask(text: str, lang: str = "en", farm=None, topic=None) -> dict:
    return krishi.answer(None, kb, text=text, topic=topic, screen="home", lang=lang, farm=farm)


@pytest.mark.parametrize("lang, text, target", [
    ("en", "how do i control stem borer in rice organically", "rice_yellow_stem_borer"),
    ("en", "what is rice blast", "rice_blast"),
    ("hi", "धान में तना छेदक का जैविक उपाय", "rice_yellow_stem_borer"),
    ("mr", "कापसावरील पांढरी माशी कशी नियंत्रित करावी", "cotton_whitefly"),
    ("hi", "कपास में गुलाबी सुंडी", "cotton_pink_bollworm"),
    ("hi", "dhan me tana chhedak ka ilaj", "rice_yellow_stem_borer"),
    ("en", "fall armyworm maize what to spray", "maize_fall_armyworm"),
    ("en", "blast", "rice_blast"),
    ("en", "brown spot rice what to do", "rice_brown_spot"),
])
def test_a_named_pest_is_found_however_it_is_asked(lang, text, target):
    out = ask(text, lang)
    assert out["topic"].startswith(f"crop:{target}:"), (text, out["topic"])


def test_an_organic_answer_names_no_chemical_and_shows_every_level():
    out = ask("how do i control stem borer in rice organically")
    adv = advisory.compose(kb, "rice_yellow_stem_borer", "en")
    said = " ".join([out["text"], *out["steps"]])
    for r in adv["ladder"]:
        if r["tier"] == "chemical":
            assert r["product"] not in said
    assert adv["organic"][0]["product"] in said          # registered by CIB&RC
    assert "Agniastra" in said and "not a registered pesticide" in said  # natural farming, labelled
    assert any("Trichogramma" in s for s in out["steps"])  # the PAU step, sourced


def test_what_to_do_puts_the_chemical_last_with_the_spray_check():
    out = ask("what can I spray on cotton whitefly")
    steps = out["steps"]
    chem = next(i for i, s in enumerate(steps) if s.startswith("Chemical"))
    assert any("Spray check" in s for s in steps[chem:])
    assert out["text"].startswith("The chemical for Whitefly")


def test_a_description_lists_candidates_and_never_diagnoses():
    """Krishi cannot tell a disease from words. A description gets the problems
    whose signs read like it, each with its signs, and a photo to decide."""
    out = ask("my rice leaves have brown spots with grey centres")
    assert out["topic"].endswith(":symptoms")
    names = {tr(kb.targets[t]["names"], "en") for t in ("rice_blast", "rice_brown_spot")}
    assert all(any(s.startswith(n) for s in out["steps"]) for n in names)
    assert "photo" in out["steps"][-1].lower()
    said = " ".join(out["steps"])
    for pid, p in kb.pesticides.items():
        assert p["name"] not in said  # no product for a problem nobody has named


@pytest.mark.parametrize("text", ["leaf spot", "stem borer"])
def test_a_name_on_more_than_one_crop_asks_which(text):
    assert ask(text)["topic"] == "crop:need_crop"


def test_the_farmers_own_crop_settles_an_ambiguous_name():
    farm = Farm(farmer_name="x", crop="maize", sowing_date=date.today() - timedelta(days=30), district="Pune",
                lat=18.5, lon=73.8, area_acres=2)
    assert ask("stem borer", farm=farm)["topic"].startswith("crop:maize_stem_borer:")


def test_a_product_question_gets_the_registers_verdict():
    out = ask("can i use mancozeb on rice blast")
    ing = kb.match_pesticide("mancozeb")
    assert out["steps"] == [labelcheck.check(kb, ing, "rice", "rice_blast", "en")["message"]]
    assert out["go"][0]["to"] == "/app/spray"


def test_a_recipe_is_the_preparations_own_with_its_label():
    out = ask("how to make neemastra")
    prep = kb.homemade["neemastra"]
    assert out["topic"] == "prep:neemastra"
    assert prep["recipe"]["en"][0] in out["steps"]
    assert any("not a registered pesticide" in s for s in out["steps"])
    assert any(prep["recipe_source"] in s for s in out["steps"])


def test_a_chip_opens_the_same_pest_another_way():
    first = ask("what is rice blast")
    chip = next(c for c in first["suggestions"] if c["id"].endswith(":organic"))
    again = ask("", topic=chip["id"])
    assert again["topic"] == "crop:rice_blast:organic" and again["steps"]


@pytest.mark.parametrize("text, topic", [
    ("how do I take a photo of a sick plant", "scan_photo"),
    ("will it rain tomorrow", "weather_now"),
    ("how does the app work", "what_is_app"),
])
def test_questions_about_the_app_still_get_the_apps_answers(text, topic):
    assert ask(text)["topic"] == topic


def test_neem_inside_a_preparation_name_is_not_a_product():
    assert cropqa._product_in(kb, "neemastra for whitefly") is None
    assert cropqa._product_in(kb, "can i use mancozeb") == kb.match_pesticide("mancozeb")


# --- Darpan -------------------------------------------------------------------

@pytest.fixture()
def officer_world(monkeypatch):
    monkeypatch.setattr(geo, "locate", lambda state, district, village=None: {"lat": 21.17, "lon": 79.65})
    Base.metadata.drop_all(bind=engine)
    with TestClient(app):
        with SessionLocal() as db:
            for i, district in enumerate(("Bhandara", "Bhandara", "Gondia")):
                db.add(Farm(farmer_name=f"F{i}", crop="rice", sowing_date=date.today() - timedelta(days=50),
                            district=district, village=f"V{i}", lat=21.17, lon=79.65, area_acres=2, is_demo=True))
            db.commit()
            farms = db.query(Farm).all()
            now = datetime.now()
            for f, days in ((farms[0], 1), (farms[1], 2), (farms[0], 9)):
                db.add(Problem(farm_id=f.id, target="rice_blast", status="open", opened_at=now - timedelta(days=days)))
            db.add(Alert(farm_id=farms[2].id, target="rice_blast", trigger="weather", level="high", reason={},
                         tasks={"en": ["Check the leaves"]}, issued_on=date.today()))
            db.commit()
        yield


def test_darpan_answers_a_named_disease_with_its_own_counts(officer_world):
    with SessionLocal() as db:
        out = darpan.answer(db, kb, text="blast in bhandara", demo=True, officer=None)
    assert out["intent"] == "pest"
    text = " ".join(out["lines"])
    assert out["lines"][0].startswith("In Bhandara: Rice blast")
    assert "Reported: 2 this week against 1 the week before — up." in text
    assert "Gondia" not in text  # the alert there is outside the district asked about
    assert any(g["to"].startswith("/officer/advisories?target=rice_blast") for g in out["go"])


def test_darpan_says_what_to_advise_organic_first(officer_world):
    with SessionLocal() as db:
        out = darpan.answer(db, kb, text="करपा", demo=True, officer=None)
    lines = out["lines"]
    organic = next(i for i, l in enumerate(lines) if l.startswith("Registered organic"))
    chem = next(i for i, l in enumerate(lines) if l.startswith("Chemical"))
    assert organic < chem


def test_darpan_asks_which_crop_for_a_name_on_two(officer_world):
    with SessionLocal() as db:
        out = darpan.answer(db, kb, text="stem borer", demo=True, officer=None)
    assert out["intent"] == "pest" and "Which crop" in out["lines"][0]


# --- amounts for the farmer's own field ----------------------------------------

def test_every_cure_gives_the_amount_for_the_farmers_field():
    """The standard dose and the same thing for this field. The only ones left
    per unit are a cotton seed treatment (cotton has no single seed rate: a
    hybrid pouch to 4 kg an acre), a seedling root dip, and a seed product whose
    dose is the printed label's."""
    without = []
    for tid in kb.advisories:
        a = advisory.compose(kb, tid, "en", 2.0)
        for x in [*a["organic"], *[r for r in a["ladder"] if r["tier"] == "chemical"], *a["homemade"]]:
            if not x.get("for_field"):
                without.append((tid, x.get("use"), x.get("dose")))
    assert all(tid.startswith("cotton_") and use == "seed" or use in ("root_dip",) or "label" in (dose or "")
               for tid, use, dose in without), without
    assert len(without) <= 5


def test_field_amounts_scale_with_the_field_and_keep_the_standard_dose():
    one = advisory.compose(kb, "rice_yellow_stem_borer", "en", 1.0)
    three = advisory.compose(kb, "rice_yellow_stem_borer", "en", 3.0)
    agni1 = next(h for h in one["homemade"] if h["prep"] == "agniastra")
    agni3 = next(h for h in three["homemade"] if h["prep"] == "agniastra")
    assert agni1["dose"] == agni3["dose"] and "6 to 8 litres in 200 litres" in agni1["dose"]
    assert "6–8 litres in 200 litres of water" in agni1["for_field"]
    assert "18–24 litres in 600 litres of water" in agni3["for_field"]
    gran = next(r for r in three["ladder"] if r.get("ingredient") == "chlorantraniliprole_0_4gr")
    assert "12 kg" in gran["for_field"]


def test_a_seed_treatment_is_worked_out_for_the_whole_sowing():
    a = advisory.compose(kb, "rice_blast", "en", 2.5)
    seed = next(o for o in a["organic"] if o["use"] == "seed")
    assert seed["dose"] == "10 g per kg of seed."
    assert "about 20 kg of seed, so 200 g (at 8 kg of seed an acre)" in seed["for_field"]


def test_krishi_gives_the_field_amount_when_a_field_is_open():
    farm = Farm(farmer_name="x", crop="maize", sowing_date=date.today() - timedelta(days=30), district="Pune",
                lat=18.5, lon=73.8, area_acres=3)
    out = ask("how to control fall armyworm", farm=farm)
    reg = next(s for s in out["steps"] if s.startswith("Registered organic"))
    assert "6.3 ml per litre of water. For your 3 acre field: about 3.8 litres in 600 litres of water." in reg
    recipe = ask("how to make agniastra", farm=farm)
    assert any("For your 3 acre field: 18–24 litres in 600 litres of water" in s for s in recipe["steps"])


# --- every language Krishi claims ----------------------------------------------

def test_odia_is_read_as_odia():
    assert krishi.register("ଧାନରେ କାଣ୍ଡ ଛେଦକ", "en") == ("od", False)


def test_a_pest_named_in_its_own_language_is_found_through_the_word_endings():
    """"தண்டு துளைப்பதை" is how a Tamil question says the name the memory has
    as "மஞ்சள் தண்டுத் துளைப்பான்": the endings change the last letters."""
    assert cropqa._same_word("தண்டு", "தண்டுத்") and cropqa._same_word("துளைப்பதை", "துளைப்பான்")
    assert not cropqa._same_word("white", "whitefly")
    hits = cropqa.find(kb, "நெல்லில் மஞ்சள் தண்டு துளைப்பதை எப்படி கட்டுப்படுத்துவது")
    assert hits and hits[0][0] == "rice_yellow_stem_borer"


def test_a_split_english_name_is_still_the_name():
    assert cropqa.find(kb, "white fly on cotton")[0][0] == "cotton_whitefly"


@pytest.mark.parametrize("lang, text, english", [
    ("bn", "ধানের মাজরা পোকা জৈব উপায়ে কীভাবে দমন করব?", "How can rice stem borer be controlled biologically?"),
    ("od", "ଚାଉଳରେ ଥିବା କାଣ୍ଡ ଛେଦକକୁ ଜୈବିକ ଉପାୟରେ ମୁଁ କିପରି ନିୟନ୍ତ୍ରଣ କରିପାରିବି?",
     "How can I control stem borer in rice organically?"),
    ("pa", "ਨਰਮੇ ਵਿੱਚ ਚਿੱਟੀ ਮੱਖੀ, ਮੈਨੂੰ ਕੀ ਛਿੜਕਾਅ ਕਰਨਾ ਚਾਹੀਦਾ ਹੈ?", "White fly in cotton, what should I spray?"),
])
def test_a_question_in_another_language_is_answered_in_it(monkeypatch, lang, text, english):
    """Names and cues are written in English, Hindi and Marathi; a question in
    any other language is also read in English, and answered in its own."""
    from app import cache
    monkeypatch.setattr(cache, "get_json", lambda key: None)
    monkeypatch.setattr(cache, "set_json", lambda *a, **k: None)
    monkeypatch.setattr(krishi.voice, "translate", lambda t, s, d: english)
    out = ask(text, lang)
    assert out["topic"].startswith("crop:") and out["lang"] == lang
    said = " ".join([out["text"], *out["steps"]])
    letters = [c for c in said if c.isalpha()]
    assert sum(not c.isascii() for c in letters) / len(letters) > 0.6  # in the farmer's script, not English


@pytest.mark.parametrize("lang", ["bn", "ta", "te", "kn", "ml", "gu", "pa", "od"])
def test_a_dose_unit_reads_in_order_in_every_language(lang):
    """"3 g per litre of water" is put together as the number and then this
    fragment: the fragment must name the unit, in the language's letters."""
    for unit in ("g", "ml"):
        frag = tr(advisory.UNIT_WORDS[unit], lang)
        assert frag != advisory.UNIT_WORDS[unit]["en"] and not any(c.isascii() and c.isalpha() for c in frag)
