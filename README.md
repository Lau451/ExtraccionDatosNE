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

Levanta los 3 procesos necesarios para usar el proyecto completo, cada uno en su
propia ventana de consola:

- **http://localhost:8000** — `services/extraccion` (backend legacy + HTML viejo)
- **http://localhost:8001** — `services/presupuestacion` (backend nuevo, exige JWT)
- **http://localhost:5173** — `frontend/` (Vite + React, el frontend nuevo — requiere
  login contra `services/presupuestacion`, ver `frontend/.env.example`)

O directamente, cada uno por separado:

```bash
uvicorn services.extraccion.main:app --host 0.0.0.0 --port 8000
uvicorn services.presupuestacion.main:app --host 0.0.0.0 --port 8001
cd frontend && npm run dev
```

`scripts\run_presupuestacion.bat` sigue disponible para levantar solo el backend de
presupuestación (puerto 8001), sin los otros dos.

---

## Estructura del proyecto

```
services/
  extraccion/             — backend legacy: bot de extracción con Gemini
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
    Dockerfile

  presupuestacion/         — backend nuevo: presupuestación automática (por dominio)
    core/                   — config, database, auth, audit, exceptions, texto, stock
    pricing/ matching/ presupuestos/ extraccion/ comparativas/ compras/ clientes/
    main.py
    Dockerfile

frontend/                — frontend nuevo (Vite + React + TanStack Router/Query), reemplaza
                            gradualmente el HTML legacy de services/extraccion/templates

supabase/migrations/     — migraciones SQL (tablas, RPC, pg_cron TTL)
docs/schema/              — snapshot de referencia del DDL y las políticas RLS aplicadas
                            (no son migraciones ejecutables, ya están corridas)
tests/                   — suite de tests con pytest (espeja services/presupuestacion/ por dominio)
scripts/run.bat                    — inicia extraccion (8000) + presupuestacion (8001) + frontend (5173)
scripts/run_presupuestacion.bat    — inicia solo services/presupuestacion (puerto 8001)

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
