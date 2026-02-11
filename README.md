# Proyecto de Extraccion de Datos
### Drogueria Nueva Era

---

Este repositorio contiene un proyecto de **extraccion y procesamiento de datos** a partir de documentos como **PDF, JPG y otros formatos**, utilizando **Python** y **Gemini (Google Generative AI)**.

El objetivo es automatizar la lectura de documentos y generar informacion estructurada para su posterior analisis y comparacion.

---

## Estructura de Carpetas

El sistema crea las carpetas necesarias dentro de `data/` si no existen:

- **data/Procesados**
  Archivos ya procesados (movidos despues de la extraccion)

- **data/Salida**
  Resultados finales (CSV)

> Estas carpetas estan ignoradas por Git y no se suben al repositorio.

---

## Instalacion de Dependencias

Asegurate de tener **Python 3.9 o superior** instalado.

Instala las dependencias principales con el siguiente comando:

```bash
pip install google-generativeai pandas python-dotenv
```

---

## Configuracion de Variables de Entorno (.env)

Para proteger la **API Key de Gemini**, el proyecto utiliza variables de entorno.

Crear un archivo `.env` en la raiz del proyecto con:

```env
GEMINI_API_KEY=tu_api_key_aqui
```

> El archivo `.env` contiene informacion sensible y **no debe subirse al repositorio**.

---

## Configuracion Local de Rutas

Las rutas locales ya no estan hardcodeadas en el codigo.

Opciones soportadas (prioridad):

1. Variable de entorno `OUTPUT_BASE_DIR`
2. Archivo local `config_local.py` (ignorado por Git)

### Paso recomendado

1. Copiar `config_local.example.py` a `config_local.py`
2. Completar `OUTPUT_BASE_DIR` con la ruta local de tu equipo

Ejemplo:

```python
from pathlib import Path
OUTPUT_BASE_DIR = Path(r"C:\Users\TU_USUARIO\ruta\a\ExtraccionDatosNE\data\Salida")
```

Si falta `config_local.py` y no existe `OUTPUT_BASE_DIR`, el sistema mostrara un error claro al iniciar.

---

## Flujo de Uso

1. Seleccionar el documento directamente desde la interfaz (no existe carpeta **Entrada**)
2. Ejecutar el proceso
3. Los archivos procesados se moveran a la ruta configurada en **Procesados**
4. Los resultados se guardaran en la ruta configurada de **Salida**

**Nombres de salida:**
- El CSV generado conserva el nombre completo del archivo original (incluyendo la parte posterior al primer "_")
- Dentro del CSV, el campo `origen` solo incluye el texto anterior al primer "_"

---

## Tecnologias Utilizadas

- Python
- Google Generative AI (Gemini)
- Pandas
- python-dotenv

---