@echo off
:: ─────────────────────────────────────────────────────────────────────────────
:: refresh.bat — Lance l'agent J-1 + ouvre le blog dans le navigateur
:: Double-cliquer ou lancer depuis le terminal : .\refresh.bat
:: ─────────────────────────────────────────────────────────────────────────────

setlocal

cd /d "%~dp0"

echo.
echo  ⚽  Blog CdM 2026 — Rafraîchissement J-1
echo  ───────────────────────────────────────────
echo.

:: Vérifier que .env existe
if not exist ".env" (
    echo  ❌  Fichier .env introuvable.
    echo      Copiez .env.example en .env et renseignez ANTHROPIC_API_KEY.
    pause
    exit /b 1
)

:: Lancer l'agent en mode refresh
python agent.py --refresh
if errorlevel 1 (
    echo.
    echo  ❌  L'agent a rencontré une erreur. Voir les messages ci-dessus.
    pause
    exit /b 1
)

echo.
echo  🌐  Démarrage du serveur local...
start "" http://localhost:8000

:: Lancer le serveur en arrière-plan (remplace un éventuel serveur existant)
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8000 "') do (
    taskkill /f /pid %%a >nul 2>&1
)
start /b python -m http.server 8000

echo  ✅  Blog mis à jour et disponible sur http://localhost:8000
echo.
pause
