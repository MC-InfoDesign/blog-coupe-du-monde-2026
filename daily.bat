@echo off
cd /d "%~dp0"

echo.
echo  ===========================================
echo   Blog CdM 2026 - Refresh quotidien
echo  ===========================================
echo.

:: 0. Installer les dependances si besoin
echo [0/4] Verification des dependances Python...
python -m pip install requests groq anthropic python-dotenv -q

:: 1. Rafraichir les articles
echo [1/4] Generation des articles J-1...
python agent.py --refresh --count 12
if errorlevel 1 ( echo ERREUR agent.py & pause & exit /b 1 )

:: 2. Mettre a jour le sitemap
echo.
echo [2/4] Mise a jour du sitemap...
python sitemap.py --base-url https://blog-coupe-du-monde-2026.vercel.app

:: 3. Committer
echo.
echo [3/4] Commit Git...
git add articles.json sitemap.xml
git diff --staged --quiet && (echo Rien a committer) || git commit -m "Refresh du %date%"

:: 4. Pousser vers GitHub (Vercel redeploie automatiquement)
echo.
echo [4/4] Push vers GitHub...
git push
if errorlevel 1 ( echo ERREUR git push & pause & exit /b 1 )

echo.
echo  OK - Blog mis a jour sur https://blog-coupe-du-monde-2026.vercel.app
echo.
pause
