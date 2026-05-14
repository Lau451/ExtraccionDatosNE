# Extractor de Datos — Droguería Nueva Era

Sistema web para extracción automática de datos estructurados a partir de documentos (PDF, Excel, imágenes) usando Gemini AI, con persistencia en Supabase.

---

## Tipos de documento soportados

| Tipo | Descripción | Formatos |
|------|-------------|---------|
| **Licitaciones** | Extrae ítems, cantidades y descripciones de pliegos | PDF, JPG, PNG, XLS, XLSX |
| **Comparativas** | Extrae tabla de precios por proveedor y renglón | PDF, JPG, PNG, XLS, XLSX, ODS, HTML |

El output en ambos casos es un CSV con delimitador `;`, guardado en `data/Salida/<cliente>/`.

---

## Stack tecnológico

- **FastAPI + Uvicorn** — API web async
- **Gemini 2.5 Flash** — extracción inteligente de datos
- **Supabase (PostgreSQL)** — persistencia de sesiones y resultados
- **pdfplumber** — extracción nativa de PDFs con texto embebido
- **Docling** — fallback para PDFs nativos complejos
- **Gemini Vision** — fallback para PDFs escaneados e imágenes
- **Pandas** — normalización de Excel
- **Python 3.11+**

---

## Arquitectura

```
Upload → SHA256 dedup → Crear sesión → Gemini → CSV → Background task → Supabase
                ↓
        (duplicado detectado → 409)
```

### Pipeline de PDFs

```
PDF nativo → pdfplumber (rápido, bajo RAM)
               ↓ vacío o error
           Docling lightweight (chunks de 15 páginas)
               ↓ fallo por chunk
           Gemini Vision (último recurso, por chunk)

PDF escaneado → Docling lightweight → Vision fallback
```

### Persistencia en Supabase

| Tabla | Contenido |
|-------|-----------|
| `processing_sessions` | Sesión por documento (status: running/completed/failed) |
| `extraction_results` | Resultado general (SHA256, row_count, csv_path) |
| `licitaciones_results` | Filas extraídas en JSONB para licitaciones |
| `comparativas_results` | Filas extraídas en JSONB para comparativas |

El background task tiene **3 intentos con backoff exponencial** (2s, 4s, 8s). Si falla, el CSV en disco sigue disponible.

---

## Instalación

```bash
pip install -r requirements.txt
```

Requiere Python 3.11+.

---

## Variables de entorno

Crear un archivo `.env` en la raíz:

```env
GEMINI_API_KEY=tu_api_key_aqui
SUPABASE_URL=https://tu-proyecto.supabase.co
SUPABASE_KEY=tu_service_role_key
```

> `.env` nunca debe subirse al repositorio.

---

## Ejecución

```bash
.\scripts\run.bat
```

O directamente:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

La app queda disponible en **http://localhost:8000**

---

## Estructura del proyecto

```
app/
  main.py                — rutas FastAPI, deduplicación, orquestación
  robot.py               — extracción de licitaciones (Gemini)
  robot_comparativas.py  — extracción de comparativas (Gemini, chunking)
  parsers.py             — pipeline PDF: pdfplumber → Docling → Vision
  persistent_chunking.py — CRUD de processing_sessions en Supabase
  persistent_output.py   — INSERT en extraction_results y tablas hijas
  background_tasks.py    — retry con backoff exponencial
  supabase_client.py     — cliente Supabase singleton
  config.py              — rutas de salida, clientes Gemini
  gemini_errors.py       — manejo de errores de la API

supabase/migrations/     — migraciones SQL (tablas, RPC, pg_cron TTL)
tests/                   — suite de tests con pytest
scripts/run.bat          — script de inicio para Windows

data/
  Salida/                — CSVs generados (ignorado por Git)
  Procesados/            — archivos ya procesados (ignorado por Git)
```

---

## Convención de nombres de archivo

El nombre del archivo determina el `cliente`:

```
c1002_compraagil.pdf
└─┬──┘
  └── cliente = "c1002"
      csv de salida = data/Salida/c1002/c1002_compraagil.csv
      campo `origen` en el CSV = "c1002"
```

---

## Deduplicación

Antes de procesar, el sistema calcula el **SHA256** del archivo y consulta la RPC `reserve_extraction` en Supabase. Si el documento ya fue procesado exitosamente, devuelve HTTP 409 sin reprocesar.

---

## Tests

```bash
pytest tests/
```

La suite cubre: background tasks, persistent chunking, persistent output, integración de main, brand distribution y parsers.

---

## Concurrencia

La app soporta hasta **15 requests simultáneos a Gemini** (controlado por semáforo). Las llamadas bloqueantes corren en `asyncio.to_thread()` para no bloquear el event loop de FastAPI.
