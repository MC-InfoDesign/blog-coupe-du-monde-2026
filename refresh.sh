#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# refresh.sh — Lance l'agent J-1 + ouvre le blog (Linux/Mac/WSL)
# Usage : bash refresh.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

echo ""
echo "  ⚽  Blog CdM 2026 — Rafraîchissement J-1"
echo "  ───────────────────────────────────────────"
echo ""

# Vérifier .env
if [ ! -f ".env" ]; then
    echo "  ❌  Fichier .env introuvable."
    echo "      Copiez .env.example en .env et renseignez ANTHROPIC_API_KEY."
    exit 1
fi

# Lancer l'agent
python agent.py --refresh

echo ""
echo "  🌐  Démarrage du serveur local…"

# Tuer un éventuel serveur existant sur 8000
fuser -k 8000/tcp 2>/dev/null || true

# Lancer le serveur en arrière-plan
python -m http.server 8000 &
SERVER_PID=$!
echo "  ✅  Serveur démarré (PID $SERVER_PID) sur http://localhost:8000"

# Ouvrir dans le navigateur selon l'OS
if command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:8000
elif command -v open &>/dev/null; then
    open http://localhost:8000
fi

echo ""
echo "  Appuyez sur Ctrl+C pour arrêter le serveur."
wait $SERVER_PID
