# Módulo Usuarios — `services/presupuestacion/usuarios/`

## Qué es

Usuarios gestiona el ciclo de vida completo de una cuenta de la aplicación — alta por
invitación de email, cambio de rol, activación/desactivación, edición de perfil propio y
eliminación — sobre la tabla `usuarios` de Supabase. Es el módulo dueño de esa tabla en
el sentido de negocio (modelo, roles válidos, reglas de creación y de cambio de rol);
Core solo la lee de forma acotada para resolver el perfil del solicitante autenticado —
ver [`../core/base_de_datos.md`](../core/base_de_datos.md#usuarios).

El módulo creció sustancialmente desde la revisión anterior: 4 archivos, 335 líneas en
total (`models.py` 36, `repository.py` 66, `service.py` 150, `router.py` 83 —
verificado con `wc -l` en esta sesión, antes 161 líneas y 4 endpoints), 7 endpoints,
sin máquina de estados propia.

## Qué NO hace

- **No gestiona usuarios de sistema desde el alta.** Todo usuario creado por este módulo
  tiene `es_sistema=False` hardcodeado (`service.py:47`); no hay ninguna vía en esta API
  para crear un usuario con `es_sistema=True` ni con `rol="sistema"` (la BD lo permite vía
  CHECK, pero el `Literal Rol` de Python no lo incluye — ver
  [`decisiones.md`](./decisiones.md) D-USUARIOS-004). Sí protege explícitamente a
  `rol="sistema"` de ser tocado por `cambiar_rol`, `cambiar_activo` y `eliminar_usuario`
  — ver D-USUARIOS-006.
- **No tiene `estados.md`.** El campo `activo` ahora sí está implementado como toggle
  binario (`PATCH /usuarios/{id}/activo`), pero no como una máquina de estados con
  transiciones o reglas más allá de activo/inactivo — se sigue omitiendo este documento
  del set, igual que se hizo en el módulo Core.
- **No genera ni comunica contraseñas.** El alta es por invitación de email — el propio
  usuario define su contraseña al aceptar la invitación en `{frontend_url}/accept-invite`
  (RN-USUARIOS-013); ningún endpoint de este módulo recibe ni devuelve un password.

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `usuarios/__init__.py` | Vacío. |
| `usuarios/models.py` | `Rol` (Literal de 6 roles), `UsuarioCreate` (con `apellido` obligatorio, sin `password`), `UsuarioRolUpdate`, `UsuarioActivoUpdate`, `UsuarioPerfilUpdate`, `UsuarioOut`. |
| `usuarios/repository.py` | Acceso a datos puro más mapeo de errores de Supabase Auth a excepciones de dominio: invitación por email, insert/select/update/delete sobre `usuarios`. |
| `usuarios/service.py` | Reglas de negocio de las 5 operaciones (`crear_usuario`, `cambiar_rol`, `cambiar_activo`, `eliminar_usuario`, `actualizar_perfil_propio`) más sus wrappers HTTP (`*_para_endpoint`). |
| `usuarios/router.py` | 7 endpoints. Los 2 GET consultan la tabla directo con RLS; POST, los 2 PATCH de rol/activo y el DELETE delegan en `service.py` con `require_roles`; `PATCH /me` delega en `service.py` sin chequeo de rol (autoservicio). |

## Quién lo consume

Los endpoints se montan en `services/presupuestacion/main.py:54`
(`app.include_router(usuarios_router, tags=["usuarios"])`), sin prefijo adicional.
**A diferencia de la revisión anterior**, este ya no es un módulo sin consumidor real: el
frontend usa activamente esta API para la gestión de usuarios (alta por invitación,
roles, activación, "Mi cuenta", eliminación) — ver
[`casos_de_uso.md`](./casos_de_uso.md) "Consumidores reales". Dentro del backend de
`presupuestacion/` sigue sin haber ningún `service.py` de otro módulo que importe de
`usuarios/`.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias hacia Core, asimetría de capas
  entre GET y POST/PATCH, diagrama del flujo de autorización.
- [`base_de_datos.md`](./base_de_datos.md) — tabla `usuarios`, qué toca y qué no toca
  este módulo, policy RLS relevante.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-USUARIOS-NNN).
- [`flujo.md`](./flujo.md) — los 6 flujos principales paso a paso.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 7 endpoints y quién puede invocarlos.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-USUARIOS-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P2/P3.

Para `UsuarioPerfil`, `get_current_user`, `require_roles` y el patrón
`service_client`/`user_client` que este módulo consume intensivamente, ver
[`../core/`](../core/) — no se repite esa documentación acá.
