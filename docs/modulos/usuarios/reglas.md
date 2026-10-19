# Reglas — Usuarios

Todas las reglas fueron releídas y reverificadas contra el código real (`usuarios/models.py`,
`repository.py`, `service.py`, `router.py`, `auth/*.py`, `services/shared/auth.py`) y sus
tests (`tests/usuarios/test_service.py`, `tests/usuarios/test_router.py`,
`tests/auth/test_router.py`, `tests/auth/test_repository.py`, `tests/shared/test_auth.py`).
Las referencias de línea de esta revisión corresponden a la rama
`feat/login-usuario-alta-admin` (odd/tasks/login-usuario-alta-admin.md).

Numeración: RN-USUARIOS-001 a 029 existían antes; algunas se modificaron (marcadas
**[MODIFICADA]**). RN-USUARIOS-013 (alta por invitación de email) quedó **[ELIMINADA]** —
se conserva el número, no se renumera. RN-USUARIOS-030 en adelante son del login con
nombre de usuario y del alta por el admin.

**Matriz de roles (odd/tasks/roles-permisos-matriz.md S7)**: `gerencia` se suma a
`superadmin`/`admin` como rol de gestión de usuarios (`ROLES_GESTION_USUARIOS`,
`service.py:20`), acotado a su propia droguería y a los roles inferiores a `admin`
(`ROLES_GESTIONABLES_POR_GERENCIA`, `service.py:24`; RN-USUARIOS-029). Los casos de
`gerencia` y la preservación de `admin`/`superadmin` están cubiertos en
`tests/usuarios/test_router.py:132-303`.

## Reglas de creación (`crear_usuario`)

### RN-USUARIOS-001 — **[MODIFICADA]** Solo `superadmin`/`admin`/`gerencia` pueden crear usuarios

- **Descripción**: cualquier otro rol que intente crear un usuario es rechazado antes de
  evaluar el resto de las reglas. `gerencia` se sumó con la matriz de roles (S7), con el
  alcance acotado de RN-USUARIOS-029.
- **Condición**: `creador.rol not in ROLES_GESTION_USUARIOS`
  (`("superadmin", "admin", "gerencia")`, `service.py:20`).
- **Resultado**: `ForbiddenError("Solo superadmin, admin o gerencia pueden crear usuarios")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:77-78`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:130` (`test_rol_no_autorizado_no_puede_crear_usuario`)
  y, vía HTTP, en `tests/usuarios/test_router.py:295`
  (`test_roles_sin_gestion_siguen_rechazados`: `lider_comercial`, `comercial` y `compras`
  reciben 403 en el guard del router).

### RN-USUARIOS-002 — **[MODIFICADA]** Un `admin` no puede crear usuarios con rol `superadmin` NI `admin`

- **Descripción**: crear cualquiera de los dos roles queda reservado a un `superadmin` —
  aplica igual a `admin` y a `gerencia`.
- **Condición**: `body.rol in ("superadmin", "admin") and creador.rol != "superadmin"`.
- **Resultado**: `ForbiddenError("Solo superadmin puede crear usuarios con rol superadmin o admin")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:80-81`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en `tests/usuarios/test_service.py:64`
  (`test_admin_no_puede_crear_superadmin`) y `:70` (`test_admin_no_puede_crear_admin`).
  Contraparte positiva: `test_superadmin_crea_admin` (`tests/usuarios/test_service.py:76`).
  Para `gerencia`: `tests/usuarios/test_router.py:171`
  (`test_gerencia_no_puede_invitar_admin_ni_superadmin`).

### RN-USUARIOS-003 — **[MODIFICADA]** Si el creador es `admin` o `gerencia`, se fuerza su propia `drogueria_id`

- **Descripción**: el valor de `body.drogueria_id` se ignora por completo cuando el
  creador es `admin` o `gerencia`; se usa siempre `creador.drogueria_id`.
- **Condición**: `creador.rol in ("admin", "gerencia")`.
- **Resultado**: `drogueria_id = creador.drogueria_id`, sin importar qué venga en el body.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:86-87`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:48` (`test_admin_crea_usuario_fuerza_su_propia_drogueria`)
  y, para `gerencia`, en `tests/usuarios/test_router.py:161`
  (`test_gerencia_invita_rol_inferior_en_su_drogueria`).

### RN-USUARIOS-004 — Si el creador es `superadmin`, se respeta `body.drogueria_id`

- **Descripción**: contraparte de RN-USUARIOS-003.
- **Condición**: `creador.rol not in ("admin", "gerencia")` (en la práctica, `superadmin`).
- **Resultado**: `drogueria_id = body.drogueria_id`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:88-89`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:90` (`test_superadmin_crea_usuario_con_drogueria_explicita`).

### RN-USUARIOS-005 — Un `superadmin` no debe tener `drogueria_id`

- **Descripción**: validación de consistencia sobre el `drogueria_id` ya resuelto por
  RN-USUARIOS-003/004.
- **Condición**: `body.rol == "superadmin" and drogueria_id is not None`.
- **Resultado**: `ValidationError("Un usuario superadmin no debe tener drogueria_id")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:91-92`.
- **Observaciones**: [IMPLEMENTADO]. Camino contrario cubierto por
  `test_superadmin_crea_otro_superadmin_sin_drogueria`
  (`tests/usuarios/test_service.py:105`); no hay test que dispare específicamente
  esta rama con `drogueria_id` no nulo.

### RN-USUARIOS-006 — Un no-`superadmin` requiere `drogueria_id`

- **Descripción**: contraparte de RN-USUARIOS-005.
- **Condición**: `body.rol != "superadmin" and drogueria_id is None`.
- **Resultado**: `ValidationError("Los usuarios no-superadmin requieren drogueria_id")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:93-94`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:118`
  (`test_superadmin_crea_usuario_no_superadmin_sin_drogueria_lanza_validation_error`).

### RN-USUARIOS-007 — Todo usuario creado por esta API tiene `es_sistema=False`

- **Descripción**: no hay ningún parámetro de entrada que permita crear un usuario con
  `es_sistema=True` — el valor está hardcodeado en el dict insertado.
- **Condición**: cualquier llamada exitosa a `crear_usuario`.
- **Resultado**: la fila insertada en `usuarios` siempre tiene `es_sistema=False`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/usuarios/service.py:121`.
- **Observaciones**: [IMPLEMENTADO]. Consistente con el CHECK de la base
  `ck_usuarios_es_sistema: (rol = 'sistema') = (es_sistema = TRUE)`
  (`docs/schema/rls_final.sql:43`): como el `Literal Rol` de Python nunca permite
  `rol="sistema"` (RN-USUARIOS-012 / D-USUARIOS-004), este hardcodeo nunca puede violar
  ese CHECK. Usuarios técnicos se siguen creando fuera de esta API — ver
  `seed_usuario_sistema` en `tests/conftest.py`.

### RN-USUARIOS-013 — **[ELIMINADA]** Alta por invitación de email

- **Estado**: eliminada por odd/tasks/login-usuario-alta-admin.md (S2, L2). Ya no existen
  `invitar_usuario_auth`, `invite_user_by_email`, el `redirect_to` a
  `{frontend_url}/accept-invite` ni la ruta `/accept-invite` del frontend. El alta ahora
  es con `username` + contraseña temporal — ver RN-USUARIOS-030 a 034. El mapeo de
  errores de Auth que vivía en esta regla (429 → 409, resto → 422) se conserva para
  `create_user` en RN-USUARIOS-040.
- Se conserva el número para no renumerar las reglas que la citaban.

## Reglas de cambio de rol (`cambiar_rol`)

### RN-USUARIOS-008 — **[MODIFICADA]** Solo `superadmin`/`admin`/`gerencia` pueden cambiar el rol de otro usuario

- **Descripción**: misma restricción de rol que RN-USUARIOS-001, aplicada a `cambiar_rol`.
- **Condición**: `creador.rol not in ROLES_GESTION_USUARIOS` (`service.py:20`).
- **Resultado**: `ForbiddenError("Solo superadmin, admin o gerencia pueden cambiar roles")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:137-138`.
- **Observaciones**: [IMPLEMENTADO]. Sin test directo en
  `tests/usuarios/test_service.py` que dispare específicamente esta rama del service con
  un rol no autorizado — ver [`pendientes.md`](./pendientes.md). Vía HTTP, el guard del
  router rechaza con 403 a `lider_comercial`/`comercial`/`compras` antes de llegar acá
  (`tests/usuarios/test_router.py:295`).

### RN-USUARIOS-014 — Nadie puede cambiar su propio rol

- **Descripción**: sin esta regla, un `admin` podía autopromoverse/autodegradarse y quedar
  sin nadie con permisos para revertirlo. Se evalúa **antes** de comprobar que el usuario
  objetivo existe (RN-USUARIOS-011) — mismo orden en `cambiar_activo` (RN-USUARIOS-017),
  `eliminar_usuario` (RN-USUARIOS-023), `blanquear_password` y `cambiar_username`
  (RN-USUARIOS-036/037).
- **Condición**: `usuario_id == creador.id`.
- **Resultado**: `ForbiddenError("No podés cambiar tu propio rol")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:140-141`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:239` (`test_no_se_puede_cambiar_el_propio_rol`).

### RN-USUARIOS-011 — Usuario objetivo inexistente → `NotFoundError`

- **Descripción**: se valida que el usuario a modificar exista, **después** de
  RN-USUARIOS-008 y RN-USUARIOS-014, y **antes** de las reglas de protección de rol.
- **Condición**: `repo.obtener_usuario(client, usuario_id=usuario_id)` devuelve `None`.
- **Resultado**: `NotFoundError("No se encontró el usuario")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:143-145`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:204` (`test_cambiar_rol_usuario_inexistente_lanza_not_found`).

### RN-USUARIOS-009 — **[MODIFICADA]** Cambiar rol desde o hacia `superadmin` O `sistema` está prohibido por esta vía

- **Descripción**: la condición cubre ambos roles simétricamente, en línea con el CHECK
  `ck_usuarios_superadmin` de la base, que ya trata a `superadmin` y `sistema` igual
  (`docs/schema/rls_final.sql:39-42`: ambos exigen `drogueria_id IS NULL`).
- **Condición**: `objetivo["rol"] in ("superadmin", "sistema") or nuevo_rol in ("superadmin", "sistema")`.
- **Resultado**: `ForbiddenError("Cambiar desde/hacia superadmin o sistema no está permitido por esta vía")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:147-150`.
- **Observaciones**: [IMPLEMENTADO]. Rama `superadmin` verificada en
  `tests/usuarios/test_service.py:181` (`test_cambiar_rol_no_permite_hacia_superadmin`) y
  `:193` (`test_cambiar_rol_no_permite_desde_superadmin`); rama `sistema` en
  `tests/usuarios/test_service.py:325` (`test_no_se_puede_cambiar_rol_de_usuario_sistema`).

### RN-USUARIOS-015 — Solo `superadmin` puede promover a rol `admin`

- **Descripción**: espejo de RN-USUARIOS-002 pero para `cambiar_rol`.
- **Condición**: `nuevo_rol == "admin" and creador.rol != "superadmin"`.
- **Resultado**: `ForbiddenError("Solo superadmin puede asignar el rol admin")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:152-153`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en `tests/usuarios/test_service.py:215`
  (`test_admin_no_puede_promover_a_admin`) y `:227` (`test_superadmin_puede_promover_a_admin`).
  También aplica a `gerencia`: `tests/usuarios/test_router.py:187`
  (`test_gerencia_no_puede_asignar_admin`).

### RN-USUARIOS-010 — **[MODIFICADA]** Un `admin` o `gerencia` solo puede cambiar rol dentro de su propia `drogueria_id`

- **Descripción**: `admin` y `gerencia` están acotados a los usuarios de su propia
  droguería; un `superadmin` no tiene esta restricción (más allá de
  RN-USUARIOS-009/015). Se evalúa después de RN-USUARIOS-029.
- **Condición**: `creador.rol in ("admin", "gerencia") and objetivo["drogueria_id"] != creador.drogueria_id`.
- **Resultado**: `ForbiddenError("Un admin solo puede modificar usuarios de su droguería")` (admin) o `ForbiddenError("Gerencia solo puede modificar usuarios de su droguería")` (gerencia) — `_mensaje_otra_drogueria`, `service.py:69-73`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:159-160`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:153` (`test_admin_no_puede_cambiar_rol_de_usuario_de_otra_drogueria`);
  camino positivo en `tests/usuarios/test_service.py:141`
  (`test_admin_cambia_rol_de_usuario_de_su_drogueria`). Para `gerencia`, caso
  `comercial-otra` de `tests/usuarios/test_router.py:198`.

### RN-USUARIOS-012 — `nuevo_rol` no está tipado contra `Rol`

- **Descripción**: `cambiar_rol` sigue recibiendo `nuevo_rol: str` sin validar contra el
  `Literal Rol` de `models.py`. El único guardarraíl para un valor fuera de los roles
  válidos, si se llama a esta función fuera del router (que sí valida vía
  `UsuarioRolUpdate.rol: Rol`), sigue siendo el CHECK `ck_usuarios_rol` de la base.
- **Condición**: llamada directa a `cambiar_rol` (no vía HTTP) con un `nuevo_rol` arbitrario.
- **Resultado**: si el valor no cumple el CHECK de `rol` en Postgres, la excepción del
  driver de Supabase no está mapeada a ningún `DomainError` de este módulo.
- **Prioridad**: Baja.
- **Archivo**: `services/presupuestacion/usuarios/service.py:134-136` (firma).
- **Observaciones**: [IMPLEMENTADO] el hecho de que sigue sin tipar. Ver
  [`pendientes.md`](./pendientes.md) P3.

## Reglas de activar/desactivar (`cambiar_activo`)

### RN-USUARIOS-016 — **[MODIFICADA]** Solo `superadmin`/`admin`/`gerencia` pueden activar/desactivar usuarios

- **Condición**: `creador.rol not in ROLES_GESTION_USUARIOS` (`service.py:20`).
- **Resultado**: `ForbiddenError("Solo superadmin, admin o gerencia pueden activar/desactivar usuarios")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:168-169`.
- **Observaciones**: [IMPLEMENTADO]. Sin test directo del service que ejercite un rol no
  autorizado — mismo gap que RN-USUARIOS-008, ver [`pendientes.md`](./pendientes.md);
  vía HTTP lo cubre `tests/usuarios/test_router.py:295`.

### RN-USUARIOS-017 — Nadie puede activarse/desactivarse a sí mismo

- **Descripción**: sin esta regla, un `admin` podía desactivar su propia cuenta y quedar
  bloqueado por `get_current_user` (RN-USUARIOS-021) sin nadie que lo reactive.
- **Condición**: `usuario_id == creador.id`.
- **Resultado**: `ForbiddenError("No podés activar/desactivar tu propio usuario")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:171-172`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:306` (`test_no_se_puede_desactivar_el_propio_usuario`).

### RN-USUARIOS-018 — Usuario objetivo inexistente → `NotFoundError`

- **Condición**: `repo.obtener_usuario(client, usuario_id=usuario_id)` devuelve `None`.
- **Resultado**: `NotFoundError("No se encontró el usuario")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:174-176`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:344` (`test_cambiar_activo_usuario_inexistente_lanza_not_found`).

### RN-USUARIOS-019 — No se puede activar/desactivar un `superadmin` o `sistema` por esta vía

- **Condición**: `objetivo["rol"] in ("superadmin", "sistema")`.
- **Resultado**: `ForbiddenError("No se puede activar/desactivar un superadmin o sistema por esta vía")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:178-179`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:295` (`test_no_se_puede_desactivar_superadmin`) y
  `:314` (`test_no_se_puede_desactivar_usuario_sistema`).

### RN-USUARIOS-020 — **[MODIFICADA]** Un `admin` o `gerencia` solo puede activar/desactivar usuarios de su propia `drogueria_id`

- **Condición**: `creador.rol in ("admin", "gerencia") and objetivo["drogueria_id"] != creador.drogueria_id`.
- **Resultado**: `ForbiddenError("Un admin solo puede modificar usuarios de su droguería")` (admin) o `ForbiddenError("Gerencia solo puede modificar usuarios de su droguería")` (gerencia).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:183-184`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:271` (`test_admin_no_puede_desactivar_usuario_de_otra_drogueria`);
  camino positivo en `:254` (`test_admin_desactiva_usuario_de_su_drogueria`). Para
  `gerencia`: `tests/usuarios/test_router.py:216`.

### RN-USUARIOS-021 — **[MODIFICADA]** El gate real de `activo=False` está en `get_current_user`, no en `cambiar_activo`

- **Descripción**: `cambiar_activo` solo escribe la columna; el efecto de bloquear al
  usuario ocurre en `services/shared/auth.py` (reexportado por
  `services/presupuestacion/core/auth.py`). `_cargar_perfil` incluye `activo` en el
  `SELECT` de `usuarios` y, si `perfil.activo` es `False`, levanta
  `AuthenticationError("Usuario desactivado")` (401) — **aunque el JWT de Supabase del
  usuario siga vigente**. Desde login-usuario-alta-admin el chequeo vive en
  `_cargar_perfil`, compartido por `get_current_user` y por la dependencia permisiva
  `get_current_user_con_password_pendiente`, así que un usuario desactivado recibe 401
  también en `GET /usuarios/{su id}` y en `POST /auth/cambiar-password`.
- **Condición**: cualquier request autenticado de un usuario con `activo=False`.
- **Resultado**: `401 Usuario desactivado` en cualquier endpoint que dependa de
  `get_current_user`, `get_current_user_con_password_pendiente` o `require_roles`, sin
  importar la vigencia del JWT. Un usuario desactivado **sí** obtiene sesión en
  `POST /auth/login` (RN-USUARIOS-038) y recibe este 401 en el primer request siguiente.
- **Prioridad**: Alta.
- **Archivo**: `services/shared/auth.py:44-57` (`activo` en el `select`, `:47`; chequeo y
  `raise`, `:55-56`).
- **Observaciones**: [IMPLEMENTADO]. Verificado con dependencias sobreescritas en
  `tests/shared/test_auth.py:157` (`test_usuario_desactivado_sigue_recibiendo_401`) y
  `tests/auth/test_router.py:287` (`test_cambiar_password_usuario_desactivado_sigue_recibiendo_401`).
  Sigue sin haber un test de integración con un JWT real — ver
  [`pendientes.md`](./pendientes.md).

## Reglas de eliminación (`eliminar_usuario`)

Comparte exactamente el mismo alcance de autorización que `cambiar_activo`
(RN-USUARIOS-016 a 020), aplicado a un `DELETE` en vez de un `UPDATE`.

### RN-USUARIOS-022 — **[MODIFICADA]** Solo `superadmin`/`admin`/`gerencia` pueden eliminar usuarios

- **Condición**: `creador.rol not in ROLES_GESTION_USUARIOS` (`service.py:20`).
- **Resultado**: `ForbiddenError("Solo superadmin, admin o gerencia pueden eliminar usuarios")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:190-191`.
- **Observaciones**: [IMPLEMENTADO]. Sin test directo del service que ejercite un rol no
  autorizado — mismo gap que RN-USUARIOS-008/016; vía HTTP lo cubre
  `tests/usuarios/test_router.py:295`.

### RN-USUARIOS-023 — Nadie puede eliminarse a sí mismo

- **Condición**: `usuario_id == creador.id`.
- **Resultado**: `ForbiddenError("No podés eliminar tu propio usuario")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:193-194`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:384` (`test_no_se_puede_eliminar_el_propio_usuario`).

### RN-USUARIOS-024 — Usuario objetivo inexistente → `NotFoundError`

- **Condición**: `repo.obtener_usuario(client, usuario_id=usuario_id)` devuelve `None`.
- **Resultado**: `NotFoundError("No se encontró el usuario")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:196-198`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:420` (`test_eliminar_usuario_inexistente_lanza_not_found`).

### RN-USUARIOS-025 — No se puede eliminar un `superadmin` o `sistema` por esta vía

- **Condición**: `objetivo["rol"] in ("superadmin", "sistema")`.
- **Resultado**: `ForbiddenError("No se puede eliminar un superadmin o sistema por esta vía")`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:200-201`.
- **Observaciones**: [IMPLEMENTADO]. Rama `superadmin` en
  `tests/usuarios/test_service.py:390` (`test_no_se_puede_eliminar_superadmin`); rama
  `sistema` en `:336` (`test_no_se_puede_eliminar_usuario_sistema`).

### RN-USUARIOS-026 — **[MODIFICADA]** Un `admin` o `gerencia` solo puede eliminar usuarios de su propia `drogueria_id`

- **Condición**: `creador.rol in ("admin", "gerencia") and objetivo["drogueria_id"] != creador.drogueria_id`.
- **Resultado**: `ForbiddenError("Un admin solo puede eliminar usuarios de su droguería")` (admin) o `ForbiddenError("Gerencia solo puede eliminar usuarios de su droguería")` (gerencia).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:205-206`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en
  `tests/usuarios/test_service.py:398` (`test_admin_no_puede_eliminar_usuario_de_otra_drogueria`);
  camino positivo en `:375` (`test_admin_elimina_usuario_de_su_drogueria`). Para
  `gerencia`: `tests/usuarios/test_router.py:232`.

### RN-USUARIOS-027 — Eliminar un usuario con actividad asociada falla con `ConflictError` (409), no con un error crudo

- **Descripción**: `usuarios.id` referencia `auth.users.id` con `ON DELETE CASCADE`
  (`docs/schema/rls_final.sql:36`), por lo que en principio borrar el usuario de Auth
  alcanza para borrar también su fila de `usuarios`. Pero si el usuario tiene actividad
  asociada por FK sin cascada (por ejemplo `eventos.created_by`, o filas de
  `historial_cambios`), la eliminación en cascada viola esa FK y Supabase Auth devuelve
  un `AuthApiError`. `repo.eliminar_usuario_auth` atrapa **cualquier** `AuthApiError`
  (sin distinguir status, a diferencia del mapeo condicional del alta en
  RN-USUARIOS-040) y lo traduce a `ConflictError`.
- **Condición**: `client.auth.admin.delete_user(usuario_id)` lanza `AuthApiError`.
- **Resultado**: `ConflictError("No se puede eliminar: el usuario tiene actividad
  asociada (eventos, historial de cambios, etc.).")` (409).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/repository.py:86-95`.
- **Observaciones**: [IMPLEMENTADO], verificado con un test de integración real:
  `tests/usuarios/test_service.py:430`
  (`test_eliminar_usuario_con_actividad_asociada_lanza_conflict`). Ver
  [`decisiones.md`](./decisiones.md) D-USUARIOS-008.

## Reglas de alcance de `gerencia` — **[matriz de roles S7]**

### RN-USUARIOS-029 — `gerencia` solo gestiona usuarios de roles inferiores a `admin`

- **Descripción**: `gerencia` puede crear, cambiar el rol, activar/desactivar, eliminar,
  blanquear la contraseña y editar el username de usuarios, pero solo de los roles
  `gerencia`, `lider_comercial`, `comercial` y `compras` de su propia droguería
  (RN-USUARIOS-003/010/020/026/036/037). Nunca toca usuarios `admin` (ni
  `superadmin`/`sistema`, ya protegidos) ni asigna `admin`. Las reglas existentes siguen
  valiendo: nadie se modifica a sí mismo y solo `superadmin` asigna `admin`
  (RN-USUARIOS-002/015).
- **Condición**: `creador.rol == "gerencia"` y, según la operación:
  - crear: `body.rol not in ROLES_GESTIONABLES_POR_GERENCIA` (`service.py:83-84`);
  - cambiar rol / activar-desactivar / eliminar / blanquear / editar username:
    `objetivo["rol"] not in ROLES_GESTIONABLES_POR_GERENCIA`
    (`_validar_objetivo_de_gerencia`, `service.py:64-66`, invocado en `:155`, `:181`,
    `:203` y, vía `_objetivo_gestionable`, en `:235`);
  - cambiar rol: además `nuevo_rol not in ROLES_GESTIONABLES_POR_GERENCIA`
    (`service.py:156-157`).
- **Resultado**: `ForbiddenError("Gerencia solo puede crear usuarios de roles inferiores a admin")`,
  `ForbiddenError("Gerencia solo puede gestionar usuarios de roles inferiores a admin")` o
  `ForbiddenError("Gerencia solo puede asignar roles inferiores a admin")`, respectivamente.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:20-24`, `:64-66`, `:83-84`,
  `:155-157`, `:181`, `:203`, `:235`.
- **Observaciones**: [IMPLEMENTADO]. Como `Rol` solo admite los 6 roles de negocio
  (`models.py:7`) y RN-USUARIOS-002/009/015 se evalúan antes, las ramas de `:83-84` y
  `:156-157` son defensa en profundidad. Verificado vía HTTP en
  `tests/usuarios/test_router.py:161-232` (casos permitidos y rechazados de `gerencia`),
  con preservación de `admin`/`superadmin` en `:243-285`, y para blanqueo/username en
  `:436`, `:455`, `:523` y `:571`. El frontend espeja la regla: `gerencia` no ve la
  opción `admin` ni puede editar filas `admin`
  (`frontend/src/features/gestion-usuarios/GestionUsuarios.tsx:35-41`).

## Reglas de autoservicio de perfil (`actualizar_perfil_propio`)

### RN-USUARIOS-028 — Cualquier usuario autenticado edita su propio `nombre`/`apellido`, sin chequeo de rol

- **Descripción**: `actualizar_perfil_propio` no valida `creador.rol` en absoluto. La
  restricción real de "solo tu propio perfil" es que el router toma `usuario_id` del
  propio token (`usuario.id` resuelto por `get_current_user`, `router.py:105-107`), no
  de un parámetro de la URL.
- **Condición**: cualquier request autenticado a `PATCH /usuarios/me` sin cambio de
  contraseña pendiente (con cambio pendiente responde 403, RN-USUARIOS-035).
- **Resultado**: se actualizan únicamente los campos provistos en el body
  (`body.model_dump(exclude_unset=True)`, `service.py:294`).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/usuarios/service.py:288-295`,
  `services/presupuestacion/usuarios/router.py:102-107`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en `tests/usuarios/test_service.py:359`
  (`test_actualizar_perfil_propio_solo_toca_campos_provistos`) y, vía HTTP, en
  `tests/usuarios/test_router.py:603` (`test_editar_perfil_propio_sigue_funcionando`).

## Reglas de login con nombre de usuario y alta por el admin — **[NUEVAS, login-usuario-alta-admin]**

### RN-USUARIOS-030 — Alta con `username` + contraseña temporal, sin invitación por email

- **Descripción**: `UsuarioCreate` recibe `username` y `password` (temporal) en vez de
  `email` (`models.py:10-17`). `crear_usuario`, después de las validaciones
  RN-USUARIOS-001 a 006/029 y 031 a 033, genera un email interno opaco
  `f"{uuid.uuid4().hex}@{get_settings().auth_email_domain}"` (`service.py:103`) — no
  deriva del username, así que editar el username después no toca la cuenta de Auth — y
  llama a `repo.crear_usuario_auth`, que usa `client.auth.admin.create_user` con
  `email_confirm=True` y `nombre`/`apellido`/`rol` como `user_metadata`
  (`repository.py:19-26`). No se envía ningún correo. Después inserta el perfil con
  `username` normalizado y `debe_cambiar_password=True` (`service.py:113-125`).
- **Condición**: cualquier llamada exitosa a `crear_usuario`.
- **Resultado**: cuenta de Auth confirmada en el acto con la contraseña temporal; fila de
  `usuarios` con `username` y `debe_cambiar_password=True`. El admin le pasa usuario y
  contraseña temporal a la persona por fuera del sistema.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:96-125`,
  `services/presupuestacion/usuarios/repository.py:12-39`,
  `services/shared/config.py:18-21` (`auth_email_domain`, default `usuarios.local`).
- **Observaciones**: [IMPLEMENTADO]. Verificado en `tests/usuarios/test_router.py:309`
  (`test_alta_crea_cuenta_auth_con_email_interno_opaco_y_flag_pendiente`: parte local de
  32 caracteres que no contiene el username, dominio = `auth_email_domain`, flag en
  `True`) y `:421` (`test_alta_sin_password_es_rechazada`). Los tests de
  `tests/usuarios/test_service.py` que ejercitan el alta real contra Supabase son de
  integración y no se corrieron en esta rama — ver [`pendientes.md`](./pendientes.md).

### RN-USUARIOS-031 — Formato del nombre de usuario

- **Descripción**: el username se normaliza con `strip().lower()` y debe cumplir
  `[a-z0-9._-]{3,30}` (`normalizar_username`, `service.py:40-43`; patrón en `:28`, el
  mismo que el CHECK `ck_usuarios_username_formato` de `0038`). Aplica al alta, a la
  edición de username y al login.
- **Condición**: el username normalizado no cumple el patrón.
- **Resultado**: en alta y edición, `ValidationError("El nombre de usuario debe tener
  entre 3 y 30 caracteres: letras, números, punto, guion o guion bajo")` (422,
  `service.py:30-33`, `:53-57`). En el login, el error genérico de RN-USUARIOS-038 (401),
  sin revelar que el formato era inválido.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:28`, `:30-33`, `:40-43`, `:53-57`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en `tests/usuarios/test_router.py:326`
  (se guarda en minúsculas), `:336` (límites `abc`, 30 caracteres, `j.perez_2-x`), `:346`
  (rechaza `ab`, 31 caracteres, espacios, `@`, `ñ`), `:552` (edición inválida → 422) y
  `tests/auth/test_router.py:169` (login con formato inválido → error genérico).

### RN-USUARIOS-032 — Contraseña de al menos 8 caracteres

- **Descripción**: `validar_password` (`service.py:46-50`) exige
  `len(password) >= PASSWORD_LARGO_MINIMO` (8, `service.py:29`). Aplica a la contraseña
  temporal del alta, a la del blanqueo y a la nueva contraseña de
  `POST /auth/cambiar-password`.
- **Condición**: `len(password) < 8`.
- **Resultado**: `ValidationError("La contraseña debe tener al menos 8 caracteres")` (422).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:29`, `:46-50`, invocada en
  `:97`, `:254` y `services/presupuestacion/auth/service.py:51`.
- **Observaciones**: [IMPLEMENTADO]. Límites verificados en
  `tests/usuarios/test_router.py:360`/`:369` (alta, 8 acepta / 7 rechaza),
  `:503`/`:492` (blanqueo) y `tests/auth/test_router.py:237`/`:246` (cambio propio).

### RN-USUARIOS-033 — El nombre de usuario es único (sin distinguir mayúsculas)

- **Descripción**: antes de crear la cuenta de Auth, `crear_usuario` busca el username
  normalizado (`service.py:98-99`); `cambiar_username` hace lo mismo pero ignora la fila
  del propio objetivo (`service.py:275-277`). Para la carrera entre ese chequeo y el
  `INSERT`/`UPDATE`, un `APIError` con código `23505` (índice único
  `ux_usuarios_username_lower` de `0038`) también se traduce a 409
  (`_es_username_duplicado`, `service.py:60-61`, usado en `:129-130` y `:283-284`).
- **Condición**: ya existe otro usuario con el mismo username normalizado.
- **Resultado**: `ConflictError("Ya existe un usuario con ese nombre de usuario")` (409,
  `service.py:34`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:34-37`, `:60-61`, `:98-99`,
  `:126-131`, `:275-285`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en `tests/usuarios/test_router.py:381`
  (`comercial-propio` y `Comercial-Propio` → 409), `:406` (unique violation al insertar →
  409 y compensa) y `:542` (edición repetida → 409).

### RN-USUARIOS-034 — Si falla el perfil, se borra la cuenta de Auth recién creada (compensación)

- **Descripción**: el alta escribe en dos sistemas (Auth y la tabla `usuarios`) sin
  transacción común. Si `crear_perfil_usuario` lanza **cualquier** excepción después de
  que Auth ya creó la cuenta, `crear_usuario` llama a `repo.descartar_usuario_auth`
  (`delete_user`) y relanza el error original (o `ConflictError` si era un username
  duplicado).
- **Condición**: excepción en el `INSERT` del perfil (`service.py:112-131`).
- **Resultado**: no queda una cuenta de Auth huérfana. Si el propio `delete_user` falla,
  `descartar_usuario_auth` lo loguea (`logger.exception`) y no relanza
  (`repository.py:42-48`): en ese caso sí puede quedar una huérfana.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:112-131`,
  `services/presupuestacion/usuarios/repository.py:42-48`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en `tests/usuarios/test_router.py:392`
  (`test_alta_borra_la_cuenta_auth_si_falla_el_perfil`) y `:406`.

### RN-USUARIOS-035 — Cambio de contraseña forzado: `debe_cambiar_password` bloquea la API con 403

- **Descripción**: el alta (RN-USUARIOS-030) y el blanqueo (RN-USUARIOS-036) dejan
  `debe_cambiar_password=True`. Mientras esté en `True`, `get_current_user` levanta
  `ForbiddenError` (`exigir_password_al_dia`, `services/shared/auth.py:60-62`, invocado en
  `:72`) en todo endpoint autenticado — incluidos los de `require_roles`, que dependen de
  `get_current_user` (`:86-92`). Las únicas excepciones usan la dependencia permisiva
  `get_current_user_con_password_pendiente` (`services/shared/auth.py:76-83`):
  `GET /usuarios/{usuario_id}` cuando el id es el propio (`router.py:39-48`; para un id
  ajeno vuelve a aplicar `exigir_password_al_dia`, `:47-48`) y
  `POST /auth/cambiar-password` (`auth/router.py:17-21`). Los usuarios existentes antes
  de `0038` quedan con el flag en `False` (DEFAULT de la columna) y no se los obliga a
  cambiar. Sin recuperación por email: si alguien olvida la contraseña, un admin se la
  blanquea.
- **Condición**: request autenticado de un usuario con `debe_cambiar_password=True`.
- **Resultado**: `403 Debés cambiar tu contraseña antes de continuar`
  (`MENSAJE_CAMBIO_PASSWORD_PENDIENTE`, `services/shared/auth.py:25`).
- **Prioridad**: Alta.
- **Archivo**: `services/shared/auth.py:25`, `:33`, `:47`, `:60-83`,
  `services/presupuestacion/usuarios/router.py:39-52`,
  `services/presupuestacion/auth/router.py:17-23`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en `tests/shared/test_auth.py:98` (403 en
  un endpoint normal), `:105` (403 al listar usuarios), `:112` (no edita su perfil),
  `:127` (lee su propio perfil), `:136` (no lee un perfil ajeno), `:143`/`:150`
  (usuario al día no cambia), `:166` (perfil sin el campo → sin cambio pendiente) y
  `:173` (texto del mensaje). **Solo se aplica en el backend**: RLS no mira este flag —
  ver [`pendientes.md`](./pendientes.md).

### RN-USUARIOS-036 — Blanqueo de contraseña por el admin (`PATCH /usuarios/{id}/password`)

- **Descripción**: `blanquear_password` (`service.py:243-258`) pone una nueva contraseña
  temporal en Auth (`repo.actualizar_password_auth`) y deja
  `debe_cambiar_password=True`. Autorización idéntica a activar/desactivar, vía
  `_objetivo_gestionable` (`service.py:211-240`): creador en `ROLES_GESTION_USUARIOS`,
  nadie sobre sí mismo (antes de buscar al objetivo), objetivo existente,
  `superadmin`/`sistema` protegidos, `gerencia` solo sobre roles inferiores y
  `admin`/`gerencia` solo en su droguería. Después valida la contraseña (RN-USUARIOS-032).
- **Condición**: según el orden anterior.
- **Resultado**: `ForbiddenError("Solo superadmin, admin o gerencia pueden gestionar usuarios")`,
  `ForbiddenError("No podés blanquear tu propia contraseña")`,
  `NotFoundError("No se encontró el usuario")`,
  `ForbiddenError("No se puede blanquear la contraseña de un superadmin o sistema por esta vía")`,
  los de RN-USUARIOS-029/020 (`"... solo puede modificar usuarios de su droguería"`), o
  `ValidationError` de RN-USUARIOS-032. En éxito, `UsuarioOut` del objetivo con
  `debe_cambiar_password: true`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/usuarios/service.py:211-258`,
  `services/presupuestacion/usuarios/router.py:80-88`,
  `services/presupuestacion/usuarios/repository.py:51-55`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en `tests/usuarios/test_router.py:436`,
  `:455`, `:464`, `:473`, `:483`, `:492`, `:503`, `:512` y `:590` (roles sin gestión → 403).
  Nota de orden: la contraseña de Auth se cambia antes de marcar el flag; si el `UPDATE`
  del flag fallara, la contraseña ya quedó cambiada sin forzar el cambio.

### RN-USUARIOS-037 — Edición del nombre de usuario por el admin (`PATCH /usuarios/{id}/username`)

- **Descripción**: `cambiar_username` (`service.py:261-285`) usa la misma autorización que
  el blanqueo (`_objetivo_gestionable`, mensajes `"No podés cambiar tu propio nombre de
  usuario"` y `"No se puede cambiar el nombre de usuario de un superadmin o sistema por
  esta vía"`), después valida el formato (RN-USUARIOS-031) y la unicidad
  (RN-USUARIOS-033). Si el username normalizado es igual al actual, devuelve el objetivo
  sin escribir (`:278-279`). Solo toca `usuarios.username`: el email interno de Auth no
  cambia.
- **Condición / Resultado**: análogos a RN-USUARIOS-036; en éxito, `UsuarioOut` con el
  username nuevo.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/usuarios/service.py:261-285`,
  `services/presupuestacion/usuarios/router.py:91-99`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en `tests/usuarios/test_router.py:523`,
  `:533` (mismo valor no choca consigo mismo), `:542`, `:552`, `:571`, `:579` y `:590`.

### RN-USUARIOS-038 — Login con nombre de usuario (`POST /auth/login`), error genérico

- **Descripción**: `login` (`auth/service.py:18-45`) normaliza el username
  (RN-USUARIOS-031), busca la fila por username con el service client, obtiene el email
  interno de Auth con la Admin API (`auth/repository.py:9-16`) y abre la sesión con un
  cliente anon nuevo por llamada (`auth/repository.py:19-41`). Devuelve los campos de la
  sesión de Supabase (`access_token`, `refresh_token`, `expires_in`, `expires_at`,
  `token_type`, `user.id`) para `supabase.auth.setSession`. El email nunca se devuelve.
- **Condición**: username con formato inválido, inexistente, sin cuenta de Auth o
  contraseña incorrecta.
- **Resultado**: siempre `AuthenticationError("Usuario o contraseña incorrectos")` (401,
  `auth/service.py:15`), así no se pueden sondear usernames. Un usuario **desactivado**
  con credenciales correctas sí obtiene sesión y recibe el 401 `Usuario desactivado` en
  el primer request siguiente (RN-USUARIOS-021). El endpoint es público
  (`auth/router.py:11-14`).
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/auth/service.py:13-45`,
  `services/presupuestacion/auth/repository.py`, `services/presupuestacion/auth/router.py:11-14`.
- **Observaciones**: [IMPLEMENTADO]. Verificado en `tests/auth/test_router.py:128`
  (sesión), `:147` (mayúsculas), `:156` (inexistente y contraseña incorrecta dan el mismo
  error), `:169` (formato inválido), `:179` (sin cuenta de Auth), `:191` (público) y
  `tests/auth/test_repository.py:37`/`:58` (cliente anon nuevo por llamada; credenciales
  inválidas → `None`). El sign-in lo hace el backend, así que el rate limit por IP de
  Supabase Auth se comparte entre todos los usuarios — ver [`pendientes.md`](./pendientes.md).

### RN-USUARIOS-039 — Cambio de la propia contraseña (`POST /auth/cambiar-password`)

- **Descripción**: `cambiar_password` (`auth/service.py:48-62`) sirve para el cambio
  forzado y para el voluntario desde Mi cuenta. Orden: valida la nueva (RN-USUARIOS-032),
  exige que sea distinta de la actual, verifica la actual con un sign-in contra Auth y
  recién entonces actualiza la contraseña en Auth y pone `debe_cambiar_password=False`.
- **Condición / Resultado** (todos 422, `ValidationError`):
  - nueva con menos de 8 caracteres → `"La contraseña debe tener al menos 8 caracteres"`;
  - nueva igual a la actual → `"La nueva contraseña debe ser distinta de la actual"`;
  - actual incorrecta (o sin email de Auth) → `"La contraseña actual es incorrecta"`, sin
    cambiar nada.
  - En éxito, `204 No Content`.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/auth/service.py:48-62`,
  `services/presupuestacion/auth/router.py:17-23`.
- **Observaciones**: [IMPLEMENTADO]. La contraseña actual incorrecta da 422 y no 401 a
  propósito: un 401 haría que el frontend cerrara la sesión (D-USUARIOS-013). Verificado
  en `tests/auth/test_router.py:204` (con flag: cambia y limpia), `:217` (voluntario),
  `:237`, `:246`, `:256`, `:266` (actual incorrecta no cambia nada) y `:277` (requiere
  autenticación).

### RN-USUARIOS-040 — Errores de Supabase Auth en el alta: 429 → 409, resto → 422

- **Descripción**: hereda el mapeo que tenía la invitación (RN-USUARIOS-013, eliminada).
  `crear_usuario_auth` atrapa `AuthApiError` (`repository.py:27-38`): si
  `exc.status == 429`, `ConflictError("No se pudo crear la cuenta en este momento (límite
  de pedidos alcanzado). Probá de nuevo en un rato.")`; cualquier otro,
  `ValidationError(f"No se pudo crear el usuario: {exc.message}")`. Sin este catch, la
  excepción caería al 500 default de FastAPI, fuera de `CORSMiddleware` ("Failed to
  fetch" en el navegador).
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/usuarios/repository.py:27-38`.
- **Observaciones**: [IMPLEMENTADO]. Sin test automatizado de las ramas 429/otros — ver
  [`pendientes.md`](./pendientes.md).

### RN-USUARIOS-041 — Backfill de `username` para los usuarios existentes (migración `0038`)

- **Descripción**: `0038` agrega `usuarios.username` y lo completa para cada fila con
  `username IS NULL`, en orden `created_at, id`: parte local de `auth.users.email` en
  minúsculas, sin caracteres fuera de `a-z 0-9 . _ -`, recortada a 27; si queda vacía,
  `usuario`; si queda con 1-2 caracteres, se completa con `0`; si choca, sufijo numérico
  desde 2 (`jperez`, `jperez2`, ...). Los existentes conservan su contraseña y su email
  interno, con `debe_cambiar_password=FALSE`.
- **Prioridad**: Alta.
- **Archivo**: `supabase/migrations/0038_usuarios_username.sql:33-65`.
- **Observaciones**: [IMPLEMENTADO] en SQL, **no aplicada a ninguna base todavía** — ver
  [`base_de_datos.md`](./base_de_datos.md) y [`pendientes.md`](./pendientes.md).
