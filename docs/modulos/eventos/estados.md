# Máquina de estados — Eventos

A diferencia de `procesos_comerciales` (que no tiene `estados.md` propio: su `Literal`
es puramente nominal, sin ninguna guarda), Eventos **sí** tiene lógica de transición real
codificada en `service.py` — pero solo para 2 de las 6 transiciones posibles, y ninguna
de las 2 valida el estado anterior antes de aplicarse.

## Los 6 valores de `EstadoEvento`

`EstadoEvento = Literal["pendiente", "bloqueado", "en_progreso", "completado",
"cancelado", "vencido"]` (`models.py:10`), espejo exacto de `ck_eventos_estado`
(`extractor_final.sql:762-764`).

```
                         crear_evento (RN-EVENTOS-001)
                    ┌───────────────────┴───────────────────┐
       sin depende_de_id, o dependencia          con depende_de_id apuntando
       ya "completado"                            a un evento no completado
                    │                                       │
                    ▼                                       ▼
               pendiente                               bloqueado
                    │                                       │
                    │        completar_evento del evento    │
                    │        del que depende (RN-EVENTOS-002,│
                    │        desbloqueo en cascada, UN nivel)│
                    │                                       │
                    │              ┌────────────────────────┘
                    │              ▼
                    │         pendiente
                    │              │
                    └──────┬───────┘
                           ▼
              completar_evento (sin guarda de
              estado_anterior — ver más abajo)
                           │
                           ▼
                      completado
                (fecha_real = now())

  PATCH /eventos/{id} con estado="cancelado" (único valor manual
  aceptado por EventoUpdate.estado, models.py:39) — SIN guarda de
  estado_anterior, alcanzable desde cualquier estado incluyendo
  "completado":
                           │
                           ▼
                       cancelado

  en_progreso, vencido: valores válidos del Literal y del CHECK de BD,
  NINGÚN código de este módulo los escribe jamás (ver más abajo).
```

## Quién escribe `estado`

| Transición | Función | Guarda de `estado_anterior` | Archivo:línea |
|---|---|---|---|
| `(nuevo) → pendiente` | `crear_evento` | Implícita: solo si no hay `depende_de_id`, o la dependencia ya está `completado` | `service.py:41-47` |
| `(nuevo) → bloqueado` | `crear_evento` | Implícita: `depende_de_id` existe y su `estado != "completado"` | `service.py:42-47` |
| `bloqueado → pendiente` | `completar_evento` (efecto colateral, sobre el **dependiente**, no sobre el evento que se completa) | **Ninguna** — se ejecuta para todo evento devuelto por `listar_bloqueados_por_dependencia`, sin revalidar su estado actual entre el `SELECT` y el `UPDATE` | `service.py:166-181` |
| `* → completado` | `completar_evento` (sobre el evento propio) | **Ninguna.** `estado_anterior = evento["estado"]` se lee (`:143`) solo para auditar `valor_anterior`, nunca se compara contra un conjunto de estados válidos antes de forzar `"completado"` | `service.py:141-164` |
| `* → cancelado` | `actualizar_evento` (vía `EventoUpdate.estado`) | **Ninguna** — `actualizar_evento` trata `estado` como cualquier otro campo del diff genérico (`:113-125`), sin lógica especial | `service.py:109-138`, `models.py:39` |
| `→ en_progreso` | — | No existe ninguna función en este módulo que escriba `"en_progreso"` | — |
| `→ vencido` | — | No existe ninguna función en este módulo que escriba `"vencido"` como valor de `estado` | — |

## Ausencia confirmada de guardas de transición

Ninguna de las dos funciones que cambian `estado` verifica el valor anterior antes de
aplicar el nuevo:

- **`completar_evento` (`service.py:141-164`)**: no existe ningún `if evento["estado"]
  not in (...): raise ConflictError(...)`. Se puede completar un evento que está
  `"bloqueado"` (sin que su propia dependencia se haya completado nunca), uno que ya
  está `"cancelado"`, o llamar `completar_evento` dos veces seguidas sobre el mismo
  evento sin error — cada llamada simplemente vuelve a hacer el `UPDATE` y a generar una
  fila de auditoría nueva con `valor_anterior` = lo que sea que estuviera guardado en
  ese momento. [IMPLEMENTADO], confirmado por lectura completa de la función; no hay
  ningún test en `tests/eventos/test_service.py` que ejercite completar un evento
  bloqueado directamente (todos los tests completan el evento **del que depende**, no
  el evento bloqueado en sí).
- **`actualizar_evento` (`service.py:109-138`)**: mismo patrón — `estado="cancelado"`
  vía `PATCH` se acepta sin mirar el `estado` actual del evento.

## `vencido`: solo existe como campo derivado, nunca como valor de `estado`

`"vencido"` es un valor válido del `CHECK` de BD y del `Literal` de Python, pero
**ningún** `INSERT`/`UPDATE` de este módulo lo asigna jamás a la columna `eventos.estado`
— confirmado por `Grep` de `"vencido"` dentro de `eventos/` en esta sesión, con una
única coincidencia real de uso: `CalendarioItem.vencido: bool` (`models.py:97`), un
campo **booleano separado**, calculado por la vista `v_calendario`
(`fecha_limite < NOW()` salvo `estado IN ('completado','cancelado')`,
`rls_final.sql:440-444`) — no una transición del `Literal` `EstadoEvento`. Un evento con
`fecha_limite` en el pasado sigue teniendo `estado="pendiente"` (o el que tuviera) para
siempre a nivel de columna; solo se ve como vencido en el calendario. Ver
[`pendientes.md`](./pendientes.md).

## `en_progreso`: valor muerto

Igual que `"vencido"` pero sin siquiera un campo derivado que lo calcule: `"en_progreso"`
no aparece en ningún archivo de `eventos/` fuera de su declaración en el `Literal`
(`models.py:10`) y el `CHECK` de BD. No hay ningún flujo, endpoint, ni condición que
transicione un evento a ese estado. Ver [`pendientes.md`](./pendientes.md).
