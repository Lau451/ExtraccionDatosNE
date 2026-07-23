# Arquitectura — Eventos

## Dependencias hacia Core

| Import | Origen | Uso |
|---|---|---|
| `registrar_cambio`, `registrar_cambios`, `registrar_evento_ciclo_vida` | `core/audit.py` | Auditoría sistemática — ver la sección siguiente. |
| `get_service_client` | `core/database.py` | Resuelto internamente por los 4 wrappers `*_para_endpoint` (`service.py:214-233`, `:296-313`). |
| `get_user_client` | `core/database.py` | Inyectado en los endpoints de solo lectura (`router.py:5`, `:42`, `:64`, `:98`, `:108`, `:117`). |
| `NotFoundError`, `ValidationError` | `core/exceptions.py` | `NotFoundError` en `obtener_evento`/`obtener_bloqueo`/`actualizar_evento_recurrente` (`service.py:88`, `:204`, `:285`); `ValidationError` en `crear_evento` (dependencia inexistente, `:45`) y `crear_evento_recurrente` (`RRULE` inválida, `:245`). |
| `UsuarioPerfil`, `require_roles` | `core/auth.py` | Solo en `router.py:4`, `:41`, `:55`, etc. — `service.py` no importa nada de `core/auth.py`; la resolución de rol y de `drogueria_id`/`usuario_id` ocurre íntegramente en la capa HTTP. |

Ver [`../core/`](../core/) para el detalle de estas piezas — no se repite acá.

## Uso sistemático de auditoría (hallazgo confirmado)

A diferencia de otros módulos ya documentados de `presupuestacion/` donde la auditoría
es parcial o inconsistente, **`eventos/service.py` audita las 4 operaciones de escritura
de `eventos`** sin excepción:

| Operación | Función de auditoría | Línea |
|---|---|---|
| Crear evento | `registrar_evento_ciclo_vida(tipo_cambio="creacion", ...)` | `service.py:73-81` |
| Actualizar evento (campos que sí cambiaron) | `registrar_cambios(...)` | `service.py:127-136` |
| Completar evento (evento propio) | `registrar_cambio(campo="estado", ...)` | `service.py:153-164` |
| Completar evento (cada dependiente desbloqueado) | `registrar_cambio(campo="estado", ...)`, una vez por dependiente | `service.py:170-181` |
| Eliminar evento (soft delete) | `registrar_evento_ciclo_vida(tipo_cambio="eliminacion", ...)` | `service.py:189-197` |
| Generar instancia recurrente | `registrar_evento_ciclo_vida(tipo_cambio="creacion", origen="sistema", ...)` | `service.py:342-350` |

`actualizar_evento` (`service.py:109-138`) es la única operación que audita
condicionalmente: solo llama a `registrar_cambios` si `cambios_reales` no está vacío
(`:127`) — es decir, si al menos un campo enviado difiere del valor ya guardado
(`:118-122`), evitando escribir filas de auditoría vacías en un `PATCH` sin cambios
reales.

`tests/eventos/conftest.py:10-13` documenta en un comentario, verificado textualmente,
que este comportamiento es reciente y llegó a afectar el propio fixture de limpieza:

> "historial_cambios.evento_id (fk_hc_ev) no tiene CASCADE -- hay que borrar el
> historial antes que los eventos que referencia, ahora que crear/actualizar/
> completar/eliminar evento generan filas de auditoría."

`crear_evento_recurrente` y `actualizar_evento_recurrente` **no** auditan — ninguna de
las dos llama a ninguna función de `core/audit.py` (confirmado leyendo `service.py:238-
293` completo). La auditoría sistemática de este módulo cubre `eventos`, no
`eventos_recurrentes`. Ver [`pendientes.md`](./pendientes.md).

## Dependencia externa — `dateutil.rrule`

`service.py:5` importa `rrulestr` de `dateutil.rrule`, usada en dos puntos:

- `crear_evento_recurrente` (`:242-245`): parsea `body.rrule` con
  `dtstart=datetime.now(timezone.utc)` para validarla y calcular la primera
  `proxima_ejecucion` con `regla.after(...)`. Cualquier `ValueError`/`TypeError` se
  traduce a `ValidationError("rrule inválida: ...")` — es la única validación de formato
  de la `RRULE` en todo el módulo, delegada por completo a `dateutil`.
- `generar_instancias_recurrentes` (`:353-355`): reconstruye la regla con
  `dtstart=ejecutada_en` (la `proxima_ejecucion` que se acaba de materializar) para
  calcular la siguiente ocurrencia.

No hay ningún wrapper propio sobre `dateutil` ni normalización adicional del string de
`RRULE` — se persiste tal cual el usuario la mandó (`repository.py:83-84`, columna
`rrule` de `eventos_recurrentes`).

## Relación con `automatizaciones/` (consumidor)

`automatizaciones/service.py:14-15` importa `EventoCreate` (de `eventos/models.py`) y
`crear_evento` (de `eventos/service.py`). El único call site,
`automatizaciones/service.py:99-110` (dentro de `_ejecutar_accion`), arma
`EventoCreate(**campos_evento)` a partir de `parametros_accion` de la regla más la FK de
la entidad que disparó la regla, y llama:

```python
evento = crear_evento(
    client, drogueria_id=drogueria_id, body=body, usuario_id=usuario_id, origen="automatico"
)
```

Es el único call site de todo el repositorio que pasa `origen="automatico"`
explícitamente (`crear_evento` lo tiene como default `"usuario"`, `service.py:39`) — ver
RN-EVENTOS-004 y D-EVENTOS-001 en [`reglas.md`](./reglas.md)/[`decisiones.md`](./decisiones.md)
para el mapeo de vocabularios que ese `origen` dispara. Este módulo (`automatizaciones/`)
todavía no está documentado; se documentará completo en el próximo módulo de esta serie.
No hay ningún import en la dirección inversa: `eventos/` no importa nada de
`automatizaciones/` (confirmado por `Grep` en esta sesión).

## Acoplamiento a nivel de tabla (fuera de este código Python)

No se encontró, en esta sesión, ningún otro módulo de `presupuestacion/` que consulte
directamente las tablas `eventos` o `eventos_recurrentes` con su propio cliente Supabase
(a diferencia de `procesos_comerciales`, que tiene 5+ consumidores de tabla). El único
acoplamiento de negocio real con `eventos` pasa por la función `crear_evento` de este
módulo, vía `automatizaciones/`.

```
                    eventos/ (dueño exclusivo de "eventos" y "eventos_recurrentes")
                          │
                          │  crear_evento(origen="automatico")
                          ▼
                  automatizaciones/service.py:99-110
                  (único consumidor de código Python de este módulo)
```
