# Módulo Droguerías — `services/presupuestacion/droguerias/`

## Qué es

Droguerías es el CRUD de "empresas" del sistema: cada fila de la tabla `droguerias` es
un tenant. La tabla ya existía en el schema (referenciada por `drogueria_id` en 36
tablas del schema, confirmado con un conteo por bloque `CREATE TABLE` sobre
`docs/schema/extractor_final.sql` en esta sesión — cifra cercana a la estimación previa
de "~35 tablas") pero no tenía backend propio hasta esta sesión: no existía
`services/presupuestacion/droguerias/` antes de este módulo.

El módulo tiene 4 archivos, 121 líneas en total (`models.py` 59, `repository.py` 21,
`service.py` 51, `router.py` 61, `__init__.py` vacío — verificado leyendo cada archivo
en esta sesión), 5 endpoints, sin máquina de estados propia.

## Qué NO hace

- **No ejecuta auditoría.** 0 referencias a `core.audit`, `registrar_cambio`,
  `registrar_cambios` o `registrar_evento_ciclo_vida` en los 4 archivos fuente
  (confirmado por grep en esta sesión) — mismo patrón de deuda ya documentado para
  [`../clientes/`](../clientes/) y [`../usuarios/`](../usuarios/). Ver
  [`pendientes.md`](./pendientes.md) P1.
- **No hace soft-delete.** A diferencia de `clientes` (ver
  [`../clientes/reglas.md`](../clientes/reglas.md) RN-CLIENTES-005),
  `eliminar_drogueria` hace un `DELETE` real sobre la fila
  (`repository.py:19-20`) — no existen columnas `deleted_at`/`deleted_by` en este
  módulo. Ver [`decisiones.md`](./decisiones.md) D-DROGUERIAS-002.
- **`droguerias.activa` no tiene ningún efecto funcional confirmado en este
  repositorio.** El campo es escribible vía `PATCH /droguerias/{id}`
  (`DrogueriaUpdate.activa`, `models.py:36`) y se expone en `DrogueriaOut.activa`
  (`models.py:57`), pero `GET /droguerias` no lo filtra (ni como columna fija ni como
  query param opcional, `router.py:17-24`), y `core/auth.py:39` — que resuelve el
  perfil del usuario en cada request — solo lee `usuarios.activo`, nunca
  `droguerias.activa`. No se encontró ningún otro punto del backend que lea este campo
  para bloquear algo. Ver [`pendientes.md`](./pendientes.md) P2.
- **No tiene `estados.md`.** No hay una máquina de estados: `activa` es un booleano de
  negocio sin transiciones ni efecto observable verificado (a diferencia de
  `clientes.activo`, que sí filtra un listado y sí es forzado por un soft-delete) —
  mismo criterio de omisión ya aplicado en Core, Usuarios y Clientes.
- **No expone el flujo de "crear el primer admin de la empresa".** No existe un
  endpoint propio de este módulo para eso — lo resuelve el frontend reusando
  `POST /usuarios` con `drogueria_id` explícito. Ver
  [`../usuarios/`](../usuarios/) para ese detalle, no se repite acá.

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `droguerias/__init__.py` | Vacío. |
| `droguerias/models.py` | Validación de formato de CUIT (`_validar_formato_cuit`, `models.py:8-11`) y 3 modelos Pydantic (`DrogueriaCreate`, `DrogueriaUpdate`, `DrogueriaOut`). |
| `droguerias/repository.py` | Acceso a datos puro sobre la tabla `droguerias`: `obtener_drogueria`, `crear_drogueria`, `actualizar_drogueria`, `eliminar_drogueria` (hard-delete). |
| `droguerias/service.py` | Valida existencia antes de `UPDATE`/`DELETE` y traduce la violación de FK del `DELETE` a `ConflictError`; 3 wrappers `*_para_endpoint` que fijan `get_service_client()`. |
| `droguerias/router.py` | 5 endpoints HTTP. Los 2 `GET` consultan `droguerias` directo con `user_client`, sin pasar por `service.py`. |

## Quién lo consume

Montado en `services/presupuestacion/main.py:55`
(`app.include_router(droguerias_router, tags=["droguerias"])`), sin prefijo adicional.
Ningún otro módulo de `presupuestacion/` importa `droguerias/` como módulo Python
(confirmado por grep en esta sesión).

Acoplamiento a nivel de tabla, fuera de este código: `services/presupuestacion/core/auth.py:39`
consulta `usuarios` (no `droguerias`) para resolver `drogueria_id` del solicitante en
cada request — no es un consumidor de este módulo, pero es la pieza que hace que
`drogueria_id` esté disponible para las 36 tablas que lo referencian. Ver
[`arquitectura.md`](./arquitectura.md).

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias hacia Core, por qué los `GET`
  no pasan por `service.py`, rol de esta tabla como raíz del multi-tenant.
- [`base_de_datos.md`](./base_de_datos.md) — la tabla `droguerias`, columnas, CRUD.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-DROGUERIAS-NNN).
- [`flujo.md`](./flujo.md) — los 3 flujos principales paso a paso.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 5 endpoints y quién puede invocarlos.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-DROGUERIAS-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.

Para `UsuarioPerfil`, `require_roles`, `service_client`/`user_client` y el mecanismo de
auditoría que este módulo NO usa, ver [`../core/`](../core/) — no se repite esa
documentación acá.
