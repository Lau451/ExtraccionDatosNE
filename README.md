# 📄 Proyecto de Extracción de Datos  
### Droguería Nueva Era

---

Este repositorio contiene un proyecto de **extracción y procesamiento de datos** a partir de documentos como **PDF, JPG y otros formatos**, utilizando **Python** y **Gemini (Google Generative AI)**.

El objetivo es automatizar la lectura de documentos y generar información estructurada para su posterior análisis y comparación.

---

## 📁 Estructura de Carpetas

Antes de ejecutar el proyecto, es necesario crear la siguiente estructura de carpetas en la raíz del repositorio:

Entrada/
Entrada_Comparativas/
Procesados/
Salida/
Salida_Comparativas/


**Descripción:**

- **Entrada**  
  Documentos a procesar

- **Entrada_Comparativas**  
  Documentos utilizados para comparativas

- **Procesados**  
  Archivos ya procesados

- **Salida**  
  Resultados finales

- **Salida_Comparativas**  
  Resultados de comparaciones

> ⚠️ Estas carpetas están ignoradas por Git y no se suben al repositorio.

---

## 🛠️ Instalación de Dependencias

Asegurate de tener **Python 3.9 o superior** instalado.

Instalá las dependencias principales con el siguiente comando:

pip install google-generativeai pandas


---

## 🔐 Configuración de Variables de Entorno (.env)

Para proteger la **API Key de Gemini**, el proyecto utiliza variables de entorno.

---

### 1️⃣ Instalar dependencia para manejar `.env`

pip install python-dotenv


---

### 2️⃣ Crear archivo `.env`

En la raíz del proyecto, crear un archivo llamado `.env` con el siguiente contenido:

GEMINI_API_KEY=tu_api_key_aqui


> ⚠️ El archivo `.env` contiene información sensible y **no debe subirse al repositorio**.

---

## 🚀 Flujo de Uso

1. Colocar los documentos en **Entrada** o **Entrada_Comparativas**
2. Ejecutar el script principal del proyecto
3. Los archivos procesados se moverán a **Procesados**
4. Los resultados se guardarán en **Salida** o **Salida_Comparativas**

---

## 🧩 Tecnologías Utilizadas

- Python  
- Google Generative AI (Gemini)  
- Pandas  
- python-dotenv  

---
