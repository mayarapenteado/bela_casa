@echo off
cd /d "%~dp0"
echo Instalando as dependencias do projeto...
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Nao foi possivel instalar as dependencias. Confira sua instalacao do Python.
  pause
  exit /b 1
)
echo Iniciando o Bela Casa...
python app.py
pause
