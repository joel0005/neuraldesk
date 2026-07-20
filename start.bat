@echo off
echo Starting NeuralDesk...
call venv\Scripts\activate
echo.
echo ==========================================
echo   NeuralDesk is running!
echo   Open: http://localhost:5000
echo   Admin: http://localhost:5000/admin
echo   Press Ctrl+C to stop
echo ==========================================
echo.
python app.py