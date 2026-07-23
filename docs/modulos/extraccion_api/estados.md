# Estados — `processing_sessions.status`

Este módulo tiene un único campo con forma de máquina de estados de dominio propia
(escrita y leída por código de este módulo): `processing_sessions.status`. Se documenta
por separado porque, a diferencia de otros módulos de este árbol sin `estados.md`, acá sí
hay transiciones reales, valores documentados-pero-inalcanzables, y un estado sin
transición de salida garantizada — verificado con grep exhaustivo de todos los call
sites de `cerrar_sesion` en el repositorio completo en esta sesión.

## Valores declarados

`cerrar_sesion` documenta el tipo del campo como `"completed" | "partial" | "failed"`
(`persistent_chunking.py:208`, firma `status: str`, sin `Literal` — no hay validación de
tipo en runtime). Sumado al valor inicial `"running"` (`persistent_chunking.py:65`), el
vocabulario completo observado en el código de este módulo es:

```
running → completed | failed | partial (declarado, sin escritor) | running (sin salida)
```

## Diagrama de transición (evidencia de código)

```
        crear_sesion()
              │
              ▼
        ┌──────────┐
        │ running  │  (persistent_chunking.py:65, INSERT inicial)
        └────┬─────┘
             │
   ┌─────────┼──────────────────────────┐
   │         │                          │
   ▼         ▼                          ▼
completed  failed                  (sin transición)
   │         │                          │
   │         │                          │
background_tasks.py:96   background_tasks.py:118-122   robot/extraccion_ia falla
(persistir_output_final   (3 reintentos agotados,        ANTES de background_tasks
 tuvo éxito)               error_msg=str(exc))            (main.py: except UnsupportedFormatError/
                                                            ParserError/NoProvidersDetectedError/
                                                            Gemini*Error/Exception, líneas 283-337)
                                                            → NUNCA llama a cerrar_sesion
                                                            → la sesión queda "running" para siempre
```

`"partial"` aparece únicamente como valor documentado en la firma de `cerrar_sesion`
(`persistent_chunking.py:208`) — **ningún call site en todo el repositorio lo pasa**
(confirmado por `grep -r "cerrar_sesion(" .` en esta sesión: los únicos 2 call sites
reales son `background_tasks.py:96` con `status="completed"` y `background_tasks.py:118`
con `status="failed"`, más 2 usos en tests que pasan `"completed"`/`"failed"` también). Es
un estado diseñado pero actualmente inalcanzable desde este módulo.

## Gaps confirmados

1. **`running` sin garantía de salida**: si `procesar_archivo`/`procesar_comparativa`
   lanza cualquiera de las excepciones capturadas en `main.py:283-337` **después** de que
   `crear_sesion` (paso 10 del Flujo 1) ya insertó la fila, ningún código de ese bloque
   `except` llama a `cerrar_sesion` — la sesión queda en `status="running"`
   indefinidamente, sin `completed_at`. Solo el camino feliz (`schedule_persist_output` →
   `_retry_persist` → `cerrar_sesion`) cierra la sesión.
2. **`"partial"` inalcanzable**: declarado en la firma de `cerrar_sesion` como valor
   válido, pero sin ningún productor real. Puede ser vocabulario reservado para un flujo
   de chunking parcial de `extraccion_ia` (que sí importa `guardar_chunk`/
   `cargar_chunks_existentes` de este módulo) — fuera del alcance de esta documentación
   verificar si `robot_comparativas.py` lo usa; el grep de esta sesión no encontró
   ninguna llamada a `cerrar_sesion` en ese archivo tampoco.

Ver P1 en [`pendientes.md`](./pendientes.md) para el detalle de impacto de estos gaps.

## `extraction_results.status` y `chunk_results.status` — no son máquinas de estado en este módulo

- `chunk_results.status` se escribe siempre como `"completed"` literal
  (`persistent_chunking.py:129`) — no hay otro valor observado, es una constante, no un
  estado con transiciones.
- `extraction_results.status` se escribe siempre como `"completed"` literal desde este
  módulo (`persistent_output.py:207`) — el docstring de `buscar_duplicado_con_lock`
  menciona `"partial"`/`"failed"` como valores que la RPC `reserve_extraction` puede leer
  (`persistent_output.py:69`), pero esa RPC es código server-side (PL/pgSQL o similar) no
  visible en este repositorio; no hay evidencia de código Python de este módulo que
  escriba esos valores en `extraction_results.status`.
