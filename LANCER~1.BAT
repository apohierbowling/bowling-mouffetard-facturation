@echo off
REM Se place dans le dossier contenant ce fichier .bat (donc dans le dossier de l'appli)
cd /d "%~dp0"

echo Lancement de l'application Devis ^& Factures...
echo (le navigateur va s'ouvrir automatiquement dans quelques secondes)
echo.

python -m streamlit run app.py

echo.
echo L'application s'est arretee.
pause
