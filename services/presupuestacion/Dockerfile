FROM python:3.11-windowsservercore-1809

WORKDIR C:/app

COPY requirements.txt .

RUN python -m pip install --upgrade pip
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY services/presupuestacion ./services/presupuestacion
COPY services/shared ./services/shared

# Exponemos el puerto
EXPOSE 8001

CMD ["python", "-m", "uvicorn", "services.presupuestacion.main:app", "--host", "0.0.0.0", "--port", "8001"]
