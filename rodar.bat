@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

echo ================================================
echo Bela Casa - Inicializador
echo ================================================

if not exist "requirements.txt" (
  echo [ERRO] Arquivo requirements.txt nao encontrado nesta pasta.
  pause
  exit /b 1
)

set "PY_CMD="
where py >nul 2>nul
if not errorlevel 1 set "PY_CMD=py -3"
if not defined PY_CMD (
  where python >nul 2>nul
  if not errorlevel 1 set "PY_CMD=python"
)

if not defined PY_CMD (
  echo [AVISO] Python nao foi encontrado no computador.
  where winget >nul 2>nul
  if errorlevel 1 (
    echo [ERRO] Nao foi possivel instalar automaticamente: winget nao encontrado.
    echo Instale Python 3.10+ e rode este arquivo novamente.
    pause
    exit /b 1
  )

  echo Tentando instalar Python 3 automaticamente via winget...
  winget install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
  if errorlevel 1 (
    echo [ERRO] Falha na instalacao automatica do Python.
    echo Instale manualmente o Python 3.10+ e rode novamente.
    pause
    exit /b 1
  )

  set "PY_CMD="
  where py >nul 2>nul
  if not errorlevel 1 set "PY_CMD=py -3"
  if not defined PY_CMD (
    where python >nul 2>nul
    if not errorlevel 1 set "PY_CMD=python"
  )
)

if not defined PY_CMD (
  echo [ERRO] Python continua indisponivel apos tentativa de instalacao.
  pause
  exit /b 1
)

echo [OK] Python detectado: %PY_CMD%

if not exist ".venv\Scripts\python.exe" (
  echo Criando ambiente virtual local .venv...
  %PY_CMD% -m venv .venv
  if errorlevel 1 (
    echo [ERRO] Nao foi possivel criar o ambiente virtual.
    pause
    exit /b 1
  )
)

set "VENV_PY=.venv\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [ERRO] Python da venv nao encontrado em %VENV_PY%.
  pause
  exit /b 1
)

echo Garantindo pip na venv...
"%VENV_PY%" -m ensurepip --upgrade >nul 2>nul

echo Atualizando ferramentas basicas de instalacao da venv...
"%VENV_PY%" -m pip --disable-pip-version-check install --upgrade pip setuptools wheel
if errorlevel 1 (
  echo [AVISO] Nao foi possivel atualizar pip/setuptools/wheel. Continuando...
)

echo Instalando as dependencias do projeto...
"%VENV_PY%" -m pip --disable-pip-version-check install -r requirements.txt
if errorlevel 1 (
  echo Primeira tentativa falhou. Limpando cache e tentando novamente...
  "%VENV_PY%" -m pip --disable-pip-version-check install --no-cache-dir -r requirements.txt
  if errorlevel 1 (
    echo [ERRO] Nao foi possivel instalar as dependencias na venv.
    pause
    exit /b 1
  )
)

echo Validando imports principais...
"%VENV_PY%" -c "import flask, werkzeug, app"
if errorlevel 1 (
  echo [ERRO] Falha ao validar imports dentro da venv.
  echo Dependencias instaladas:
  "%VENV_PY%" -m pip show Flask Werkzeug
  pause
  exit /b 1
)

echo Iniciando o Bela Casa em http://127.0.0.1:8000 ...
"%VENV_PY%" app.py

echo.
echo Aplicacao encerrada.
pause
