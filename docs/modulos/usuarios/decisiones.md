# Decisiones de diseño — Usuarios

Numeración D-USUARIOS-NNN. D-001 a 004 existían antes (releídas y reverificadas contra
el código actual, con referencias de línea actualizadas); D-005 en adelante son de esta
sesión.

### D-USUARIOS-001 — Crear, cambiar rol, activar/desactivar y eliminar usan `service_client`, con autorización en Python

- **Decisión**: los 5 wrappers `*_para_endpoint` de escritura (`crear_usuario_para_endpoint`,
  `cambiar_rol_para_endpoint`, `cambiar_activo_para_endpoint`,
  `eliminar_usuario_para_endpoint`, y también `actualizar_perfil_propio_para_endpoint`)
  resuelven `get_service_client()` (`service.py:131-132`, `:135-136`, `:139-140`,
  `:143-146`, `:149-150`) en vez de recibir un `user_client` con RLS, delegando el
  control de acceso enteramente a las validaciones explícitas de `service.py`.
- **Motivo**: no documentado explícitamente en el código. Inferido de la estructura: las
  reglas de estas operaciones son más finas que lo que una policy de RLS podría expresar
  razonablemente — por ejemplo, distinguir "cambiar rol hacia `admin`" (solo
  `superadmin`, RN-USUARIOS-015) de "cambiar rol dentro de la misma droguería" (`admin`,
  RN-USUARIOS-010), o bloquear la auto-modificación (RN-USUARIOS-014/017/023), algo que
  la policy `usuarios_upd` de la base ni siquiera contempla (ver
  `docs/schema/rls_final.sql:121-123`: no distingue `usuario_id == auth.uid()`).
- **Ventajas**: reglas de negocio expresivas y testeables en Python, con mensajes de
  error específicos por caso, en vez de un rechazo genérico de RLS.
- **Desventajas**: si en el futuro se agrega un call site a estas 5 funciones que no pase
  por su wrapper `*_para_endpoint` correspondiente, se pierde toda la protección adicional
  sin que nada lo impida estructuralmente — la protección vive enteramente en la
  disciplina de invocar siempre el wrapper correcto. Esta sesión agregó 3 funciones más a
  esa lista (`cambiar_activo`, `eliminar_usuario`, `actualizar_perfil_propio`), ampliando
  la superficie de esta desventaja preexistente.

### D-USUARIOS-002 — Los GET usan `user_client` y delegan el aislamiento por tenant a RLS

- **Decisión**: `GET /usuarios` y `GET /usuarios/{usuario_id}` usan `user_client`
  (`router.py:28`, `:37`) y no aplican ningún filtro `.eq("drogueria_id", ...)` explícito
  en Python — el aislamiento por droguería, si existe, queda enteramente en manos de la
  policy `usuarios_sel`. Sin cambios respecto de la revisión anterior.
- **Motivo**: no documentado explícitamente en el código. Inferido: menos código en el
  router, y un único punto de verdad para el aislamiento (la policy de la base), en vez
  de duplicar esa lógica en Python.
- **Ventajas**: simplicidad del endpoint — dos líneas de `SELECT` sin lógica adicional.
- **Desventajas**: la garantía de aislamiento por tenant no es verificable leyendo solo
  este módulo, esa policy sigue sin vivir en una migración versionada (a diferencia de
  la columna `apellido`, que sí llegó por migración en esta sesión — ver
  [`base_de_datos.md`](./base_de_datos.md)), y ningún test del repositorio la ejercita
  con un JWT real — ver [`pendientes.md`](./pendientes.md).

### D-USUARIOS-003 — Las funciones de negocio reciben `Client` como parámetro explícito

- **Decisión**: `crear_usuario`, `cambiar_rol`, `cambiar_activo`, `eliminar_usuario` y
  `actualizar_perfil_propio` toman `client: Client` como primer parámetro (o parámetro
  con nombre, en el caso de `actualizar_perfil_propio`), con wrappers `*_para_endpoint`
  que resuelven `get_service_client()` y lo pasan por ellas.
- **Motivo**: confirmado por el uso real en los tests — `tests/usuarios/test_service.py`
  importa las 5 funciones directamente (`:14-20`) y les pasa `service_client` en cada
  test, sin pasar por HTTP ni por `require_roles`.
- **Ventajas**: tests de lógica de negocio puros y rápidos — no requieren levantar la app
  FastAPI ni resolver un JWT real para verificar cada regla RN-USUARIOS-NNN. Esta sesión
  se apoyó en este patrón para escribir el nuevo test de `eliminar_usuario` con actividad
  asociada (RN-USUARIOS-027) sin necesitar un servidor HTTP real.
- **Desventajas**: la lógica de negocio queda desacoplada de la autorización HTTP
  (`require_roles` en `router.py`), que se convierte en una capa de responsabilidad
  separada y potencialmente duplicada: la whitelist de roles `("superadmin", "admin")`
  está repetida en `router.py` (4 endpoints de escritura) y de nuevo, de forma distinta,
  dentro de cada función de `service.py` (RN-USUARIOS-001/008/016/022).

### D-USUARIOS-004 — `es_sistema` hardcodeado; `Rol` (Python) excluye `"sistema"`

- **Decisión**: `crear_usuario` siempre inserta `es_sistema=False` (`service.py:47`), y
  el `Literal Rol` de `models.py:5` no incluye `"sistema"`, aunque el CHECK
  `ck_usuarios_rol` de la base sí lo permite (`docs/schema/rls_final.sql:38`).
- **Motivo**: pendiente de definición funcional — no hay comentario en el código que lo
  explique. Es razonable suponer (sin evidencia de código que lo confirme) que los
  usuarios técnicos se crean fuera de esta API: `seed_usuario_sistema` en
  `tests/conftest.py:126-142` los crea insertando directo con `service_client`.
- **Ventajas**: si la suposición anterior es correcta, evita que un `admin`/`superadmin`
  cree accidentalmente un usuario técnico vía la API pública. Reforzado en esta sesión
  por RN-USUARIOS-009/019/025, que ahora protegen explícitamente a `rol="sistema"` de
  cambios de rol, desactivación y eliminación, no solo de creación.
- **Desventajas**: la BD y el código de este módulo siguen desincronizados en qué roles
  considera válidos, sin que exista una razón documentada para esa diferencia.

### D-USUARIOS-005 — **[NUEVA]** Alta por invitación de email en vez de password directa

- **Decisión**: `crear_usuario` ya no acepta `password` en `UsuarioCreate`; usa
  `client.auth.admin.invite_user_by_email` en vez de `client.auth.admin.create_user`
  (`repository.py:9-19`). El `redirect_to` de la invitación apunta a
  `{frontend_url}/accept-invite`, con `frontend_url` como setting nueva de
  `core/config.py:17` (default `http://localhost:5173`).
- **Motivo**: no documentado explícitamente en el código, pero consistente con el
  propósito declarado de la migración `0007_apellido_y_planes.sql:4-5` ("módulo de
  autenticación/gestión de usuarios completo: invitación por email"). El diseño anterior
  (password elegida por quien crea la cuenta, o generada y comunicada por fuera del
  sistema) no dejaba rastro de que el propio usuario la hubiera definido.
- **Ventajas**: el usuario define su propia contraseña al aceptar la invitación, sin que
  un `admin`/`superadmin` la conozca en ningún momento; el flujo de "olvidé mi
  contraseña" y el de "alta de cuenta" convergen en el mismo mecanismo de Supabase Auth.
- **Desventajas**: el alta ahora depende de que el usuario reciba y responda un email
  (posible fricción, deliverability, o rate limit de Supabase Auth — ver
  RN-USUARIOS-013 y [`pendientes.md`](./pendientes.md)); no hay forma de crear una cuenta
  ya utilizable de inmediato (por ejemplo, para un script de seed) sin pasar por ese
  flujo — de ahí que `tests/usuarios/conftest.py` defina `crear_usuario_directo` como
  scaffolding que inserta directo, evitando gastar el rate limit de envío de emails.

### D-USUARIOS-006 — **[NUEVA]** `sistema` protegido igual que `superadmin` en cambio de rol, activación y eliminación

- **Decisión**: RN-USUARIOS-009 (extendida), 019 y 025 tratan a `rol="sistema"` con la
  misma protección que a `rol="superadmin"` — ninguno de los dos puede ser objetivo ni
  destino de `cambiar_rol`, `cambiar_activo` ni `eliminar_usuario`.
- **Motivo**: **hallazgo real de esta sesión**, no solo una decisión de diseño abstracta.
  Antes de este cambio, `cambiar_activo` no protegía `sistema` — un `admin` podía
  desactivar el usuario técnico real identificado por `usuario_sistema_id`
  (`core/config.py`), usado por el backend con `service_role` para ejecutar procesos
  automáticos (`docs/schema/rls_final.sql:46`: "usuarios técnicos [...] que ejecutan
  procesos automáticos"). Un `admin` desactivándolo accidentalmente rompería cualquier
  proceso que dependa de su identidad, sin relación con permisos de negocio legítimos
  sobre usuarios humanos.
- **Ventajas**: simetría con el CHECK `ck_usuarios_superadmin` de la base, que ya trata a
  `superadmin` y `sistema` de forma idéntica (`docs/schema/rls_final.sql:39-42`: ambos
  exigen `drogueria_id IS NULL`) — el código de aplicación ahora refleja una invariante
  que la base ya imponía a nivel de constraint.
- **Desventajas**: ninguna identificada; es estrictamente una corrección de un caso no
  cubierto antes. Queda pendiente extender el mismo criterio a `cambiar_rol`, que solo
  tiene test explícito para la rama `superadmin`, no para `sistema` — ver
  [`pendientes.md`](./pendientes.md).

### D-USUARIOS-007 — **[NUEVA]** Auto-modificación bloqueada explícitamente en las 3 operaciones destructivas/sensibles

- **Decisión**: `cambiar_rol`, `cambiar_activo` y `eliminar_usuario` rechazan
  explícitamente `usuario_id == creador.id`, evaluado **antes** de comprobar que el
  usuario objetivo existe.
- **Motivo**: **hallazgo del usuario en esta sesión**. Sin esta regla, un `admin` podía
  autosacarse el rol de `admin` (dejando potencialmente su droguería sin nadie con ese
  rol para revertirlo), autodesactivarse (quedando bloqueado por RN-USUARIOS-021 sin
  nadie que lo reactive), o autoeliminarse.
- **Ventajas**: cierra una vía de auto-bloqueo/auto-degradación irreversible por error
  humano o mal uso, sin depender de que exista siempre otro `superadmin`/`admin`
  disponible para revertirla.
- **Desventajas**: un `superadmin` tampoco puede auto-modificarse por esta vía (la regla
  no distingue rol del creador) — si algún día se necesita que un `superadmin` cambie su
  propio rol o se desactive a sí mismo, haría falta un mecanismo distinto (fuera del
  alcance de lo verificado en esta sesión).

### D-USUARIOS-008 — **[NUEVA]** Mapeo de errores de Supabase Auth: condicional en invitar, incondicional en eliminar

- **Decisión**: `invitar_usuario_auth` distingue por `exc.status` (429 → `ConflictError`,
  cualquier otro → `ValidationError`, `repository.py:20-32`), mientras que
  `eliminar_usuario_auth` mapea **cualquier** `AuthApiError` a `ConflictError`, sin mirar
  el status (`repository.py:57-66`).
- **Motivo**: los dos casos representan situaciones semánticamente distintas. Al invitar,
  un error puede ser un problema transitorio de rate limit (429, reintentable → 409) o un
  problema de los datos enviados (email inválido, 400 → 422, no reintentable sin
  corregir el input). Al eliminar, la causa realista de que Auth rechace el `delete_user`
  es que existan filas dependientes por FK sin cascada (eventos, historial de cambios) —
  un conflicto de estado del recurso, no un problema de validación de la request — por lo
  que **todo** error de Auth en esa operación se interpreta como 409.
- **Ventajas**: el status HTTP resultante en ambos casos es semánticamente razonable para
  el escenario más probable de cada operación, sin necesitar parsear el mensaje de error
  de Supabase para distinguir causas.
- **Desventajas**: el mapeo incondicional de `eliminar_usuario_auth` puede convertir un
  error de Auth genuinamente distinto (por ejemplo, un problema de red o de
  configuración) en un 409 con un mensaje que asume incorrectamente "actividad
  asociada" — no hay forma de distinguirlo desde la respuesta HTTP. Esto no fue
  ejercitado más allá del caso de FK confirmado por
  `test_eliminar_usuario_con_actividad_asociada_lanza_conflict`
  (`tests/usuarios/test_service.py:409-433`).

### D-USUARIOS-009 — **[NUEVA]** El gate de `activo=False` vive en `core/auth.py`, no en `usuarios/`

- **Decisión**: `cambiar_activo` (en `usuarios/service.py`) solo escribe la columna; el
  efecto de bloquear al usuario ocurre en `get_current_user`
  (`core/auth.py:33-49`), que ahora selecciona `activo` y levanta
  `AuthenticationError` si es `False` (`:39`, `:47-48`).
- **Motivo**: `get_current_user` es la dependencia compartida por prácticamente todos los
  endpoints protegidos del backend (no solo de `usuarios/`); centralizar el chequeo ahí,
  en vez de replicarlo módulo por módulo, garantiza que un usuario desactivado quede
  bloqueado en **toda** la API con un único punto de cambio.
- **Ventajas**: consistente con que Core ya es dueño de la resolución del perfil
  autenticado (ver [`../core/`](../core/)); `usuarios/` no necesita saber nada sobre cómo
  se aplica el bloqueo, solo escribir el campo.
- **Desventajas**: el efecto de `PATCH /usuarios/{id}/activo` no es inmediato para
  sesiones ya en curso del lado del JWT — un usuario recién desactivado sigue teniendo un
  JWT de Supabase técnicamente vigente; el bloqueo ocurre recién en su próximo request al
  backend, no al desactivarlo. No verificado con qué frecuencia el frontend revalida al
  usuario ni si existe algún mecanismo de invalidación de sesión más inmediato (fuera del
  alcance de este módulo).
