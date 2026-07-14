@echo off
uvicorn services.presupuestacion.main:app --host 0.0.0.0 --port 8001
