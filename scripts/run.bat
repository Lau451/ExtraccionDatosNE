@echo off
cd /d %~dp0..

start "extraccion (8000)" cmd /k "call venv\Scripts\activate.bat && uvicorn services.extraccion.main:app --host 0.0.0.0 --port 8000"
start "presupuestacion (8001)" cmd /k "call venv\Scripts\activate.bat && uvicorn services.presupuestacion.main:app --host 0.0.0.0 --port 8001"
start "frontend (5173)" cmd /k "cd frontend && npm run dev"

echo.
echo Extraccion:      http://localhost:8000
echo Presupuestacion: http://localhost:8001
echo Frontend:        http://localhost:5173
echo.
