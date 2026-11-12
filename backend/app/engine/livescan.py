"""Live field walk: a guided, real-time camera session ("a video call with the AI").

The phone keeps the camera open and sends a small still frame about once a
second. Nothing is recorded: each frame is checked and discarded, except the
few that become evidence for a finding. The session:

  1. guides the farmer through views of the field (overview, a whole plant,
     leaf close-ups top and underside, the plant base, a second spot);
  2. checks every frame live (sharp? bright enough? crop in view? a new view?)
     and coaches until the step has enough good views;
  3. runs the photo model on close-ups only, and accumulates evidence per
     problem across views;
  4. adds a step when it glimpses something ("show me more leaves with those
     spots"), and asks the Doubt Doctor question when two problems compete;
  5. reports a problem as seen only when at least two separate close-ups agree
     above the same 0.70 gate the photo path uses. A single weak sighting goes
     to an expert, never to a spray.

Pure: no I/O. The caller injects the classifier and persists the result.
"""

from __future__ import annotations

import io
from collections.abc import Callable
from dataclasses import dataclass, field
from statistics import median

import numpy as np
from PIL import Image

from app.config import FLOOR, GATE, MARGIN, gate_for
from app.engine.gate import crop_of, is_healthy
from app.engine.vision import MAX_PIXELS, vegetation_fraction
from app.kb import tr

# --- frame quality -----------------------------------------------------------
WORK = 256                 # px, long side used for measuring
DARK, GLARE = 45.0, 235.0  # mean brightness (0-255) outside which a frame is unusable
# Laplacian variance at WORK px. Calibrated on real photos: sharp field close-ups
# (CCMT, ICAR) score >= 26 at the 5th percentile; the same photos blurred by a
# 2 px Gaussian score 6-22 (ICAR ~22 at p5 only because its originals are huge).
SHARP_SCENE = 15.0
SHARP_CLOSE = 35.0
NOVELTY = 7.0              # mean abs difference (0-255) on a 24 px thumb to count as a new view

KINDS = {
    #          min vegetation, min sharpness, run the photo model
    "scene": (0.20, SHARP_SCENE, False),
    "plant": (0.30, SHARP_SCENE, False),
    "close": (0.40, SHARP_CLOSE, True),  # insects on a leaf show less green than a bare leaf
    "base": (0.06, SHARP_SCENE, False),
}

TEXT = {
    # What the walk asks for, step by step. Spoken aloud, so each is one plain
    # sentence a farmer can act on without looking at the screen.
    "overview": {
        "en": "Stand at the edge of your field and slowly show me the whole field.",
        "hi": "खेत के किनारे खड़े होकर धीरे-धीरे पूरा खेत दिखाइए।",
        "mr": "शेताच्या कडेला उभे राहून हळूहळू संपूर्ण शेत दाखवा.",
        "bn": "মাঠের কিনারায় দাঁড়ান এবং ধীরে ধীরে পুরো মাঠটি দেখান।",
        "ta": "வயலின் ஓரத்தில் நின்று, மெதுவாக வயல் முழுவதையும் காட்டுங்கள்.",
        "te": "పొలం అంచున నిలబడి, నెమ్మదిగా పొలం మొత్తం చూపించండి.",
        "kn": "ಹೊಲದ ಅಂಚಿನಲ್ಲಿ ನಿಂತು, ನಿಧಾನವಾಗಿ ಇಡೀ ಹೊಲವನ್ನು ತೋರಿಸಿ.",
        "ml": "വയലിന്റെ അരികിൽ നിന്ന് പതുക്കെ വയൽ മുഴുവൻ കാണിക്കുക.",
        "gu": "ખેતરની કિનારે ઊભા રહીને ધીમે ધીમે આખું ખેતર બતાવો.",
        "pa": "ਖੇਤ ਦੇ ਕਿਨਾਰੇ ਖੜ੍ਹੇ ਹੋ ਕੇ ਹੌਲੀ-ਹੌਲੀ ਸਾਰਾ ਖੇਤ ਦਿਖਾਓ।",
    },
    "plant": {
        "en": "Walk into the field. Show me one whole plant, from top to bottom.",
        "hi": "खेत के अंदर जाइए। एक पूरा पौधा ऊपर से नीचे तक दिखाइए।",
        "mr": "शेतात आत चला. एक संपूर्ण रोप वरपासून खालपर्यंत दाखवा.",
        "bn": "মাঠের ভিতরে যান। একটি গোটা গাছ উপর থেকে নিচ পর্যন্ত দেখান।",
        "ta": "வயலுக்குள் நடந்து செல்லுங்கள். ஒரு செடியை மேலிருந்து கீழ் வரை முழுவதுமாகக் காட்டுங்கள்.",
        "te": "పొలంలోకి నడవండి. ఒక మొక్కను పై నుంచి కింది వరకు పూర్తిగా చూపించండి.",
        "kn": "ಹೊಲದ ಒಳಗೆ ನಡೆಯಿರಿ. ಒಂದು ಗಿಡವನ್ನು ಮೇಲಿಂದ ಕೆಳಗಿನವರೆಗೆ ಪೂರ್ತಿ ತೋರಿಸಿ.",
        "ml": "വയലിനുള്ളിലേക്ക് നടക്കുക. ഒരു ചെടി മുകളിൽ നിന്ന് താഴെ വരെ മുഴുവനായി കാണിക്കുക.",
        "gu": "ખેતરની અંદર ચાલો. એક આખો છોડ ઉપરથી નીચે સુધી બતાવો.",
        "pa": "ਖੇਤ ਦੇ ਅੰਦਰ ਜਾਓ। ਇੱਕ ਪੂਰਾ ਬੂਟਾ ਉੱਪਰੋਂ ਹੇਠਾਂ ਤੱਕ ਦਿਖਾਓ।",
    },
    "leaf_top": {
        "en": "Bring the camera close to the leaves, about one hand away. Show the top side.",
        "hi": "कैमरा पत्तियों के पास लाइए, लगभग एक हाथ दूर। पत्ती का ऊपरी भाग दिखाइए।",
        "mr": "कॅमेरा पानांच्या जवळ आणा, सुमारे एक हात अंतरावर. पानाची वरची बाजू दाखवा.",
        "bn": "ক্যামেরাটি পাতার কাছে আনুন, প্রায় এক হাত দূরে। পাতার উপরের দিক দেখান।",
        "ta": "கேமராவை இலைகளுக்கு அருகில் கொண்டு வாருங்கள், சுமார் ஒரு கை தூரத்தில். இலையின் மேல் பக்கத்தைக் காட்டுங்கள்.",
        "te": "కెమెరాను ఆకుల దగ్గరకు తీసుకురండి, సుమారు ఒక చేయి దూరంలో. ఆకు పై వైపు చూపించండి.",
        "kn": "ಕ್ಯಾಮೆರಾವನ್ನು ಎಲೆಗಳ ಹತ್ತಿರ ತನ್ನಿ, ಸುಮಾರು ಒಂದು ಕೈ ದೂರದಲ್ಲಿ. ಎಲೆಯ ಮೇಲ್ಭಾಗ ತೋರಿಸಿ.",
        "ml": "ക്യാമറ ഇലകളുടെ അടുത്തേക്ക് കൊണ്ടുവരുക, ഏകദേശം ഒരു കൈ അകലത്തിൽ. ഇലയുടെ മുകൾഭാഗം കാണിക്കുക.",
        "gu": "કેમેરાને પાનની નજીક લાવો, લગભગ એક હાથ દૂર. પાનની ઉપરની બાજુ બતાવો.",
        "pa": "ਕੈਮਰਾ ਪੱਤਿਆਂ ਦੇ ਨੇੜੇ ਲਿਆਓ, ਲਗਭਗ ਇੱਕ ਹੱਥ ਦੂਰ। ਪੱਤੇ ਦਾ ਉੱਪਰਲਾ ਪਾਸਾ ਦਿਖਾਓ।",
    },
    "leaf_under": {
        "en": "Now turn a leaf over and show me its underside.",
        "hi": "अब एक पत्ती पलटकर उसका निचला भाग दिखाइए।",
        "mr": "आता एक पान उलटून त्याची खालची बाजू दाखवा.",
        "bn": "এবার একটি পাতা উল্টে তার নিচের দিক দেখান।",
        "ta": "இப்போது ஒரு இலையைத் திருப்பி அதன் அடிப்பக்கத்தைக் காட்டுங்கள்.",
        "te": "ఇప్పుడు ఒక ఆకును తిప్పి దాని కింది వైపు చూపించండి.",
        "kn": "ಈಗ ಒಂದು ಎಲೆಯನ್ನು ತಿರುಗಿಸಿ ಅದರ ಕೆಳಭಾಗ ತೋರಿಸಿ.",
        "ml": "ഇനി ഒരു ഇല മറിച്ച് അതിന്റെ അടിഭാഗം കാണിക്കുക.",
        "gu": "હવે એક પાન ઉલટાવીને તેની નીચેની બાજુ બતાવો.",
        "pa": "ਹੁਣ ਇੱਕ ਪੱਤਾ ਪਲਟ ਕੇ ਉਸ ਦਾ ਹੇਠਲਾ ਪਾਸਾ ਦਿਖਾਓ।",
    },
    "base": {
        "en": "Show me the base of the plant, where it meets the soil or water.",
        "hi": "पौधे का निचला हिस्सा दिखाइए, जहाँ वह मिट्टी या पानी से मिलता है।",
        "mr": "रोपाचा खालचा भाग दाखवा, जिथे ते माती किंवा पाण्याला मिळते.",
        "bn": "গাছের গোড়া দেখান, যেখানে সেটি মাটি বা জলের সঙ্গে মিশেছে।",
        "ta": "செடியின் அடிப்பகுதியைக் காட்டுங்கள், அது மண்ணையோ தண்ணீரையோ தொடும் இடத்தை.",
        "te": "మొక్క మొదలు చూపించండి, అది మట్టిని లేదా నీటిని తాకే చోటు.",
        "kn": "ಗಿಡದ ಬುಡ ತೋರಿಸಿ, ಅದು ಮಣ್ಣು ಅಥವಾ ನೀರನ್ನು ಸೇರುವ ಜಾಗ.",
        "ml": "ചെടിയുടെ ചുവട് കാണിക്കുക, അത് മണ്ണിലോ വെള്ളത്തിലോ ചേരുന്ന ഭാഗം.",
        "gu": "છોડનો નીચેનો ભાગ બતાવો, જ્યાં તે માટી કે પાણીને મળે છે.",
        "pa": "ਬੂਟੇ ਦਾ ਹੇਠਲਾ ਹਿੱਸਾ ਦਿਖਾਓ, ਜਿੱਥੇ ਉਹ ਮਿੱਟੀ ਜਾਂ ਪਾਣੀ ਨਾਲ ਮਿਲਦਾ ਹੈ।",
    },
    "second_spot": {
        "en": "Walk about 20 steps to another part of the field and show me leaves close up again.",
        "hi": "लगभग 20 कदम चलकर खेत के दूसरे हिस्से में जाइए और फिर से पत्तियाँ पास से दिखाइए।",
        "mr": "सुमारे 20 पावले चालून शेताच्या दुसऱ्या भागात जा आणि पुन्हा पाने जवळून दाखवा.",
        "bn": "প্রায় বিশ পা হেঁটে মাঠের অন্য অংশে যান এবং আবার পাতা কাছ থেকে দেখান।",
        "ta": "சுமார் இருபது அடி நடந்து வயலின் வேறு ஒரு பகுதிக்குச் சென்று, மீண்டும் இலைகளை அருகில் காட்டுங்கள்.",
        "te": "సుమారు ఇరవై అడుగులు నడిచి పొలంలో వేరే భాగానికి వెళ్లి, మళ్లీ ఆకులను దగ్గరగా చూపించండి.",
        "kn": "ಸುಮಾರು ಇಪ್ಪತ್ತು ಹೆಜ್ಜೆ ನಡೆದು ಹೊಲದ ಬೇರೆ ಭಾಗಕ್ಕೆ ಹೋಗಿ, ಮತ್ತೆ ಎಲೆಗಳನ್ನು ಹತ್ತಿರದಿಂದ ತೋರಿಸಿ.",
        "ml": "ഏകദേശം ഇരുപത് ചുവട് നടന്ന് വയലിന്റെ മറ്റൊരു ഭാഗത്ത് ചെന്ന്, വീണ്ടും ഇലകൾ അടുത്ത് കാണിക്കുക.",
        "gu": "લગભગ વીસ ડગલાં ચાલીને ખેતરના બીજા ભાગમાં જાઓ અને ફરીથી પાન નજીકથી બતાવો.",
        "pa": "ਲਗਭਗ ਵੀਹ ਕਦਮ ਚੱਲ ਕੇ ਖੇਤ ਦੇ ਦੂਜੇ ਹਿੱਸੇ ਵਿੱਚ ਜਾਓ ਅਤੇ ਫਿਰ ਪੱਤੇ ਨੇੜਿਓਂ ਦਿਖਾਓ।",
    },
    "confirm": {
        "en": "I think I see {name}. Show me more leaves with those marks, close up.",
        "hi": "मुझे {name} जैसा कुछ दिख रहा है। ऐसे निशान वाली और पत्तियाँ पास से दिखाइए।",
        "mr": "मला {name} सारखे काहीतरी दिसत आहे. असे डाग असलेली आणखी पाने जवळून दाखवा.",
        "bn": "আমার মনে হচ্ছে {name} দেখছি। এমন দাগ আছে এমন আরও পাতা কাছ থেকে দেখান।",
        "ta": "எனக்கு {name} போல் தெரிகிறது. அந்த மாதிரி அடையாளம் உள்ள இன்னும் சில இலைகளை அருகில் காட்டுங்கள்.",
        "te": "నాకు {name} లాగా కనిపిస్తోంది. అలాంటి మచ్చలు ఉన్న మరిన్ని ఆకులను దగ్గరగా చూపించండి.",
        "kn": "ನನಗೆ {name} ಇದ್ದಂತೆ ಕಾಣುತ್ತಿದೆ. ಅಂಥ ಕಲೆ ಇರುವ ಇನ್ನಷ್ಟು ಎಲೆಗಳನ್ನು ಹತ್ತಿರದಿಂದ ತೋರಿಸಿ.",
        "ml": "എനിക്ക് {name} പോലെ തോന്നുന്നു. അത്തരം പാടുകളുള്ള കൂടുതൽ ഇലകൾ അടുത്ത് കാണിക്കുക.",
        "gu": "મને {name} જેવું લાગે છે. એવા ડાઘવાળાં વધુ પાન નજીકથી બતાવો.",
        "pa": "ਮੈਨੂੰ {name} ਵਰਗਾ ਕੁਝ ਦਿਸ ਰਿਹਾ ਹੈ। ਇਹੋ ਜਿਹੇ ਨਿਸ਼ਾਨ ਵਾਲੇ ਹੋਰ ਪੱਤੇ ਨੇੜਿਓਂ ਦਿਖਾਓ।",
    },
}

HINTS = {
    # Coaching while a view is not usable yet. Spoken at most once every few
    # seconds, so each one names the fix, not the fault.
    "too_dark": {
        "en": "Too dark — turn towards the light.",
        "hi": "बहुत अँधेरा है — रोशनी की तरफ़ घूमिए।",
        "mr": "खूप अंधार आहे — उजेडाकडे वळा.",
        "bn": "খুব অন্ধকার। আলোর দিকে ঘুরুন।",
        "ta": "மிகவும் இருட்டாக இருக்கிறது. வெளிச்சத்தை நோக்கித் திரும்புங்கள்.",
        "te": "చాలా చీకటిగా ఉంది. వెలుతురు వైపు తిరగండి.",
        "kn": "ತುಂಬಾ ಕತ್ತಲೆ ಇದೆ. ಬೆಳಕಿನ ಕಡೆ ತಿರುಗಿ.",
        "ml": "വളരെ ഇരുട്ടാണ്. വെളിച്ചത്തിന്റെ ഭാഗത്തേക്ക് തിരിയുക.",
        "gu": "બહુ અંધારું છે. પ્રકાશ તરફ ફરો.",
        "pa": "ਬਹੁਤ ਹਨੇਰਾ ਹੈ। ਰੌਸ਼ਨੀ ਵੱਲ ਮੁੜੋ।",
    },
    "too_bright": {
        "en": "Too much glare — shade the leaf or turn a little.",
        "hi": "बहुत चमक है — पत्ती पर छाया कीजिए या थोड़ा घूमिए।",
        "mr": "खूप चकाकी आहे — पानावर सावली करा किंवा थोडे वळा.",
        "bn": "খুব চকচক করছে। পাতায় ছায়া দিন বা একটু ঘুরুন।",
        "ta": "மிகவும் பளபளக்கிறது. இலையின் மேல் நிழல் விடுங்கள் அல்லது கொஞ்சம் திரும்புங்கள்.",
        "te": "చాలా మెరుస్తోంది. ఆకుపై నీడ పడేలా చేయండి లేదా కొంచెం తిరగండి.",
        "kn": "ತುಂಬಾ ಹೊಳೆಯುತ್ತಿದೆ. ಎಲೆಯ ಮೇಲೆ ನೆರಳು ಮಾಡಿ ಅಥವಾ ಸ್ವಲ್ಪ ತಿರುಗಿ.",
        "ml": "വളരെ തിളക്കമുണ്ട്. ഇലയ്ക്ക് മുകളിൽ തണൽ കൊടുക്കുക, അല്ലെങ്കിൽ അല്പം തിരിയുക.",
        "gu": "બહુ ચમક છે. પાન પર છાંયો કરો અથવા થોડું ફરો.",
        "pa": "ਬਹੁਤ ਚਮਕ ਹੈ। ਪੱਤੇ ਉੱਤੇ ਛਾਂ ਕਰੋ ਜਾਂ ਥੋੜ੍ਹਾ ਮੁੜੋ।",
    },
    "hold_steady": {
        "en": "Hold the phone steady.",
        "hi": "फ़ोन स्थिर पकड़िए।",
        "mr": "फोन स्थिर धरा.",
        "bn": "ফোনটি স্থির করে ধরুন।",
        "ta": "ஃபோனை அசையாமல் பிடியுங்கள்.",
        "te": "ఫోన్‌ను కదలకుండా పట్టుకోండి.",
        "kn": "ಫೋನ್ ಅಲ್ಲಾಡದಂತೆ ಹಿಡಿಯಿರಿ.",
        "ml": "ഫോൺ ഇളകാതെ പിടിക്കുക.",
        "gu": "ફોન સ્થિર પકડો.",
        "pa": "ਫ਼ੋਨ ਸਥਿਰ ਫੜੋ।",
    },
    "show_crop": {
        "en": "Point the camera at your crop.",
        "hi": "कैमरा अपनी फसल की ओर कीजिए।",
        "mr": "कॅमेरा तुमच्या पिकाकडे करा.",
        "bn": "ক্যামেরা আপনার ফসলের দিকে করুন।",
        "ta": "கேமராவை உங்கள் பயிரை நோக்கித் திருப்புங்கள்.",
        "te": "కెమెరాను మీ పంట వైపు తిప్పండి.",
        "kn": "ಕ್ಯಾಮೆರಾವನ್ನು ನಿಮ್ಮ ಬೆಳೆಯ ಕಡೆ ತಿರುಗಿಸಿ.",
        "ml": "ക്യാമറ നിങ്ങളുടെ വിളയുടെ നേരെ തിരിക്കുക.",
        "gu": "કેમેરા તમારા પાક તરફ કરો.",
        "pa": "ਕੈਮਰਾ ਆਪਣੀ ਫ਼ਸਲ ਵੱਲ ਕਰੋ।",
    },
    "come_closer": {
        "en": "Come closer to the leaves.",
        "hi": "पत्तियों के और पास आइए।",
        "mr": "पानांच्या आणखी जवळ या.",
        "bn": "পাতার আরও কাছে আসুন।",
        "ta": "இலைகளுக்கு இன்னும் அருகில் வாருங்கள்.",
        "te": "ఆకులకు ఇంకా దగ్గరగా రండి.",
        "kn": "ಎಲೆಗಳ ಇನ್ನೂ ಹತ್ತಿರ ಬನ್ನಿ.",
        "ml": "ഇലകളുടെ കൂടുതൽ അടുത്തേക്ക് വരിക.",
        "gu": "પાનની વધુ નજીક આવો.",
        "pa": "ਪੱਤਿਆਂ ਦੇ ਹੋਰ ਨੇੜੇ ਆਓ।",
    },
    "move_a_little": {
        "en": "Good. Now move a little to show a different part.",
        "hi": "अच्छा। अब थोड़ा हटकर दूसरा हिस्सा दिखाइए।",
        "mr": "छान. आता थोडे हलून दुसरा भाग दाखवा.",
        "bn": "ভালো হয়েছে। এবার একটু সরে অন্য একটি অংশ দেখান।",
        "ta": "நல்லது. இப்போது கொஞ்சம் நகர்ந்து வேறு ஒரு பகுதியைக் காட்டுங்கள்.",
        "te": "బాగుంది. ఇప్పుడు కొంచెం కదిలి వేరే భాగం చూపించండి.",
        "kn": "ಒಳ್ಳೆಯದು. ಈಗ ಸ್ವಲ್ಪ ಸರಿದು ಬೇರೆ ಭಾಗ ತೋರಿಸಿ.",
        "ml": "നന്നായി. ഇനി അല്പം മാറി മറ്റൊരു ഭാഗം കാണിക്കുക.",
        "gu": "સરસ. હવે થોડું ખસીને બીજો ભાગ બતાવો.",
        "pa": "ਵਧੀਆ। ਹੁਣ ਥੋੜ੍ਹਾ ਹਟ ਕੇ ਦੂਜਾ ਹਿੱਸਾ ਦਿਖਾਓ।",
    },
    "good": {
        "en": "Good, keep going.",
        "hi": "बढ़िया, ऐसे ही दिखाते रहिए।",
        "mr": "छान, असेच दाखवत राहा.",
        "bn": "ভালো হচ্ছে, এভাবেই দেখাতে থাকুন।",
        "ta": "நல்லது, இப்படியே காட்டிக் கொண்டே இருங்கள்.",
        "te": "బాగుంది, ఇలాగే చూపిస్తూ ఉండండి.",
        "kn": "ಒಳ್ಳೆಯದು, ಹೀಗೇ ತೋರಿಸುತ್ತಿರಿ.",
        "ml": "നന്നായി, ഇങ്ങനെ തന്നെ കാണിച്ചുകൊണ്ടിരിക്കുക.",
        "gu": "સરસ, આમ જ બતાવતા રહો.",
        "pa": "ਵਧੀਆ, ਇਵੇਂ ਹੀ ਦਿਖਾਉਂਦੇ ਰਹੋ।",
    },
}

BASE_STEPS = [("overview", "scene", 3), ("plant", "plant", 2), ("leaf_top", "close", 4),
              ("leaf_under", "close", 2), ("base", "base", 2), ("second_spot", "close", 3)]
CONFIRM_NEED = 3
MAX_EVIDENCE_FRAMES = 3
MIN_SHARE_OF_STRONG = 0.25
"""A second problem must make up at least this share of the walk's strong disease
readings to be reported as seen; below it, it goes to an expert as possible."""
MIN_VIDEO_VIEWS = 2
"""Readable frames below which a video is worth explaining rather than only
reporting. Two is the bar a disease must clear anyway, so under it the farmer
was never going to get an answer and deserves to know why.

A video does NOT get an easier bar than a walk, and the temptation to give it
one should be resisted here rather than rediscovered. Thirty seconds held on a
single diseased leaf feels like far more evidence than two photographs, and it
is not: a model that misreads that leaf misreads every frame of it the same
way, so those frames are one sample wearing thirty hats. Counting them would
buy a confident answer on exactly the footage least able to support one.

What saves the rule from being merely timid is that it never counted frames in
the first place. A frame becomes a view only by passing the novelty gate, and
that gate measures each frame against the last *accepted* one — so a handheld
video that drifts across a plant accumulates real views as it goes, while a
camera resting on a bund accumulates none. Different looks count; the same look
repeated does not. That is the distinction the rule is actually for, and it
already draws it.

So a static video ends at "possible — an expert will check", with the reading
telling the farmer to walk the row and film a few different plants. That is the
honest answer, and the expert's verdict now reaches them."""
VIDEO_KIND = "close"
"""A file is read for usable close-ups of the crop and nothing else: there is no
one to coach towards the other views, so there is no point measuring against
them."""
MAX_MARKS = 720
"""Entries kept of what each frame of a video came to. Above the server's own
frame limit, so in practice every frame gets one; it is a bound on what is
stored with the result, not a sampling rate."""
MIN_OTHER_CROP_VIEWS = 2
"""Readings of a different crop before the farmer is told so. One is a misread;
two that are also most of what the model could read is the wrong field picked,
or the wrong crop registered, and neither a disease name nor "could not see
your plants" is the truth about that footage."""


@dataclass
class Quality:
    ok: bool
    hint: str | None
    sharp: float
    bright: float
    veg: float
    novel: bool


@dataclass
class Step:
    id: str
    kind: str
    need: int
    got: int = 0
    name: str | None = None  # for the confirm step


@dataclass
class Sighting:
    target: str
    conf: float
    frame: int
    at: float | None = None  # video: seconds into the file this frame came from


@dataclass
class LiveSession:
    crop: str
    lang: str
    can_classify: bool
    target_name: Callable[[str], str] = lambda t: t
    steps: list[Step] = field(default_factory=list)
    idx: int = 0
    frames: int = 0
    good_frames: int = 0
    classified: int = 0
    sightings: list[Sighting] = field(default_factory=list)
    evidence: dict[str, list[tuple[float, bytes]]] = field(default_factory=dict)
    closeups: list[tuple[float, bytes]] = field(default_factory=list)  # sharpest, for crops without a model
    other_crop: int = 0
    confirm_added: bool = False
    asked: str | None = None
    answer: tuple[str, str] | None = None  # (cue_id, yes/no/unknown)
    mode: str = "walk"     # "walk": a camera being guided; "video": a file being read
    skipped: list[str] = field(default_factory=list)  # views the farmer could not get
    ended: bool = False    # video: the caller says there are no more frames
    kept: int = 0          # video: frames the model could actually read
    clear: int = 0         # video: frames that passed the quality gate
    #: Why frames were passed over, counted. A video that yields nothing has to
    #: be able to say which wall it hit: a farmer told "nothing close enough"
    #: refilms closer, and one whose footage the model cannot recognise as a
    #: crop at all needs to hear something completely different.
    passed_over_why: dict[str, int] = field(default_factory=dict)
    #: Video: what each frame came to, in order — (seconds in, code). The codes
    #: are "h" a healthy reading, "p" a problem glimpsed, "c" a clear close-up
    #: nobody could classify (no model for this crop), "o" another crop, and
    #: "x" passed over. It is what lets the result show *where* in the video
    #: something was seen, and how much of it was readable at all.
    marks: list[tuple[float, str]] = field(default_factory=list)
    #: The record this session was saved as, once it has been. Saving is asked
    #: for again when the answer does not arrive, and must not write it twice.
    saved: int | None = None
    _last_thumb: np.ndarray | None = None

    def __post_init__(self):
        if not self.steps:
            self.steps = [Step(i, k, n) for i, k, n in BASE_STEPS]

    # --- public ---------------------------------------------------------------
    @property
    def done(self) -> bool:
        if self.mode == "video":
            return self.ended
        return self.idx >= len(self.steps)

    def guide(self) -> dict:
        # Reading a file has no steps to be at, so there is nothing to guide:
        # what the caller wants to show is how much of the video has been read
        # and how much of it was worth reading.
        if self.mode == "video":
            return {"step": None, "index": 0, "total": 0, "read": self.frames,
                    "clear": self.clear, "kept": self.kept, "why_thin": self.why_thin()}
        if self.done:
            return {"step": None, "index": len(self.steps), "total": len(self.steps)}
        s = self.steps[self.idx]
        text = tr(TEXT[s.id], self.lang)
        return {"step": s.id, "kind": s.kind, "index": self.idx, "total": len(self.steps),
                "need": s.need, "got": s.got, "text": text.format(name=s.name or "")}

    def on_frame(self, img: Image.Image, jpeg: bytes,
                 classify: Callable[[Image.Image], list[tuple[str, float]]] | None,
                 at: float | None = None) -> dict:
        """One frame. `at` is how far into the file it came from, for a video;
        a camera has no such thing and leaves it out.

        All or nothing. If the model fails part-way through a frame, the frame
        is undone entirely: counted half-way, it left the view looking already
        seen, so the same frame sent again after the call was picked back up
        was passed over as "the same view" and that second was never read."""
        before = self._checkpoint()
        try:
            return self._on_frame(img, jpeg, classify, at)
        except Exception:
            self._restore(before)
            raise

    def _checkpoint(self) -> dict:
        return {
            "counts": (self.frames, self.good_frames, self.classified, self.other_crop, self.clear,
                       self.kept, self.idx, self.confirm_added),
            "steps": [(st, st.got) for st in self.steps],
            "sightings": len(self.sightings), "marks": len(self.marks),
            "evidence": {k: list(v) for k, v in self.evidence.items()},
            "closeups": list(self.closeups), "thumb": self._last_thumb,
            "passed": dict(self.passed_over_why),
        }

    def _restore(self, c: dict) -> None:
        (self.frames, self.good_frames, self.classified, self.other_crop, self.clear,
         self.kept, self.idx, self.confirm_added) = c["counts"]
        self.steps = [st for st, _ in c["steps"]]
        for st, got in c["steps"]:
            st.got = got
        del self.sightings[c["sightings"]:]
        del self.marks[c["marks"]:]
        self.evidence, self.closeups = c["evidence"], c["closeups"]
        self._last_thumb, self.passed_over_why = c["thumb"], c["passed"]

    def _on_frame(self, img: Image.Image, jpeg: bytes,
                  classify: Callable[[Image.Image], list[tuple[str, float]]] | None,
                  at: float | None) -> dict:
        if self.mode == "video" and at is not None and self.marks and self.marks[-1][0] == round(float(at), 1):
            # The same second again: the frame that was on its way when the
            # line dropped, re-sent because the phone cannot know it arrived.
            # It did, and it has been read; reading it twice would count it
            # twice and mark that second "the same view" on the timeline.
            return {"quality": None, "counted": False, "advanced": False, "live": None,
                    "mark": None, "repeat": True, "guide": self.guide()}
        self.frames += 1
        if self.mode == "video":
            return self._read_frame(img, jpeg, classify, at)
        if self.done:
            return {"quality": None, "counted": False, "advanced": False, "guide": self.guide()}
        step = self.steps[self.idx]
        q = measure(img, step.kind, self._last_thumb)
        out: dict = {"quality": q.__dict__ | {"hint_text": self.hint_text(q.hint)}, "counted": False,
                     "advanced": False, "live": None}
        if not q.ok:
            return out | {"guide": self.guide()}
        self.good_frames += 1
        self._last_thumb = _thumb(img)
        step.got += 1
        out["counted"] = True
        vmin, smin, run_model = KINDS[step.kind]
        if run_model:
            self.closeups.append((q.sharp, jpeg))
            self.closeups = sorted(self.closeups, key=lambda x: -x[0])[:MAX_EVIDENCE_FRAMES]
            if classify is not None and self.can_classify:
                preds = classify(img)
                if not preds:  # the model says this is not a crop view at all
                    step.got -= 1
                    self.good_frames -= 1
                    self.closeups = [c for c in self.closeups if c[1] is not jpeg]
                    q.ok, q.hint = False, "show_crop"
                    return out | {"quality": q.__dict__ | {"hint_text": self.hint_text(q.hint)}, "counted": False,
                                  "guide": self.guide()}
                self.classified += 1
                out["live"] = self._record(preds, jpeg)
        if step.got >= step.need:
            self._maybe_add_confirm()
            self.idx += 1
            out["advanced"] = True
        return out | {"guide": self.guide()}

    def _read_frame(self, img: Image.Image, jpeg: bytes,
                    classify: Callable[[Image.Image], list[tuple[str, float]]] | None,
                    at: float | None = None) -> dict:
        """One frame out of a video the farmer filmed before they got here.

        Nothing is asked for and nothing is refused. The video is already shot,
        so coaching it towards a view it does not contain would only be a
        complaint. Every frame is read; a frame is kept only when it is a close
        enough, steady enough, green enough look at the crop to be worth the
        model's opinion. What those opinions are worth is settled afterwards by
        findings(), on exactly the evidence rules the guided walk uses — two
        separate frames must agree before anything is called seen.
        """
        q = measure(img, VIDEO_KIND, self._last_thumb)
        out: dict = {"quality": q.__dict__ | {"hint_text": None}, "counted": False,
                     "advanced": False, "live": None, "mark": "x"}
        if not q.ok:
            self._passed_over(q.hint or "unclear")
            self._mark(at, "x")
            return out | {"guide": self.guide()}
        self.clear += 1
        self._last_thumb = _thumb(img)
        self.good_frames += 1
        self.closeups.append((q.sharp, jpeg))
        self.closeups = sorted(self.closeups, key=lambda x: -x[0])[:MAX_EVIDENCE_FRAMES]
        if classify is not None and self.can_classify:
            preds = classify(img)
            if not preds:
                # Sharp, green and close enough, and still not something the
                # model recognises as a crop it has been taught. A screen
                # recording of a video player is the honest example: a
                # watermark, playback chrome and two rounds of compression over
                # footage that is a crop underneath. The gate is right to
                # refuse it — it is what stops a confident disease name on a
                # photograph of something else — but the farmer has to be told,
                # because from where they stand a good video simply did nothing.
                self.good_frames -= 1
                self.closeups = [c for c in self.closeups if c[1] is not jpeg]
                self._passed_over("not_crop")
                self._mark(at, "x")
                return out | {"guide": self.guide()}
            self.classified += 1
            out["live"] = self._record(preds, jpeg, at)
            top, conf = preds[0]
            out["mark"] = ("o" if crop_of(top) != self.crop else "h" if is_healthy(top)
                           else "p" if conf >= FLOOR else "h")
        else:
            out["mark"] = "c"
        self.kept += 1
        out["counted"] = True
        self._mark(at, out["mark"])
        return out | {"guide": self.guide()}

    def _passed_over(self, why: str) -> None:
        self.passed_over_why[why] = self.passed_over_why.get(why, 0) + 1

    def _mark(self, at: float | None, code: str) -> None:
        if at is not None and len(self.marks) < MAX_MARKS:
            self.marks.append((round(float(at), 1), code))

    def other_crop_seen(self) -> dict | None:
        """The crop the footage mostly showed, when it was not this field's.

        A farmer with two fields who picks the wrong one, or whose field is
        still registered under last season's crop, films perfectly good maize
        against a rice field. Every reading is then thrown away as "another
        crop" — correctly — and what they were told was that the camera could
        not see their plants, which is false and sends them out to film the
        same maize again. This needs most of the readable views to agree on
        one other crop, so a single misread leaf never raises it.
        """
        if self.other_crop < MIN_OTHER_CROP_VIEWS or self.other_crop * 2 <= self.classified:
            return None
        # And only when this field's own crop gave no answer. Footage that pans
        # over the neighbour's maize on its way to a rice disease is a rice
        # finding, and so is enough sure looks at healthy rice: telling that
        # farmer to pick another field, over a result about this one, is a
        # contradiction on one screen.
        own = [s for s in self.sightings if crop_of(s.target) == self.crop]
        if any(not is_healthy(s.target) and s.conf >= FLOOR for s in own):
            return None
        if sum(is_healthy(s.target) and s.conf >= gate_for(s.target) for s in own) >= 2:
            return None
        tally: dict[str, int] = {}
        for s in self.sightings:
            c = crop_of(s.target)
            if c and c != self.crop:
                tally[c] = tally.get(c, 0) + 1
        if not tally:
            return None
        crop, views = max(tally.items(), key=lambda kv: kv[1])
        return {"crop": crop, "views": views} if views * 2 > self.classified else None

    def reading(self) -> dict:
        """How the looking itself went — kept with the result, because a
        verdict means something different on top of forty clear close-ups than
        on top of two, and the difference should still be readable next year.

        A video says how much of it could be read and where; a walk says which
        views were never shown."""
        if self.mode != "video":
            return {"mode": "walk", "skipped": list(self.skipped), "other_crop": self.other_crop_seen()}
        return {"mode": "video", "read": self.frames, "clear": self.clear, "kept": self.kept,
                "why_thin": self.why_thin(), "passed_over": dict(self.passed_over_why),
                "marks": [list(m) for m in self.marks], "other_crop": self.other_crop_seen()}

    def why_thin(self) -> str | None:
        """The one thing most worth telling a farmer whose video gave little.

        Not a tally — a sentence's worth of cause. "not_crop" outranks the rest
        even when it is not the commonest: a video the model cannot read at all
        needs different advice from one that was merely dark, and hearing "too
        dark" about footage that was never going to be read would send the
        farmer out to refilm the same unusable thing.
        """
        if self.other_crop_seen():
            # Read perfectly well — as something this field is not growing. No
            # amount of refilming the same plants changes that.
            return "other_crop"
        if self.kept >= MIN_VIDEO_VIEWS or not self.passed_over_why:
            return None
        if self.passed_over_why.get("not_crop"):
            return "not_crop"
        return max(self.passed_over_why.items(), key=lambda kv: kv[1])[0]

    def skip(self) -> bool:
        """Move past the view being asked for.

        Some views cannot be had: a leaf underside on a crop grown flat to the
        ground, a plant base under standing water, a second spot across a bund
        the farmer is not going to cross in the rain. Coaching someone towards a
        picture that does not exist until the session times out is the worst
        answer available — it wastes their walk and ends with nothing. Moving on
        costs only the evidence that view would have given, and the evidence
        rules already know how to say "not enough to be sure".
        """
        if self.done or self.mode != "walk":
            return False
        self.skipped.append(self.steps[self.idx].id)
        self.idx += 1
        return True

    def pending_question(self, kb) -> dict | None:
        """A Doubt Doctor question once the close-ups are in, if the two
        strongest problems compete and a field check separates them."""
        if self.asked or self.answer or not self.done:
            return None
        ranked = self._ranked()
        if len(ranked) < 2:
            return None
        (a, ca), (b, cb) = ranked[0], ranked[1]
        if ca - cb > MARGIN or cb < FLOOR:
            return None
        cue = kb.cue_for(a, b)
        if cue:
            self.asked = cue["id"]
            return cue
        return None

    def on_answer(self, cue_id: str, answer: str) -> None:
        if cue_id == self.asked:
            self.answer = (cue_id, answer)

    def findings(self, kb) -> dict:
        """What the walk showed. 'seen' = at least two separate close-ups agree
        above the gate; 'possible' = glimpsed, goes to an expert."""
        seen, possible = [], []
        settled = None
        if self.answer and self.answer[1] in ("yes", "no"):
            cue = next((c for c in kb.cues if c["id"] == self.answer[0]), None)
            if cue:
                a, b = cue["pair"]
                settled = cue["yes_means"] if self.answer[1] == "yes" else (b if cue["yes_means"] == a else a)
        by_target: dict[str, list[float]] = {}
        moments: dict[str, list[float]] = {}
        for s in self.sightings:
            by_target.setdefault(s.target, []).append(s.conf)
            if s.at is not None and s.conf >= FLOOR:
                moments.setdefault(s.target, []).append(round(s.at, 1))
        # Strong disease readings across the whole walk. A problem read strongly in
        # only a sliver of them — two frames among fifteen that agree on something
        # else — is more likely a misread than a second disease: it goes to an
        # expert as 'possible', never to the farmer as 'seen'.
        total_strong = sum(sum(c >= gate_for(t) for c in confs) for t, confs in by_target.items()
                           if not is_healthy(t) and crop_of(t) == self.crop)
        for t, confs in sorted(by_target.items(), key=lambda kv: -max(kv[1])):
            if is_healthy(t) or crop_of(t) != self.crop:
                continue
            strong = [c for c in confs if c >= gate_for(t)]
            tier = kb.targets.get(t, {}).get("tier")
            share = len(strong) / total_strong if total_strong else 0.0
            item = {"target": t, "views": len(confs), "strong_views": len(strong),
                    "share_of_strong": round(share, 2),
                    "confidence": round(median(strong) if strong else max(confs), 3)}
            if moments.get(t):
                # Where in the video it was seen: the farmer can go back to the
                # second and look at the leaf the reading is about.
                item["moments"] = sorted(moments[t])[:12]
            if tier == "diagnosable" and ((len(strong) >= 2 and share >= MIN_SHARE_OF_STRONG)
                                          or (settled == t and max(confs) >= FLOOR)):
                seen.append(item | {"settled_by_answer": settled == t and len(strong) < 2})
            elif max(confs) >= FLOOR:
                reason = "NOT_PHOTO_DIAGNOSABLE" if tier != "diagnosable" else \
                    "MINORITY_VIEWS" if len(strong) >= 2 else "FEW_VIEWS"
                possible.append(item | {"reason": reason})
        # Look-alikes (a Doubt Doctor pair, e.g. blast and brown spot) are exactly what
        # the model confuses; unless the farmer's answer settled it, only the one
        # with more strong views is 'seen' — the other goes to the expert.
        for a in sorted(seen, key=lambda x: -x["strong_views"]):
            for b in list(seen):
                if b is a or b not in seen or a not in seen or b.get("settled_by_answer"):
                    continue
                if kb.cue_for(a["target"], b["target"]) and b["strong_views"] <= a["strong_views"] \
                        and settled != b["target"]:
                    seen.remove(b)
                    possible.append({k: v for k, v in b.items() if k != "settled_by_answer"} | {"reason": "LOOKALIKE"})
        healthy_views = sum(1 for s in self.sightings if is_healthy(s.target) and crop_of(s.target) == self.crop)
        # Healthy at any confidence is not evidence of health: a blurred or
        # half-seen leaf lands on "healthy" as easily as on anything else. Only
        # views the model was sure of may back a "your plants are healthy".
        healthy_confident = sum(1 for s in self.sightings if is_healthy(s.target)
                                and crop_of(s.target) == self.crop and s.conf >= gate_for(s.target))
        return {
            "seen": seen,
            "possible": [p for p in possible if p["target"] not in {s["target"] for s in seen}],
            "classified_views": self.classified,
            "healthy_views": healthy_views,
            "healthy_confident_views": healthy_confident,
            "other_crop_views": self.other_crop,
            "good_frames": self.good_frames,
            "frames": self.frames,
            "answer": {"cue_id": self.answer[0], "answer": self.answer[1]} if self.answer else None,
            # Which views were never shown. A thin walk should read back as a
            # thin walk years later, not as a field that looked fine.
            "skipped_views": list(self.skipped),
            "reading": self.reading(),
        }

    def evidence_for(self, target: str) -> list[bytes]:
        return [j for _, j in sorted(self.evidence.get(target, []), key=lambda x: -x[0])]

    def hint_text(self, key: str | None) -> str | None:
        return tr(HINTS[key], self.lang) if key else None

    # --- internals ------------------------------------------------------------
    def _record(self, preds: list[tuple[str, float]], jpeg: bytes, at: float | None = None) -> dict:
        top, conf = preds[0]
        if crop_of(top) != self.crop:
            self.other_crop += 1
        self.sightings.append(Sighting(top, conf, self.frames, at))
        if not is_healthy(top) and conf >= FLOOR:
            ev = self.evidence.setdefault(top, [])
            ev.append((conf, jpeg))
            ev.sort(key=lambda x: -x[0])
            del ev[MAX_EVIDENCE_FRAMES:]
        return {"top": [{"target": t, "name": self.target_name(t), "confidence": round(c, 3)} for t, c in preds]}

    def _ranked(self) -> list[tuple[str, float]]:
        acc: dict[str, list[float]] = {}
        for s in self.sightings:
            if not is_healthy(s.target) and crop_of(s.target) == self.crop:
                acc.setdefault(s.target, []).append(s.conf)
        return sorted(((t, float(np.mean(v))) for t, v in acc.items()), key=lambda kv: -kv[1])

    def _maybe_add_confirm(self) -> None:
        """Glimpsed a problem but not yet two strong views: ask for more close-ups once."""
        if self.confirm_added or self.steps[self.idx].kind != "close":
            return
        remaining_close = any(s.kind == "close" for s in self.steps[self.idx + 1:])
        for t, confs in self._by_target().items():
            strong = sum(c >= gate_for(t) for c in confs)
            if strong < 2 and max(confs) >= FLOOR and not remaining_close:
                self.steps.insert(self.idx + 1, Step("confirm", "close", CONFIRM_NEED, name=self.target_name(t)))
                self.confirm_added = True
                return

    def _by_target(self) -> dict[str, list[float]]:
        acc: dict[str, list[float]] = {}
        for s in self.sightings:
            if not is_healthy(s.target) and crop_of(s.target) == self.crop:
                acc.setdefault(s.target, []).append(s.conf)
        return acc


def _thumb(img: Image.Image) -> np.ndarray:
    return np.asarray(img.convert("L").resize((24, 24)), dtype=np.float32)


def sharpness(gray: np.ndarray) -> float:
    """Variance of the Laplacian — the standard blur measure."""
    g = gray.astype(np.float32)
    if g.shape[0] < 3 or g.shape[1] < 3:
        return 0.0  # too small to have edges (and var() of nothing is NaN, which is not JSON)
    lap = (-4 * g[1:-1, 1:-1] + g[:-2, 1:-1] + g[2:, 1:-1] + g[1:-1, :-2] + g[1:-1, 2:])
    return float(lap.var())


def measure(img: Image.Image, kind: str, last_thumb: np.ndarray | None) -> Quality:
    small = img.convert("RGB")
    small.thumbnail((WORK, WORK))
    gray = np.asarray(small.convert("L"), dtype=np.float32)
    bright = float(gray.mean())
    sharp = sharpness(gray)
    veg = vegetation_fraction(small)
    vmin, smin, _ = KINDS[kind]
    novel = True
    if last_thumb is not None:
        novel = float(np.abs(_thumb(small) - last_thumb).mean()) >= NOVELTY
    hint = None
    if bright < DARK:
        hint = "too_dark"
    elif bright > GLARE:
        hint = "too_bright"
    elif sharp < smin:
        hint = "hold_steady"
    elif veg < vmin:
        hint = "come_closer" if kind == "close" and veg >= 0.15 else "show_crop"
    elif not novel:
        hint = "move_a_little"
    return Quality(ok=hint is None, hint=hint, sharp=round(sharp, 1), bright=round(bright, 1),
                   veg=round(veg, 3), novel=novel)


MIN_SIDE = 64  # smaller than this is a camera glitch (a stopped track gives 0-2 px frames)


def decode(jpeg: bytes) -> Image.Image:
    im = Image.open(io.BytesIO(jpeg))
    # The socket caps a frame at 400 KB, which is not a cap on what it decodes
    # to: a flat image compresses far past a hundred to one. The header is read
    # before anything is expanded (the same bar as the photo path).
    w, h = im.size
    if w * h > MAX_PIXELS:
        raise ValueError(f"frame too large to decode: {im.size}")
    im.load()
    if min(im.size) < MIN_SIDE:
        raise ValueError(f"frame too small: {im.size}")
    return im.convert("RGB")


