# Decisiones de diseño — Clientes

Numeración D-CLIENTES-NNN, verificada contra el código en esta sesión.

> **Actualización (change `terceros-modelo`, Fase 8/10)**: `clientes/` dejó de ser
> dueño de la identidad y de los contactos. `service.py` ahora orquesta
> `services.terceros.api` (D5, ver [`../terceros/decisiones.md`](../terceros/decisiones.md)
> D-TERCEROS-005) para todo lo que antes vivía en `clientes.nombre` y en
> `cliente_contactos` (tabla eliminada, reemplazada por `terceros_contactos`). Las
> notas de abajo describen el módulo **antes** de esa migración salvo que se indique lo
> contrario — se conservan porque documentan decisiones de código que en varios casos
> siguen vigentes tal cual (p. ej. D-CLIENTES-003, D-CLIENTES-005), y en un caso quedó
> explícitamente resuelta (D-CLIENTES-004, ver nota en esa sección).

### D-CLIENTES-006 — La identidad y los contactos se resuelven vía `services.terceros.api`, no contra `clientes`/`cliente_contactos`

- **Decisión**: `crear_cliente`/`actualizar_cliente`/`obtener_cliente`/`listar_clientes`
  orquestan `api.crear_tercero`+`api.asignar_rol_cliente` /
  `api.actualizar_tercero`+`api.actualizar_rol_cliente` /
  `api.obtener_cliente_con_tercero` / `api.listar_clientes_con_tercero`. Los contactos
  (`crear_contacto`/`listar_contactos`/`actualizar_contacto`) proxyean a las funciones
  homónimas de `services.terceros.api` con `tercero_id=cliente_id`.
- **Motivo**: D1 (una empresa cliente-y-proveedor es un solo tercero, no dos
  identidades) y D5 (frontera de consumo unidireccional) — ver
  [`../terceros/decisiones.md`](../terceros/decisiones.md).
- **Ventajas**: resuelve D-CLIENTES-004 (ver nota en esa sección) para todo lo que pasa
  por la fachada — `NotFoundError` consistente en vez de tres excepciones distintas
  para el mismo escenario de tenant.
- **Desventajas**: `GET /clientes` cambia de forma. Se decidió (explícitamente pedido
  en esa sesión) mantener un dict plano combinado tercero+rol en vez de un objeto
  anidado `{"tercero":..., "rol":...}`, para minimizar el cambio de contrato en
  `ClienteOut` — documentado también en el docstring de ese modelo.
- **eliminar_cliente ya no borra al tercero**: desactiva solo la fila de rol
  (`ClienteRolUpdate(activo=False)`) — el mismo tercero puede seguir activo como
  proveedor (D1/D4).

### D-CLIENTES-001 — Escrituras de sub-recursos usan `service_client`, precedidas por validación con `user_client` en el router

- **Decisión**: los 4 endpoints de escritura de sub-recursos (contactos,
  formato-documentos, observaciones) resuelven `drogueria_id` con `user_client` en el
  router (`_validar_cliente_y_obtener_drogueria_id`, `router.py:107`, `:119`, `:165`,
  `:194`) y luego delegan en un wrapper `*_para_endpoint` que usa `service_client`
  internamente (`service.py:180-231`).
- **Motivo**: documentado explícitamente **solo** para `cliente_formato_documentos` —
  ver D-CLIENTES-002. Para el resto de los sub-recursos (contactos, observaciones) no
  hay comentario puntual en el código; el patrón se repite de forma idéntica sin
  explicación adicional — motivo pendiente de definición, salvo la inferencia de que
  se sigue "el mismo criterio que el resto de los módulos" citado en el docstring de
  D-CLIENTES-002.
- **Ventajas**: evita bloqueos por policies de RLS incompletas (confirmado
  explícitamente para `cliente_formato_documentos` en D-CLIENTES-002).
- **Desventajas**: doble validación de tenant, con dos implementaciones y dos tipos de
  excepción distintos (`ForbiddenError` en el router vs `ValidationError`/`NotFoundError`
  en `service.py`) que pueden desincronizarse si una se modifica sin la otra — ver
  [`pendientes.md`](./pendientes.md) P2.

### D-CLIENTES-002 — `upsert_formato_documento_para_endpoint` corre con `service_role` porque la RLS no cubre `superadmin`

- **Decisión**: el wrapper de escritura de `cliente_formato_documentos` usa
  explícitamente `get_service_client()`.
- **Motivo**: cita textual verificada del docstring, `service.py:211-212`:

  > "Corre con service_role: la RLS de cliente_formato_documentos no incluye
  > 'superadmin' en INSERT/UPDATE — mismo criterio que el resto de los módulos."

- **Ventajas**: un `superadmin` puede cargar instrucciones de formato para cualquier
  cliente sin depender de que la policy de RLS lo contemple explícitamente.
- **Desventajas**: el comentario confirma que la policy RLS de `INSERT`/`UPDATE` sobre
  esta tabla está incompleta respecto a los roles que la usan en la práctica —
  bypasear RLS con `service_client` es el remedio elegido en vez de corregir la
  policy. La afirmación "mismo criterio que el resto de los módulos" no está
  desarrollada con más detalle en este archivo.

### D-CLIENTES-003 — El soft-delete existe solo para `clientes`, no para los 3 sub-recursos

- **Decisión**: `repository.py` no define ninguna función de borrado (ni físico ni
  lógico) para `cliente_contactos`, `cliente_formato_documentos` ni
  `cliente_observaciones`; solo `clientes` tiene `soft_delete_cliente`
  (`repository.py:52-59`).
- **Motivo**: pendiente de definición funcional — no hay comentario en el código que
  explique por qué el borrado se limitó a la entidad raíz.
- **Ventajas**: simplicidad — menos superficie de API y de reglas que mantener por
  sub-recurso.
- **Desventajas**: no hay forma de "retirar" un contacto, un formato de documento o una
  observación sin borrarlos físicamente por fuera de esta API (por ejemplo, con SQL
  directo) o sin usar el campo `activo` de `cliente_contactos`, que en la práctica no
  tiene ningún efecto (ver [`pendientes.md`](./pendientes.md) P3).

### D-CLIENTES-004 — Tres tipos de excepción distintos para el mismo problema de fondo (tenant isolation) — **resuelta para los caminos que pasan por `services.terceros.api`**

> **Resolución (Fase 8, `terceros-modelo`)**: `api.obtener_cliente_con_tercero` y el
> resto de las funciones de `services.terceros.api` que usa `clientes/service.py`
> siempre lanzan `NotFoundError` (D3, guard único
> `asegurar_tercero_de_la_drogueria`). El `ValidationError` que describía el punto
> original de esta decisión (`_validar_cliente_de_la_drogueria`) fue reemplazado; el
> test correspondiente se actualizó a
> `test_upsert_formato_documento_cliente_de_otra_drogueria_falla` esperando
> `NotFoundError`. El resto de esta sección describe el estado **previo** a esa fase.


- **Decisión**: la pertenencia de un cliente a una droguería se valida en tres lugares
  con tres resultados distintos ante el mismo escenario ("el cliente es de otra
  droguería"): `service.py:obtener_cliente` (RN-CLIENTES-001) usa `NotFoundError`,
  `service.py:_validar_cliente_de_la_drogueria` (RN-CLIENTES-002) usa
  `ValidationError`, y `router.py:_validar_cliente_y_obtener_drogueria_id`
  (RN-CLIENTES-007) usa `ForbiddenError`.
- **Motivo**: no documentado en el código.
- **Ventajas**: ninguna identificada — no hay evidencia de que la distinción sea
  deliberada (por ejemplo, para exponer o no la existencia del recurso vía el status
  HTTP) más allá de que `router.py` sí exceptúa explícitamente al rol `superadmin`
  (`router.py:137`), algo que ninguna de las dos validaciones de `service.py` hace.
- **Desventajas**: el mismo caso de negocio produce 404, 422 o 403 según qué capa lo
  detecte primero, con mensajes de error también distintos entre sí — comportamiento
  inconsistente para un cliente de la API que dependa del status HTTP para
  diferenciar casos. Ver [`pendientes.md`](./pendientes.md) P3(1).

### D-CLIENTES-005 — Los `GET` de sub-recursos usan solo `user_client`, sin `service_client`

- **Decisión**: los 3 endpoints `GET` de sub-recursos (`listar_contactos_endpoint`,
  `listar_formato_documentos_endpoint`, `listar_observaciones_endpoint`) usan
  únicamente `user_client` inyectado por `Depends(get_user_client)`
  (`router.py:94`, `:149`, `:178`), sin resolver `service_client` en ningún punto.
- **Motivo**: no documentado explícitamente. Consistente con el patrón de "lecturas
  vía RLS, escrituras vía `service_client`" que también usa Usuarios (ver
  [`../usuarios/decisiones.md`](../usuarios/decisiones.md) D-USUARIOS-001/002).
- **Ventajas**: respeta el aislamiento por RLS de forma nativa, sin duplicar lógica de
  filtrado en Python para las lecturas.
- **Desventajas / riesgo**: si la policy de `SELECT` de estas 3 tablas tampoco cubre
  `superadmin` — de forma análoga a lo que D-CLIENTES-002 confirma para `INSERT`/`UPDATE`
  de `cliente_formato_documentos` — un `superadmin` podría no ver sub-recursos de un
  cliente aunque sí vea al cliente mismo (que sí pasa antes por la validación explícita
  de `router.py:137`, que exceptúa a `superadmin`). No verificable desde este módulo:
  la policy vive en SQL fuera de este repositorio — pendiente de definición funcional.
