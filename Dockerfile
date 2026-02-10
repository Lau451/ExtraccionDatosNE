FROM mcr.microsoft.com/windows/python:3.11

WORKDIR C:\app

# Copiamos dependencias primero (mejor cache)
COPY requirements.txt C:\app\requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copiamos la app
COPY app C:\app\app

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
