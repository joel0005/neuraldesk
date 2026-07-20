@echo off
echo ==========================================
echo   NeuralDesk - Code Protection
echo   This compiles Python files to bytecode
echo   and removes readable source code
echo ==========================================
echo.
echo WARNING: This cannot be undone!
echo Make sure you have a backup (GitHub).
echo.
set /p confirm="Type YES to continue: "
if /i not "%confirm%"=="YES" (
    echo Cancelled.
    pause
    exit
)

echo.
echo Compiling Python files...
python -m compileall src -b -q
python -m compileall app.py -b -q

echo Removing source files...
for /r src %%f in (*.py) do (
    if exist "%%~dpnf.pyc" (
        del "%%f"
        ren "%%~dpnf.pyc" "%%~nf.py"
    )
)

if exist app.pyc (
    del app.py
    ren app.pyc app.py
)

echo Removing unnecessary files...
del /q admin_tool.py 2>nul
del /q debug.py 2>nul
del /q debug2.py 2>nul
del /q fix_questions.py 2>nul
del /q fix_threshold.py 2>nul
del /q test_api.py 2>nul
del /q test_direct.py 2>nul
del /q test_full.py 2>nul
del /q test_llm.py 2>nul
del /q test_upload.py 2>nul
del /q check_questions.py 2>nul
del /q upgrade.py 2>nul
del /q protect.bat 2>nul
del /q package_for_client.bat 2>nul
del /q .gitignore 2>nul
rmdir /s /q .git 2>nul

echo.
echo ==========================================
echo   Code protected! Source files removed.
echo   Client can run but cannot read your code.
echo ==========================================
pause