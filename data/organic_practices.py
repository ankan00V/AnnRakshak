"""Organic steps for the problems whose advisories had too few: sourced field
practices and natural control, written into the advisories' ladders.

Every disease and pest the app advises on has to give the farmer an organic
route as well as a chemical one. Where the advice was one field step and
nothing else (false smut was one: gather the smut balls and bury them), these
add what the government IPM packages and IRRI recommend for that problem —
seed treatments, named resistant varieties, water and nitrogen management,
natural enemies, trap crops. Nothing is added that a source does not name for
that problem, and each step carries its source.

  NCIPM & DPPQS, Integrated Pest Management Packages for Rice, Maize and Soybean
      (niphm.gov.in/IPMPackages/; raw copies in data/raw/ipm/): resistant and
      tolerant varieties by disease, seed treatment with Trichoderma or
      Pseudomonas for seed-borne disease, Trichoderma harzianum seed treatment
      for banded leaf and sheath blight, dhaincha as a trap crop for girdle
      beetle, conservation of natural enemies.
  IRRI Rice Knowledge Bank, False smut: alternate wetting and drying, moderate
      nitrogen, field sanitation, hot-water seed treatment at 52 °C for 10 min.
  PAU Ludhiana, Package of Practices for Crops of Punjab, Kharif 2026 (raw copy
      in data/raw/organic/pp_kharif.pdf): Trichogramma cards for rice stem
      borers and leaf folder (organic farming chapter) and for maize borer, the
      rope for leaf folder, tapping the plants to count planthoppers, clipping
      hispa-infested seedling tips, borer-stubble destruction in maize, timely
      and even sowing against fall armyworm, and the pheromone traps for pink
      and American bollworm.

Each step says who stands behind it (`backing`): "recommended" when the source
is ICAR, an agricultural university or the government IPM packages ICAR's NCIPM
writes with DPPQS. IRRI is none of these, so its steps carry no level.

Where a PAU step gives numbers for something a hand-written step already said
without a source (a Trichogramma release, a pheromone trap), the hand-written
step is taken out (SUPERSEDED) so the farmer does not read two doses for one
thing.

Re-runnable: the steps it added before are taken out and written again.

    .venv/bin/python data/organic_practices.py   -> backend/kb/advisories.json
"""

from __future__ import annotations

import json
from pathlib import Path

KB = Path(__file__).resolve().parents[1] / "backend" / "kb"
TAG = "organic_practices"

RICE = "NCIPM & DPPQS, Integrated Pest Management Package for Rice"
MAIZE = "NCIPM & DPPQS, Integrated Pest Management Package for Maize"
SOY = "NCIPM & DPPQS, Integrated Pest Management Package for Soybean"
IRRI = "IRRI Rice Knowledge Bank, False smut"
PAU = "PAU Ludhiana, Package of Practices for Crops of Punjab, Kharif 2026"
PAU_ORGANIC = f"{PAU} (organic farming chapter)"

TRICHO_RICE = {
    "en": "From 30 days after transplanting, staple Trichogramma egg cards: two cards each of T. japonicum and T. chilonis per acre, 5 to 6 times, a week apart. Cut each card into 20 strips and staple them under the leaves at 40 spots across the acre, in the evening.",
    "hi": "रोपाई के 30 दिन बाद से ट्राइकोग्रामा अंडा कार्ड लगाएँ: प्रति एकड़ टी. जैपोनिकम और टी. चिलोनिस के दो-दो कार्ड, एक-एक हफ्ते के अंतर पर 5 से 6 बार। हर कार्ड को 20 पट्टियों में काटें और शाम को एकड़ भर में 40 जगह पत्तियों के नीचे स्टेपल करें।",
    "mr": "पुनर्लागवडीनंतर 30 दिवसांपासून ट्रायकोग्रामा अंडी कार्ड लावा: एकरी टी. जॅपोनिकम आणि टी. चिलोनिसचे प्रत्येकी दोन कार्ड, आठवड्याच्या अंतराने 5 ते 6 वेळा. प्रत्येक कार्डाच्या 20 पट्ट्या कापा आणि संध्याकाळी एकरभर 40 ठिकाणी पानांच्या खाली स्टेपल करा.",
}

# Hand-written steps a sourced step below replaces, by their English text.
SUPERSEDED = {
    "rice_yellow_stem_borer": ["Release Trichogramma japonicum at 50,000 per hectare when moths are seen in traps."],
    "rice_white_stem_borer": ["Release Trichogramma japonicum at 50,000 per hectare when moths are seen in traps."],
    "rice_leaf_folder": [
        "Release the egg parasitoid Trichogramma chilonis (cards at 50,000 per hectare), weekly for 4–6 weeks.",
        "Avoid excess nitrogen; drag a rope across the crop to shake the larvae out of the folds.",
    ],
    "maize_stem_borer": ["Release Trichogramma chilonis cards (about 1 lakh per hectare) from 10 days after sowing."],
    "cotton_pink_bollworm": ["Install pheromone traps at 5 per hectare from 45 days after sowing to watch moth numbers."],
}

STEPS: dict[str, list[tuple[str, dict, str]]] = {
    "rice_false_smut": [
        ("cultural", {
            "en": "Alternate wetting and drying instead of keeping the field flooded, keep nitrogen moderate, and after harvest clear the infected panicles and stubble from the field.",
            "hi": "खेत में लगातार पानी भरा रखने के बजाय बारी-बारी से गीला-सूखा करें, नाइट्रोजन सीमित रखें, और कटाई के बाद संक्रमित बालियाँ और ठूँठ खेत से हटा दें।",
            "mr": "शेतात सतत पाणी साचवण्याऐवजी आलटून-पालटून ओले-कोरडे करा, नत्र मर्यादित ठेवा, आणि कापणीनंतर बाधित लोंब्या व खुंट शेतातून काढून टाका.",
        }, IRRI),
        ("biological", {
            "en": "Next season, soak the seed in hot water at 52 °C for 10 minutes, or coat it with Pseudomonas fluorescens at 10 g per kg of seed.",
            "hi": "अगले मौसम में बीज को 52 °C गर्म पानी में 10 मिनट भिगोएँ, या प्रति किलो बीज 10 ग्राम स्यूडोमोनास फ्लोरेसेंस से उपचारित करें।",
            "mr": "पुढील हंगामात बियाणे 52 °C गरम पाण्यात 10 मिनिटे भिजवा, किंवा प्रति किलो बियाण्यास 10 ग्रॅम स्युडोमोनास फ्लुरोसन्स लावा.",
        }, f"{IRRI}; {RICE} (seed treatment for seed-borne disease)"),
    ],
    "rice_tungro": [
        ("cultural", {
            "en": "Tolerant varieties named in the national IPM package: Vikramarya, Nidhi, Amulya, Dinesh, Lakshmi and Nalini. Transplant seedlings older than 3 weeks, at the same time as your neighbours.",
            "hi": "राष्ट्रीय IPM पैकेज में बताई गई सहनशील किस्में: विक्रमार्य, निधि, अमूल्य, दिनेश, लक्ष्मी और नलिनी। 3 सप्ताह से पुरानी पौध रोपें, पड़ोसियों के साथ एक ही समय पर।",
            "mr": "राष्ट्रीय IPM पॅकेजमधील सहनशील वाण: विक्रमार्य, निधी, अमूल्य, दिनेश, लक्ष्मी आणि नलिनी. 3 आठवड्यांपेक्षा जुनी रोपे लावा, शेजाऱ्यांसोबत एकाच वेळी.",
        }, RICE),
        ("biological", {
            "en": "Protect the spiders, mirid bugs and other predators that eat the green leafhopper which spreads tungro: no broad-spectrum sprays early in the season.",
            "hi": "टुंग्रो फैलाने वाले हरे फुदके को खाने वाली मकड़ियों, मिरिड बग और दूसरे शिकारी कीटों को बचाएँ: मौसम की शुरुआत में व्यापक असर वाले छिड़काव न करें।",
            "mr": "टुंग्रो पसरवणाऱ्या हिरव्या तुडतुड्याला खाणारे कोळी, मिरिड ढेकूण आणि इतर भक्षक वाचवा: हंगामाच्या सुरुवातीला सर्वव्यापी फवारण्या करू नका.",
        }, RICE),
    ],
    "maize_common_rust": [
        ("cultural", {
            "en": "Resistant hybrids named in the national IPM package: Buland, Sheetal, HHM 1, HHM 2, HQPM 1 and Nithyashree.",
            "hi": "राष्ट्रीय IPM पैकेज में बताए गए प्रतिरोधी संकर: बुलंद, शीतल, HHM 1, HHM 2, HQPM 1 और नित्यश्री।",
            "mr": "राष्ट्रीय IPM पॅकेजमधील प्रतिकारक संकरित वाण: बुलंद, शीतल, HHM 1, HHM 2, HQPM 1 आणि नित्यश्री.",
        }, MAIZE),
    ],
    "maize_maydis_leaf_blight": [
        ("cultural", {
            "en": "Resistant varieties named in the national IPM package: HM 10, PAU 352, Malviya Hybrid Makka 2, PEMH 1, PEMH 5, HQPM 1, HQPM 4, HQPM 5, HQPM 7, Shaktiman 3, Shaktiman 4 and HSC 1.",
            "hi": "राष्ट्रीय IPM पैकेज में बताई गई प्रतिरोधी किस्में: HM 10, PAU 352, मालवीय हाइब्रिड मक्का 2, PEMH 1, PEMH 5, HQPM 1, HQPM 4, HQPM 5, HQPM 7, शक्तिमान 3, शक्तिमान 4 और HSC 1।",
            "mr": "राष्ट्रीय IPM पॅकेजमधील प्रतिकारक वाण: HM 10, PAU 352, मालवीय हायब्रिड मका 2, PEMH 1, PEMH 5, HQPM 1, HQPM 4, HQPM 5, HQPM 7, शक्तिमान 3, शक्तिमान 4 आणि HSC 1.",
        }, MAIZE),
    ],
    "maize_downy_mildew": [
        ("cultural", {
            "en": "Sow before the rains set in, and do not sow maize next to sorghum or after it. Resistant varieties in the national IPM package: PEMH 5, Bio 9636, DMH 1, COH(M) 4, COH(M) 5 and Nithyashree.",
            "hi": "बारिश शुरू होने से पहले बुवाई करें, और मक्का को ज्वार के पास या ज्वार के बाद न बोएँ। राष्ट्रीय IPM पैकेज की प्रतिरोधी किस्में: PEMH 5, बायो 9636, DMH 1, COH(M) 4, COH(M) 5 और नित्यश्री।",
            "mr": "पाऊस सुरू होण्यापूर्वी पेरणी करा, आणि मका ज्वारीच्या शेजारी किंवा ज्वारीनंतर पेरू नका. राष्ट्रीय IPM पॅकेजमधील प्रतिकारक वाण: PEMH 5, बायो 9636, DMH 1, COH(M) 4, COH(M) 5 आणि नित्यश्री.",
        }, MAIZE),
    ],
    "maize_banded_leaf_sheath_blight": [
        ("cultural", {
            "en": "Resistant varieties named in the national IPM package: Pratap Kanchan 2, Pratap Makka 3, Pratap Makka 5, Shaktiman 1 and Shaktiman 3.",
            "hi": "राष्ट्रीय IPM पैकेज में बताई गई प्रतिरोधी किस्में: प्रताप कंचन 2, प्रताप मक्का 3, प्रताप मक्का 5, शक्तिमान 1 और शक्तिमान 3।",
            "mr": "राष्ट्रीय IPM पॅकेजमधील प्रतिकारक वाण: प्रताप कांचन 2, प्रताप मका 3, प्रताप मका 5, शक्तिमान 1 आणि शक्तिमान 3.",
        }, MAIZE),
        ("biological", {
            "en": "Next season, coat the seed with Trichoderma harzianum 2% WP at 20 g per kg of seed.",
            "hi": "अगले मौसम में प्रति किलो बीज 20 ग्राम ट्राइकोडर्मा हार्जियानम 2% WP से बीज उपचार करें।",
            "mr": "पुढील हंगामात प्रति किलो बियाण्यास 20 ग्रॅम ट्रायकोडर्मा हर्जियानम 2% WP लावा.",
        }, MAIZE),
    ],
    "maize_turcicum_leaf_blight": [
        ("cultural", {
            "en": "Resistant varieties named in the national IPM package: PEMH 5, Vivek 21, Vivek 23, Vivek 25 and Pratap Kanchan 2; Nithyashree for Karnataka and Andhra Pradesh.",
            "hi": "राष्ट्रीय IPM पैकेज में बताई गई प्रतिरोधी किस्में: PEMH 5, विवेक 21, विवेक 23, विवेक 25 और प्रताप कंचन 2; कर्नाटक और आंध्र प्रदेश के लिए नित्यश्री।",
            "mr": "राष्ट्रीय IPM पॅकेजमधील प्रतिकारक वाण: PEMH 5, विवेक 21, विवेक 23, विवेक 25 आणि प्रताप कांचन 2; कर्नाटक व आंध्र प्रदेशासाठी नित्यश्री.",
        }, MAIZE),
    ],
    "maize_curvularia_leaf_spot": [
        ("cultural", {
            "en": "Before sowing, plough deep two or three times, 10 to 15 days apart, to bury the old crop debris and weeds; sow certified seed and throw out light, chaffy or damaged seed.",
            "hi": "बुवाई से पहले 10 से 15 दिन के अंतर पर दो-तीन बार गहरी जुताई करें, ताकि पुरानी फसल के अवशेष और खरपतवार दब जाएँ; प्रमाणित बीज बोएँ और हल्के, खोखले या टूटे बीज निकाल दें।",
            "mr": "पेरणीपूर्वी 10 ते 15 दिवसांच्या अंतराने दोन-तीन वेळा खोल नांगरट करा, म्हणजे जुन्या पिकाचे अवशेष व तण गाडले जातील; प्रमाणित बियाणे पेरा आणि हलके, पोचट किंवा तुटलेले बी काढून टाका.",
        }, f"{MAIZE} (cultural practices for diseases)"),
    ],
    "maize_ear_rot": [
        ("cultural", {
            "en": "Do not let the crop go short of water from flowering to grain filling, and do not give high nitrogen with too little potash.",
            "hi": "फूल आने से दाना भरने तक फसल में पानी की कमी न होने दें, और कम पोटाश के साथ ज़्यादा नाइट्रोजन न दें।",
            "mr": "फुलोऱ्यापासून दाणे भरेपर्यंत पिकाला पाण्याचा ताण पडू देऊ नका, आणि कमी पालाशसोबत जास्त नत्र देऊ नका.",
        }, f"{MAIZE} (cultural practices for diseases)"),
    ],
    "rice_yellow_stem_borer": [("biological", TRICHO_RICE, PAU_ORGANIC)],
    "rice_white_stem_borer": [("biological", TRICHO_RICE, PAU_ORGANIC)],
    "rice_leaf_folder": [
        ("cultural", {
            "en": "Do not over-fertilise with nitrogen: heavily fertilised plots draw the moths to lay their eggs.",
            "hi": "नाइट्रोजन खाद ज़्यादा न डालें: ज़्यादा खाद वाले खेत पतंगों को अंडे देने के लिए खींचते हैं।",
            "mr": "नत्र खत जास्त देऊ नका: जास्त खत दिलेली शेते पतंगांना अंडी घालण्यासाठी आकर्षित करतात.",
        }, RICE),
        ("cultural", {
            "en": "Before flowering, with water standing in the field, pass a 20–30 metre coir or jute rope across the top of the crop, forwards and then back, to shake the larvae out of the folds.",
            "hi": "फूल आने से पहले, खेत में पानी भरा रहते हुए, 20–30 मीटर लंबी नारियल या जूट की रस्सी फसल के ऊपर से आगे और फिर पीछे खींचें, ताकि मुड़ी पत्तियों से सूंडियाँ गिर जाएँ।",
            "mr": "फुलोऱ्यापूर्वी, शेतात पाणी साचलेले असताना, 20–30 मीटर लांब काथ्याचा किंवा तागाचा दोर पिकाच्या वरून पुढे आणि मग मागे ओढा, म्हणजे गुंडाळलेल्या पानांतून अळ्या खाली पडतील.",
        }, PAU),
        ("biological", TRICHO_RICE, PAU_ORGANIC),
    ],
    "rice_brown_planthopper": [
        ("cultural", {
            "en": "From a month after transplanting, tilt a few plants every week and tap their base 2 or 3 times. Act when 5 or more hoppers per hill fall onto the water.",
            "hi": "रोपाई के एक महीने बाद से, हर हफ्ते कुछ पौधों को थोड़ा झुकाकर उनके निचले हिस्से पर 2-3 बार थपथपाएँ। जब प्रति झुंड 5 या ज़्यादा फुदके पानी पर गिरें, तब उपाय करें।",
            "mr": "पुनर्लागवडीनंतर एका महिन्यापासून, दर आठवड्याला काही चुडे थोडे झुकवून त्यांच्या बुडख्यावर 2-3 वेळा टॅप करा. प्रति चूड 5 किंवा जास्त तुडतुडे पाण्यावर पडल्यास उपाय करा.",
        }, PAU),
    ],
    "rice_hispa": [
        ("cultural", {
            "en": "If the attack starts in the nursery, clip off and destroy the leaf tips of the affected seedlings before transplanting.",
            "hi": "अगर हमला नर्सरी में शुरू हो, तो रोपाई से पहले प्रभावित पौध की पत्तियों के सिरे काटकर नष्ट करें।",
            "mr": "प्रादुर्भाव रोपवाटिकेतच सुरू झाल्यास, पुनर्लागवडीपूर्वी बाधित रोपांच्या पानांची टोके कापून नष्ट करा.",
        }, PAU),
    ],
    "maize_stem_borer": [
        ("cultural", {
            "en": "After harvest, plough the field and destroy the stubble, stalks and cobs where the borer larvae spend the winter. While hoeing, pull out and destroy badly bored plants.",
            "hi": "कटाई के बाद खेत जोतें और ठूंठ, डंठल और भुट्टे नष्ट करें, जिनमें तना छेदक की सूंडियाँ सर्दी बिताती हैं। निराई-गुड़ाई के समय बुरी तरह छेदे गए पौधे उखाड़कर नष्ट करें।",
            "mr": "काढणीनंतर शेत नांगरा आणि खोडकिडीच्या अळ्या हिवाळा घालवतात ते खुंट, धाटे आणि कणसे नष्ट करा. खुरपणी करताना जास्त पोखरलेली झाडे उपटून नष्ट करा.",
        }, PAU),
        ("biological", {
            "en": "Staple Trichogramma chilonis egg cards twice: 40,000 parasitised eggs per acre on the 10-day-old crop, and again 7 days later. Cut the cards into 40 strips and staple them under the central whorl leaves in the evening. Not on rainy days.",
            "hi": "ट्राइकोग्रामा चिलोनिस अंडा कार्ड दो बार लगाएँ: 10 दिन की फसल पर प्रति एकड़ 40,000 परजीवित अंडे, और फिर 7 दिन बाद। कार्डों को 40 पट्टियों में काटें और शाम को बीच की पोंगली की पत्तियों के नीचे स्टेपल करें। बारिश वाले दिन नहीं।",
            "mr": "ट्रायकोग्रामा चिलोनिस अंडी कार्ड दोनदा लावा: 10 दिवसांच्या पिकावर एकरी 40,000 परजीवीग्रस्त अंडी, आणि पुन्हा 7 दिवसांनी. कार्डांच्या 40 पट्ट्या कापा आणि संध्याकाळी मधल्या पोंग्याच्या पानांखाली स्टेपल करा. पावसाच्या दिवशी नाही.",
        }, PAU),
    ],
    "maize_fall_armyworm": [
        ("cultural", {
            "en": "Sow at the recommended time, and do not sow maize at different times in neighbouring fields: it lets the pest move from field to field. Look for the egg masses, covered in hairs and easy to see on the leaves, and destroy them.",
            "hi": "सिफारिश किए गए समय पर बोएँ, और पास के खेतों में अलग-अलग समय पर मक्का न बोएँ: इससे कीट एक खेत से दूसरे में जाता है। पत्तियों पर बालों से ढके, आसानी से दिखने वाले अंडों के गुच्छे ढूँढकर नष्ट करें।",
            "mr": "शिफारस केलेल्या वेळी पेरा, आणि शेजारच्या शेतांत वेगवेगळ्या वेळी मका पेरू नका: त्यामुळे कीड एका शेतातून दुसऱ्यात जाते. पानांवर केसांनी झाकलेले, सहज दिसणारे अंड्यांचे पुंजके शोधून नष्ट करा.",
        }, PAU),
    ],
    "cotton_pink_bollworm": [
        ("cultural", {
            "en": "From the start of flowering, watch moth numbers with a Sticka or Delta trap baited with gossyplure: one trap per hectare, 15 cm above the crop, lure changed every 15 days.",
            "hi": "फूल आने की शुरुआत से, गॉसिप्ल्योर वाले स्टिका या डेल्टा ट्रैप से पतंगों की संख्या देखें: प्रति हेक्टेयर एक ट्रैप, फसल से 15 सेमी ऊपर, हर 15 दिन में ल्योर बदलें।",
            "mr": "फुलोऱ्याच्या सुरुवातीपासून, गॉसिप्लूर असलेल्या स्टिका किंवा डेल्टा सापळ्याने पतंगांची संख्या पाहा: हेक्टरी एक सापळा, पिकाच्या 15 सेमी वर, दर 15 दिवसांनी ल्युअर बदला.",
        }, PAU),
    ],
    "cotton_american_bollworm": [
        ("cultural", {
            "en": "From the start of flowering, watch moth numbers with Sleeve or Moth-catch pheromone traps holding at least 2 mg of pheromone: two traps per hectare, 15 cm above the crop, lure changed every 15 days.",
            "hi": "फूल आने की शुरुआत से, कम से कम 2 मिग्रा फेरोमोन वाले स्लीव या मॉथ-कैच ट्रैप से पतंगों की संख्या देखें: प्रति हेक्टेयर दो ट्रैप, फसल से 15 सेमी ऊपर, हर 15 दिन में ल्योर बदलें।",
            "mr": "फुलोऱ्याच्या सुरुवातीपासून, किमान 2 मिग्रॅ फेरोमोन असलेल्या स्लीव्ह किंवा मॉथ-कॅच सापळ्यांनी पतंगांची संख्या पाहा: हेक्टरी दोन सापळे, पिकाच्या 15 सेमी वर, दर 15 दिवसांनी ल्युअर बदला.",
        }, PAU),
    ],
    "soybean_girdle_beetle": [
        ("cultural", {
            "en": "Grow dhaincha as a trap crop around the field: the beetles gather on it, away from the soybean.",
            "hi": "खेत के चारों ओर ढैंचा को फँसाऊ फसल के रूप में उगाएँ: भृंग सोयाबीन से हटकर उस पर जमा होते हैं।",
            "mr": "शेताभोवती धैंचा सापळा पीक म्हणून लावा: भुंगे सोयाबीनपासून दूर त्यावर जमतात.",
        }, SOY),
    ],
}


def backing(source: str) -> str | None:
    """Recommended when ICAR, an agricultural university or the ICAR-NCIPM and
    DPPQS packages stand behind it; IRRI alone is none of those."""
    return "recommended" if any(k in source for k in ("NCIPM", "ICAR", "PAU", "TNAU", "DPPQS")) else None


def main() -> None:
    adv = json.loads((KB / "advisories.json").read_text())
    added = 0
    for tid, entry in adv.items():
        if tid.startswith("_"):
            continue
        gone = set(SUPERSEDED.get(tid, []))
        entry["ladder"] = [r for r in entry["ladder"] if r.get("added_by") != TAG
                           and (r.get("action") or {}).get("en") not in gone]
    for tid, steps in STEPS.items():
        ladder = adv[tid]["ladder"]
        for tier, action, source in steps:
            rung = {"tier": tier, "action": action, "source": source, "added_by": TAG}
            if backing(source):
                rung["backing"] = backing(source)
            # keep the ladder in order: after the last rung of the same or an earlier tier
            rank = {"cultural": 0, "biological": 1, "chemical": 2}
            at = max((i + 1 for i, r in enumerate(ladder) if rank[r["tier"]] <= rank[tier]), default=0)
            ladder.insert(at, rung)
            added += 1
    (KB / "advisories.json").write_text(json.dumps(adv, indent=1, ensure_ascii=False) + "\n")
    print(f"{added} organic steps on {len(STEPS)} problems")


if __name__ == "__main__":
    main()
