# Casos de uso — Extracción IA (legacy)

Este módulo no expone HTTP ni tiene "casos de uso" de negocio propios en el sentido de
otros módulos — es una librería de pipeline invocada por código de otro módulo. Esta
página documenta **quién la llama**, con evidencia de import y de sitio de invocación,
como referencia adelantada al módulo "API & Persistencia" (`main.py`,
`background_tasks.py`, etc.), que se documenta formalmente a continuación en este
proyecto.

## Único consumidor confirmado: `services/extraccion/main.py`

Confirmado por grep en todo el repositorio en esta sesión: el único archivo que importa
algo de `robot.py`, `robot_comparativas.py`, `parsers.py`, `config.py` o
`gemini_errors.py` — fuera de los propios 5 archivos entre sí y de los tests — es
`services/extraccion/main.py`:

```python
from services.extraccion.robot import obtener_cliente, procesar_archivo
from services.extraccion.robot_comparativas import procesar_comparativa, NoProvidersDetectedError
from services.extraccion.parsers import parse_document, ParserError, UnsupportedFormatError
from services.extraccion.config import get_output_dir, get_tmp_dir, OUTPUT_BASE, COMPARATIVAS_OUTPUT_BASE
from services.extraccion.gemini_errors import GeminiQuotaExceededError, GeminiRateLimitError, GeminiAPIError
# main.py:26-30
```

`services/presupuestacion/` **no** importa nada de este módulo — confirmado por grep en
esta sesión sobre todo `services/presupuestacion/`, sin resultados. Los dos servicios
están desacoplados a nivel de código Python.

## Sitio de invocación: `POST /procesar` (dentro de `main.py`, fuera de este módulo)

- El endpoint corre `procesar_comparativa` o `procesar_archivo` (según el parámetro
  `tipo` del request) dentro de `asyncio.to_thread(...)` — para no bloquear el loop de
  eventos de FastAPI con trabajo síncrono — y dentro de un `asyncio.Semaphore(15)`
  (`main.py:67`, `:241`) que limita a 15 la cantidad de llamadas concurrentes a este
  pipeline por instancia del proceso (`main.py:240-255`).
- Antes de invocar el pipeline, `main.py` crea una sesión de persistencia
  (`crear_sesion`, de `persistent_chunking.py`, fuera de este módulo) y le pasa el
  `session_id` resultante a `procesar_comparativa`/`procesar_archivo` — el mecanismo de
  guardado best-effort de chunks descripto en
  [`base_de_datos.md`](./base_de_datos.md).
- Después de la llamada, `main.py` lee el CSV devuelto y programa su persistencia en
  Supabase (`schedule_persist_output`, fuera de este módulo) — es decir, la
  persistencia real del resultado ocurre **después** de que este módulo termina, nunca
  dentro de él.
- Las excepciones de dominio de este módulo (`UnsupportedFormatError`, `ParserError`,
  `NoProvidersDetectedError`, `GeminiQuotaExceededError`, `GeminiRateLimitError`,
  `GeminiAPIError`) se capturan explícitamente en `main.py:283-329`, cada una mapeada a
  un status HTTP y un mensaje de usuario distinto (415, 422, 422, 503, 429, 500
  respectivamente) — el detalle completo de ese mapeo pertenece al módulo "API &
  Persistencia".

## Tests que ejercitan la integración (fuera del alcance de este módulo, mencionados como evidencia)

`tests/test_key_fix.py` importa `services.extraccion.main.app` y ejercita
`POST /procesar` end-to-end para verificar que el cliente Gemini elegido por
`get_next_client()` se reutiliza para todo un request (`test_key_fix.py:43-76`) y que
requests distintos rotan entre clientes (`test_key_fix.py:78-123`) — evidencia indirecta
del comportamiento de round-robin de `config.py` (D-EXTRACCIONIA-005), pero el test en
sí pertenece al módulo "API & Persistencia" por depender de `main.py`/FastAPI. No se
incluye entre los tests principales de este módulo porque no fue parte del alcance
explícito de esta documentación, pero se lo cita acá por relevancia directa a
`get_next_client`.

`tests/test_concurrency.py`, `tests/test_concurrency_pytest.py` y
`run_concurrency_test.sh` **no pertenecen a este módulo**: prueban la concurrencia del
endpoint HTTP `/procesar` (`main.py`) mockeando `procesar_archivo` por completo — el
propio docstring de `test_concurrency_pytest.py` lo declara: "Mockea procesar_archivo
para no consumir quota de Gemini" (`test_concurrency_pytest.py:5`). No ejercitan
llamadas reales a Gemini ni ninguna función de los 5 archivos de este módulo — se
excluyen deliberadamente del alcance, consistente con el criterio pedido para esta
documentación.

Para el detalle de la API pública invocable de cada uno de los 5 archivos, ver
[`api.md`](./api.md).
