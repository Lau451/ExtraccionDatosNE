# 1. Usamos la imagen oficial de Python para Windows Server Core 1809 (LTSC 2019)
FROM python:3.11-windowsservercore-1809

# 2. Definimos el directorio de trabajo
WORKDIR C:/app

# 3. Copiamos e instalamos dependencias
# Nota: Usamos "/" en lugar de "\" para evitar problemas de escape de caracteres
COPY requirements.txt . 
RUN pip install --no-cache-dir -r requirements.txt

# 4. Copiamos el resto del código
COPY app ./app

# 5. Exponemos el puerto
EXPOSE 8000

# 6. Comando de ejecución
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]