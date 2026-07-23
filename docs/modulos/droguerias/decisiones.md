# Decisiones de diseño — Droguerías

Numeración D-DROGUERIAS-NNN, verificada contra el código en esta sesión.

### D-DROGUERIAS-001 — Solo `superadmin` puede crear, editar o eliminar una droguería

- **Decisión**: los 3 endpoints de escritura usan `require_roles("superadmin")`
  (`router.py:41`, `:50`, `:58`), sin ningún otro rol habilitado — a diferencia de
  Clientes o Usuarios, que sí tienen roles de escritura más amplios
  (`_ROLES_ESCRITURA` con 4 roles en Clientes).
- **Motivo**: no documentado explícitamente en el código (sin comentario ni
  docstring). Inferencia razonable dado el rol de esta tabla como raíz del
  multi-tenant (36 tablas dependen de `drogueria_id`, ver
  [`arquitectura.md`](./arquitectura.md)): permitir que un `admin` de una droguería
  cree o edite otras droguerías, o la propia, rompería el aislamiento que el resto del
  sistema asume — no verificable como motivo real sin un comentario del autor.
- **Ventajas**: superficie de ataque mínima sobre la tabla raíz del tenant.
- **Desventajas**: cualquier operación administrativa sobre la propia empresa (por
  ejemplo, un `admin` corrigiendo su propio `contacto_telefono`) requiere intervención
  de un `superadmin` — no hay autoservicio, ni siquiera para los campos no sensibles.
  Contrasta con la policy RLS `droguerias_upd`, que sí permitiría a un `admin` editar
  su propia droguería — ver D-DROGUERIAS-003.

### D-DROGUERIAS-002 — `eliminar_drogueria` es un hard-delete real, con `ConflictError` como salvaguarda ante FK

- **Decisión**: a diferencia de `clientes` (soft-delete con `deleted_at`/`deleted_by`),
  este módulo no tiene esas columnas; `DELETE /droguerias/{id}` ejecuta un `DELETE`
  real sobre la fila (`repository.py:19-20`). La única protección contra pérdida de
  datos es que Postgres rechaza el `DELETE` si hay filas dependientes por FK, y
  `service.py` traduce esa `APIError` a `ConflictError` con mensaje explícito
  (`service.py:32-38`).
- **Motivo**: no documentado en el código. No hay comentario que explique por qué se
  optó por hard-delete en vez de replicar el patrón de soft-delete ya establecido en
  Clientes.
- **Ventajas**: verificado empíricamente (`tests/droguerias/test_service.py:108-126`)
  que en la práctica es casi imposible eliminar una droguería con actividad real — la
  cascada de 36 tablas con `drogueria_id` actúa como un soft-delete de facto para
  cualquier droguería que no esté completamente vacía.
- **Desventajas**: para el caso límite en que sí se puede eliminar (droguería recién
  creada, sin ningún dato asociado todavía), la operación es irreversible — no hay
  forma de "deshacer" un `DELETE` exitoso, a diferencia de un soft-delete. También
  implica que el campo `activa` (pensado presumiblemente para desactivar sin borrar) y
  el hard-delete son dos mecanismos de "dar de baja" con semánticas distintas y sin
  relación entre sí en el código — ver [`pendientes.md`](./pendientes.md) P2.

### D-DROGUERIAS-003 — La policy RLS `droguerias_upd` permite más que lo que expone la API

- **Decisión**: `docs/schema/rls_final.sql:103` define
  `droguerias_upd` con `es_superadmin() OR (get_rol() = 'admin' AND id = get_drogueria_id())`
  — un `admin` podría actualizar su propia droguería vía RLS. Sin embargo,
  `PATCH /droguerias/{id}` en `router.py:46-52` exige `require_roles("superadmin")`
  únicamente, y el `UPDATE` real corre con `service_client` (sin RLS) — la policy más
  permisiva nunca se ejecuta para este endpoint.
- **Motivo**: no documentado. Es consistente con que la policy pueda haber sido escrita
  pensando en un caso de uso futuro (autoservicio de `admin` sobre su propia empresa)
  que todavía no se implementó a nivel de API — coincide con el criterio general de
  "dejar preparada la estructura" que también se aplicó en `planes` (ver
  [`../planes/decisiones.md`](../planes/decisiones.md)), pero no hay evidencia textual
  de que sea la misma intención.
- **Ventajas**: si en el futuro se decide exponer autoservicio de `admin`, la policy
  RLS ya está lista — solo haría falta cambiar `router.py` para usar `user_client` en
  vez de `require_roles("superadmin")` + `service_client`.
- **Desventajas**: dos fuentes de verdad para "quién puede editar una droguería" —la
  policy SQL y `require_roles` de Python— actualmente desalineadas. Si alguien
  reemplazara `service_client` por `user_client` en este endpoint sin revisar la policy,
  el comportamiento cambiaría silenciosamente (un `admin` empezaría a poder editar su
  propia droguería) sin que ningún test de este módulo lo señale, porque
  `tests/droguerias/test_service.py` usa `service_client` exclusivamente.

### D-DROGUERIAS-004 — Los `GET` consultan la tabla directo desde el router, sin pasar por `service.py`

- **Decisión**: `listar_droguerias_endpoint` y `obtener_drogueria_endpoint` construyen
  la query Supabase directamente en `router.py` (`:17-24`, `:27-36`), en vez de delegar
  en una función de `service.py` como sí hace Clientes para sus lecturas.
- **Motivo**: no documentado. Consistente con que no hay lógica de negocio adicional en
  la lectura de este módulo más allá de lo que ya resuelve RLS (`droguerias_sel`) — a
  diferencia de Clientes, que sí tiene reglas de negocio propias en sus lecturas
  (RN-CLIENTES-001).
- **Ventajas**: menos código, menos capas para un módulo pequeño.
- **Desventajas**: `repository.py:obtener_drogueria` queda con un único consumidor
  interno (`service.py`, para chequeos de existencia) que implementa una query
  equivalente a la que el router repite manualmente para el `GET` por `id` — dos
  implementaciones de la misma consulta en el mismo módulo. Ver
  [`pendientes.md`](./pendientes.md) P3.
