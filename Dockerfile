FROM mcr.microsoft.com/windows/servercore:ltsc2019

SHELL ["powershell", "-Command", "$ErrorActionPreference = 'Stop';"]

# Instalar Python
RUN Invoke-WebRequest -Uri https://www.python.org/ftp/python/3.11.6/python-3.11.6-amd64.exe -OutFile python.exe ; \
    Start-Process python.exe -ArgumentList '/quiet InstallAllUsers=1 PrependPath=1' -Wait ; \
    Remove-Item python.exe

WORKDIR C:\app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app C:\app\app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
