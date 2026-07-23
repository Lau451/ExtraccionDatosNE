# API pública — Extracción IA (legacy)

Firmas verificadas contra el código real en esta sesión. Se incluyen funciones privadas
(prefijo `_`) cuando son piezas centrales del pipeline — mismo criterio que otros
módulos de este árbol de documentación.

## `config.py`

```python
GEMINI_API_KEYS: str            # config.py:61-67; fallback a GEMINI_API_KEY (singular)
api_keys: list[str]             # config.py:69, split por coma
PRIMARY_MODEL = "gemini-2.5-flash"        # config.py:76
FALLBACK_MODEL = "gemini-3-flash-preview" # config.py:77
MODEL_NAME = PRIMARY_MODEL      # config.py:78 — "compatibilidad hacia atrás"; sin uso
                                 # confirmado en el resto del repo (ver pendientes.md)
CLIENTS: list[genai.Client]     # config.py:80, uno por API key
CLIENT = CLIENTS[0]             # config.py:81 — "default para compatibilidad hacia atrás"

def get_next_client() -> genai.Client: ...
# config.py:89-94
# Round-robin thread-safe (threading.Lock) sobre CLIENTS.

def generate_with_fallback(client, contents, config=None): ...
# config.py:96-105
# Intenta PRIMARY_MODEL; ante cualquier Exception, reintenta una vez con
# FALLBACK_MODEL usando el mismo client. Ver RN-EXTRACCIONIA-007.

DATA_DIR: Path                  # config.py:110
OUTPUT_BASE: Path               # config.py:111, de OUTPUT_BASE_DIR (env o config_local.py)
COMPARATIVAS_OUTPUT_BASE: Path  # config.py:112

def get_output_dir(base_dir: Path = OUTPUT_BASE, origen_id: str = "", ensure_exists: bool = True) -> Path: ...
# config.py:157-162

def get_processed_dir(base_dir: Path = OUTPUT_BASE, origen_id: str = "", ensure_exists: bool = True) -> Path: ...
# config.py:165-174
# Subcarpeta "Procesados" de get_output_dir.

def get_tmp_dir(base_dir: Path = OUTPUT_BASE, origen_id: str = "") -> Path: ...
# config.py:177-182
# Subcarpeta "tmp".
```

Privadas de soporte: `_load_local_config` (`:19-34`, carga `config_local.py` como
módulo), `_resolve_output_base_dir` (`:40-58`, resuelve `OUTPUT_BASE_DIR` desde env o
`config_local.py`), `_safe_folder_value` (`:115-131`, sanitiza nombres de carpeta),
`_ensure_dir` (`:134-139`), `_base_work_dir` (`:142-154`).

## `gemini_errors.py`

```python
class GeminiQuotaExceededError(Exception): ...   # :18-23
class GeminiRateLimitError(Exception): ...        # :26-31
class GeminiTruncationError(Exception): ...       # :34-44, determinístico, no reintentable
class GeminiAPIError(Exception): ...              # :47-52, genérico

def handle_gemini_errors(max_retries: int = 3, backoff_factor: float = 2.0) -> Callable: ...
# :69-140
# Decorador de reintento con backoff diferenciado por tipo de error clasificado.
# Ver RN-EXTRACCIONIA-008.
```

Privada de soporte: `_classify_gemini_error(e: Exception) -> tuple[type, str]` (`:55-66`,
clasifica por keywords en `str(e).lower()`).

## `robot.py`

```python
def obtener_cliente(nombre_archivo: str) -> str: ...
# :20-21 — primer segmento antes de "_" en el nombre de archivo.

def nombre_unico(base: str, carpeta: Path, extension: str) -> str: ...
# :24-35 — genera un nombre no colisionante vía os.O_CREAT | os.O_EXCL.

@handle_gemini_errors(max_retries=4, backoff_factor=40.0)
def procesar_archivo(
    ruta_archivo: Path,
    nombre_original: Optional[str] = None,
    *,
    session_id: Optional[UUID] = None,
    instrucciones_extra: Optional[str] = None,
) -> Path: ...
# :267-359 — función principal del pipeline de licitaciones/pedidos.
```

Privadas de soporte: `_normalizar_texto` (`:38-44`), `_mejor_match_columna`
(`:47-71`, umbral 0.72), `_score_cantidad`/`_score_descripcion`/`_col_to_series`
(`:74-104`), `_limpiar_cantidad` (`:107-140`, RN-EXTRACCIONIA-010),
`_rellenar_items_incrementales` (`:143-187`), `_normalizar_excel` (`:191-260`,
RN-EXTRACCIONIA-009).

## `robot_comparativas.py`

```python
class NoProvidersDetectedError(ValueError): ...
# :105-114 — hereda de ValueError, mismo criterio que ParserError de parsers.py.

def procesar_comparativa(
    ruta_archivo: Path,
    nombre_original: Optional[str] = None,
    *,
    session_id: Optional[UUID] = None,
    instrucciones_extra: Optional[str] = None,
) -> Path: ...
# :893-1007 — función principal del pipeline de comparativas. Signature sin cambios
# respecto de versiones previas (ver docstring de módulo, :19-24).
```

Privadas de soporte (orden de aparición en el archivo): `_llamar_gemini_json`
(`:122-169`, decorada con `handle_gemini_errors`), `_limpiar_precio` (`:172-225`,
RN-EXTRACCIONIA-011), `_guardar_docling_output` (`:228-254`), `_comprimir_markdown`
(`:257-288`), `_split_markdown_chunks` (`:296-408`, RN-EXTRACCIONIA-003),
`_split_chunk_in_half` (`:411-454`, RN-EXTRACCIONIA-006), `_process_chunk`
(`:457-488`), `_extraer_comparativa` (`:491-572`), `_split_pdf_by_pages`
(`:580-626`, distinta de la homónima de `parsers.py`), `_procesar_chunk_pdf`
(`:629-647`), `_extraer_comparativa_por_paginas` (`:650-729`, RN-EXTRACCIONIA-004),
`_filtrar_top_3_por_renglon` (`:732-823`, RN-EXTRACCIONIA-012), `_escribir_csv`
(`:831-863`), `_mover_a_procesados` (`:866-885`).

Constantes de módulo: `_JSON_CONFIG` (`:47-50`), `_CHUNK_THRESHOLD=40_000`,
`_CHUNK_SIZE=15`, `_MAX_PARALLEL_CHUNKS=3` (`:52-54`), `_PDF_PAGE_THRESHOLD=20`,
`_PAGE_CHUNK_SIZE=15`, `_PAGE_OVERLAP=1` (`:56-58`), `_PROMPT_UNIFIED` (`:64-98`).

## `parsers.py`

```python
class UnsupportedFormatError(ValueError): ...
# :72-77

class ParserError(RuntimeError): ...
# :80-89 — envuelve la excepción original con raise ... from cause.

def is_scanned_pdf(path: Path, sample_pages: int = 3) -> bool: ...
# :196-218 — pública (sin prefijo "_"), pero solo consumida dentro del propio archivo
# (confirmado por grep en esta sesión, sin importaciones externas). RN-EXTRACCIONIA-013.

def parse_document(filepath: Path) -> str: ...
# :718-771 — único punto de entrada público del router de parseo.
```

Privadas de soporte: `_split_pdf_by_pages` (`:97-163`, `pages_per_chunk=50` default,
usada con `15` desde `_parse_pdf`), `_docling_convert` (`:166-193`),
`_merge_fragmented_rows` (`:221-237`), `_clean_brand` (`:240-259`), `_distribute_brands`
(`:262-348`, RN-EXTRACCIONIA-015), `_rows_to_markdown` (`:351-367`),
`_extract_native_pdf` (`:370-434`), `_parse_excel` (`:442-474`), `_parse_ods`
(`:477-508`), `_parse_pdf` (`:511-597`, RN-EXTRACCIONIA-014), `_parse_html`
(`:599-621`), `_parse_image` (`:624-692`, usado como Vision fallback en 3 puntos
distintos del pipeline).

Tabla de ruteo por extensión: `_EXTENSION_ROUTER` (`:699-711`), 10 extensiones → 5
handlers.
