# Reglas — Usuarios

Todas las reglas fueron releídas y reverificadas contra el código real (`models.py`,
`repository.py`, `service.py`, `router.py`) y sus tests
(`tests/usuarios/test_service.py`, `tests/usuarios/conftest.py`) en esta sesión de
actualización. El módulo creció de 4 endpoints a 7 y de 2 funciones de negocio
(`crear_usuario`, `cambiar_rol`) a 5 (`crear_usuario`, `cambiar_rol`, `cambiar_activo`,
`eliminar_usuario`, `actualizar_perfil_propio`). Reglas RN-USUARIOS-001 a 012 existían
antes; algunas se modificaron (marcadas **[MODIFICADA]**) y se agregan RN-USUARIOS-013
en adelante.

## Reglas de creación (`crear_usuario`)

### RN-USUARIOS-001 — Solo `superadmin`/`admin` pueden crear usuarios

- **Descripción**: cualquier otro rol que intente crear un usuario es rechazado antes de
  evaluar el resto de las reglas.
- **Condición**: `creador.rol not in ("superadmin", "admin")`.
- **Resultado**: `ForbiddenError("Solo superadmin o admin pueden crear usuarios")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:14-15`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:128-132` (`test_rol_no_autorizado_no_puede_crear_usuario`).

### RN-USUARIOS-002 — **[MODIFICADA]** Un `admin` no puede crear usuarios con rol `superadmin` NI `admin`

- **Descripción**: antes de esta sesión solo se bloqueaba crear un `superadmin`; ahora
  también se bloquea crear un `admin`. Crear cualquiera de los dos roles queda reservado
  a un `superadmin`.
- **Condición**: `body.rol in ("superadmin", "admin") and creador.rol != "superadmin"`.
- **Resultado**: `ForbiddenError("Solo superadmin puede crear usuarios con rol superadmin o admin")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:17-18`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en dos tests separados —
  `tests/usuarios/test_service.py:62-65` (`test_admin_no_puede_crear_superadmin`) y
  `tests/usuarios/test_service.py:68-71` (`test_admin_no_puede_crear_admin`, nuevo en
  esta sesión). Contraparte positiva: `test_superadmin_crea_admin`
  (`tests/usuarios/test_service.py:74-83`).

### RN-USUARIOS-003 — Si el creador es `admin`, se fuerza su propia `drogueria_id`

- **Descripción**: el valor de `body.drogueria_id` se ignora por completo cuando el
  creador es `admin`; se usa siempre `creador.drogueria_id`.
- **Condición**: `creador.rol == "admin"`.
- **Resultado**: `drogueria_id = creador.drogueria_id`, sin importar qué venga en el body.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:20-21`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:46-59` (`test_admin_crea_usuario_fuerza_su_propia_drogueria`).

### RN-USUARIOS-004 — Si el creador es `superadmin`, se respeta `body.drogueria_id`

- **Descripción**: contraparte de RN-USUARIOS-003.
- **Condición**: `creador.rol != "admin"` (en la práctica, `superadmin`).
- **Resultado**: `drogueria_id = body.drogueria_id`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:22-23`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:88-100` (`test_superadmin_crea_usuario_con_drogueria_explicita`).

### RN-USUARIOS-005 — Un `superadmin` no debe tener `drogueria_id`

- **Descripción**: validación de consistencia sobre el `drogueria_id` ya resuelto por
  RN-USUARIOS-003/004.
- **Condición**: `body.rol == "superadmin" and drogueria_id is not None`.
- **Resultado**: `ValidationError("Un usuario superadmin no debe tener drogueria_id")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:25-26`.
- **Observaciones**: [IMPLEMENTADO]. Camino contrario cubierto por
  `test_superadmin_crea_otro_superadmin_sin_drogueria`
  (`tests/usuarios/test_service.py:103-113`); no hay test que dispare específicamente
  esta rama con `drogueria_id` no nulo.

### RN-USUARIOS-006 — Un no-`superadmin` requiere `drogueria_id`

- **Descripción**: contraparte de RN-USUARIOS-005.
- **Condición**: `body.rol != "superadmin" and drogueria_id is None`.
- **Resultado**: `ValidationError("Los usuarios no-superadmin requieren drogueria_id")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:27-28`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:116-125`
  (`test_superadmin_crea_usuario_no_superadmin_sin_drogueria_lanza_validation_error`).

### RN-USUARIOS-007 — Todo usuario creado por esta API tiene `es_sistema=False`

- **Descripción**: no hay ningún parámetro de entrada que permita crear un usuario con
  `es_sistema=True` — el valor está hardcodeado en el dict insertado.
- **Condición**: cualquier llamada exitosa a `crear_usuario`.
- **Resultado**: la fila insertada en `usuarios` siempre tiene `es_sistema=False`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/usuarios/service.py:47`.
- **Observaciones**: [IMPLEMENTADO]. Consistente con el CHECK de la base
  `ck_usuarios_es_sistema: (rol = 'sistema') = (es_sistema = TRUE)`
  (`docs/schema/rls_final.sql:43`): como el `Literal Rol` de Python nunca permite
  `rol="sistema"` (RN-USUARIOS-012 / D-USUARIOS-004), este hardcodeo nunca puede violar
  ese CHECK. Usuarios técnicos se siguen creando fuera de esta API — ver
  `seed_usuario_sistema` en `tests/conftest.py:126-142`.

### RN-USUARIOS-013 — **[NUEVA]** Alta por invitación de email, no por password directa

- **Descripción**: `UsuarioCreate` ya no recibe `password` — el body ahora requiere
  `apellido` (nuevo campo obligatorio, `models.py:11`). `crear_usuario` arma
  `redirect_to = f"{get_settings().frontend_url}/accept-invite"` y llama a
  `repo.invitar_usuario_auth`, que usa `client.auth.admin.invite_user_by_email` (antes
  usaba `client.auth.admin.create_user` con `password` y `email_confirm=True`) pasando
  `nombre`, `apellido` y `rol` como metadata (`data`) de la invitación. El usuario recibe
  un email de Supabase Auth y define su propia contraseña al aceptar la invitación en
  `{frontend_url}/accept-invite`.
- **Condición**: cualquier llamada exitosa a `crear_usuario`.
- **Resultado**: se crea la cuenta en `auth.users` sin contraseña asignada por el backend
  y se envía el email de invitación; recién entonces se inserta la fila de perfil en
  `usuarios` con el `id` devuelto por Auth.
- **Manejo de errores de Auth**: `invitar_usuario_auth` atrapa `AuthApiError`
  (`repository.py:20-32`) y lo traduce a un error de dominio: si `exc.status == 429`
  (rate limit de envío de emails), `ConflictError` con mensaje explicando que hay que
  reintentar más tarde; para cualquier otro código, `ValidationError` con el mensaje de
  Supabase. Sin este catch, la excepción no mapeada caía al handler `500` default de
  FastAPI, que corre **fuera** de `CORSMiddleware` — el navegador lo veía como
  `Failed to fetch` sin ningún detalle legible, en vez de un error de dominio con mensaje
  claro y status HTTP correcto.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:13-38`,
  `services/presupuestacion/usuarios/repository.py:9-33`,
  `services/presupuestacion/core/config.py:17` (`frontend_url`).
- **Observaciones**: [IMPLEMENTADO] el mecanismo de invitación en sí, verificado por
  todos los tests de `crear_usuario` en `tests/usuarios/test_service.py` (que sí
  ejercitan la invitación real por email, a diferencia de `crear_usuario_directo` usado
  como scaffolding en el resto del archivo — ver el comentario de
  `tests/usuarios/test_service.py:38-43`). El **mapeo de errores 429/otros** fue
  verificado **manualmente por el usuario en esta sesión** contra Supabase Auth real
  (rate limit real y un email inválido), no hay un test automatizado que lo cubra — ver
  [`pendientes.md`](./pendientes.md).

## Reglas de cambio de rol (`cambiar_rol`)

### RN-USUARIOS-008 — Solo `superadmin`/`admin` pueden cambiar el rol de otro usuario

- **Descripción**: misma restricción de rol que RN-USUARIOS-001, aplicada a `cambiar_rol`.
- **Condición**: `creador.rol not in ("superadmin", "admin")`.
- **Resultado**: `ForbiddenError("Solo superadmin o admin pueden cambiar roles")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:55-56`.
- **Observaciones**: [IMPLEMENTADO]. Sin test directo en
  `tests/usuarios/test_service.py` que dispare específicamente esta rama con un rol no
  autorizado — ver [`pendientes.md`](./pendientes.md) (hallazgo preexistente, sigue sin
  cubrirse).

### RN-USUARIOS-014 — **[NUEVA]** Nadie puede cambiar su propio rol

- **Descripción**: hallazgo de esta sesión — sin esta regla, un `admin` podía
  autopromoverse/autodegradarse (incluido autosacarse el rol de `admin`) y quedar sin
  nadie con permisos para revertirlo. Se evalúa **antes** de comprobar que el usuario
  objetivo existe (RN-USUARIOS-011) — mismo orden en `cambiar_activo` (RN-USUARIOS-017) y
  `eliminar_usuario` (RN-USUARIOS-023).
- **Condición**: `usuario_id == creador.id`.
- **Resultado**: `ForbiddenError("No podés cambiar tu propio rol")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:58-59`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:238-245` (`test_no_se_puede_cambiar_el_propio_rol`).

### RN-USUARIOS-011 — Usuario objetivo inexistente → `NotFoundError`

- **Descripción**: se valida que el usuario a modificar exista, ahora **después** de
  RN-USUARIOS-008 y RN-USUARIOS-014, y **antes** de las reglas de protección de rol.
- **Condición**: `repo.obtener_usuario(client, usuario_id=usuario_id)` devuelve `None`.
- **Resultado**: `NotFoundError("No se encontró el usuario")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:61-63`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:202-210` (`test_cambiar_rol_usuario_inexistente_lanza_not_found`).
  Ver [`flujo.md`](./flujo.md) para el orden completo de validaciones.

### RN-USUARIOS-009 — **[MODIFICADA]** Cambiar rol desde o hacia `superadmin` O `sistema` está prohibido por esta vía

- **Descripción**: antes de esta sesión la protección solo cubría `superadmin`; el rol
  técnico `sistema` no tenía ninguna protección — un `admin` podía, en teoría,
  reasignarle el rol a un usuario `sistema` o degradar a un usuario `sistema` existente
  (por ejemplo el usuario técnico real `SYSTEM`, identificado por
  `usuario_sistema_id` en `core/config.py`) sin que el código lo impidiera. Ahora la
  condición cubre ambos roles simétricamente, en línea con el CHECK
  `ck_usuarios_superadmin` de la base, que ya trata a `superadmin` y `sistema` igual
  (`docs/schema/rls_final.sql:39-42`: ambos exigen `drogueria_id IS NULL`).
- **Condición**: `objetivo["rol"] in ("superadmin", "sistema") or nuevo_rol in ("superadmin", "sistema")`.
- **Resultado**: `ForbiddenError("Cambiar desde/hacia superadmin o sistema no está permitido por esta vía")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:65-68`.
- **Observaciones**: [IMPLEMENTADO]. La rama `superadmin` sigue verificada en dos tests
  — `tests/usuarios/test_service.py:179-188` (`test_cambiar_rol_no_permite_hacia_superadmin`)
  y `tests/usuarios/test_service.py:191-199` (`test_cambiar_rol_no_permite_desde_superadmin`).
  **No se encontró un test que ejercite específicamente la rama `sistema` en
  `cambiar_rol`** (sí existe para `cambiar_activo`, ver RN-USUARIOS-019) — anotado como
  gap nuevo en [`pendientes.md`](./pendientes.md).

### RN-USUARIOS-015 — **[NUEVA]** Solo `superadmin` puede promover a rol `admin`

- **Descripción**: espejo de RN-USUARIOS-002 pero para `cambiar_rol` — antes cualquier
  `admin` podía promover a otro usuario a `admin` (mientras no fuera `superadmin`/`sistema`
  por RN-USUARIOS-009); ahora esa promoción está reservada a `superadmin`.
- **Condición**: `nuevo_rol == "admin" and creador.rol != "superadmin"`.
- **Resultado**: `ForbiddenError("Solo superadmin puede asignar el rol admin")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:70-71`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en dos tests —
  `tests/usuarios/test_service.py:213-222` (`test_admin_no_puede_promover_a_admin`) y
  `tests/usuarios/test_service.py:225-234` (`test_superadmin_puede_promover_a_admin`).

### RN-USUARIOS-010 — Un `admin` solo puede cambiar rol dentro de su propia `drogueria_id`

- **Descripción**: un `admin` está acotado a los usuarios de su propia droguería; un
  `superadmin` no tiene esta restricción (más allá de RN-USUARIOS-009/015).
- **Condición**: `creador.rol == "admin" and objetivo["drogueria_id"] != creador.drogueria_id`.
- **Resultado**: `ForbiddenError("Un admin solo puede modificar usuarios de su droguería")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:73-74`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:151-176` (`test_admin_no_puede_cambiar_rol_de_usuario_de_otra_drogueria`);
  camino positivo en `tests/usuarios/test_service.py:139-148`
  (`test_admin_cambia_rol_de_usuario_de_su_drogueria`).

### RN-USUARIOS-012 — `nuevo_rol` no está tipado contra `Rol`

- **Descripción**: `cambiar_rol` sigue recibiendo `nuevo_rol: str` sin validar contra el
  `Literal Rol` de `models.py`. El único guardarraíl para un valor fuera de los roles
  válidos, si se llama a esta función fuera del router (que sí valida vía
  `UsuarioRolUpdate.rol: Rol`), sigue siendo el CHECK `ck_usuarios_rol` de la base.
- **Condición**: llamada directa a `cambiar_rol` (no vía HTTP) con un `nuevo_rol` arbitrario.
- **Resultado**: si el valor no cumple el CHECK de `rol` en Postgres, la excepción del
  driver de Supabase no está mapeada a ningún `DomainError` de este módulo.
- **Prioridad**: Baja.
- **Archivo**: `services/presupuestacion/usuarios/service.py:52-54` (firma).
- **Observaciones**: [IMPLEMENTADO] el hecho de que sigue sin tipar. Sin cambios desde
  la última revisión. Ver [`pendientes.md`](./pendientes.md) P3.

## Reglas de activar/desactivar (`cambiar_activo`) — **[NUEVA función]**

`cambiar_activo` no existía en la revisión anterior; toda esta sección es nueva.

### RN-USUARIOS-016 — Solo `superadmin`/`admin` pueden activar/desactivar usuarios

- **Condición**: `creador.rol not in ("superadmin", "admin")`.
- **Resultado**: `ForbiddenError("Solo superadmin o admin pueden activar/desactivar usuarios")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:82-83`.
- **Observaciones**: [IMPLEMENTADO]. Sin test directo que ejercite un rol no autorizado
  para `cambiar_activo` — mismo gap que RN-USUARIOS-008, ver [`pendientes.md`](./pendientes.md).

### RN-USUARIOS-017 — Nadie puede activarse/desactivarse a sí mismo

- **Descripción**: mismo hallazgo de esta sesión que RN-USUARIOS-014 — sin esta regla,
  un `admin` podía desactivar su propia cuenta y quedar bloqueado por
  `get_current_user` (RN-USUARIOS-021) sin nadie que lo reactive.
- **Condición**: `usuario_id == creador.id`.
- **Resultado**: `ForbiddenError("No podés activar/desactivar tu propio usuario")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:85-86`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:304-309` (`test_no_se_puede_desactivar_el_propio_usuario`).

### RN-USUARIOS-018 — Usuario objetivo inexistente → `NotFoundError`

- **Condición**: `repo.obtener_usuario(client, usuario_id=usuario_id)` devuelve `None`.
- **Resultado**: `NotFoundError("No se encontró el usuario")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:88-90`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:323-331` (`test_cambiar_activo_usuario_inexistente_lanza_not_found`).

### RN-USUARIOS-019 — No se puede activar/desactivar un `superadmin` o `sistema` por esta vía

- **Descripción**: misma protección simétrica de RN-USUARIOS-009, aplicada a
  `cambiar_activo`. A diferencia de RN-USUARIOS-009, acá sí existe un test explícito
  para la rama `sistema`.
- **Condición**: `objetivo["rol"] in ("superadmin", "sistema")`.
- **Resultado**: `ForbiddenError("No se puede activar/desactivar un superadmin o sistema por esta vía")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:92-93`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:293-301` (`test_no_se_puede_desactivar_superadmin`) y
  `tests/usuarios/test_service.py:312-320` (`test_no_se_puede_desactivar_usuario_sistema`,
  usa el fixture `seed_usuario_sistema` de `tests/conftest.py:126-142` — confirma
  empíricamente el bug real que motivó extender RN-USUARIOS-009 también acá).

### RN-USUARIOS-020 — Un `admin` solo puede activar/desactivar usuarios de su propia `drogueria_id`

- **Condición**: `creador.rol == "admin" and objetivo["drogueria_id"] != creador.drogueria_id`.
- **Resultado**: `ForbiddenError("Un admin solo puede modificar usuarios de su droguería")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:95-96`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:269-290` (`test_admin_no_puede_desactivar_usuario_de_otra_drogueria`);
  camino positivo en `tests/usuarios/test_service.py:252-266`
  (`test_admin_desactiva_usuario_de_su_drogueria`, que además confirma la
  reactivación con `activo=True`).

### RN-USUARIOS-021 — El gate real de `activo=False` está en `get_current_user`, no en `cambiar_activo`

- **Descripción**: `cambiar_activo` solo escribe la columna; el efecto de bloquear al
  usuario ocurre en `core/auth.py`. `get_current_user` ahora incluye `activo` en el
  `SELECT` de `usuarios` y, si `perfil.activo` es `False`, levanta
  `AuthenticationError("Usuario desactivado")` (401) — **aunque el JWT de Supabase del
  usuario siga vigente**. Antes de esta sesión el campo `activo` se leía pero no se
  evaluaba en ningún punto del código (confirmado: no había ningún `if` sobre `activo`
  en todo el módulo ni en Core).
- **Condición**: cualquier request autenticado de un usuario con `activo=False` en la
  tabla `usuarios`.
- **Resultado**: `401 Usuario desactivado` en cualquier endpoint que dependa de
  `get_current_user` o `require_roles` (es decir, prácticamente toda la API salvo rutas
  públicas), sin importar la vigencia del JWT.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/core/auth.py:33-49` (`activo` en el `select`,
  `:39`; chequeo y `raise`, `:47-48`).
- **Observaciones**: [IMPLEMENTADO]. No hay un test de integración HTTP end-to-end en
  `tests/usuarios/` que dispare un request real con un usuario desactivado y confirme el
  401 (los tests de `cambiar_activo` verifican solo el valor de la columna, no el efecto
  en `get_current_user`) — ver [`pendientes.md`](./pendientes.md).

## Reglas de eliminación (`eliminar_usuario`) — **[NUEVA función]**

`eliminar_usuario` no existía en la revisión anterior; toda esta sección es nueva.
Comparte exactamente el mismo alcance de autorización que `cambiar_activo`
(RN-USUARIOS-016 a 020), aplicado a un `DELETE` en vez de un `UPDATE`.

### RN-USUARIOS-022 — Solo `superadmin`/`admin` pueden eliminar usuarios

- **Condición**: `creador.rol not in ("superadmin", "admin")`.
- **Resultado**: `ForbiddenError("Solo superadmin o admin pueden eliminar usuarios")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:102-103`.
- **Observaciones**: [IMPLEMENTADO]. Sin test directo que ejercite un rol no autorizado
  — mismo gap que RN-USUARIOS-008/016.

### RN-USUARIOS-023 — Nadie puede eliminarse a sí mismo

- **Condición**: `usuario_id == creador.id`.
- **Resultado**: `ForbiddenError("No podés eliminar tu propio usuario")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:105-106`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:363-366` (`test_no_se_puede_eliminar_el_propio_usuario`).

### RN-USUARIOS-024 — Usuario objetivo inexistente → `NotFoundError`

- **Condición**: `repo.obtener_usuario(client, usuario_id=usuario_id)` devuelve `None`.
- **Resultado**: `NotFoundError("No se encontró el usuario")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:108-110`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:399-406` (`test_eliminar_usuario_inexistente_lanza_not_found`).

### RN-USUARIOS-025 — No se puede eliminar un `superadmin` o `sistema` por esta vía

- **Condición**: `objetivo["rol"] in ("superadmin", "sistema")`.
- **Resultado**: `ForbiddenError("No se puede eliminar un superadmin o sistema por esta vía")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:112-113`.
- **Observaciones**: [IMPLEMENTADO] la rama `superadmin`, verificada en
  `tests/usuarios/test_service.py:369-374` (`test_no_se_puede_eliminar_superadmin`).
  **No se encontró un test que ejercite la rama `sistema` para `eliminar_usuario`**
  (sí existe para `cambiar_activo`, RN-USUARIOS-019) — gap anotado en
  [`pendientes.md`](./pendientes.md).

### RN-USUARIOS-026 — Un `admin` solo puede eliminar usuarios de su propia `drogueria_id`

- **Condición**: `creador.rol == "admin" and objetivo["drogueria_id"] != creador.drogueria_id`.
- **Resultado**: `ForbiddenError("Un admin solo puede eliminar usuarios de su droguería")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:115-116`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:378-396` (`test_admin_no_puede_eliminar_usuario_de_otra_drogueria`);
  camino positivo en `tests/usuarios/test_service.py:355-360`
  (`test_admin_elimina_usuario_de_su_drogueria`).

### RN-USUARIOS-027 — Eliminar un usuario con actividad asociada falla con `ConflictError` (409), no con un error crudo

- **Descripción**: `usuarios.id` referencia `auth.users.id` con `ON DELETE CASCADE`
  (`docs/schema/rls_final.sql:36`), por lo que en principio borrar el usuario de Auth
  alcanza para borrar también su fila de `usuarios`. Pero si el usuario tiene actividad
  asociada por FK sin cascada (por ejemplo `eventos.created_by`, o filas de
  `historial_cambios` como `created_by`/`usuario_id`), la eliminación en cascada viola
  esa FK y Supabase Auth devuelve un `AuthApiError`. `repo.eliminar_usuario_auth` atrapa
  **cualquier** `AuthApiError` (no solo un status específico, a diferencia del mapeo
  condicional de `invitar_usuario_auth` en RN-USUARIOS-013) y lo traduce a
  `ConflictError` con un mensaje explícito sobre actividad asociada.
- **Condición**: `client.auth.admin.delete_user(usuario_id)` lanza `AuthApiError`.
- **Resultado**: `ConflictError("No se puede eliminar: el usuario tiene actividad
  asociada (eventos, historial de cambios, etc.).")` (409).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/repository.py:57-66`.
- **Observaciones**: [IMPLEMENTADO], **verificado empíricamente en esta sesión** con un
  test de integración real: `tests/usuarios/test_service.py:409-433`
  (`test_eliminar_usuario_con_actividad_asociada_lanza_conflict`), que crea un evento con
  `created_by` apuntando al usuario y confirma que el `DELETE` levanta `ConflictError` en
  vez de propagar la excepción cruda de Supabase. Ver
  [`decisiones.md`](./decisiones.md) para por qué se eligió mapear **todo**
  `AuthApiError` acá a `ConflictError`, sin distinguir por status como en la invitación.

## Reglas de autoservicio de perfil (`actualizar_perfil_propio`) — **[NUEVA función]**

### RN-USUARIOS-028 — Cualquier usuario autenticado edita su propio `nombre`/`apellido`, sin chequeo de rol

- **Descripción**: a diferencia de todas las reglas anteriores, `actualizar_perfil_propio`
  no valida `creador.rol` en absoluto. La restricción real de "solo tu propio perfil" no
  es una regla de negocio explícita en `service.py` — es que el router toma `usuario_id`
  del propio token (`usuario.id` resuelto por `get_current_user`,
  `router.py:73`), no de un parámetro de la URL, así que no hay forma de pasar el `id` de
  otro usuario desde este endpoint.
- **Condición**: cualquier request autenticado a `PATCH /usuarios/me`.
- **Resultado**: se actualizan únicamente los campos provistos en el body
  (`body.model_dump(exclude_unset=True)`, `service.py:127`) — un campo omitido no se
  toca, no se pisa con `None`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/usuarios/service.py:121-128`,
  `services/presupuestacion/usuarios/router.py:70-75`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:339-347`
  (`test_actualizar_perfil_propio_solo_toca_campos_provistos`, que actualiza solo
  `apellido` y confirma que `nombre` no cambia).
