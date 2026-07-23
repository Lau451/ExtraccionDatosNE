# Arquitectura — Procesos Comerciales

## Dependencias hacia Core

Procesos Comerciales no importa de ningún otro módulo de negocio de `presupuestacion/`
para su lógica de dominio; depende únicamente de Core.

| Import | Origen | Uso |
|---|---|---|
| `UsuarioPerfil`, `require_roles` | `core/auth.py` | Perfil del solicitante y autorización por rol en los 2 endpoints (`router.py:4`, `:18-19`). |
| `get_user_client` | `core/database.py` | Cliente con RLS, inyectado en `GET /procesos-comerciales` (`router.py:5`, `:26`). |
| `get_service_client` | `core/database.py` | Cliente sin RLS, resuelto internamente por `crear_proceso_comercial_para_endpoint` (`service.py:6`, `:76`). |
| `ValidationError` | `core/exceptions.py` | Única excepción de dominio levantada por este módulo, en `_validar_campos_de_seguimiento` (`service.py:7`, `:31-34`, RN-PROCESOS-001). |
| `registrar_evento_ciclo_vida` | `core/audit.py` | Auditoría de la creación (`service.py:5`, `:60-68`, RN-PROCESOS-003). |

Ver [`../core/`](../core/) para la documentación de estas piezas — no se repite acá.

## Acoplamiento a nivel de tabla (fuera de este código Python)

Cinco módulos de `presupuestacion/` más un servicio externo leen o escriben directo
sobre `procesos_comerciales`, sin pasar por `procesos_comerciales/repository.py` ni por
`procesos_comerciales/service.py`. Es el mismo patrón que documentan
[`../catalogo/arquitectura.md`](../catalogo/arquitectura.md) para las tablas de
Catálogo y [`../clientes/arquitectura.md`](../clientes/arquitectura.md) para
`clientes`, con una diferencia importante: acá uno de los consumidores no solo lee,
sino que hace el único `UPDATE` de la tabla — ver la sección siguiente.

### `matching/repository.py` — lectura acotada

`matching/repository.py:14-22` (`buscar_proceso_comercial`) hace
`SELECT id, drogueria_id, cliente_id FROM procesos_comerciales WHERE id=? LIMIT 1`.

### `extraccion/repository.py` (dentro de `presupuestacion/`) — lectura con `clase`

`extraccion/repository.py:13-21` (`buscar_proceso_comercial`) hace
`SELECT id, drogueria_id, cliente_id, clase FROM procesos_comerciales WHERE id=? LIMIT 1`
— necesita `clase` para distinguir el flujo de cotización del de licitación.

### `pricing/repository.py` — lectura con `clase`

`pricing/repository.py:135-143` (`buscar_proceso_comercial`) repite exactamente la
misma consulta que `extraccion/repository.py` (`id, drogueria_id, cliente_id, clase`),
implementada de forma independiente.

### `compras/repository.py` y `compras/router.py` — lectura acotada, una vez por capa

`compras/repository.py:6-14` (`buscar_proceso_comercial`) hace
`SELECT id, drogueria_id, cliente_id FROM procesos_comerciales WHERE id=? LIMIT 1`.
Además, `compras/router.py:50-56` repite una consulta equivalente **inline**, sin pasar
por la función del repository (`SELECT id, drogueria_id ... LIMIT 1`, con `user_client`
en vez del cliente resuelto internamente por el repository).

### `pricing/router.py` — lectura inline

`pricing/router.py:22-28` hace la misma consulta inline (`id, drogueria_id`) que
`compras/router.py`, también con `user_client`, también sin pasar por
`pricing/repository.py:buscar_proceso_comercial`.

### `presupuestos/` — el único escritor de `estado`

`presupuestos/repository.py:18-26` (`buscar_proceso_comercial`) lee
`id, drogueria_id, clase, estado` — es el único consumidor que trae `estado`
explícitamente. `presupuestos/repository.py:68-71` (`actualizar_proceso_comercial`) es
el **único `UPDATE`** de `procesos_comerciales` en todo el repositorio, invocado desde
`presupuestos/service.py:239-241` dentro de `presentar_presupuesto`. Ver la sección
"Ciclo de vida partido" más abajo y [`estados.md`](./estados.md) para el detalle
completo.

### `services/extraccion/procesos_comerciales_client.py` — cross-servicio

114 líneas, `service_role` (bypasea RLS). `validar_proceso_comercial_id`
(`:30-77`) valida UUID + existencia + pertenencia a la droguería que sirve la instancia
de `services/extraccion`, sin distinguir "no existe" de "es de otra droguería" en el
mensaje (anti-leak, `:72-76`). `listar_nombres_procesos_comerciales` (`:80-114`)
resuelve `{id: nombre}` en batch, con manejo best-effort ante error de Supabase
(`:101-114`, retorna `{}` en vez de propagar la excepción).

El docstring del módulo (`:1-16`) documenta que reemplaza a
`routers.licitaciones.validar_licitacion_id()` porque la tabla vieja `licitaciones`
"ya no existe", y que deliberadamente no importa nada de `routers/licitaciones.py` —
ese router se deja intacto mientras el HTML legacy (`templates/licitaciones.html`,
`calendario.html`) lo siga usando, según el propio comentario (referencia a
`openspec/changes/carga-documentos/proposal.md`, no verificada en esta sesión). Ver
[`pendientes.md`](./pendientes.md) P3 sobre el estado incierto de esa tabla legacy.

```
                              procesos_comerciales
                                      │
   ┌────────────┬─────────────┬──────┴──────┬─────────────┬───────────────┐
   │            │             │             │             │               │
procesos_    matching/    extraccion/    pricing/      compras/      presupuestos/
comerciales/ (lee id,     (lee id,       (lee id,      (lee id,      (lee id + clase +
(dueño:      drogueria_   drogueria_id,  drogueria_id, drogueria_id, estado; ÚNICO
INSERT +     id,          cliente_id,    cliente_id,   cliente_id,   escritor de
listado)     cliente_id)  clase)         clase)        + query       estado, vía
                                                        inline en     UPDATE)
                                                        router.py)         │
                                                                           │
                                                              (efecto colateral de
                                                               presentar_presupuesto)
```

Ningún módulo de este diagrama importa código Python de otro para acceder a la tabla —
cada uno construye sus propias queries Supabase. Fuera del diagrama, cross-servicio:
`services/extraccion/procesos_comerciales_client.py` consulta la misma tabla con
`service_role`, sin relación de código con ninguno de los módulos anteriores.

## Ciclo de vida partido con `presupuestos/` (hallazgo principal)

`procesos_comerciales/` define la máquina de estados nominal completa (`Estado`,
`models.py:9-18`) y su vocabulario de estados terminales (`_ESTADOS_TERMINALES`,
`repository.py:9`), pero **no escribe la columna `estado` en ningún punto**: el INSERT
de `service.py:41-58` no incluye `estado` (lo asigna un default de columna en la BD —
RN-PROCESOS-004), y `router.py` no expone ningún PATCH/PUT.

El único write real de `estado` vive en otro módulo:

```
presupuestos/service.py:presentar_presupuesto (líneas 180-255)
        │
        │  presupuesto.estado: aprobado → presentado
        │  (guardado por "if presupuesto['estado'] != 'aprobado': raise ConflictError",
        │   presupuestos/service.py:186-187 — guarda sobre EL PRESUPUESTO, no sobre
        │   el proceso comercial)
        ▼
presupuestos/repository.py:actualizar_proceso_comercial (líneas 68-71)
        │
        │  UPDATE procesos_comerciales SET estado='presentado' WHERE id=proceso['id']
        │  (presupuestos/service.py:239-241)
        ▼
procesos_comerciales.estado := "presentado"
   (sin verificar el estado anterior del proceso comercial, sin importar nada de
    procesos_comerciales/service.py ni de procesos_comerciales/repository.py)
```

Consecuencia directa: `procesos_comerciales/` no puede garantizar ninguna invariante
sobre su propio campo `estado`. Cualquier guarda de transición que se agregue en
`procesos_comerciales/service.py` en el futuro **no protegería** este `UPDATE`, porque
`presupuestos/repository.py:actualizar_proceso_comercial` no pasa por ese archivo. Ver
[`estados.md`](./estados.md) para el detalle de lectura/escritura y
[`decisiones.md`](./decisiones.md) D-PROCESOS-002 / [`pendientes.md`](./pendientes.md)
P1(1) para el análisis de riesgo.
