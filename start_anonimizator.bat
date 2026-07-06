@echo off
echo Instaluje/aktualizuje zaleznosci (jednorazowo moze potrwac dluzej)...
pip install -r requirements.txt
echo.
echo Uruchamiam Anonimizator lokalnie pod adresem http://127.0.0.1:5000
echo Zamknij to okno, aby zatrzymac aplikacje.
python app.py
pause
