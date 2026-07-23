# Base de datos — Extracción IA (legacy)

Este módulo **no toca la base de datos directamente**.

Verificación: ninguno de los 5 archivos (`robot.py`, `robot_comparativas.py`,
`parsers.py`, `config.py`, `gemini_errors.py`) importa `supabase_client` — confirmado
por grep en esta sesión sobre los 5 archivos, sin resultados.

## La única excepción parcial: `guardar_chunk()` desde `robot_comparativas.py`

`robot_comparativas.py` importa `guardar_chunk` de `persistent_chunking.py`
(`robot_comparativas.py:43`) — un archivo fuera de este módulo que sí importa
`supabase_client` (`persistent_chunking.py:19`,
`from services.extraccion.supabase_client import get_client,
resolver_drogueria_id_unica`).

`guardar_chunk()` se invoca en dos puntos, ambos condicionados a que el caller haya
pasado un `session_id` (parámetro opcional, `Optional[UUID] = None`):

- `_extraer_comparativa` (flujo Markdown-chunking), `robot_comparativas.py:556-560`.
- `_extraer_comparativa_por_paginas` (flujo PDF por páginas),
  `robot_comparativas.py:713-717`.

En ambos casos la llamada está envuelta en `try/except Exception` que solo logea un
`warning` si falla (`robot_comparativas.py:559-560`, `:716-717`) — el pipeline de
extracción **nunca se interrumpe** por un fallo de persistencia de chunks. Esto es
consistente con el propio docstring de `persistent_chunking.py` (`:10-11`): "Todas las
funciones son no-op (retornan None/False/{}) si el cliente Supabase no está disponible
— el flujo principal NUNCA se interrumpe por fallo de BD."

`robot.py` y `parsers.py` no llaman a `persistent_chunking.py` ni a ninguna otra pieza
de persistencia — confirmado por grep en esta sesión.

## Consecuencia

El pipeline de este módulo es *stateless* respecto de la base de datos: recibe un
archivo, devuelve un `Path` a un CSV en el filesystem local
(`OUTPUT_BASE`/`COMPARATIVAS_OUTPUT_BASE`, `config.py`). La persistencia del resultado
(lectura del CSV, escritura en tablas de negocio) es responsabilidad exclusiva del
módulo "API & Persistencia" (`main.py`, `background_tasks.py`, `persistent_output.py`,
`supabase_client.py`), documentado por separado — ver [`README.md`](./README.md) y
[`casos_de_uso.md`](./casos_de_uso.md).
