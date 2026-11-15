"""SMS: the channel that reaches a farmer with a basic phone.

What a farmer or an officer would notice, end to end: a code that arrives by
SMS to the number they typed and says nothing but the code and how long it
lasts; a sign-up that needs no email; a warning, the expert's answer and the
day-four question on a phone with no app, once each and never at night; a
reply of "3" that puts an expert back on the case; a forged reply refused; and
a STOP that is obeyed.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import re
from datetime import date, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app import cache, config, notify, sms
from app.db import Base, SessionLocal, engine
from app.kb import get_kb
from app.main import app
from app.models import Case, Farm, FollowUp, Notice, OtpChallenge, Problem, SmsLog, User
from app.routers import auth as auth_router

SOWN = (date.today() - timedelta(days=40)).isoformat()
PHONE = "9876543210"
E164 = "+919876543210"
SECRET = "inbound-shared-secret-for-tests"


# --------------------------------------------------------------------------
# Fixtures
# --------------------------------------------------------------------------

class Phone:
    """Every SMS the app sends, instead of sending it."""

    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.fail = False

    def code(self) -> str:
        return re.search(r"\b(\d{6})\b", self.sent[-1]["text"]).group(1)

    def to(self, number: str) -> list[dict]:
        return [m for m in self.sent if m["to"] == number]


@pytest.fixture()
def phone(monkeypatch):
    p = Phone()

    def fake_outbox(to, text, kind, variables):
        if p.fail:
            return "failed", "provider down"
        p.sent.append({"to": to, "text": text, "kind": kind, "vars": variables})
        return "outbox", None

    monkeypatch.setattr(config, "SMS_BACKEND", "outbox")
    monkeypatch.setattr(config, "SMS_INBOUND_SECRET", SECRET)
    monkeypatch.setattr(sms, "_outbox", fake_outbox)
    cache._counts.clear()  # the per-number hourly cap is in-process here
    return p


@pytest.fixture()
def mail(monkeypatch):
    sent: list[dict] = []

    def fake_send(to, subject, text, html_body, **_):
        sent.append({"to": to, "subject": subject, "text": text})
        return "sent", None

    monkeypatch.setattr(auth_router.mailer, "send", fake_send)
    return sent


@pytest.fixture()
def client(monkeypatch, mail, phone):
    monkeypatch.setattr(config, "AUTH_ENFORCE", True)
    monkeypatch.setattr(config, "OTP_RESEND_SECONDS", 0)
    monkeypatch.setattr(auth_router, "limit", lambda *a, **k: None)
    Base.metadata.drop_all(bind=engine)
    with TestClient(app) as c:
        yield c


def signup(c: TestClient, phone: Phone, number=PHONE, email: str | None = None, lang="mr"):
    r = c.post("/api/auth/otp", json={"role": "farmer", "purpose": "signup", "phone": number,
                                      "email": email, "lang": lang})
    assert r.status_code == 200, r.text
    sent = r.json()
    code = phone.code() if sent["channel"] == "sms" else None
    return sent, code


def finish_signup(c: TestClient, challenge_id: str, code: str, number=PHONE, email=None, lang="mr"):
    return c.post("/api/auth/signup/farmer", json={
        "challenge_id": challenge_id, "code": code, "name": "Sunita Bhoyar", "phone": number, "email": email,
        "lang": lang, "district": "Bhandara", "village": "Mohadi", "lat": 21.38, "lon": 79.73, "consent": True,
        "farms": [{"crop": "rice", "sowing_date": SOWN, "area_acres": 2, "irrigation": "canal"}]})


def prove_email(c: TestClient, mail: list[dict]) -> None:
    """Confirm the email the farmer typed at an SMS sign-up, the only way it
    becomes theirs: a code sent there, typed back."""
    r = c.post("/api/auth/me/email", json={"lang": "en"})
    assert r.status_code == 200, r.text
    code = re.search(r"\b(\d{6})\b", mail[-1]["text"]).group(1)
    ok = c.post("/api/auth/me/email/verify", json={"challenge_id": r.json()["challenge_id"], "code": code})
    assert ok.status_code == 200, ok.text


@pytest.fixture()
def db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as s:
        yield s


def a_farmer(db, *, email: str | None = None, sms_pref: str | None = None, number=E164, demo=False,
             lang="hi") -> Farm:
    user = User(role="farmer", name="Sunita", phone=number, email=email, lang=lang, sms_pref=sms_pref)
    db.add(user)
    db.flush()
    farm = Farm(user_id=user.id, farmer_name="Sunita", phone=number, email=email, lang=lang, crop="rice",
                sowing_date=date.today() - timedelta(days=40), district="Bhandara", lat=21.17, lon=79.65,
                is_demo=demo)
    db.add(farm)
    db.commit()
    return farm


def a_warning(db, farm: Farm, now: datetime, key="thunderstorm:1") -> Notice:
    n = Notice(farm_id=farm.id, rule="thunderstorm", severity="warning", category="safety", dedupe_key=key,
               values={"when": (now + timedelta(hours=3)).strftime("%Y-%m-%dT%H:%M")},
               valid_until=now + timedelta(hours=8), created_at=now)
    db.add(n)
    db.commit()
    return n


def a_question(db, farm: Farm, due: date | None = None) -> FollowUp:
    p = Problem(farm_id=farm.id, status="open", target="rice_blast")
    db.add(p)
    db.flush()
    fu = FollowUp(problem_id=p.id, due_on=due or date.today())
    db.add(fu)
    db.commit()
    return fu


DAY = datetime.combine(date.today(), datetime.min.time()).replace(hour=10)
NIGHT = DAY.replace(hour=22)


# --------------------------------------------------------------------------
# Signing in by SMS
# --------------------------------------------------------------------------

def test_a_farmer_signs_up_with_a_mobile_number_and_nothing_else(client, phone, mail):
    sent, code = signup(client, phone)
    assert sent["channel"] == "sms" and sent["sent_to"] == "+91 ••••••3210"
    assert phone.sent[-1]["to"] == E164 and not mail  # by SMS, and no email went anywhere
    r = finish_signup(client, sent["challenge_id"], code)
    assert r.status_code == 201, r.text
    me = r.json()
    assert me["phone"] == E164 and me["email"] is None
    # With no email, SMS is how this farmer hears from us: on until they say no.
    assert me["sms_pref"] == "warnings" and me["sms_available"] is True
    with SessionLocal() as s:
        ch = s.scalar(select(OtpChallenge))
        assert (ch.channel, ch.destination) == ("sms", E164)


def test_the_code_sms_is_the_code_and_its_expiry_in_the_farmers_language(client, phone):
    signup(client, phone, lang="mr")
    text = phone.sent[-1]["text"]
    code = phone.code()
    assert text.startswith(code) and "5 मिनिटे" in text
    assert "http" not in text and "www" not in text  # a link in a code message is what phishing looks like
    assert sms.segments(text) == 1
    assert phone.sent[-1]["vars"]["otp"] == code  # what a DLT template is filled with


def test_the_code_is_never_written_down(client, phone):
    signup(client, phone)
    code = phone.code()
    with SessionLocal() as s:
        rows = s.scalars(select(SmsLog)).all()
        assert rows and all(r.body is None or code not in r.body for r in rows)
        assert all(PHONE not in r.number for r in rows) and rows[0].number.endswith("3210")


def test_login_by_mobile_goes_by_sms_and_by_email_goes_by_email(client, phone, mail):
    sent, code = signup(client, phone, email="sunita@example.in")
    assert sent["channel"] == "sms"  # a farmer's number first, even with an email on the form
    assert finish_signup(client, sent["challenge_id"], code, email="sunita@example.in").status_code == 201
    prove_email(client, mail)

    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "login", "identifier": PHONE})
    assert r.json()["channel"] == "sms" and r.json()["sent_to"].endswith("3210")
    ok = client.post("/api/auth/login", json={"challenge_id": r.json()["challenge_id"], "code": phone.code(),
                                              "role": "farmer"})
    assert ok.status_code == 200 and ok.json()["phone"] == E164

    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "login", "identifier": "sunita@example.in"})
    assert r.json()["channel"] == "email" and mail[-1]["to"] == "sunita@example.in"


def test_when_the_sms_does_not_go_the_code_falls_back_to_email_and_says_so(client, phone, mail):
    sent, code = signup(client, phone, email="sunita@example.in")
    finish_signup(client, sent["challenge_id"], code, email="sunita@example.in")
    prove_email(client, mail)
    phone.fail = True
    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "login", "identifier": PHONE})
    assert r.status_code == 200
    assert r.json()["channel"] == "email" and r.json()["sent_to"].startswith("su")
    assert mail[-1]["to"] == "sunita@example.in"
    with SessionLocal() as s:  # the failed SMS left no challenge behind to be checked against
        assert s.scalar(select(OtpChallenge).where(OtpChallenge.channel == "sms",
                                                   OtpChallenge.purpose == "login")) is None
        assert s.scalar(select(SmsLog).where(SmsLog.status == "failed")).error == "provider down"


def test_a_failed_sms_with_no_email_to_fall_back_on_says_try_again(client, phone):
    phone.fail = True
    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "signup", "phone": PHONE, "lang": "hi"})
    assert r.status_code == 502 and "SMS" in r.json()["detail"]


def test_a_code_proves_only_the_number_it_went_to(client, phone):
    sent, code = signup(client, phone)
    r = finish_signup(client, sent["challenge_id"], code, number="9123456780")
    assert r.status_code == 400 and "मोबाइल" in r.json()["detail"]


def test_without_sms_a_farmer_still_needs_an_email(client, monkeypatch):
    monkeypatch.setattr(config, "SMS_BACKEND", "off")
    assert client.get("/api/auth/options").json()["otp"] == {"digits": 6, "minutes": 5, "channel": "email",
                                                             "sms": False}
    r = client.post("/api/auth/otp", json={"role": "farmer", "purpose": "signup", "phone": PHONE, "lang": "en"})
    assert r.status_code == 422 and "email" in r.json()["detail"]


def test_options_tell_the_form_a_mobile_number_is_enough(client):
    assert client.get("/api/auth/options").json()["otp"]["sms"] is True


def test_an_officers_code_never_goes_by_sms(client, phone, mail):
    r = client.post("/api/auth/otp", json={"role": "expert", "purpose": "signup", "phone": "9123456780",
                                           "email": "dr.kale@kvk.org.in"})
    assert r.json()["channel"] == "email" and not phone.sent and mail[-1]["to"] == "dr.kale@kvk.org.in"


def test_a_farmer_turns_sms_alerts_off_and_an_officer_has_none(client, phone):
    sent, code = signup(client, phone)
    finish_signup(client, sent["challenge_id"], code)
    r = client.patch("/api/auth/me/profile", json={"sms_pref": "off"})
    assert r.status_code == 200 and r.json()["sms_pref"] == "off"
    assert client.get("/api/auth/me").json()["sms_pref"] == "off"
    assert client.patch("/api/auth/me/profile", json={"sms_pref": "often"}).status_code == 422


# --------------------------------------------------------------------------
# Alerts by SMS
# --------------------------------------------------------------------------

def test_a_weather_warning_reaches_a_phone_without_the_app_once(db, phone):
    kb = get_kb()
    farm = a_farmer(db)
    a_warning(db, farm, DAY)
    assert notify.sms_alerts(db, kb, farm, DAY) == 1
    db.commit()
    msg = phone.sent[-1]
    assert msg["to"] == E164 and msg["kind"] == "warning"
    assert msg["text"].startswith("AnnRakshak: ") and "बिजली" in msg["text"]  # Hindi, the farmer's language
    assert msg["text"].endswith(f"{config.PUBLIC_APP_URL}/app/weather") and sms.segments(msg["text"]) <= 2
    # The watcher runs every half hour; the farmer hears it once.
    assert notify.sms_alerts(db, kb, farm, DAY + timedelta(minutes=30)) == 0
    assert len(phone.sent) == 1


def test_a_warning_waits_out_the_night(db, phone):
    farm = a_farmer(db)
    a_warning(db, farm, NIGHT)
    assert notify.sms_alerts(db, get_kb(), farm, NIGHT) == 0 and not phone.sent


def test_no_sms_for_a_farmer_who_said_no_or_has_email_and_never_asked(db, phone):
    kb = get_kb()
    said_no = a_farmer(db, sms_pref="off")
    has_email = a_farmer(db, email="r@example.in", number="+919000000002")
    said_yes = a_farmer(db, email="s@example.in", number="+919000000003", sms_pref="warnings")
    for f in (said_no, has_email, said_yes):
        a_warning(db, f, DAY)
    assert [notify.sms_alerts(db, kb, f, DAY) for f in (said_no, has_email, said_yes)] == [0, 0, 1]


def test_a_demo_field_is_never_texted(db, phone):
    farm = a_farmer(db, demo=True)
    a_warning(db, farm, DAY)
    assert notify.sms_alerts(db, get_kb(), farm, DAY) == 0 and not phone.sent


def test_alert_sms_stop_at_the_daily_cap_but_the_verdict_still_goes(db, phone, monkeypatch):
    kb = get_kb()
    farm = a_farmer(db)
    for i in range(config.MAX_ALERT_SMS_PER_FARM_PER_DAY + 2):
        a_warning(db, farm, DAY, key=f"thunderstorm:{i}")
    assert notify.sms_alerts(db, kb, farm, DAY) == config.MAX_ALERT_SMS_PER_FARM_PER_DAY
    db.commit()
    fu = a_question(db, farm)
    out = notify.verdict_reached(db, kb, farm, fu.problem_id, "rice_blast")
    assert out["sms"] == "outbox" and phone.sent[-1]["kind"] == "verdict"


def test_the_experts_answer_goes_whatever_the_hour_and_once(db, phone):
    kb = get_kb()
    farm = a_farmer(db, lang="mr")
    fu = a_question(db, farm)
    notify.verdict_reached(db, kb, farm, fu.problem_id, "rice_blast")
    text = phone.sent[-1]["text"]
    assert "तज्ज्ञ" in text and text.endswith(f"/app/history/{fu.problem_id}")
    notify.verdict_reached(db, kb, farm, fu.problem_id, "rice_blast")
    assert len(phone.sent) == 1
    # A corrected verdict is news.
    notify.verdict_reached(db, kb, farm, fu.problem_id, "rice_brown_spot")
    assert len(phone.sent) == 2


def test_the_day_four_question_asks_for_a_reply_only_when_one_will_be_read(db, phone, monkeypatch):
    kb = get_kb()
    farm = a_farmer(db, lang="en")
    a_question(db, farm)
    assert notify.sms_alerts(db, kb, farm, DAY) == 1
    assert "Reply 1 if better, 2 if the same, 3 if worse." in phone.sent[-1]["text"]

    monkeypatch.setattr(config, "SMS_INBOUND_SECRET", "")
    other = a_farmer(db, lang="en", number="+919000000004")
    a_question(db, other)
    notify.sms_alerts(db, kb, other, DAY)
    assert "Tell us in the app:" in phone.sent[-1]["text"] and "Reply 1" not in phone.sent[-1]["text"]


def test_an_old_unanswered_question_is_not_texted_months_late(db, phone):
    farm = a_farmer(db)
    a_question(db, farm, due=date.today() - timedelta(days=30))
    assert notify.sms_alerts(db, get_kb(), farm, DAY) == 0


def test_a_provider_that_is_down_is_tried_again_then_given_up(db, phone):
    kb = get_kb()
    farm = a_farmer(db)
    a_warning(db, farm, DAY)
    phone.fail = True
    for _ in range(config.SMS_RETRIES + 2):
        notify.sms_alerts(db, kb, farm, DAY)
        db.commit()
    tries = db.scalar(select(func.count(SmsLog.id)).where(SmsLog.status == "failed"))
    assert tries == config.SMS_RETRIES


def test_a_field_that_was_texted_can_still_be_removed(client, phone):
    sent, code = signup(client, phone)
    farm_id = finish_signup(client, sent["challenge_id"], code).json()["farm_ids"][0]
    with SessionLocal() as s:
        farm = s.get(Farm, farm_id)
        fu = a_question(s, farm)
        notify.verdict_reached(s, get_kb(), farm, fu.problem_id, "rice_blast")
    assert client.delete(f"/api/farms/{farm_id}").status_code == 204
    with SessionLocal() as s:
        assert s.scalar(select(func.count(SmsLog.id)).where(SmsLog.farm_id == farm_id)) == 0


# --------------------------------------------------------------------------
# Replies by SMS
# --------------------------------------------------------------------------

def reply(c: TestClient, text: str, sender=PHONE, secret: str | None = SECRET):
    headers = {"X-AnnRakshak-Secret": secret} if secret else {}
    return c.post("/api/sms/inbound", data={"sender": sender, "message": text}, headers=headers)


@pytest.fixture()
def asked(client, phone):
    """A farmer with no app, asked on day four how the crop is."""
    sent, code = signup(client, phone, lang="hi")
    farm_id = finish_signup(client, sent["challenge_id"], code, lang="hi").json()["farm_ids"][0]
    with SessionLocal() as s:
        fu = a_question(s, s.get(Farm, farm_id))
        return fu.id


def test_three_by_sms_puts_an_expert_back_on_the_case(client, phone, asked):
    r = reply(client, "3 पत्ते और पीले हो गए")
    assert r.status_code == 200 and r.json()["response"] == "got_worse" and r.json()["escalated"]
    with SessionLocal() as s:
        fu = s.get(FollowUp, asked)
        assert fu.response == "got_worse"
        assert s.scalar(select(Case).where(Case.problem_id == fu.problem_id)).status == "open"
    assert phone.sent[-1]["to"] == E164 and "विशेषज्ञ" in phone.sent[-1]["text"]


@pytest.mark.parametrize("text,answer", [
    ("1", "improved"), ("better", "improved"), ("बेहतर है", "improved"), ("१", "improved"),
    ("2", "no_change"), ("वैसा ही", "no_change"), ("3.", "got_worse"), ("kharab", "got_worse"),
])
def test_a_reply_in_digits_or_the_farmers_own_words_is_read(client, asked, text, answer):
    assert reply(client, text).json()["response"] == answer
    with SessionLocal() as s:
        assert s.get(FollowUp, asked).response == answer


def test_better_closes_the_case_and_same_asks_again_later(client, phone, asked):
    assert reply(client, "2").json()["response"] == "no_change"
    with SessionLocal() as s:
        assert s.get(FollowUp, asked).response == "no_change"
        assert s.scalar(select(func.count(FollowUp.id)).where(FollowUp.response.is_(None))) == 1
    assert f"{config.FOLLOWUP_DUE_DAYS} दिन" in phone.sent[-1]["text"]


@pytest.mark.parametrize("text", ["not better", "बेहतर नहीं", "hello", "12", ""])
def test_what_cannot_be_read_is_answered_with_the_options_and_changes_nothing(client, phone, asked, text):
    r = reply(client, text)
    assert r.json()["matched"] is False
    assert "1" in phone.sent[-1]["text"] and "3" in phone.sent[-1]["text"]
    with SessionLocal() as s:
        assert s.get(FollowUp, asked).response is None


def test_an_unknown_number_is_logged_and_told_the_options(client, phone):
    r = reply(client, "3", sender="9000000099")
    assert r.json() == {"matched": False, "reason": "unknown sender"}
    assert phone.sent[-1]["to"] == "+919000000099" and "Reply 1 if better" in phone.sent[-1]["text"]
    with SessionLocal() as s:
        row = s.scalar(select(SmsLog).where(SmsLog.direction == "in"))
        assert row.kind == "unknown" and "9000000099" not in row.number


@pytest.mark.parametrize("secret", [None, "wrong"])
def test_a_reply_without_the_providers_secret_is_refused(client, asked, secret):
    assert reply(client, "1", secret=secret).status_code == 403
    with SessionLocal() as s:
        assert s.get(FollowUp, asked).response is None


def test_nothing_is_taken_when_no_secret_is_configured(client, monkeypatch, asked):
    monkeypatch.setattr(config, "SMS_INBOUND_SECRET", "")
    assert reply(client, "1", secret="").status_code == 403


def test_stop_turns_sms_off_and_start_turns_it_back_on(client, phone, asked):
    r = reply(client, "STOP")
    assert r.json()["sms_pref"] == "off" and "START" in phone.sent[-1]["text"]
    assert client.get("/api/auth/me").json()["sms_pref"] == "off"
    with SessionLocal() as s:
        farm = s.scalar(select(Farm).where(Farm.phone == E164))
        assert notify.sms_alerts(s, get_kb(), farm, DAY) == 0  # the day-four question is not sent
    reply(client, "चालू")
    assert client.get("/api/auth/me").json()["sms_pref"] == "warnings"


def test_stop_inside_a_sentence_is_not_an_unsubscribe():
    assert sms.parse_switch("stop the spray?") is None
    assert sms.parse_switch("STOP") == "off" and sms.parse_switch("SMS बंद करो") == "off"
    assert sms.parse_switch("बंद") == "off" and sms.parse_switch("Start") == "on"


def test_a_twilio_reply_is_taken_on_twilios_signature(client, phone, asked, monkeypatch):
    monkeypatch.setattr(config, "SMS_INBOUND_SECRET", "")
    monkeypatch.setattr(config, "SMS_BACKEND", "twilio")
    monkeypatch.setattr(config, "TWILIO_ACCOUNT_SID", "AC123")
    monkeypatch.setattr(config, "TWILIO_AUTH_TOKEN", "tok")
    monkeypatch.setattr(config, "TWILIO_FROM", "+15550001111")
    posted = []
    monkeypatch.setattr(sms.httpx, "post", lambda url, **kw: posted.append((url, kw)) or httpx.Response(201))
    params = {"From": E164, "Body": "1"}
    url = f"{config.PUBLIC_APP_URL}/api/sms/inbound"
    data = url + "".join(k + params[k] for k in sorted(params))
    good = base64.b64encode(hmac.new(b"tok", data.encode(), hashlib.sha1).digest()).decode()

    assert client.post("/api/sms/inbound", data=params, headers={"X-Twilio-Signature": "forged"}).status_code == 403
    r = client.post("/api/sms/inbound", data=params, headers={"X-Twilio-Signature": good})
    assert r.status_code == 200 and "<Response/>" in r.text
    with SessionLocal() as s:
        assert s.get(FollowUp, asked).response == "improved"
    assert posted[-1][1]["data"]["To"] == E164  # the thank-you went back by Twilio


# --------------------------------------------------------------------------
# The sender itself
# --------------------------------------------------------------------------

def test_msg91_is_sent_with_its_dlt_template_and_never_raises(monkeypatch):
    monkeypatch.setattr(config, "SMS_BACKEND", "msg91")
    monkeypatch.setattr(config, "MSG91_AUTH_KEY", "key")
    monkeypatch.setattr(config, "SMS_SENDER_ID", "ANRKSK")
    monkeypatch.setattr(config, "MSG91_TEMPLATES", {k: f"tpl-{k}" for k in sms.KINDS})
    cache._counts.clear()
    calls = []

    def fake_post(url, **kw):
        calls.append(kw)
        return httpx.Response(200, json={"type": "success"})

    monkeypatch.setattr(sms.httpx, "post", fake_post)
    assert sms.send(E164, "123456 is your code", kind="otp", variables={"otp": "123456"}) == ("sent", None)
    body = calls[-1]["json"]
    assert body["template_id"] == "tpl-otp" and body["sender"] == "ANRKSK"
    assert body["recipients"] == [{"mobiles": "919876543210", "text": "123456 is your code", "otp": "123456"}]
    assert calls[-1]["headers"]["authkey"] == "key" and calls[-1]["timeout"] == config.SMS_TIMEOUT_S

    monkeypatch.setattr(sms.httpx, "post", lambda url, **kw: httpx.Response(
        200, json={"type": "error", "message": "Invalid template for 919876543210"}))
    status, err = sms.send(E164, "x", kind="otp")
    assert status == "failed" and "9876543210" not in err

    def down(url, **kw):
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(sms.httpx, "post", down)
    assert sms.send(E164, "x", kind="otp") == ("failed", "ConnectTimeout")


def test_one_number_is_never_flooded(phone):
    results = [sms.send(E164, "hello", kind="reply")[0] for _ in range(config.SMS_MAX_PER_NUMBER_PER_HOUR + 2)]
    assert results.count("outbox") == config.SMS_MAX_PER_NUMBER_PER_HOUR
    assert results[-1] == "limited"


def test_the_outbox_writes_a_file_a_developer_can_read(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "SMS_BACKEND", "outbox")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    cache._counts.clear()
    assert sms.send(E164, "मौसम चेतावनी", kind="warning") == ("outbox", None)
    (f,) = (tmp_path / "sms-outbox").iterdir()
    assert "मौसम चेतावनी" in f.read_text(encoding="utf-8")


def test_a_long_message_is_cut_to_two_sms_and_the_link_survives():
    link = "https://annrakshak.in/app/history/42"
    words, whole = sms.fit("AnnRakshak: " + "धान में झुलसा रोग का खतरा है। " * 20, link)
    assert sms.segments(whole) <= 2 and whole.endswith(link) and words.endswith("…")
    assert sms.segments("a" * 160) == 1 and sms.segments("a" * 161) == 2
    assert sms.segments("क" * 70) == 1 and sms.segments("क" * 71) == 2
    assert sms.plain("Rain — 30°C") == "Rain - 30 C"  # typography that would cost a segment


def test_a_number_is_masked_wherever_it_is_written():
    assert sms.mask(E164) == "+91 ••••••3210"
    assert sms.mask("12") == "••••"


# --------------------------------------------------------------------------
# What production refuses
# --------------------------------------------------------------------------

@pytest.fixture()
def safe(monkeypatch):
    monkeypatch.setattr(config, "DEMO_LOGIN", False)
    monkeypatch.setattr(config, "EXPERT_AUTO_VERIFY", False)
    monkeypatch.setattr(config, "COOKIE_SECURE", True)
    monkeypatch.setattr(config, "DB_URL", "postgresql+psycopg://user@host/annrakshak")
    monkeypatch.setattr(config, "PUBLIC_APP_URL", "https://annrakshak.in")
    monkeypatch.setattr(config, "EMAIL_BACKEND", "smtp")
    monkeypatch.setattr(config, "TURNSTILE_SECRET", "0xAREALSECRETFROMCLOUDFLARE")
    monkeypatch.setattr(config, "SMS_BACKEND", "off")
    return monkeypatch


def test_sms_off_is_a_decision_and_says_nothing(safe):
    assert config.start_checks() == []


def test_production_refuses_an_sms_outbox(safe):
    safe.setattr(config, "SMS_BACKEND", "outbox")
    (problem,) = config.start_checks()
    assert "SMS_BACKEND is 'outbox'" in problem


def test_production_refuses_msg91_without_its_key_or_a_dlt_template(safe):
    safe.setattr(config, "SMS_BACKEND", "msg91")
    safe.setattr(config, "MSG91_AUTH_KEY", "key")
    safe.setattr(config, "SMS_SENDER_ID", "ANRKSK")
    safe.setattr(config, "MSG91_TEMPLATES", {k: f"tpl-{k}" for k in sms.KINDS})
    assert config.start_checks() == []
    safe.setattr(config, "MSG91_TEMPLATES", {k: f"tpl-{k}" for k in sms.KINDS} | {"verdict": ""})
    (problem,) = config.start_checks()
    assert "MSG91_TEMPLATE_VERDICT" in problem
    safe.setattr(config, "MSG91_AUTH_KEY", "")
    assert "MSG91_AUTH_KEY" in config.start_checks()[0]


def test_production_refuses_twilio_without_its_token(safe):
    safe.setattr(config, "SMS_BACKEND", "twilio")
    safe.setattr(config, "TWILIO_ACCOUNT_SID", "AC123")
    safe.setattr(config, "TWILIO_FROM", "+15550001111")
    safe.setattr(config, "TWILIO_AUTH_TOKEN", "")
    (problem,) = config.start_checks()
    assert "TWILIO_AUTH_TOKEN" in problem


def test_a_misspelt_backend_is_caught(safe):
    safe.setattr(config, "SMS_BACKEND", "msg-91")
    assert "must be one of" in config.start_checks()[0]


# --- the secret stays out of logs ---------------------------------------------

def test_a_secret_in_the_query_string_is_refused_even_when_it_is_right(client, asked):
    """A query string is written into every access log on the way here. A
    callback registered with ?key= would leave the secret wherever the logs
    go, so it is refused outright rather than quietly accepted."""
    r = client.post(f"/api/sms/inbound?key={SECRET}", data={"sender": PHONE, "message": "1"})
    assert r.status_code == 403
    with SessionLocal() as s:
        assert s.get(FollowUp, asked).response is None


def test_a_provider_without_headers_puts_the_secret_in_the_path(client, phone, asked):
    r = client.post(f"/api/sms/inbound/{SECRET}", data={"sender": PHONE, "message": "1"})
    assert r.status_code == 200 and r.json()["matched"]
    assert client.post("/api/sms/inbound/not-the-secret", data={"sender": PHONE, "message": "1"}).status_code == 403


def test_the_path_secret_is_redacted_from_the_access_log():
    import logging

    from app.routers.sms import _HideInboundSecret

    rec = logging.LogRecord("uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
                            ("1.2.3.4:5", "POST", f"/api/sms/inbound/{SECRET}", "1.1", 200), None)
    _HideInboundSecret().filter(rec)
    line = rec.getMessage()
    assert SECRET not in line and "/api/sms/inbound/[redacted]" in line


# --- an email typed beside a phone is not proved by the phone's code -----------

def test_an_email_typed_at_an_sms_sign_up_is_not_the_accounts_until_it_is_proved(client, phone, mail):
    """The SMS code proves the phone. Taken at its word, the email beside it let
    anyone put someone else's address on their account: that person could no
    longer sign up with it, and the app wrote to a stranger's inbox."""
    victim = "someone.else@example.com"
    sent, code = signup(client, phone, email=victim)
    me = finish_signup(client, sent["challenge_id"], code, email=victim).json()
    assert me["email"] is None and me["pending_email"] == victim
    with SessionLocal() as s:
        farms = s.scalars(select(Farm).where(Farm.user_id == me["id"])).all()
        assert farms and all(f.email is None for f in farms), "the farm would email a stranger"

    # The owner of that inbox can still sign up with it.
    other = TestClient(app)
    r = other.post("/api/auth/check", json={"email": victim, "phone": "9123456780"})
    assert r.json()["free"] is True

    # And nobody signs in with it.
    r = other.post("/api/auth/otp", json={"role": "farmer", "purpose": "login", "identifier": victim})
    assert r.status_code == 404


def test_the_farmer_proves_the_email_with_a_code_sent_there(client, phone, mail):
    sent, code = signup(client, phone, email="mine@example.com")
    me = finish_signup(client, sent["challenge_id"], code, email="mine@example.com").json()
    r = client.post("/api/auth/me/email", json={"lang": "en"})
    assert r.status_code == 200, r.text
    challenge = r.json()["challenge_id"]
    assert mail[-1]["to"] == "mine@example.com"
    emailed = re.search(r"\b(\d{6})\b", mail[-1]["text"]).group(1)
    wrong = client.post("/api/auth/me/email/verify", json={"challenge_id": challenge, "code": "000000"})
    assert wrong.status_code == 400
    ok = client.post("/api/auth/me/email/verify", json={"challenge_id": challenge, "code": emailed})
    assert ok.status_code == 200, ok.text
    assert ok.json()["email"] == "mine@example.com" and ok.json()["pending_email"] is None
    with SessionLocal() as s:
        assert all(f.email == "mine@example.com"
                   for f in s.scalars(select(Farm).where(Farm.user_id == me["id"])).all())
