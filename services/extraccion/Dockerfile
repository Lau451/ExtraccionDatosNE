FROM python:3.11-windowsservercore-1809

WORKDIR C:/app

COPY requirements.txt .

RUN python -m pip install --upgrade pip
RUN python -m pip install --no-cache-dir -r requirements.txt

COPY services/extraccion ./services/extraccion
COPY docs ./docs

# Directorio de salida de archivos
ENV OUTPUT_BASE_DIR=C:/app/output

# Exponemos el puerto
EXPOSE 8000

CMD ["python", "-m", "uvicorn", "services.extraccion.main:app", "--host", "0.0.0.0", "--port", "8000"]