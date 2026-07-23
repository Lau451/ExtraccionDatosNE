# Módulo Extracción IA (legacy) — `services/extraccion/{robot.py,robot_comparativas.py,parsers.py,config.py,gemini_errors.py}`

## Qué es

Extracción IA es el pipeline de inteligencia artificial del backend legacy
`services/extraccion/` (Droguería Nueva Era): recibe un archivo de documento (PDF,
Excel, HTML o imagen), lo convierte a texto/Markdown y usa Gemini para extraer datos
estructurados, que devuelve como CSV en disco. Es distinto de `services/presupuestacion/`
— confirmado por grep en esta sesión, ningún archivo de `services/presupuestacion/`
importa nada de `services/extraccion/` (son servicios desacoplados a nivel de código
Python; solo comparten base de datos).

Este documento cubre exclusivamente 5 archivos — el resto de `services/extraccion/`
(`main.py`, `routers/`, `supabase_client.py`, `persistent_chunking.py`,
`persistent_output.py`, `background_tasks.py`, `procesos_comerciales_client.py`,
`auth.py`) es otro módulo ("API & Persistencia"), documentado por separado:

| Archivo | Líneas | Rol |
|---|---|---|
| `robot.py` | 359 | Pipeline de extracción de licitaciones/pedidos (1 proveedor → CSV `item;cantidad;descripcion;origen`). |
| `robot_comparativas.py` | 1007 | Pipeline de extracción de comparativas de precios multi-proveedor (chunking + reintento + top-3 por renglón). El archivo más grande del servicio. |
| `parsers.py` | 771 | Router de parseo multi-formato: PDF/Excel/ODS/HTML/imagen → Markdown/texto plano. |
| `config.py` | 182 | Cliente(s) Gemini, round-robin entre API keys, fallback entre modelos, rutas de salida. |
| `gemini_errors.py` | 140 | Excepciones tipadas de Gemini y decorador de reintento con backoff. |

Total: 2459 líneas, verificadas línea por línea en esta sesión.

## Qué hace

- Parsea documentos de entrada a Markdown/texto (`parsers.py:parse_document`), con una
  cadena de fallbacks específica para PDF (pdfplumber nativo → Docling → Gemini Vision
  — ver [`arquitectura.md`](./arquitectura.md)).
- Arma un prompt hardcodeado por caso de uso (licitación/pedido en `robot.py`,
  comparativa en `robot_comparativas.py`, extracción de texto genérica en
  `parsers.py` para Vision) y llama a Gemini.
- Para comparativas grandes, divide el documento en chunks (por ítems de Markdown o por
  páginas de PDF), llama a Gemini en paralelo por chunk y reintenta con split-in-half
  ante truncamiento (`finish_reason=MAX_TOKENS`) — ver [`flujo.md`](./flujo.md).
- Aplica heurísticas de limpieza de datos (fuzzy matching de columnas Excel, formato de
  cantidad AR/US, formato de precio multi-moneda) — ver [`reglas.md`](./reglas.md).
- Escribe el resultado final como CSV en el filesystem local (`OUTPUT_BASE` /
  `COMPARATIVAS_OUTPUT_BASE`, definidos en `config.py`) y mueve el archivo original a
  una carpeta `Procesados/`.

## Qué NO hace

- **No persiste en base de datos.** Ninguno de los 5 archivos de este módulo importa
  `supabase_client` (confirmado por grep en esta sesión). La única excepción parcial:
  `robot_comparativas.py` llama opcionalmente a `guardar_chunk()` de
  `persistent_chunking.py` (fuera de este módulo, sí toca Supabase) cuando el caller le
  pasa un `session_id` — un guardado *best-effort* envuelto en `try/except` que solo
  logea un `warning` si falla, sin interrumpir el pipeline
  (`robot_comparativas.py:556-560`, `:713-717`). Ver
  [`base_de_datos.md`](./base_de_datos.md).
- **No expone HTTP directamente.** Los 5 archivos no definen ningún `APIRouter` ni
  endpoint. El único consumidor confirmado es `services/extraccion/main.py`, que expone
  `POST /procesar` y orquesta la llamada a `procesar_archivo`/`procesar_comparativa`
  dentro de un `asyncio.Semaphore(15)` (`main.py:67`, `:241`) — eso pertenece al módulo
  "API & Persistencia", documentado a continuación. Ver
  [`casos_de_uso.md`](./casos_de_uso.md) para el detalle de esa integración, citado
  como referencia adelantada.
- **No gestiona una máquina de estados.** No se encontró ningún `Literal`/enum de
  estados de dominio en los 5 archivos (confirmado por grep en esta sesión); la única
  ocurrencia de la palabra "state" es `archivo_subido.state` (`robot.py:299`), un campo
  transitorio del SDK de Gemini sobre el estado de un archivo subido (`ACTIVE`,
  `PROCESSING`, etc.), no una máquina de estados de negocio. Por eso este módulo **no
  tiene `estados.md`** — mismo criterio que otros módulos de este árbol de
  documentación cuando no existe una máquina de estados real que documentar.

## Componentes de IA usados (preview)

Este resumen se profundiza en la fase de documentación transversal de IA del proyecto;
acá solo se listan los hechos verificados en esta sesión:

- **Modelos**: `gemini-2.5-flash` (`PRIMARY_MODEL`, `config.py:76`) con fallback a
  `gemini-3-flash-preview` (`FALLBACK_MODEL`, `config.py:77`) ante cualquier excepción
  del modelo primario — ver `generate_with_fallback` en
  [`arquitectura.md`](./arquitectura.md) y [`decisiones.md`](./decisiones.md).
- **Múltiples API keys con round-robin**: `GEMINI_API_KEYS` (coma-separado) crea un
  `genai.Client` por key (`config.py:69-80`); `get_next_client()` rota entre ellos con
  un lock (`config.py:89-94`).
- **3 prompts hardcodeados**: extracción de licitación/pedido (`robot.py:312-326`),
  extracción unificada de comparativas (`_PROMPT_UNIFIED`,
  `robot_comparativas.py:64-98`) y extracción de texto vía Vision (`_VISION_PROMPT`,
  `parsers.py:61-65`) — transcriptos en [`reglas.md`](./reglas.md).
- **Gemini Vision** como parser de último recurso para PDFs (imágenes/escaneados) e
  imágenes sueltas (`parsers.py:_parse_image`).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `robot.py` | `procesar_archivo`: pipeline de licitaciones/pedidos (1 llamada a Gemini, sin chunking). Incluye las heurísticas de limpieza de Excel/CSV. |
| `robot_comparativas.py` | `procesar_comparativa`: pipeline de comparativas multi-proveedor, con 2 estrategias de chunking, reintento por truncamiento y filtro top-3 por renglón. |
| `parsers.py` | `parse_document`: router de 10 extensiones a 5 handlers privados, con la cadena de fallbacks de PDF. |
| `config.py` | Carga de API keys, clientes Gemini, `generate_with_fallback`, rutas de salida (`get_output_dir`, `get_processed_dir`, `get_tmp_dir`). |
| `gemini_errors.py` | 4 excepciones tipadas + `handle_gemini_errors`, el decorador de reintento con backoff. |

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — relación entre los 5 archivos, el import
  diferido entre `robot_comparativas.py` y `parsers.py`, y el diagrama de fallback de
  parseo de PDF.
- [`base_de_datos.md`](./base_de_datos.md) — por qué este módulo no toca la base de
  datos directamente.
- [`reglas.md`](./reglas.md) — reglas técnicas de negocio (RN-EXTRACCIONIA-NNN).
- [`flujo.md`](./flujo.md) — los 3 flujos principales paso a paso.
- [`casos_de_uso.md`](./casos_de_uso.md) — quién llama a estas funciones (referencia
  adelantada a `main.py`, del próximo módulo).
- [`api.md`](./api.md) — API pública/privada relevante de cada uno de los 5 archivos.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-EXTRACCIONIA-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.
