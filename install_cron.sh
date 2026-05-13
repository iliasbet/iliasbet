#!/usr/bin/env bash
# install_cron.sh – Installe la tâche cron de rappel de loyer
# Usage: bash install_cron.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="$(command -v python3)"
AGENT="$SCRIPT_DIR/agent.py"
LOG="$SCRIPT_DIR/cron.log"

# Vérifie que l'env est configuré
if [[ ! -f "$SCRIPT_DIR/.env" ]]; then
  echo "[ERREUR] Fichier .env manquant. Copie .env.example en .env et remplis les valeurs."
  exit 1
fi

# Installe les dépendances si nécessaire
echo "Installation des dépendances Python…"
"$PYTHON" -m pip install -q -r "$SCRIPT_DIR/requirements.txt"

# Ligne cron : tous les jours à 9h00 du 25 au 31 (couvre toutes les fins de mois)
# Le script vérifie lui-même si on est vraiment dans les derniers jours du mois
CRON_LINE="0 9 25-31 * * $PYTHON $AGENT >> $LOG 2>&1"

# Ajoute la ligne uniquement si elle n'est pas déjà présente
EXISTING=$(crontab -l 2>/dev/null || true)

if echo "$EXISTING" | grep -qF "$AGENT"; then
  echo "La tâche cron existe déjà :"
  echo "$EXISTING" | grep "$AGENT"
else
  (echo "$EXISTING"; echo "$CRON_LINE") | crontab -
  echo "Tâche cron installée avec succès :"
  echo "  $CRON_LINE"
fi

echo ""
echo "Prochaines exécutions : du 25 au 31 de chaque mois à 09h00"
echo "Logs : $LOG"
echo ""
echo "Pour tester l'agent maintenant (sans attendre la fin du mois) :"
echo "  LAST_DAYS_THRESHOLD=31 $PYTHON $AGENT"
echo ""
echo "Pour désinstaller : crontab -e  (puis supprimer la ligne)"
