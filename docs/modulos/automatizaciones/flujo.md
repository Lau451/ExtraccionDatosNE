# Flujo — Automatizaciones

Ambos flujos están completos y testeados, pero ninguno tiene un disparador real en
producción (ver RN-AUTOMATIZACIONES-006 y [`pendientes.md`](./pendientes.md)). Se
documentan tal como funcionarían si algo los llamara.

## Flujo 1 — `disparar_reglas` (`service.py:134-208`)

Firma: `disparar_reglas(client, *, drogueria_id, entidad_objetivo, evento_disparador,
entidad_id, datos, usuario_id)`.

```
1. repo.reglas_activas_para(drogueria_id, entidad_objetivo, evento_disparador)
   → reglas con activa=True que matchean exactamente estos 3 campos,
     ordenadas por prioridad desc (repository.py:40-53).

2. Por cada regla (sin "break" — se evalúan todas, RN-AUTOMATIZACIONES-008):

   a. _evaluar_condicion(regla["condicion"], datos)
      → False: continue (se descarta esta regla, no genera fila).

   b. columna_fk = COLUMNA_FK_POR_ENTIDAD.get(entidad_objetivo)
      → None (extraction_result/entrega): logger.warning + continue,
        sin crear fila en acciones_ejecutadas (RN-AUTOMATIZACIONES-002).

   c. regla["modo_ejecucion"] == "inmediato":
        - inicio = now()
        - exito, resultado = _ejecutar_accion(...)   # síncrono
        - fin = now()
        - INSERT acciones_ejecutadas: estado="completada" si exito
          else "fallida", resultado (solo si exito), error_msg (solo si
          no exito), intentos=1, iniciado_at, finalizado_at, duracion_ms,
          ejecutado_at   (service.py:171-194)

      regla["modo_ejecucion"] == "cola" (cualquier otro valor):
        - INSERT acciones_ejecutadas: estado="pendiente", sin ejecutar
          nada todavía; intentos queda en el DEFAULT de BD (0), no se
          setea explícitamente en este INSERT (service.py:195-205)

   d. resultados.append(accion)

3. return resultados   # lista de filas de acciones_ejecutadas creadas
```

`_ejecutar_accion` (`service.py:87-131`) es la misma función para ambos modos — no hay
una versión "inmediata" y otra "encolada" del cuerpo de ejecución, solo cambia si se
llama dentro de `disparar_reglas` (inmediato) o dentro de
`procesar_acciones_pendientes` (cola, en el flujo 2).

```
_ejecutar_accion(client, regla, entidad_objetivo, entidad_id, drogueria_id, usuario_id):
    parametros = regla["parametros_accion"] or {}
    columna_fk = COLUMNA_FK_POR_ENTIDAD.get(entidad_objetivo)

    if tipo_accion == "crear_evento":
        arma EventoCreate(**parametros, **{columna_fk: entidad_id} si columna_fk)
        → excepción de validación → (False, "parametros_accion inválidos...")
        → OK → crear_evento(..., origen="automatico") → (True, {"evento_id": ...})

    elif tipo_accion == "enviar_notificacion":
        relaciones = {columna_fk: entidad_id} si columna_fk else {}
        crear_notificacion(destinatario_id=parametros["destinatario_id"],
                            tipo=parametros["tipo"], titulo=parametros["titulo"],
                            mensaje=parametros.get("mensaje"), ...,
                            origen="automatizacion", relaciones=relaciones)
        → KeyError/TypeError → (False, "parametros_accion inválidos...")
        → OK → (True, {"notificacion_id": ...})

    else:
        return (False, f"tipo_accion '{tipo_accion}' no implementado aún")
```

## Flujo 2 — `procesar_acciones_pendientes` (`service.py:211-267`)

Firma: `procesar_acciones_pendientes(client, *, usuario_scheduler_id)`. Sin parámetro de
`drogueria_id` — procesa pendientes de **todas** las droguerías en una corrida (ver
[`base_de_datos.md`](./base_de_datos.md)).

```
1. repo.listar_acciones_pendientes(client)
   → todas las filas estado="pendiente" con proximo_intento_at IS NULL
     o proximo_intento_at <= NOW(), de cualquier drogueria_id
     (repository.py:64-73).

2. Por cada accion pendiente:

   a. regla = repo.obtener_regla(regla_id=accion["regla_id"]) si regla_id
      else None.

   b. regla is None (la regla fue borrada -- aunque no hay DELETE de
      reglas en el código actual, la FK no tiene ON DELETE CASCADE
      confirmado, así que esta rama cubre un estado inconsistente
      teórico o generado fuera de la app):
        UPDATE estado="fallida", error_msg="La regla asociada ya no
        existe"; procesadas += 1; continue.   (service.py:218-224)

   c. entidad_id = accion.get(columna_fk) si columna_fk else None
      (columna_fk resuelto de regla["entidad_objetivo"], igual mapeo
      que en el flujo 1).

   d. inicio = now(); exito, resultado = _ejecutar_accion(...); fin = now()
      intentos = accion["intentos"] + 1

   e. exito:
        UPDATE estado="completada", resultado, intentos, iniciado_at,
        finalizado_at, duracion_ms, ejecutado_at.   (:238-247)

      not exito and intentos < regla["max_reintentos"]:
        proximo = fin + timedelta(minutes=2 ** intentos)
        UPDATE estado="pendiente", error_msg, intentos, proximo_intento_at.
        (:248-256)  -- backoff: 2, 4, 8, 16... minutos según el número
        de intento (RN-AUTOMATIZACIONES-005).

      not exito and intentos >= regla["max_reintentos"]:
        UPDATE estado="fallida", error_msg, intentos, finalizado_at.
        (:257-264)  -- fin definitivo, no se reprograma más.

   f. procesadas += 1   # se incrementa en TODAS las ramas, incluida "b"

3. return procesadas   # cuenta de filas tocadas en esta corrida, no de
                        # acciones completadas con éxito
```

**Nota sobre `procesadas`**: el valor de retorno cuenta cuántas filas de
`acciones_ejecutadas` se tocaron en la corrida (`completada`, `fallida`, o
`pendiente` reprogramada), no cuántas se completaron con éxito — un caller que
interprete `procesadas` como "éxitos" leería mal el resultado. Confirmado por lectura
completa de la función: `procesadas += 1` está al final del `for`, fuera de cualquier
condicional de éxito (`:265`).
