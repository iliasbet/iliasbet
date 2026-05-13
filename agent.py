#!/usr/bin/env python3
"""
Agent de rappel de loyer - Lit Gmail (malocateam), parse avec Claude, envoie SMS Twilio.
Conçu pour tourner en cron en fin de mois.
"""

import os
import imaplib
import email
import email.header
import json
import calendar
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
import anthropic

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(Path(__file__).parent / "agent.log"),
    ],
)
log = logging.getLogger(__name__)

STATE_FILE = Path(__file__).parent / "state.json"
MALOCATEAM_SENDER = os.getenv("MALOCATEAM_SENDER", "malocateam")
LAST_DAYS_THRESHOLD = int(os.getenv("LAST_DAYS_THRESHOLD", "5"))


# ---------------------------------------------------------------------------
# State management – évite les doublons d'envoi dans le même mois
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def already_sent_this_month() -> bool:
    state = load_state()
    current_month = datetime.now().strftime("%Y-%m")
    return state.get("last_sent_month") == current_month


def mark_sent(subject: str) -> None:
    save_state({
        "last_sent_month": datetime.now().strftime("%Y-%m"),
        "last_email_subject": subject,
        "sent_at": datetime.now().isoformat(),
    })


# ---------------------------------------------------------------------------
# Timing – on n'envoie que dans les derniers jours du mois
# ---------------------------------------------------------------------------

def is_end_of_month() -> bool:
    today = datetime.now()
    last_day = calendar.monthrange(today.year, today.month)[1]
    return today.day >= (last_day - LAST_DAYS_THRESHOLD + 1)


# ---------------------------------------------------------------------------
# Gmail via IMAP (App Password)
# ---------------------------------------------------------------------------

def decode_header_value(value: str) -> str:
    parts = email.header.decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def get_body(msg: email.message.Message) -> str:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset() or "utf-8"
                return payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        charset = msg.get_content_charset() or "utf-8"
        return payload.decode(charset, errors="replace")
    return ""


def fetch_latest_malocateam_email() -> dict | None:
    gmail_address = os.environ["GMAIL_ADDRESS"]
    app_password = os.environ["GMAIL_APP_PASSWORD"]

    log.info("Connexion à Gmail IMAP…")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(gmail_address, app_password)
    mail.select("inbox")

    # Cherche tous les emails contenant le mot malocateam dans l'expéditeur
    _, data = mail.search(None, f'FROM "{MALOCATEAM_SENDER}"')
    ids = data[0].split()

    if not ids:
        log.warning("Aucun email de malocateam trouvé dans la boite.")
        mail.logout()
        return None

    # Prend le plus récent
    latest_id = ids[-1]
    _, msg_data = mail.fetch(latest_id, "(RFC822)")
    raw = msg_data[0][1]
    mail.logout()

    msg = email.message_from_bytes(raw)
    result = {
        "subject": decode_header_value(msg.get("Subject", "(sans sujet)")),
        "from": msg.get("From", ""),
        "date": msg.get("Date", ""),
        "body": get_body(msg),
    }
    log.info("Email trouvé: [%s] — %s", result["date"], result["subject"])
    return result


# ---------------------------------------------------------------------------
# Claude – extraction intelligente des infos de loyer
# ---------------------------------------------------------------------------

def parse_rent_info(email_data: dict) -> dict:
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    system_prompt = (
        "Tu es un assistant qui extrait les informations de loyer depuis des emails "
        "de gestion locative (malocateam). Tu réponds UNIQUEMENT avec du JSON valide, "
        "sans markdown, sans explication."
    )

    user_prompt = f"""Email de malocateam:
Sujet: {email_data['subject']}
Date: {email_data['date']}
Corps:
{email_data['body'][:3000]}

Extrait et retourne ce JSON:
{{
  "montant": "montant en euros (ex: 850€) ou null si non trouvé",
  "date_echeance": "date d'échéance ou 'fin du mois' si non précisée",
  "message_sms": "SMS de rappel en français, max 160 caractères, incluant le montant si disponible"
}}"""

    log.info("Analyse de l'email avec Claude…")
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = response.content[0].text.strip()
    # Retire les blocs markdown si Claude en ajoute quand même
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    return json.loads(raw)


# ---------------------------------------------------------------------------
# SMS via Twilio
# ---------------------------------------------------------------------------

def send_sms(body: str) -> None:
    from twilio.rest import Client  # import tardif pour garder l'agent léger sans Twilio

    account_sid = os.environ["TWILIO_ACCOUNT_SID"]
    auth_token = os.environ["TWILIO_AUTH_TOKEN"]
    from_number = os.environ["TWILIO_PHONE_NUMBER"]
    to_number = os.environ["MY_PHONE_NUMBER"]

    client = Client(account_sid, auth_token)
    message = client.messages.create(body=body, from_=from_number, to=to_number)
    log.info("SMS envoyé (sid=%s): %s", message.sid, body)


# ---------------------------------------------------------------------------
# Point d'entrée principal
# ---------------------------------------------------------------------------

def main() -> None:
    log.info("=== Agent loyer démarré ===")

    if already_sent_this_month():
        log.info("SMS déjà envoyé ce mois-ci. Rien à faire.")
        return

    if not is_end_of_month():
        log.info(
            "Pas encore en fin de mois (seuil: %d derniers jours). Rien à faire.",
            LAST_DAYS_THRESHOLD,
        )
        return

    # 1. Lire Gmail
    email_data = fetch_latest_malocateam_email()

    if email_data is None:
        # Fallback : pas d'email trouvé, on envoie quand même un rappel générique
        sms = "Rappel loyer: pense à vérifier ton avis de loyer malocateam et à payer avant la fin du mois!"
        send_sms(sms)
        mark_sent("(aucun email trouvé – rappel générique)")
        return

    # 2. Parser avec Claude
    rent_info = parse_rent_info(email_data)
    log.info("Infos extraites: %s", rent_info)

    # 3. Construire le message SMS
    sms = rent_info.get("message_sms")
    if not sms:
        montant = rent_info.get("montant", "?")
        echeance = rent_info.get("date_echeance", "fin du mois")
        sms = f"Rappel loyer: {montant} à payer avant le {echeance}. (malocateam)"

    # Tronque à 160 caractères (limite SMS standard)
    sms = sms[:160]

    # 4. Envoyer le SMS
    send_sms(sms)
    mark_sent(email_data["subject"])

    log.info("=== Agent terminé avec succès ===")


if __name__ == "__main__":
    main()
