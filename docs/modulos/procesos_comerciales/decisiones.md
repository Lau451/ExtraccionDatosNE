# Decisiones de diseño — Procesos Comerciales

Numeración D-PROCESOS-NNN, verificada contra el código en esta sesión.

### D-PROCESOS-001 — La creación usa `service_client`, el listado usa `user_client`

- **Decisión**: `POST /procesos-comerciales` resuelve `service_client` internamente
  (vía `crear_proceso_comercial_para_endpoint`, `service.py:72-77`), mientras que
  `GET /procesos-comerciales` recibe `user_client` inyectado por
  `Depends(get_user_client)` (`router.py:26`).
- **Motivo**: no documentado con comentario en este módulo — "Motivo pendiente de
  definición funcional". A diferencia de Clientes (D-CLIENTES-002, que sí explica por
  qué un wrapper puntual usa `service_role`), acá no hay ningún docstring ni comentario
  que justifique la elección para el INSERT.
- **Ventajas**: la lectura respeta el aislamiento por RLS de forma nativa, sin duplicar
  lógica de filtrado de tenant en Python.
- **Desventajas**: el aislamiento de tenant en el INSERT depende enteramente de que
  `drogueria_id` se arme correctamente en el service a partir del `UsuarioPerfil`
  resuelto por `require_roles` (`router.py:36-39`) — no hay una segunda capa de defensa
  a nivel de base de datos para esta escritura, porque `service_client` bypasea RLS por
  definición.

### D-PROCESOS-002 — El módulo no expone ninguna transición de estado (`PATCH`), pese a que `presupuestos/` sí la ejecuta

- **Decisión**: `router.py` solo define `GET` y `POST`; no existe ningún endpoint para
  cambiar `estado` desde este módulo, aunque `presupuestos/` sí lo hace como efecto
  colateral de `presentar_presupuesto` — ver [`estados.md`](./estados.md).
- **Motivo**: no documentado explícitamente en el código — "Motivo pendiente de
  definición funcional". Hipótesis razonable **no confirmada** [SUPOSICIÓN]: el cambio
  a `"presentado"` es un efecto derivado de "presentar un presupuesto" (un caso de uso
  de otro dominio, `presupuestos/`), y modelarlo como un `PATCH` genérico de
  `procesos_comerciales/` habría requerido reimplementar esa lógica de negocio dentro
  de este módulo o exponerla de forma redundante.
- **Ventajas**: evita un `PATCH` de estado genérico que cualquier rol de escritura de
  este módulo pudiera usar para forzar transiciones arbitrarias sin el contexto de
  `presentar_presupuesto` (compromiso de stock, actualización del presupuesto,
  auditoría conjunta).
- **Desventajas** [IMPLEMENTADO, confirmado]: la responsabilidad del ciclo de vida de
  `estado` queda partida entre dos módulos sin ningún contrato explícito ni import
  compartido — `procesos_comerciales/` define la máquina de estados nominal
  (`models.py:9-18`) y el vocabulario de estados terminales
  (`_ESTADOS_TERMINALES`, `repository.py:9`), pero no puede garantizar ninguna
  invariante sobre su propio campo `estado`, porque el único write real vive en
  `presupuestos/repository.py:68-71`, fuera de su alcance. Ver
  [`pendientes.md`](./pendientes.md) P1(1).

### D-PROCESOS-003 — El constraint de negocio está duplicado en código Python y en la base de datos

- **Decisión**: `_validar_campos_de_seguimiento` (`service.py:12-34`) reimplementa en
  Python la misma restricción que, según su propio comentario, ya existe como `CHECK`
  de base de datos (`ck_proc_cotizacion_sin_seguimiento`, sin migración versionada en
  este repositorio — ver RN-PROCESOS-001 en [`reglas.md`](./reglas.md)).
- **Motivo**: confirmado por el test
  `tests/procesos_comerciales/test_service.py:39-57`
  (`test_crear_cotizacion_con_apertura_rechaza_con_validation_error`), cuyo docstring
  (`:42-46`) explica que el objetivo es dar un error de negocio legible (`422`,
  `ValidationError`) en vez del `500` crudo que devolvería Postgres si el `CHECK` de
  base de datos fuera el único punto que rechaza el INSERT.
- **Ventajas**: mejor experiencia de error para el cliente de la API — un `422` con
  mensaje explícito de qué campos sobran, en vez de un error genérico de base de datos.
- **Desventajas**: fuente de verdad duplicada, sin migración rastreable en el repo para
  el `CHECK` de base de datos. Si el `CHECK` cambiara directamente en la BD (por
  ejemplo, para admitir un campo de seguimiento adicional) sin actualizar
  `service.py`, o viceversa, ambas implementaciones podrían divergir sin que el
  repositorio lo refleje — riesgo de drift silencioso. Ver
  [`pendientes.md`](./pendientes.md) P1(2).
