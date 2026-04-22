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

- **Python 3.9+**
- **FastAPI** — API web de alta performance
- **Uvicorn** — ASGI server
- **Google Generative AI (Gemini)** — Extracción inteligente de datos
- **Pandas** — Procesamiento de datos
- **python-dotenv** — Manejo de variables de entorno

---

## Ejecución de la Aplicación

### Opción 1: Script (Windows)

```bash
.\scripts\run.bat
```

### Opción 2: Comando directo

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

La aplicación estará disponible en: **http://localhost:8000**

---

## Testing — Validación de Concurrencia

El proyecto incluye una **suite de load testing** para validar que la aplicación soporta múltiples usuarios simultáneos sin congelación.

### Ejecutar los tests

**Terminal 1: Inicia la app**
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Terminal 2: Corre los tests**
```bash
cd test
python test_concurrency.py
```

### Qué valida

- ✅ 3 usuarios simultáneos (baseline)
- ✅ 7 usuarios simultáneos (objetivo del fix de concurrencia)
- ✅ 10 usuarios simultáneos (stress test)

### Resultados esperados

Todos los tests deberían pasar con eficiencia de paralelismo **> 300%**:

| Users | Time | Efficiency | Status |
|-------|------|-----------|--------|
| 3 | ~45s | 295% | ✓ PASS |
| 7 | ~28s | 501% | ✓ PASS |
| 10 | ~30s | 759% | ✓ PASS |

**Nota:** Eficiencia > 300% indica paralelismo real (no serialización).

Ver más detalles en `test/README.md`

---

## Arquitectura de Concurrencia

### El Problema

Las llamadas a Gemini API son **bloqueantes**. Sin optimización, cada usuario bloquea el event loop de FastAPI, causando que otros usuarios esperen.

### La Solución

Implementamos `asyncio.run_in_executor()` para mover operaciones bloqueantes a un thread pool, liberando el event loop.

**Beneficio:** La aplicación ahora soporta **7+ usuarios simultáneos sin congelación** (validado en commit e0d6dbc).

```python
# app/main.py (líneas 126-133)
loop = asyncio.get_event_loop()
csv_generado = await loop.run_in_executor(None, procesar_archivo, destino, nombre_original)
```

---