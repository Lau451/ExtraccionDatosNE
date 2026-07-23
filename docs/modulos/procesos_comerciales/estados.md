# Máquina de estados — Procesos Comerciales

Procesos Comerciales es el primer módulo documentado de `presupuestacion/` con una
máquina de estados nominal real. "Nominal" es la palabra clave de esta página: el tipo
`Estado` enumera 8 valores válidos, pero ningún archivo leído en esta sesión codifica
transiciones entre ellos ni las valida — ver la sección de guardas más abajo.

## Los 8 estados y el orden nominal

`Estado` (`models.py:9-18`) es un `Literal` con 8 valores, declarados en este orden:

```
abierto → presupuestado → presentado → en_evaluacion →  ┬→ adjudicado
                                                          ├→ perdido
                                                          ├→ cerrado
                                                          └→ cancelado
```

Este diagrama refleja el **orden de declaración** en el `Literal` (`models.py:10-17`),
no una máquina de estados finita codificada: `Literal` en Python solo restringe qué
valores son válidos para el campo, no permite ni prohíbe ninguna secuencia de cambios.
No existe en el código ningún diccionario de transiciones permitidas, ningún `if
estado_actual not in (...)`, ni ninguna otra estructura que imponga este orden como
regla de negocio.

Los últimos 4 (`adjudicado`, `perdido`, `cerrado`, `cancelado`) son los **estados
terminales** (`_ESTADOS_TERMINALES`, `repository.py:9`), pero ese agrupamiento se usa
para un solo propósito: excluirlos del listado "activos" por defecto (RN-PROCESOS-002,
[`reglas.md`](./reglas.md)). No bloquean ninguna operación — ni una transición
posterior, ni una nueva lectura/escritura sobre el proceso.

## Quién lee `estado`

| Archivo:línea | Para qué |
|---|---|
| `procesos_comerciales/repository.py:25-26` | Filtro del listado "activos" (RN-PROCESOS-002). |
| `presupuestos/repository.py:18-26` (`buscar_proceso_comercial`) | Selecciona `estado` explícitamente (`id, drogueria_id, clase, estado`) junto con el resto de los campos que necesita `presentar_presupuesto`. |
| `presupuestos/service.py:248` | Usa `proceso["estado"]` como `valor_anterior` al auditar el cambio a `"presentado"` (`registrar_cambio`, `presupuestos/service.py:242-253`) — **uso de auditoría, no una guarda de transición**. |

**Distinción importante verificada en esta sesión**: `presupuestos/service.py:186-187`
tiene una guarda `if presupuesto["estado"] != "aprobado": raise ConflictError(...)`,
pero esa condición es sobre el **estado del presupuesto** (`presupuestos`, no
`procesos_comerciales`). No existe una guarda equivalente sobre `proceso["estado"]` en
ningún punto de `presentar_presupuesto` (`presupuestos/service.py:180-255`) ni de
`actualizar_proceso_comercial` (`presupuestos/repository.py:68-71`).

## Quién escribe `estado`

**Nadie dentro de `procesos_comerciales/`.** Confirmado leyendo `repository.py`
(27 líneas, un INSERT y un SELECT) y `router.py` (40 líneas, solo `GET`/`POST`, sin
`PATCH`/`PUT`) completos.

El único write real de toda la tabla:

1. `presupuestos/service.py:presentar_presupuesto` (`:180-255`) transiciona el
   **presupuesto** de `aprobado` a `presentado` (`:222-226`) como parte de su propio
   flujo de negocio (presentar un presupuesto aprobado a un cliente).
2. Como efecto colateral de ese mismo flujo, `presupuestos/service.py:239-241` llama a
   `repo.actualizar_proceso_comercial(client, proceso_comercial_id=proceso["id"],
   campos={"estado": "presentado"})`.
3. `presupuestos/repository.py:actualizar_proceso_comercial` (`:68-71`) ejecuta
   `UPDATE procesos_comerciales SET estado='presentado' WHERE id=?` — sin `SELECT`
   previo del estado actual, sin condición `WHERE estado=...` de ningún tipo.

`estado="presentado"` se fuerza siempre, para cualquier proceso comercial vinculado a
un presupuesto que se presenta, sin pasar por `procesos_comerciales/service.py` ni por
`procesos_comerciales/repository.py`.

## Ausencia confirmada de guardas de transición

Ninguna validación de transición de estado existe en ningún módulo leído en esta
sesión (`procesos_comerciales/`, `presupuestos/`). En concreto,
`presupuestos/repository.py:actualizar_proceso_comercial` (`:68-71`):

- No verifica que el proceso esté en `presupuestado` o `en_evaluacion` antes de forzar
  `presentado`.
- No tiene ninguna guarda contra pisar un proceso que ya esté en `adjudicado`,
  `perdido`, `cerrado` o `cancelado` (los mismos 4 estados que RN-PROCESOS-002 excluye
  del listado por considerarlos "fuera de curso").
- Es un `UPDATE` genérico de propósito general (`campos: dict[str, Any]`), sin ninguna
  lógica específica de `procesos_comerciales` — se reutiliza tal cual para cualquier
  campo, no solo `estado`.

[IMPLEMENTADO] — hallazgo confirmado por lectura completa de
`presupuestos/service.py:180-255` y `presupuestos/repository.py:68-71` en esta sesión,
no una omisión de lectura. Ver [`arquitectura.md`](./arquitectura.md) para el diagrama
del ciclo de vida partido y [`pendientes.md`](./pendientes.md) P2(1) para el riesgo
concreto.
