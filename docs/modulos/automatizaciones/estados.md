# Máquina de estados — `acciones_ejecutadas.estado`

`reglas_automatizacion` no tiene máquina de estados propia relevante: `activa` es un
booleano simple (nace `TRUE`, se apaga vía `PATCH activa=false`, sin transiciones
intermedias). El estado que sí amerita este documento es el de la **cola de
reintentos**, `acciones_ejecutadas.estado`.

## Los 5 valores de `estado` — solo 3 usados por código

`CHECK ck_ae_estado` (`docs/schema/extractor_final.sql:932`) declara 5 valores:
`pendiente, ejecutando, completada, fallida, cancelada`. El código Python de este
módulo (único escritor de la tabla) **solo escribe 3**: `pendiente`, `completada`,
`fallida`. Confirmado por `Grep` de `"ejecutando"` y `"cancelada"` sobre
`services/presupuestacion/` completo y sobre `tests/` completo en esta sesión — cero
resultados en ambos casos. `"ejecutando"` y `"cancelada"` son valores muertos a nivel de
aplicación: existen en el `CHECK` de BD y en ningún otro lugar.

```
                    disparar_reglas (RN-AUTOMATIZACIONES-004)
             ┌──────────────────┴──────────────────┐
     modo_ejecucion="inmediato"            modo_ejecucion="cola"
     _ejecutar_accion() síncrono           sin ejecutar todavía
             │                                       │
       ┌─────┴─────┐                                 ▼
       ▼           ▼                             pendiente
  completada    fallida                              │
  (intentos=1)  (intentos=1,                          │  procesar_acciones_pendientes
                 sin reintento                        │  (RN-AUTOMATIZACIONES-005)
                 -- ver nota)                          │
                                                        ▼
                                                  _ejecutar_accion()
                                                        │
                                          ┌─────────────┼──────────────┐
                                          ▼             ▼              ▼
                                     completada    pendiente       fallida
                                    (exito=True)  (falló, intentos  (falló, intentos
                                                   < max_reintentos,  >= max_reintentos,
                                                   proximo_intento_at  definitivo)
                                                   = fin + 2**intentos
                                                   minutos -- vuelve
                                                   al mismo estado,
                                                   se reevalúa en la
                                                   siguiente corrida)

  ejecutando, cancelada: valores válidos del CHECK de BD, NINGÚN código
  de este módulo (ni de ningún otro módulo, confirmado por Grep en todo
  el repositorio) los escribe jamás.
```

**Nota sobre modo `inmediato` y fallo**: a diferencia del modo `cola`, una acción
`inmediato` que falla (`exito=False` en `_ejecutar_accion`) queda directamente en
`estado="fallida"` con `intentos=1` (`service.py:185-193`) — **no** entra al mecanismo
de reintento con backoff, porque ese mecanismo vive exclusivamente en
`procesar_acciones_pendientes`, que solo procesa filas `estado="pendiente"`. Una regla
`modo_ejecucion="inmediato"` con `tipo_accion` no implementado (por ejemplo `webhook`)
falla una única vez y queda fallida para siempre, sin importar su `max_reintentos`. No
hay ningún test que ejercite específicamente este caso (fallo en modo `inmediato`) —
los tests de reintento (`test_procesar_acciones_pendientes_reintenta_con_backoff_si_falla`,
`test_service.py:159-183`) usan `modo_ejecucion="cola"` deliberadamente.
[IMPLEMENTADO], confirmado por lectura completa de `disparar_reglas:171-194`.

## Quién escribe `estado`

| Transición | Función | Guarda de `estado_anterior` | Archivo:línea |
|---|---|---|---|
| `(nuevo) → completada` | `disparar_reglas` (modo `inmediato`, éxito) | N/A, primera escritura | `service.py:178-194` |
| `(nuevo) → fallida` | `disparar_reglas` (modo `inmediato`, fallo) | N/A, primera escritura, sin reintento (ver nota arriba) | `service.py:178-194` |
| `(nuevo) → pendiente` | `disparar_reglas` (modo `cola`) | N/A, primera escritura | `service.py:196-205` |
| `pendiente → fallida` | `procesar_acciones_pendientes` (regla ya no existe) | Ninguna — se aplica a cualquier fila con `regla_id` no resoluble | `service.py:218-224` |
| `pendiente → completada` | `procesar_acciones_pendientes` (`_ejecutar_accion` exitoso) | Ninguna explícita — la fila viene de `listar_acciones_pendientes`, que ya filtra `estado='pendiente'` en el `SELECT` | `service.py:238-247` |
| `pendiente → pendiente` (reprogramada) | `procesar_acciones_pendientes` (falló, no agotó reintentos) | Ninguna | `service.py:248-256` |
| `pendiente → fallida` (definitivo) | `procesar_acciones_pendientes` (falló, agotó `max_reintentos`) | Ninguna | `service.py:257-264` |
| `→ ejecutando` | — | No existe ninguna función en este módulo (ni en el repositorio) que escriba este valor | — |
| `→ cancelada` | — | No existe ninguna función en este módulo (ni en el repositorio) que escriba este valor; tampoco hay endpoint para cancelar una acción encolada manualmente | — |

Ninguna transición valida el `estado` anterior antes de aplicarse —
`procesar_acciones_pendientes` confía en que `listar_acciones_pendientes` ya filtró
`estado='pendiente'` en el `SELECT` (`repository.py:64-73`), sin revalidar entre el
`SELECT` y el `UPDATE` (ventana de carrera teórica si dos corridas del worker se
solaparan; no aplicable hoy porque no hay ningún worker real corriendo,
RN-AUTOMATIZACIONES-006). [IMPLEMENTADO], confirmado por lectura completa de
`procesar_acciones_pendientes`.

## No hay forma de cancelar una acción encolada manualmente

No existe ningún endpoint HTTP ni función de `service.py` que transicione una acción de
`pendiente` a `cancelada` (ni a ningún otro estado, fuera de las 2 funciones del motor).
Una acción `pendiente` cuya regla se desactiva (`activa=false` vía `PATCH`) **sigue
procesándose igual** por `procesar_acciones_pendientes` — desactivar una regla no
cancela ni filtra las acciones ya encoladas que le pertenecen, porque
`listar_acciones_pendientes` no hace ningún `JOIN` contra `reglas_automatizacion.activa`
(`repository.py:64-73`, solo filtra por `estado`/`proximo_intento_at`). [IMPLEMENTADO],
confirmado por lectura completa de ambas funciones. Ver
[`pendientes.md`](./pendientes.md).
