"""Compose a farmer-facing advisory from the knowledge base.

Deterministic: every sentence comes from the KB entry for the target, so there
is nothing to hallucinate and every advisory carries its citations. The ladder
order is re-checked here even though the KB loader already enforces it — a
structural promise should hold at the last step, not just the first.

Chemical rungs also carry a quantity worked out for the farm's own area, which
replaces a separate "dosage calculator": the dose, the water volume and the
product amount come from one place.
"""

from __future__ import annotations

from app.kb import KB, TIER_ORDER, tr, trl

UNIT_WORDS = {
    "g": {"en": "g per litre of water", "hi": "ग्राम प्रति लीटर पानी", "mr": "ग्रॅम प्रति लिटर पाणी"},
    "ml": {"en": "ml per litre of water", "hi": "मिली प्रति लीटर पानी", "mr": "मिली प्रति लिटर पाणी"},
}
FOR_AREA = {
    "en": "For your {area} acre field: about {qty} {unit} in {water} litres of water.",
    "hi": "आपके {area} एकड़ खेत के लिए: लगभग {qty} {unit}, {water} लीटर पानी में।",
    "mr": "तुमच्या {area} एकर शेतासाठी: सुमारे {qty} {unit}, {water} लिटर पाण्यात.",
}
LABEL_RULE = {
    "en": "Follow the printed label. Wear gloves and a mask; keep children and animals away.",
    "hi": "छपे लेबल का पालन करें। दस्ताने और मास्क पहनें; बच्चों और पशुओं को दूर रखें।",
    "mr": "छापील लेबलचे पालन करा. हातमोजे व मास्क वापरा; मुले व जनावरे दूर ठेवा.",
}
# The registered waiting period: the days between the last spray and harvest.
WAIT = {
    "en": "Last spray at least {days} days before harvest.",
    "hi": "आखिरी छिड़काव कटाई से कम से कम {days} दिन पहले करें।",
    "mr": "शेवटची फवारणी काढणीच्या किमान {days} दिवस आधी करा.",
}
# Organic options: a spray per acre with no registered water volume, a seed
# treatment, and a seedling root dip.
PER_ACRE = {
    "en": "About {n} {unit} per acre, mixed in water and sprayed evenly.",
    "hi": "प्रति एकड़ लगभग {n} {unit}, पानी में मिलाकर समान रूप से छिड़कें।",
    "mr": "एकरी सुमारे {n} {unit}, पाण्यात मिसळून सारखी फवारणी करा.",
}
FOR_AREA_DRY = {
    "en": "For your {area} acre field: about {qty} {unit}.",
    "hi": "आपके {area} एकड़ खेत के लिए: लगभग {qty} {unit}।",
    "mr": "तुमच्या {area} एकर शेतासाठी: सुमारे {qty} {unit}.",
}
HOME_KERNEL = {
    "en": "{n} g of kernel per litre of water: {tank} g for a 10-litre tank.",
    "hi": "प्रति लीटर पानी {n} ग्राम गिरी: 10 लीटर की टंकी के लिए {tank} ग्राम।",
    "mr": "प्रति लिटर पाण्यात {n} ग्रॅम गर: 10 लिटरच्या टाकीसाठी {tank} ग्रॅम.",
}
HOME_OIL = {
    "en": "{n} ml of neem oil and {d} ml of liquid detergent per litre of water: {tank} ml of oil for a 10-litre tank.",
    "hi": "प्रति लीटर पानी {n} मिली नीम तेल और {d} मिली तरल डिटर्जेंट: 10 लीटर की टंकी के लिए {tank} मिली तेल।",
    "mr": "प्रति लिटर पाण्यात {n} मिली निंबोळी तेल आणि {d} मिली द्रव डिटर्जंट: 10 लिटरच्या टाकीसाठी {tank} मिली तेल.",
}
PER_KG_SEED = {
    "en": "{n} {unit} per kg of seed.",
    "hi": "प्रति किलो बीज {n} {unit}।",
    "mr": "प्रति किलो बियाण्यास {n} {unit}.",
}
ROOT_DIP = {
    "en": "{n} {unit} per litre of water; dip the seedling roots for {minutes} minutes before transplanting.",
    "hi": "{n} {unit} प्रति लीटर पानी; रोपाई से पहले पौध की जड़ें {minutes} मिनट डुबोकर रखें।",
    "mr": "{n} {unit} प्रति लिटर पाणी; पुनर्लागवडीपूर्वी रोपांची मुळे {minutes} मिनिटे बुडवून ठेवा.",
}
HEALTHY = {
    "en": "No disease or pest found in this photo. Keep checking your crop every week.",
    "hi": "इस फोटो में कोई रोग या कीट नहीं मिला। हर हफ्ते फसल देखते रहें।",
    "mr": "या फोटोत कोणताही रोग किंवा कीड आढळली नाही. दर आठवड्याला पीक तपासत राहा.",
}


UNIT_SHORT = {
    "g": {"en": "g", "hi": "ग्राम", "mr": "ग्रॅम"},
    "ml": {"en": "ml", "hi": "मिली", "mr": "मिली"},
    "kg": {"en": "kg", "hi": "किलो", "mr": "किलो"},
    "L": {"en": "litres", "hi": "लीटर", "mr": "लिटर"},
}
SEED_TREATMENT = {
    "en": "Seed treatment: {n} {unit} per kg of seed{water}.",
    "hi": "बीज उपचार: प्रति किलो बीज {n} {unit}{water}।",
    "mr": "बीजप्रक्रिया: प्रति किलो बियाण्यास {n} {unit}{water}.",
}
SEED_WATER = {
    "en": ", mixed in {ml} ml of water",
    "hi": ", {ml} मिली पानी में मिलाकर",
    "mr": ", {ml} मिली पाण्यात मिसळून",
}
CHEM_NONE = {
    "en": "No pesticide is registered in India for this problem on this crop (CIB&RC list, 30.09.2026). Do not spray one: a product not registered for it has no tested dose and is not legal to use for it.",
    "hi": "भारत में इस फसल पर इस समस्या के लिए कोई कीटनाशक पंजीकृत नहीं है (CIB&RC सूची, 30.09.2026)। कोई दवा न छिड़कें: जो दवा इसके लिए पंजीकृत नहीं, उसकी कोई जाँची हुई मात्रा नहीं है और उसका इस्तेमाल कानूनी नहीं है।",
    "mr": "भारतात या पिकावर या समस्येसाठी कोणतेही कीटकनाशक नोंदणीकृत नाही (CIB&RC यादी, 30.09.2026). कोणतेही औषध फवारू नका: जे यासाठी नोंदणीकृत नाही, त्याचे तपासलेले प्रमाण नाही आणि ते वापरणे कायदेशीर नाही.",
}


class LadderOrderError(ValueError):
    pass


def _fmt(n: float) -> str:
    return f"{n:.0f}" if n >= 10 else f"{n:.1f}".rstrip("0").rstrip(".")


def _big(qty: float, unit: str) -> tuple[float, str]:
    """A field's worth in the unit a farmer buys it in: 24.3 kg, not 24300 g."""
    if unit == "g" and qty >= 1000:
        return qty / 1000, "kg"
    if unit == "ml" and qty >= 1000:
        return qty / 1000, "L"
    return qty, unit


def compose(kb: KB, target: str, lang: str, area_acres: float | None = None) -> dict:
    adv = kb.advisories[target]
    ladder_out = []
    for rung in adv["ladder"]:
        item: dict = {"tier": rung["tier"]}
        if rung["tier"] != "chemical":
            item["action"] = tr(rung["action"], lang)
            if rung.get("source"):
                item["source"] = rung["source"]
        else:
            pest = kb.pesticides[rung["ingredient"]]
            item |= {
                "ingredient": rung["ingredient"],
                "product": pest["name"],
                "class": pest["class"],
                "timing": tr(rung.get("timing"), lang),
                "verified": bool(rung.get("verified")),
                "label_rule": tr(LABEL_RULE, lang),
            }
            days = (rung.get("registration") or {}).get("waiting_days")
            if days:
                item["waiting"] = tr(WAIT, lang).format(days=days)
            item["use"] = rung.get("use", "spray")
            if rung.get("per_kg_seed"):
                sd = rung["per_kg_seed"]
                water = tr(SEED_WATER, lang).format(ml=_fmt(sd["water_ml"])) if sd.get("water_ml") else ""
                item["dose"] = tr(SEED_TREATMENT, lang).format(
                    n=_fmt(sd["amount"]), unit=tr(UNIT_SHORT[sd["unit"]], lang), water=water)
            elif rung.get("dose_per_litre") is not None and rung.get("dose_unit"):
                item |= _spray_dose(rung, lang, area_acres)
            else:
                item["dose"] = tr(rung.get("dose_basis"), lang)
        ladder_out.append(item)

    order = [TIER_ORDER[r["tier"]] for r in ladder_out]
    organic = [_organic(kb, o, lang, area_acres) for o in adv.get("organic", [])]
    homemade = [_homemade(kb, h, lang) for h in adv.get("homemade", [])]
    if order != sorted(order):
        raise LadderOrderError(f"{target}: ladder not chemical-last at composition")

    t = kb.targets[target]
    pest_or_disease = t.get("kind") in ("pest", "disease", "virus")
    return {
        "target": target,
        # deficiency and disorder are not pests: no organic or chemical pesticide applies
        "kind": t.get("kind"),
        "name": tr(t["names"], lang),
        "signature": tr(t["signature"], lang),
        "what_to_check": tr(adv["what_to_check"], lang),
        "what_to_avoid": [tr(x, lang) for x in adv["what_to_avoid"]],
        "ladder": ladder_out,
        # Registered bio-pesticides and neem products, before any chemical.
        "organic": organic,
        # Neem preparations made at home, where a government IPM source names them.
        "homemade": homemade,
        # A pest or disease no pesticide is registered for: said, not left blank.
        "chemical_none": tr(CHEM_NONE, lang)
        if pest_or_disease and not any(r["tier"] == "chemical" for r in ladder_out) else None,
        "expert_trigger": tr(adv["expert_trigger"], lang),
        "citations": adv["citations"],
        # ICAR-released products and tools for this problem, with who to call.
        "icar_options": [kb.tech_view(x, lang) for x in kb.technologies_for(target=target, audience="farmer")],
    }


def _spray_dose(rung: dict, lang: str, area_acres: float | None) -> dict:
    """Dose per litre, and the amount and water for the farm's own area."""
    dose, unit = rung["dose_per_litre"], rung["dose_unit"]
    out = {"dose": f"{_fmt(dose)} {tr(UNIT_WORDS[unit], lang)}"}
    water = rung.get("water_l_per_acre")
    if area_acres and water:
        litres = water * area_acres
        qty = dose * litres
        shown, shown_unit = _big(qty, unit)
        out["for_field"] = tr(FOR_AREA, lang).format(
            area=_fmt(area_acres), qty=_fmt(shown), unit=tr(UNIT_SHORT[shown_unit], lang), water=_fmt(litres)
        )
        out["quantity"] = {"amount": round(qty, 1), "unit": unit, "water_l": round(litres)}
    return out


def _organic(kb: KB, o: dict, lang: str, area_acres: float | None) -> dict:
    prod = kb.pesticides[o["ingredient"]]
    reg = o.get("registration") or {}
    item: dict = {
        "ingredient": o["ingredient"],
        "product": prod["name"],
        "kind": prod.get("kind", "bio-agent"),
        "use": o["use"],
        "timing": tr(o.get("timing"), lang),
        "source": reg.get("source"),
    }
    if reg.get("waiting_days"):
        item["waiting"] = tr(WAIT, lang).format(days=reg["waiting_days"])
    if o["use"] == "root_dip":
        unit = o["dose_unit"]
        item["dose"] = tr(ROOT_DIP, lang).format(
            n=_fmt(o["dose_per_litre"]), unit=tr(UNIT_SHORT[unit], lang), minutes=o["minutes"])
    elif o["use"] == "seed":
        s = o["per_kg_seed"]
        item["dose"] = tr(PER_KG_SEED, lang).format(n=_fmt(s["amount"]), unit=tr(UNIT_SHORT[s["unit"]], lang))
    elif o.get("per_acre"):
        a = o["per_acre"]
        unit = tr(UNIT_SHORT[a["unit"]], lang)
        item["dose"] = tr(PER_ACRE, lang).format(n=_fmt(a["amount"]), unit=unit)
        if area_acres:
            qty = a["amount"] * area_acres
            shown, shown_unit = _big(qty, a["unit"])
            item["for_field"] = tr(FOR_AREA_DRY, lang).format(
                area=_fmt(area_acres), qty=_fmt(shown), unit=tr(UNIT_SHORT[shown_unit], lang))
            item["quantity"] = {"amount": round(qty, 1), "unit": a["unit"], "water_l": None}
    else:
        item |= _spray_dose(o, lang, area_acres)
    return item


def _homemade(kb: KB, h: dict, lang: str) -> dict:
    prep = kb.homemade[h["prep"]]
    n = h["per_litre"]["amount"]
    if h["per_litre"]["unit"] == "g":
        dose = tr(HOME_KERNEL, lang).format(n=_fmt(n), tank=_fmt(n * 10))
    else:
        dose = tr(HOME_OIL, lang).format(n=_fmt(n), d=_fmt(h.get("detergent_ml_per_litre", 2)), tank=_fmt(n * 10))
    return {
        "prep": h["prep"],
        "name": tr(prep["name"], lang),
        "dose": dose,
        "timing": tr(h["timing"], lang),
        "recipe": trl(prep["recipe"], lang),
        "source": h["source"],
        "recipe_source": prep.get("recipe_source"),
    }


def healthy_note(lang: str) -> str:
    return tr(HEALTHY, lang)
