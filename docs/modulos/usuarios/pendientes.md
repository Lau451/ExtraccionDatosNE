# Pendientes — Auditoría técnica de Usuarios

Clasificación P2 (deuda técnica relevante) / P3 (menor), reverificada contra el código y
los tests reales en esta sesión de actualización. No se identificó ningún hallazgo de
prioridad P1 en este módulo. Los puntos 1, 2 y 4 de P2 son de la revisión anterior
(releídos y confirmados sin cambios); el punto 3 se actualizó (corrección de un dato
desactualizado); el resto son nuevos de esta sesión.

## P2 — Deuda técnica relevante

1. **Los 2 endpoints GET no exigen rol ni filtran `drogueria_id` en Python, a diferencia
   de POST/PATCH/DELETE.** `GET /usuarios` y `GET /usuarios/{usuario_id}` solo declaran
   `Depends(get_current_user)` (`router.py:27`, `:36`), sin `require_roles` ni un filtro
   `.eq("drogueria_id", ...)` explícito — mientras que POST, los 2 PATCH de rol/activo y
   el DELETE sí exigen `require_roles("superadmin", "admin")` (`router.py:47`, `:56`,
   `:65`, `:81`). `PATCH /usuarios/me` es la única excepción deliberada (autoservicio del
   propio perfil, RN-USUARIOS-028). [IMPLEMENTADO] el hecho, sin cambios respecto de la
   revisión anterior.

2. **El aislamiento por tenant de los GET depende enteramente de una policy de RLS que
   no está verificada por ningún test de este repositorio.** Sin cambios respecto de la
   revisión anterior: la policy `usuarios_sel` (`docs/schema/rls_final.sql:117`) es en
   principio correcta por lectura textual, pero:
   - **Las políticas de RLS de `usuarios` siguen sin estar en migraciones versionadas**
     (a diferencia de la columna `apellido` — ver punto 3 más abajo, que sí llegó por
     migración real en esta sesión). La `CREATE TABLE usuarios` y sus 4 policies viven
     únicamente en `docs/schema/rls_final.sql`, snapshot manual sin historial de cambios
     (`docs/schema/README.md:3-7`).
   - **Ningún test la ejercita con un JWT real.** `tests/usuarios/` sigue sin usar el
     fixture `crear_usuario_autenticado` de `tests/conftest.py:146-186` (confirmado por
     grep). Todos los tests de `tests/usuarios/test_service.py` ejercitan las funciones
     de `service.py` directamente con `service_client`, que bypasea RLS por completo.
   - [RECOMENDACIÓN], sin cambios: agregar un test de integración en `tests/usuarios/`
     que use `crear_usuario_autenticado` para confirmar empíricamente el aislamiento
     cross-tenant de `GET /usuarios`.

3. **[ACTUALIZADO] Corrección de un dato de la revisión anterior**: ya no es cierto que
   "ningún archivo de `supabase/migrations/` menciona la tabla `usuarios`". La migración
   `supabase/migrations/0007_apellido_y_planes.sql:19-20` sí la toca —
   `ALTER TABLE usuarios ADD COLUMN IF NOT EXISTS apellido TEXT`. Sigue siendo cierto,
   sin embargo, que la **definición completa** de la tabla (`CREATE TABLE usuarios` con
   sus constraints) y sus **policies de RLS** no están en ninguna migración — solo en el
   snapshot manual `docs/schema/rls_final.sql` (ver punto 2). Es decir: el estado actual
   es mixto — la columna `apellido` sí tiene historial de cambios versionado, el resto de
   la tabla y toda su RLS no.

4. **Inconsistencia de capas: los GET bypasean `repository.py`/`service.py`.** Sin
   cambios respecto de la revisión anterior: `listar_usuarios_endpoint` y
   `obtener_usuario_endpoint` construyen sus propias queries directo en `router.py`
   (`:30`, `:39`), sin reutilizar `repo.obtener_usuario` (`repository.py:40-42`), aunque
   con un cliente distinto (`user_client` en el router vs el `client` genérico de
   `repository.py`). [IMPLEMENTADO].

5. **[NUEVO] Gap de tests: ningún test dispara "rol no autorizado" para
   `cambiar_rol`/`cambiar_activo`/`eliminar_usuario`.** `crear_usuario` sí tiene
   `test_rol_no_autorizado_no_puede_crear_usuario`
   (`tests/usuarios/test_service.py:128-132`, cubre RN-USUARIOS-001), pero no existe el
   equivalente para RN-USUARIOS-008 (`cambiar_rol`), RN-USUARIOS-016 (`cambiar_activo`)
   ni RN-USUARIOS-022 (`eliminar_usuario`) — confirmado por grep en
   `tests/usuarios/test_service.py`. [IMPLEMENTADO] el hecho de la ausencia; ya estaba
   señalado parcialmente para RN-USUARIOS-008 en la revisión anterior, y se confirma que
   sigue así más el mismo gap en las 2 funciones nuevas.

6. **[NUEVO] Gap de tests: la protección de `sistema` en `cambiar_rol` y
   `eliminar_usuario` no tiene test dedicado.** El fixture `seed_usuario_sistema`
   (`tests/conftest.py:126-142`) solo se usa en
   `test_no_se_puede_desactivar_usuario_sistema`
   (`tests/usuarios/test_service.py:313-320`, cubre RN-USUARIOS-019 de
   `cambiar_activo`). No hay un test análogo que confirme que `cambiar_rol` (RN-USUARIOS-009,
   extendida a `sistema` en esta sesión) ni `eliminar_usuario` (RN-USUARIOS-025) rechazan
   tocar a `rol="sistema"` — ambas ramas están implementadas en el código (mismo patrón
   `objetivo["rol"] in (..., "sistema")`), pero solo la de `cambiar_activo` está
   verificada empíricamente. [RECOMENDACIÓN]: agregar
   `test_cambiar_rol_no_permite_usuario_sistema` y
   `test_no_se_puede_eliminar_usuario_sistema`, siguiendo el mismo patrón que el test
   existente de `cambiar_activo`.

7. **[NUEVO] El mapeo de errores 429/otros de `invitar_usuario_auth` (RN-USUARIOS-013)
   solo está verificado manualmente, no con un test automatizado.** El catch de
   `AuthApiError` en `repository.py:20-32` fue confirmado funcionando por el usuario en
   esta misma sesión, contra Supabase Auth real (rate limit 429 y un email inválido 400),
   pero no hay ningún test en `tests/usuarios/` que simule o fuerce esas condiciones y
   assert sobre `ConflictError`/`ValidationError`. Forzar un 429 real en un test
   automatizado es intrínsecamente frágil (depende de agotar un rate limit externo);
   [RECOMENDACIÓN]: si se quiere cobertura automatizada, mockear `client.auth.admin`
   para simular ambos códigos de status en vez de depender de Supabase Auth real.

8. **[NUEVO] No hay test de integración HTTP que confirme el efecto de `activo=False`
   sobre `get_current_user` (RN-USUARIOS-021).** Los tests de `cambiar_activo` verifican
   únicamente que la columna `activo` cambia de valor; ninguno hace un request real
   autenticado con un usuario desactivado contra `get_current_user`
   (`core/auth.py:33-49`) para confirmar el `401 Usuario desactivado`. El comportamiento
   está implementado y se infiere correcto por lectura directa del código
   (`core/auth.py:47-48`), pero no está verificado end-to-end con un test.
   [RECOMENDACIÓN]: agregar un test en `tests/core/` (o `tests/usuarios/`) que use
   `crear_usuario_autenticado`, desactive al usuario con `cambiar_activo` y confirme que
   un request posterior con el mismo JWT recibe 401.

## P3 — Menor

1. **`cambiar_rol(nuevo_rol: str)` sin tipar contra `Rol` (RN-USUARIOS-012).** Sin
   cambios respecto de la revisión anterior. [SUPOSICIÓN, no verificado end-to-end en
   esta sesión]: es razonable esperar que una excepción del driver de Supabase por
   violar el CHECK de la base no esté mapeada a ningún `DomainError` de
   `core/exceptions.py`, y por lo tanto caiga al status `500` genérico — pero esto sigue
   sin haberse ejercitado ni confirmado con una llamada real.

2. **Discrepancia entre `Rol` (Python) y el CHECK `rol` (BD) sin motivo documentado.**
   Ver [`decisiones.md`](./decisiones.md) D-USUARIOS-004, sin cambios. La BD acepta
   `"sistema"`, el `Literal Rol` de `models.py:5` no.

3. **[NUEVO] `eliminar_usuario_auth` mapea cualquier `AuthApiError` a `ConflictError`
   (RN-USUARIOS-027), sin distinguir causa.** Ver [`decisiones.md`](./decisiones.md)
   D-USUARIOS-008. Un error de Auth no relacionado con FKs (por ejemplo, un problema de
   red o de configuración del proyecto Supabase) se reportaría igualmente como "el
   usuario tiene actividad asociada", con un mensaje potencialmente engañoso. Impacto
   bajo: en la práctica, la causa realista de que `delete_user` falle en este flujo es la
   FK sin cascada verificada empíricamente en esta sesión.

4. **[NUEVO] `apellido` es nullable a nivel de base de datos pero obligatorio en
   `UsuarioCreate`.** La migración `0007_apellido_y_planes.sql:20-23` agrega la columna
   como `TEXT` nullable, explícitamente porque "usuarios creados antes de esta migración
   no tienen valor de backfill posible" (comentario de la propia migración). Esto es
   coherente con `UsuarioOut.apellido: str | None` (nullable en la respuesta, para no
   romper la serialización de usuarios preexistentes sin apellido), pero implica que
   todo usuario nuevo creado por esta API sí lo tendrá, mientras que usuarios anteriores
   a la migración pueden seguir con `apellido=None` indefinidamente si nadie completa su
   perfil vía `PATCH /usuarios/me`. No es un bug — es el comportamiento esperado de un
   backfill imposible — pero no hay ningún mecanismo (ni pendiente documentado antes de
   esta sesión) que fuerce a esos usuarios a completar el campo.
