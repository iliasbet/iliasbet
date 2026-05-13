# Agent de rappel de loyer par SMS

Surveille les emails de **malocateam** dans Gmail, extrait les informations de loyer avec **Claude (Anthropic)** et envoie un **SMS via Twilio** en fin de mois.

## Architecture

```
Gmail (IMAP)  →  agent.py  →  Claude API  →  SMS Twilio
                     ↑
               cron (25-31 du mois, 9h)
```

## Prérequis

- Python 3.10+
- Un compte [Twilio](https://console.twilio.com) avec un numéro SMS actif
- Un [App Password Google](https://myaccount.google.com/apppasswords) (nécessite la 2FA Gmail)
- Une clé API [Anthropic](https://console.anthropic.com)

## Installation rapide

```bash
# 1. Clone et configure
git clone <repo>
cd iliasbet
cp .env.example .env
nano .env          # Remplis toutes les valeurs

# 2. Installe le cron (lance aussi pip install automatiquement)
bash install_cron.sh
```

## Configuration (.env)

| Variable | Description |
|---|---|
| `GMAIL_ADDRESS` | Ton adresse Gmail |
| `GMAIL_APP_PASSWORD` | App Password Google (16 car.) |
| `MALOCATEAM_SENDER` | Filtre expéditeur (défaut: `malocateam`) |
| `TWILIO_ACCOUNT_SID` | SID Twilio |
| `TWILIO_AUTH_TOKEN` | Token Twilio |
| `TWILIO_PHONE_NUMBER` | Numéro source Twilio (`+33…`) |
| `MY_PHONE_NUMBER` | Ton numéro cible (`+33…`) |
| `ANTHROPIC_API_KEY` | Clé API Claude |
| `LAST_DAYS_THRESHOLD` | Jours avant fin de mois (défaut: `5`) |

## Test manuel

```bash
# Tester sans attendre la fin du mois
LAST_DAYS_THRESHOLD=31 python3 agent.py

# Voir les logs
tail -f agent.log
```

## Comportement

1. Le cron tourne chaque jour du **25 au 31** à **9h00**
2. L'agent vérifie s'il a déjà envoyé un SMS ce mois (`state.json`) → évite les doublons
3. Il cherche le dernier email de malocateam dans Gmail
4. Claude extrait le montant, la date d'échéance et génère le message SMS
5. Twilio envoie le SMS

Si aucun email malocateam n'est trouvé, un rappel générique est envoyé quand même.

## Fichiers

```
agent.py          # Script principal
requirements.txt  # Dépendances Python
.env.example      # Template de configuration
install_cron.sh   # Installe la tâche cron
state.json        # Créé automatiquement – suivi des envois
agent.log         # Logs de l'agent
cron.log          # Logs du cron
```
