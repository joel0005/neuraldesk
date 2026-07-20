@echo off
echo ==========================================
echo   NeuralDesk - AI Chatbot Builder Setup
echo ==========================================
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found. Install Python 3.10+ from python.org
    pause
    exit
)

echo Creating virtual environment...
python -m venv venv
call venv\Scripts\activate

echo Installing packages (this takes a few minutes)...
pip install -r requirements.txt

mkdir db_data 2>nul
mkdir uploads 2>nul
mkdir db_data\vectors 2>nul

echo.
echo ==========================================
echo   Choose your AI setup
echo ==========================================
echo 1. Use Ollama (free, runs on this PC/server)
echo 2. Use a cloud API (OpenAI, Gemini, Claude, Groq, Mistral)
echo 3. Skip - I'll configure it later in Settings
echo.
set /p choice="Enter choice (1/2/3): "

if "%choice%"=="1" goto ollama_setup
if "%choice%"=="2" goto api_setup
if "%choice%"=="3" goto skip_setup
goto skip_setup

:ollama_setup
ollama --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo Ollama not found. Please install it from https://ollama.ai
    echo Then run this script again.
    pause
    exit
)

echo.
echo Checking your installed Ollama models...
ollama list

echo.
set /p hasmodel="Do you already have a model installed? (y/n): "
if /i "%hasmodel%"=="y" goto skip_pull

echo Pulling a lightweight free model (gemma3:latest)...
ollama pull gemma3:latest
goto skip_pull

:api_setup
echo.
echo You'll add your API key later in the Settings page after logging in.
echo Supported: OpenAI, Google Gemini, Anthropic Claude, Groq, Mistral
goto skip_setup

:skip_pull
:skip_setup
echo.
echo ==========================================
echo   Setup Complete!
echo   Run: start.bat
echo ==========================================
pause