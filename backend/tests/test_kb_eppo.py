"""Every target that is caused by a named organism carries its EPPO code.

An EPPO code is the identifier that does not move. Scientific names do: this
knowledge base says Magnaporthe oryzae and EPPO now says Pyricularia oryzae,
and PYRIOR means the same fungus under either. It is what links a diagnosis to
pesticide registrations and to any other service that speaks EPPO.

Every code here was resolved by name against gd.eppo.int rather than written
from memory, because memory got eleven of thirty-nine wrong -- USTIVI is
Microbotryum violaceum and not rice false smut, ALTEMA is Alternaria mali, and
PSDMGL is the soybean pathogen, not the rice one. These tests pin the shape and
the exclusions; they cannot re-check the authority offline, so the lookup is
recorded in the knowledge base alongside each code as the name EPPO gives it.
"""

import re

from app.kb import get_kb

CODE = re.compile(r"^[A-Z0-9]{5,6}$")

NO_CODE = {
    "cotton_wilt",                  # Fusarium oxysporum f.sp. vasinfectum OR Verticillium dahliae
    "maize_ear_rot",                # a Fusarium / Aspergillus complex
    "soybean_potassium_deficiency",  # a nutrient shortage, not an organism
    "cotton_leaf_reddening",        # cold nights, nutrition or waterlogging
    "cotton_herbicide_damage",      # herbicide drift
}


def test_every_target_caused_by_one_organism_has_a_code():
    missing = [t for t, v in get_kb().targets.items() if "eppo" not in v and t not in NO_CODE]
    assert missing == []


def test_the_targets_without_a_code_are_the_ones_with_no_single_organism():
    """A complex, a pair of fungi, or a nutrient shortage gets no code rather
    than a plausible-looking wrong one."""
    kb = get_kb()
    assert {t for t, v in kb.targets.items() if "eppo" not in v} == NO_CODE
    for t in NO_CODE:
        assert kb.targets[t]["kind"] in ("disease", "deficiency", "disorder")


def test_the_codes_are_well_formed_and_distinct_where_they_should_be():
    kb = get_kb()
    seen = {}
    for target, v in kb.targets.items():
        eppo = v.get("eppo")
        if not eppo:
            continue
        assert CODE.match(eppo["code"]), (target, eppo["code"])
        assert eppo["name"].strip(), target
        seen.setdefault(eppo["code"], []).append(target)
    # One code may legitimately cover two targets: Rhizoctonia solani causes
    # both rice sheath blight and maize banded leaf and sheath blight.
    shared = {c: ts for c, ts in seen.items() if len(ts) > 1}
    assert shared == {"RHIZSO": ["rice_sheath_blight", "maize_banded_leaf_sheath_blight"]}


def test_a_few_codes_are_the_ones_eppo_actually_returned():
    """Spot checks on the ones a guess got wrong, so a future edit cannot
    quietly reintroduce them."""
    kb = get_kb()
    assert kb.targets["rice_false_smut"]["eppo"]["code"] == "USTNVI"        # not USTIVI
    assert kb.targets["rice_hispa"]["eppo"]["code"] == "HISPAR"             # not DICLAR
    assert kb.targets["cotton_jassid"]["eppo"]["code"] == "EMPOBI"          # not AMRABI
    assert kb.targets["rice_bacterial_panicle_blight"]["eppo"]["code"] == "PSDMGM"
    assert kb.targets["soybean_bacterial_blight"]["eppo"]["code"] == "PSDMGL"


def test_the_code_reaches_a_screen():
    """target_view is what the app renders; a code nobody can see is filing."""
    view = get_kb().target_view("rice_blast", "en")
    assert view["eppo"] == {"code": "PYRIOR", "name": "Pyricularia oryzae"}
    assert get_kb().target_view("maize_ear_rot", "en")["eppo"] is None
