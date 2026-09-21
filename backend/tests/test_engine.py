"""The guarantees the product rests on, tested at the function level."""

import copy
import io
from datetime import date, timedelta

import pytest

from app.config import FLOOR, GATE, MARGIN, PRIOR_MAX_BIAS
from app.engine import advisory, doubt, labelcheck, prior, risk, vision
from app.engine.gate import Prediction, TopK, decide
from app.engine.weather import Day, Window
from app.kb import KB, get_kb, validate

kb = get_kb()
_REAL_MODEL = vision._real_model


def topk(*pairs, **kw):
    return TopK([Prediction(t, c) for t, c in pairs], "test", is_stub=False, **kw)


def run_gate(tk, crop="rice"):
    return decide(
        tk, farm_crop=crop,
        tier_of=lambda t: kb.targets.get(t, {}).get("tier"),
        has_advisory=lambda t: t in kb.advisories,
        cue_for=kb.cue_for,
    )


# --- gate ------------------------------------------------------------------

def test_gate_advises_when_confident_and_clear():
    d = run_gate(topk(("rice_bacterial_leaf_blight", 0.85), ("rice_brown_spot", 0.1)))
    assert (d.outcome, d.reason) == ("advise", "ABOVE_GATE")
    assert len(d.alternatives) == 2  # alternatives shown even when advising


def test_gate_asks_when_torn_and_a_cue_exists():
    d = run_gate(topk(("rice_brown_spot", 0.51), ("rice_bacterial_leaf_blight", 0.42)))
    assert d.outcome == "clarify" and d.cue_id == "blb_vs_brown_spot_tip"


def test_gate_escalates_when_torn_without_a_cue():
    d = run_gate(topk(("rice_false_smut", 0.5), ("rice_sheath_blight", 0.45)))
    assert (d.outcome, d.reason) == ("escalate", "AMBIGUOUS_NO_CUE")


def test_gate_escalates_below_floor():
    d = run_gate(topk(("rice_brown_spot", FLOOR - 0.01), ("rice_false_smut", 0.1)))
    assert (d.outcome, d.reason) == ("escalate", "BELOW_FLOOR")


def test_gate_escalates_clear_but_under_gate():
    d = run_gate(topk(("rice_brown_spot", GATE - 0.02), ("rice_false_smut", 0.1)))
    assert (d.outcome, d.reason) == ("escalate", "BELOW_GATE")


def test_gate_escalates_crop_mismatch():
    d = run_gate(topk(("maize_aphid", 0.95), ("rice_brown_spot", 0.02)), crop="rice")
    assert d.reason == "CROP_MISMATCH"


def test_gate_escalates_inspection_tier_even_when_confident():
    d = run_gate(topk(("rice_brown_planthopper", 0.95), ("rice_brown_spot", 0.02)))
    assert (d.outcome, d.reason) == ("escalate", "NOT_PHOTO_DIAGNOSABLE")


def test_gate_asks_for_retake_on_non_crop_photo():
    d = run_gate(topk(("rice_brown_spot", 0.99), ("rice_false_smut", 0.0),
                      out_of_scope=True, oos_reason="NOT_A_CROP_PHOTO"))
    assert d.outcome == "retake"


def test_gate_sends_an_unfamiliar_crop_photo_to_an_expert_not_back_to_the_farmer():
    # A real maize whorl chewed by fall armyworm scored below the familiarity bar
    # and was told "this is not a crop photo". A photo that is mostly plant is a
    # crop photo whatever the bank says, so it goes to a human.
    d = run_gate(topk(("maize_fall_armyworm", 0.25), ("maize_aphid", 0.23),
                      out_of_scope=True, oos_reason="UNFAMILIAR_PHOTO"), crop="maize")
    assert (d.outcome, d.reason) == ("escalate", "UNFAMILIAR_PHOTO")


def test_vegetation_decides_retake_versus_expert_for_an_unfamiliar_photo():
    from PIL import Image

    from app.config import CLEARLY_VEGETATION
    from app.engine import vision

    class Unfamiliar:
        version, temperature = "test-0", 1.0

        def analyse(self, img, k=3, with_heatmap=True):
            return [("maize_fall_armyworm", 0.25), ("maize_aphid", 0.23)], {"grid": []}, 0.1

        def is_familiar(self, fam):
            return False

    vision._real_model.cache_clear()
    try:
        vision._real_model = lambda: Unfamiliar()  # type: ignore[assignment]
        leafy = Image.new("RGB", (64, 64), (70, 130, 50))
        assert vision.vegetation_fraction(leafy) >= CLEARLY_VEGETATION
        buf = io.BytesIO()
        leafy.save(buf, format="JPEG")
        assert vision.classify(buf.getvalue(), "maize").oos_reason == "UNFAMILIAR_PHOTO"

        grey = Image.new("RGB", (64, 64), (128, 128, 128))
        buf = io.BytesIO()
        grey.save(buf, format="JPEG")
        assert vision.classify(buf.getvalue(), "maize").oos_reason == "NOT_A_CROP_PHOTO"
    finally:
        vision._real_model = _REAL_MODEL
        vision._real_model.cache_clear()


def test_gate_healthy_is_advise_without_treatment():
    d = run_gate(topk(("rice_healthy", 0.9), ("rice_brown_spot", 0.05)))
    assert (d.outcome, d.reason) == ("advise", "HEALTHY")


@pytest.mark.parametrize("c1", [i / 20 for i in range(21)])
@pytest.mark.parametrize("gap", [0.0, 0.05, 0.14, 0.16, 0.5])
def test_gate_always_exactly_one_outcome(c1, gap):
    c2 = max(0.0, c1 - gap)
    d = run_gate(topk(("rice_brown_spot", c1), ("rice_bacterial_leaf_blight", c2)))
    assert d.outcome in {"advise", "clarify", "escalate"}
    if d.outcome == "advise":
        assert c1 >= GATE and c1 - c2 >= MARGIN


# --- Doubt Doctor ----------------------------------------------------------

def test_doubt_yes_and_no_resolve_to_each_side():
    cue = kb.cue_for("rice_brown_spot", "rice_bacterial_leaf_blight")
    assert doubt.resolve(cue, "yes") == "rice_bacterial_leaf_blight"
    assert doubt.resolve(cue, "no") == "rice_brown_spot"


def test_doubt_cant_tell_escalates_never_tiebreaks():
    cue = kb.cue_for("rice_brown_spot", "rice_bacterial_leaf_blight")
    assert doubt.resolve(cue, "unknown") is None
    assert doubt.resolve(cue, "maybe") is None


# --- prior -----------------------------------------------------------------

def test_prior_cap_cannot_cross_a_band():
    # Maximum history in favour of the runner-up of an ambiguous pair.
    tk = topk(("rice_brown_spot", 0.5), ("rice_bacterial_leaf_blight", 0.49))
    biased = prior.apply_prior(tk, {"rice_brown_spot": (999, 0)})
    top = biased.predictions[0]
    assert top.confidence - tk.predictions[0].confidence <= PRIOR_MAX_BIAS + 1e-9
    assert run_gate(biased).outcome != "advise"
    # A below-floor prediction stays out of advise however much history.
    low = prior.apply_prior(topk(("rice_brown_spot", FLOOR - 0.01), ("rice_false_smut", 0.0)),
                            {"rice_brown_spot": (999, 0)})
    assert run_gate(low).outcome == "escalate"


def test_prior_is_reported():
    biased = prior.apply_prior(topk(("rice_brown_spot", 0.6), ("rice_false_smut", 0.1)),
                               {"rice_brown_spot": (5, 0)})
    assert biased.prior_bias == {"rice_brown_spot": pytest.approx(PRIOR_MAX_BIAS / 2)}


# --- knowledge base & advisories -------------------------------------------

def test_every_advisory_is_chemical_last_and_cited():
    for target in kb.advisories:
        a = advisory.compose(kb, target, "en", area_acres=2)
        tiers = [r["tier"] for r in a["ladder"]]
        assert tiers == sorted(tiers, key=["cultural", "biological", "chemical"].index)
        assert tiers[0] != "chemical"
        assert a["citations"] and a["what_to_avoid"]


def test_kb_refuses_chemical_first_ladder():
    bad = copy.deepcopy(kb)
    lad = bad.advisories["rice_brown_spot"]["ladder"]
    lad.insert(0, lad.pop())
    assert any("chemical" in e for e in validate(bad))


def test_icar_technologies_link_to_real_targets_and_institutes():
    assert kb.technologies and not validate(kb)
    faw = {t["id"] for t in kb.technologies_for(target="maize_fall_armyworm", audience="farmer")}
    assert {"nbair_bt25_faw", "nbair_ma35_faw", "nbair_spfrnpv_faw"} <= faw
    assert "nbair_faw_lure" not in faw  # official-only item stays out of farmer advice


def test_kb_refuses_technology_on_unknown_target_or_missing_language():
    bad = copy.deepcopy(kb)
    bad.technologies[0]["targets"] = ["rice_ghost_pest"]
    assert any("unknown target" in e for e in validate(bad))
    bad = copy.deepcopy(kb)
    farmer = next(t for t in bad.technologies if t["audience"] == "farmer")
    del farmer["summary"]["mr"]
    assert any("summary missing mr" in e for e in validate(bad))


def test_advisory_carries_icar_options_with_contact():
    a = advisory.compose(kb, "rice_leaf_folder", "hi", area_acres=2)
    ids = [o["id"] for o in a["icar_options"]]
    assert "nrri_tricho_tc" in ids
    card = next(o for o in a["icar_options"] if o["id"] == "nrri_tricho_tc")
    assert card["institute"]["phone"] and card["lead_time_days"] == 45 and card["supply"]


def test_every_rule_has_at_least_two_tasks_in_every_language():
    for target, rule in kb.rules.items():
        for lang in ("en", "hi", "mr"):
            assert len(rule["tasks"][lang]) >= 2, (target, lang)


def test_dose_scales_with_field_area():
    a1 = advisory.compose(kb, "rice_brown_spot", "en", area_acres=1)
    a2 = advisory.compose(kb, "rice_brown_spot", "en", area_acres=2)
    q1 = next(r for r in a1["ladder"] if r["tier"] == "chemical")["quantity"]["amount"]
    q2 = next(r for r in a2["ladder"] if r["tier"] == "chemical")["quantity"]["amount"]
    assert q2 == pytest.approx(2 * q1)


# --- label check -----------------------------------------------------------

ENDORSE = ("safe", "approved", "you can use", "सुरक्षित", "सुरक्षित आहे")


def test_label_check_never_endorses():
    for lang in ("en", "hi", "mr"):
        for code, text in labelcheck.VERDICTS.items():
            assert not any(w in text[lang].lower() for w in ENDORSE), (code, lang)


def test_label_check_verdicts():
    chk = lambda q, t: labelcheck.check(kb, q, "rice", t, "en")["code"]  # noqa: E731
    assert chk("copper oxychloride", "rice_bacterial_leaf_blight") == "NO_OBJECTION_FOUND"
    assert chk("mancozeb", "rice_bacterial_leaf_blight") == "NOT_FOR_TARGET"
    assert chk("emamectin", "rice_bacterial_leaf_blight") == "WRONG_CLASS"
    assert chk("roundup", "rice_brown_spot") == "HERBICIDE"
    assert chk("spinetoram", "rice_leaf_folder") == "WRONG_CROP"
    assert chk("unobtainium 9000", "rice_brown_spot") == "NOT_IN_RECORDS"


# --- risk ------------------------------------------------------------------

def _window(days, rh, tmin, tmax, rain=0.0, start=date(2026, 9, 1)):
    return Window([Day(start + timedelta(i), rh, tmin, tmax, rain) for i in range(days)], "test", None)


def _score(target, window, stage, das, history=False):
    t = kb.targets[target]
    stage_names = next(s["names"] for s in kb.crops[t["crop"]]["stages"] if s["key"] == stage)
    return risk.score_rule(target, kb.rules[target], target_name=t["names"], stage=stage,
                           stage_name=stage_names, das=das, window=window, has_history=history,
                           today=date(2026, 9, 14))


def test_weather_rule_fires_on_consecutive_run_and_says_why():
    s = _score("rice_brown_spot", _window(5, 90, 23, 31), "flowering", 80)
    assert s.fired and s.level == "medium" and "5 days in a row" in s.reason["en"]
    assert s.reason["mr"] and s.reason["hi"]


def test_weather_rule_needs_the_full_run():
    assert not _score("rice_brown_spot", _window(3, 90, 23, 31), "flowering", 80).fired


def test_missing_reading_breaks_a_run():
    w = _window(6, 90, 23, 31)
    w.days[2] = Day(w.days[2].on, None, 23, 31, 0)
    assert not _score("rice_brown_spot", w, "flowering", 80).fired


def test_wrong_stage_never_fires():
    assert not _score("rice_brown_spot", _window(10, 95, 23, 31), "nursery", 10).fired


def test_history_bumps_level():
    assert _score("rice_brown_spot", _window(5, 90, 23, 31), "flowering", 80, history=True).level == "high"


def test_trap_rule_needs_consecutive_nights_over_etl():
    rule = kb.rules["cotton_pink_bollworm"]
    d = date(2026, 9, 14)
    over = [{"recorded_on": d - timedelta(i), "count": 30, "traps": 3, "nights": 1} for i in range(3)]
    assert risk.score_traps("cotton_pink_bollworm", rule, over, d).fired
    gap = over[:1] + [{"recorded_on": d - timedelta(1), "count": 3, "traps": 3, "nights": 1}] + over[2:]
    assert not risk.score_traps("cotton_pink_bollworm", rule, gap, d).fired


# --- vegetation check (reject non-crop photos before trusting the softmax) --

@pytest.mark.parametrize("rgb", [(128, 128, 128), (160, 110, 60), (190, 150, 100), (120, 85, 55), (205, 150, 120)])
def test_non_plant_colours_fail_the_vegetation_check(rgb):
    from PIL import Image

    from app.config import MIN_VEGETATION_FRACTION
    from app.engine.vision import vegetation_fraction

    assert vegetation_fraction(Image.new("RGB", (64, 64), rgb)) < MIN_VEGETATION_FRACTION


@pytest.mark.parametrize("rgb", [(70, 130, 50), (200, 200, 60), (210, 190, 120)])
def test_leaf_and_straw_colours_pass_the_vegetation_check(rgb):
    from PIL import Image

    from app.config import MIN_VEGETATION_FRACTION
    from app.engine.vision import vegetation_fraction

    assert vegetation_fraction(Image.new("RGB", (64, 64), rgb)) >= MIN_VEGETATION_FRACTION


def test_a_lab_trained_class_must_clear_its_own_higher_bar():
    # rice_blast was learnt from lab photos: 0.85 clears the global gate but not its 0.90
    d = run_gate(topk(("rice_blast", 0.85), ("rice_brown_spot", 0.05)))
    assert (d.outcome, d.reason) == ("clarify", "LAB_CLASS_CONFIRM") and d.cue_id
    d = run_gate(topk(("rice_blast", 0.85), ("rice_leaf_folder", 0.05)))
    assert (d.outcome, d.reason) == ("escalate", "LAB_CLASS_BELOW_GATE")
    assert run_gate(topk(("rice_blast", 0.93), ("rice_brown_spot", 0.03))).outcome == "advise"
    assert run_gate(topk(("rice_brown_spot", 0.75), ("rice_blast", 0.05))).outcome == "advise"  # others unchanged


def test_closed_form_cam_is_the_same_map_as_grad_cam():
    # The heatmap is computed without a backward pass, which is only allowed
    # because for a single Linear layer on pooled features the two are the same
    # map. If the head ever stops being linear, cam_from_map must return None
    # and the backward pass must come back.
    torch = pytest.importorskip("torch")

    from app.engine.model import Net, cam_from_map, gradcam

    net = Net("mobilenet_v3_large", 4, "finetune", pretrained=False).train(False)
    x = torch.rand(1, 3, 96, 96)
    with torch.no_grad():
        fmap = net.feature_map(x)
    for c in range(4):
        closed = cam_from_map(net, fmap, c)
        assert closed is not None
        assert abs(closed - gradcam(net, x.clone().requires_grad_(True), c)).max() < 1e-4

    deep = Net("mobilenet_v3_large", 4, "ann", pretrained=False).train(False)
    assert cam_from_map(deep, fmap, 0) is None  # no closed form: fall back


def test_familiarity_rejects_what_is_far_from_every_training_photo():
    import torch

    from app.engine.model import Classifier
    clf = Classifier.__new__(Classifier)  # no weights needed for the similarity maths
    clf.bank = torch.nn.functional.normalize(torch.tensor([[1.0, 0, 0], [0.9, 0.1, 0], [0.95, 0, 0.05]]), dim=1)
    clf.familiar_min, clf.familiar_k = 0.8, 2
    near = clf.familiarity(torch.tensor([1.0, 0.05, 0.0]))
    far = clf.familiarity(torch.tensor([0.0, 0.0, 1.0]))
    assert clf.is_familiar(near) and not clf.is_familiar(far)
    clf.bank = None
    assert clf.is_familiar(clf.familiarity(torch.tensor([0.0, 0.0, 1.0])))  # no bank: no opinion


def test_translation_memory_refuses_broken_placeholders(tmp_path, monkeypatch):
    """A machine translation that mangles {name} or {dep:+.0f} must show the
    English, not crash the request that formats it (Home in Telugu once did)."""
    import json

    from app import i18n
    from app.kb import tr

    src = "{month} so far: {obs} mm ({dep:+.0f}%)."
    (tmp_path / "te.json").write_text(json.dumps({"strings": {
        src: "{month} వరకు: {obs} మిమీ ({డిప్ః +.0f}%).", "Rain": "వర్షం"}}), encoding="utf-8")
    monkeypatch.setattr(i18n, "MEMORY_DIR", tmp_path)
    i18n.memory.cache_clear()
    try:
        assert tr({"en": src, "hi": "x"}, "te") == src
        assert tr({"en": src, "hi": "x"}, "te").format(month="Sep", obs=1, dep=-2.0) == "Sep so far: 1 mm (-2%)."
        assert tr({"en": "Rain", "hi": "x"}, "te") == "వర్షం"
        assert i18n.protect(src)[1] == ["month", "obs", "dep:+.0f"]
    finally:
        i18n.memory.cache_clear()


@pytest.mark.parametrize(("text", "shown"), [
    ("Water is just plain water. It does not treat fall armyworm.", True),
    ("Kerosene is a fuel, not a pesticide, and can harm the crop.", True),
    ("Use Mancozeb instead for this disease.", False),      # names a chemical
    ("Try tricyclazole, it works well.", False),            # names a chemical
    ("Emamectin benzoate is the right choice here.", False),
    ("Spray 2 ml per litre of water.", False),              # a dose
    ("Apply 500 g per acre.", False),
])
def test_an_ai_note_may_explain_but_never_recommend(text, shown):
    """The spray check asks a model what an unrecognised input is. It is told to
    explain and never to prescribe; this is the part that does not rely on it
    having listened. A named chemical or any dose is dropped, and the farmer
    keeps the verified refusal."""
    from app.engine.labelcheck import safe_suggestion

    assert (safe_suggestion(kb, text) is not None) is shown


def test_a_pesticide_warning_is_never_shown_machine_translated_before_review(monkeypatch):
    """A mistranslated spray warning can hurt someone, so the spray check shows
    a machine-translated line only after a native speaker approved it; until
    then the farmer sees the English."""
    from app import i18n
    from app.kb import tr_reviewed

    line = {"en": "Do not spray this.", "hi": "इसका छिड़काव न करें।"}
    monkeypatch.setattr(i18n, "memory", lambda lang: {"Do not spray this.": "এটা স্প্রে করবেন না।"})
    monkeypatch.setattr(i18n, "reviewed", lambda lang: frozenset())
    assert tr_reviewed(line, "bn") == "Do not spray this."           # machine line, not yet approved
    assert tr_reviewed(line, "hi") == "इसका छिड़काव न करें।"            # authored language, as ever
    monkeypatch.setattr(i18n, "reviewed", lambda lang: frozenset({"Do not spray this."}))
    assert tr_reviewed(line, "bn") == "এটা স্প্রে করবেন না।"           # approved: now shown


def test_a_candidate_is_never_deployed_for_a_crop_that_failed_its_checks():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "ml" / "deploy_candidate.py"
    spec = importlib.util.spec_from_file_location("deploy_candidate", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    meta = {"classes": ["rice_blast", "cotton_wilt", "soybean_rust"], "deploy_checks": [
        {"check": "ICAR accuracy-when-advised within 1 point of deployed", "passed": True, "value": "0.98"},
        {"check": "cotton_wilt recall >= 0.70", "passed": True, "value": "0.92"},
        {"check": "soybean_rust recall >= 0.70", "passed": False, "value": "0.57"}]}
    assert mod.refusals(meta, ["rice", "cotton"]) == []
    assert any("soybean_rust" in r for r in mod.refusals(meta, ["cotton", "soybean"]))
    assert any("no classes for maize" in r for r in mod.refusals(meta, ["maize"]))
    icar_bad = meta | {"deploy_checks": [{"check": "ICAR test top-1", "passed": False, "value": "0.80"}]}
    assert mod.refusals(icar_bad, ["cotton"])  # rice and maize must never get worse
