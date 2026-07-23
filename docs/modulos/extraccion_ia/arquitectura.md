# Arquitectura — Extracción IA (legacy)

## Grafo de dependencias entre los 5 archivos

```
config.py  ◄──────────────┬───────────────┬──────────────────┐
(sin deps internas)       │               │                  │
                       robot.py     robot_comparativas.py  parsers.py
                           ▲               │      ▲            ▲
                           │               │      │            │
                           └───────────────┘      └────────────┘
                        (import top-level,      (import DIFERIDO,
                         robot_comparativas.py:41  ver sección siguiente)
                         obtener_cliente,
                         nombre_unico)

gemini_errors.py  ◄── robot.py, robot_comparativas.py (handle_gemini_errors,
                       GeminiQuotaExceededError, GeminiRateLimitError,
                       GeminiTruncationError)
```

- `config.py` no importa nada de los otros 4 archivos — es la base de la dependencia.
- `parsers.py` importa únicamente `CLIENT, generate_with_fallback` de `config.py`
  (`parsers.py:28`). **No importa nada de `robot.py` ni de `robot_comparativas.py`**
  (confirmado por grep en esta sesión) — dato relevante para la sección siguiente.
- `robot.py` importa de `config.py` (`CLIENT, get_output_dir, get_processed_dir,
  get_next_client, generate_with_fallback`, línea 11) y de `gemini_errors.py`
  (`handle_gemini_errors, GeminiQuotaExceededError, GeminiRateLimitError`, línea 12).
- `robot_comparativas.py` importa de `config.py` (línea 40), de `robot.py`
  (`obtener_cliente, nombre_unico`, línea 41, import top-level normal), de
  `gemini_errors.py` (línea 42) y de `persistent_chunking.py`
  (`guardar_chunk`, línea 43 — fuera de este módulo, ver
  [`base_de_datos.md`](./base_de_datos.md)).

## El import diferido de `parsers.py` dentro de `robot_comparativas.py`

`robot_comparativas.py` **no** importa `parse_document` a nivel de módulo. Lo importa
de forma diferida (dentro de la función, no en el top del archivo) en dos puntos:

- `robot_comparativas.py:642`, dentro de `_procesar_chunk_pdf`:
  `from services.extraccion.parsers import parse_document  # noqa: PLC0415`.
- `robot_comparativas.py:931`, dentro de `procesar_comparativa`, precedido por el
  comentario `# Lazy import to avoid circular dependency at module load time`
  (línea 930).

**[IMPLEMENTADO]** el hecho del import diferido en ambos puntos, verificado línea por
línea. **La justificación del comentario ("avoid circular dependency") no se pudo
verificar como cierta en el estado actual del código**: `parsers.py` no importa nada de
`robot.py` ni de `robot_comparativas.py` (confirmado por grep en esta sesión, sin
resultados). Con el grafo de imports actual, un `import` top-level de
`services.extraccion.parsers` al inicio de `robot_comparativas.py` no formaría ningún
ciclo — `parsers.py → config.py` y `robot_comparativas.py → config.py`,
`robot_comparativas.py → parsers.py`, sin ninguna arista de vuelta. [SUPOSICIÓN]: el
comentario es probablemente vestigio de una versión anterior del código donde sí existía
esa dependencia inversa (por ejemplo, si `parsers.py` alguna vez importó algo de
`robot_comparativas.py` para reutilizar una constante o helper), o una medida defensiva
mantenida por precaución al refactorizar. "Motivo pendiente de definición funcional" —
no hay forma de confirmar la intención original sin historial de git, fuera del alcance
de esta sesión. Ver [`pendientes.md`](./pendientes.md).

## Diagrama del pipeline de fallback de parseo de PDF (`parsers.py:_parse_pdf`)

Cadena de decisión documentada en el docstring de `_parse_pdf`
(`parsers.py:511-522`) y verificada contra el cuerpo de la función (`:523-596`):

```
                         _parse_pdf(filepath)
                                │
                 ¿DOCLING_AVAILABLE? (import guard, parsers.py:35-42)
                                │
                 NO ─────────────────────────────► _parse_image(filepath)
                 │                                  (Gemini Vision, último recurso)
                 SÍ
                 │
                 ▼
          is_scanned_pdf(filepath)  (parsers.py:196-218)
          PyMuPDF: <50% de 3 páginas muestreadas
          tienen >50 chars de texto nativo
                 │
       ┌─────────┴─────────┐
       │ False (nativo)    │ True (escaneado)
       ▼                   │
 ¿PDFPLUMBER_AVAILABLE?     │
       │                   │
   SÍ  │  NO ───────────┐  │
       │                │  │
       ▼                │  │
 _extract_native_pdf()  │  │
 (pdfplumber, tablas +  │  │
  _distribute_brands)   │  │
       │                │  │
  ¿resultado no vacío?  │  │
       │                │  │
  SÍ ──┴──► return       │  │
       │                │  │
  NO / excepción         │  │
       └────────┬────────┘  │
                ▼            ▼
         Docling lightweight (chunks de 15 páginas vía pypdf,
         parsers.py:_split_pdf_by_pages, pages_per_chunk=15)
                │
     por cada chunk: _docling_convert(lightweight=True) + gc.collect()
                │
     ¿falla un chunk individual? ──SÍ──► _parse_image(chunk) (Vision por chunk)
                │
     ¿falla todo el bloque Docling (excepción no capturada por chunk)?
                │
               SÍ
                │
                ▼
     _parse_image(filepath) completo (Vision, último recurso del PDF entero)
```

Puntos verificados adicionales:

- El modo *lightweight* de Docling desactiva la generación de imágenes de página para
  reducir uso de RAM (`PdfPipelineOptions(generate_page_images=False)`,
  `parsers.py:180-190`) y corre `gc.collect()` después de cada chunk
  (`parsers.py:572`, `:590`).
- El chunking de `_split_pdf_by_pages` en `parsers.py` (línea 97, `pages_per_chunk=50`
  por default, invocado con `pages_per_chunk=15` en `_parse_pdf`, línea 552) es un
  mecanismo **distinto** del chunking por páginas de `robot_comparativas.py`
  (`_split_pdf_by_pages`, línea 580, `_PAGE_CHUNK_SIZE=15`, con overlap de 1 página) —
  mismo nombre de función, mismo valor de tamaño de chunk (15), pero volcados a
  propósitos distintos: acá es memoria/rendimiento de Docling (procesamiento
  secuencial), en `robot_comparativas.py` es paralelismo de llamadas a Gemini (con
  overlap para no cortar ítems al medio). No comparten código — cada archivo define su
  propia función privada `_split_pdf_by_pages`.

## Consumidor externo

`services/extraccion/main.py` (fuera de este módulo) importa los 5 archivos —
`robot.py:26`, `robot_comparativas.py:27`, `parsers.py:28`, `config.py:29`,
`gemini_errors.py:30` de `main.py` — y es el único consumidor confirmado en todo el
repositorio (ver [`casos_de_uso.md`](./casos_de_uso.md)).

`services/presupuestacion/` **no** importa nada de `services/extraccion/` — confirmado
por grep en esta sesión sobre todo `services/presupuestacion/` buscando
`from services.extraccion` / `import services.extraccion`, sin resultados. Los dos
servicios están desacoplados a nivel de código Python; el único acoplamiento posible es
a nivel de base de datos compartida, fuera del alcance de este módulo.
