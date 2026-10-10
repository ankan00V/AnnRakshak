"""Every value the app can produce fits the column that stores it.

This exists because one did not. `diagnosis.model_version` was VARCHAR(80) and
v9's name is 82 characters, so against Postgres every photo upload raised
StringDataRightTruncation and the whole diagnosis was lost -- for a day, with
no row left behind to notice it by.

Nothing in the suite caught it, and nothing in the suite could have: SQLite
ignores a declared VARCHAR length and Postgres enforces it, so a width is only
ever wrong in production. These tests therefore compare the *declared width*
against the longest value the code can actually generate, rather than writing
rows and seeing what happens.

The rule they encode: a column fed by a growing vocabulary needs real headroom,
not two spare characters. A column that is exactly its content's size is only
safe when that size cannot change -- a hex digest, an ISO language code.
"""

import typing

import pytest
from sqlalchemy import String

from app.engine.gate import Outcome
from app.i18n import LANGS
from app.kb import get_kb
from app.models import MODEL_VERSION_LEN, Base
from app.routers.auth import DESIGNATIONS, QUALIFICATIONS, Irrigation, Role
from app.services import MESSAGES, SPECIAL_VERDICTS

HEADROOM = 1.5
"""A column must be at least half as wide again as the longest value its
vocabulary can currently produce. Anything tighter is a bet that the list has
stopped growing, which is the bet model_version lost."""


def width(table: str, column: str) -> int:
    col = Base.metadata.tables[table].columns[column]
    assert isinstance(col.type, String) and col.type.length, f"{table}.{column} is not a sized String"
    return col.type.length


# vocabulary -> the columns it is stored in
VOCABULARIES = [
    ("gate and case reasons", set(MESSAGES), [("diagnosis", "gate_reason"), ("case", "reason")]),
    ("gate outcomes", set(typing.get_args(Outcome)), [("diagnosis", "gate_outcome")]),
    ("roles", set(typing.get_args(Role)), [("app_user", "role"), ("otp_challenge", "role")]),
    ("irrigation kinds", set(typing.get_args(Irrigation)), [("farm", "irrigation")]),
    ("designations", set(DESIGNATIONS), [("expert_profile", "designation")]),
    ("qualifications", set(QUALIFICATIONS), [("expert_profile", "qualification")]),
    ("languages", set(LANGS), [("app_user", "lang"), ("farm", "lang")]),
]


@pytest.mark.parametrize(("name", "values", "columns"), VOCABULARIES,
                         ids=[v[0].replace(" ", "_") for v in VOCABULARIES])
def test_a_closed_vocabulary_fits_the_columns_it_is_stored_in(name, values, columns):
    longest = max(values, key=len)
    for table, column in columns:
        assert len(longest) <= width(table, column), (
            f"{name}: {longest!r} is {len(longest)} characters, "
            f"{table}.{column} holds {width(table, column)}")


def test_a_growing_vocabulary_keeps_real_headroom():
    """Languages and roles are closed sets, sized exactly, and that is fine.
    Reasons and labels are not: they grow whenever the pipeline learns a new
    way to decline or the model learns a new class."""
    kb = get_kb()
    growing = [
        ("reason codes", max(MESSAGES, key=len), [("diagnosis", "gate_reason"), ("case", "reason")]),
        ("target ids", max(kb.targets, key=len),
         [("problem", "target"), ("advisory", "target"), ("alert", "target"),
          ("label_prior", "target"), ("officer_advisory", "target")]),
        ("crop ids", max(kb.crops, key=len),
         [("farm", "crop"), ("label_prior", "crop"), ("officer_advisory", "crop")]),
        ("cue ids", max((c["id"] for c in kb.cues), key=len), [("observation", "cue_id")]),
        ("expert verdict labels", max({*kb.targets, *SPECIAL_VERDICTS}, key=len),
         [("confirmation", "final_label"), ("confirmation", "model_label")]),
    ]
    tight = []
    for name, longest, columns in growing:
        for table, column in columns:
            if width(table, column) < len(longest) * HEADROOM:
                tight.append(f"{table}.{column} is {width(table, column)} for {name} "
                             f"(longest {longest!r}, {len(longest)})")
    assert tight == [], "no room to grow:\n  " + "\n  ".join(tight)


def test_a_models_name_fits_the_column_that_stores_it():
    """The original bug. A model's name grows with every dataset folded in."""
    shipped = "icar+extra+more+paddy+asdid+local+cotton+thin-efficientnet_v2_s-warmstart-20261008"
    assert len(shipped) > 80, "the name that broke it must stay the example"
    for table in ("diagnosis", "live_scan"):
        assert width(table, "model_version") == MODEL_VERSION_LEN
        assert width(table, "model_version") >= len(shipped) + 40  # room for the next few datasets


def test_the_model_actually_deployed_here_fits_too():
    """Belt and braces: whatever checkpoint this machine has, its name must be
    storable. A model that cannot be recorded cannot be served."""
    from app.engine import vision

    version = vision.model_status()["model_version"]
    assert len(version) <= MODEL_VERSION_LEN, f"{version!r} is {len(version)} characters"


def test_a_geocoded_place_name_is_bounded_by_the_farm_it_is_written_into():
    """The one source that no vocabulary in this file covers.

    A geocoder's answer is arbitrary text from someone else's database, and
    confirming a field's position writes it straight into these columns. The
    bound lives in app.geo because that is the boundary; this keeps the two
    numbers equal, so widening a column without widening the check (or the
    reverse) fails here rather than in front of a farmer.
    """
    from app.geo import PLACE_LIMITS

    assert PLACE_LIMITS["state"] == width("farm", "state")
    assert PLACE_LIMITS["district"] == width("farm", "district")
    assert PLACE_LIMITS["village"] == width("farm", "village")
    assert PLACE_LIMITS["taluka"] == width("farm", "taluka")


def test_a_satellite_providers_polygon_id_is_bounded_by_its_column():
    """The other id this app stores on someone else's say-so. Theirs are
    24-character ObjectIds, but the response is not a contract."""
    from app.watch import POLYGON_ID_MAX

    assert POLYGON_ID_MAX == width("farm", "agro_polygon_id")


def test_columns_sized_exactly_to_their_contents_are_ones_that_cannot_grow():
    """A column with zero headroom is only safe when its content has a fixed
    length. These are the ones that legitimately do; anything else arriving at
    100% is a column about to overflow, so it has to be added here on purpose.
    """
    fixed = {
        ("app_user", "lang"): 2,            # ISO 639-1
        ("farm", "lang"): 2,
        ("otp_challenge", "code_hash"): 64,  # sha256, hex
        ("user_session", "token_hash"): 64,
        ("otp_challenge", "salt"): 32,
    }
    for (table, column), expected in fixed.items():
        assert width(table, column) == expected, f"{table}.{column} changed size; is it still fixed-length?"
