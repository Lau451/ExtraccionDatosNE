# Specification: Login mínimo en frontend/

## Archivos

| Archivo | Responsabilidad |
|---|---|
| `frontend/src/lib/supabase.ts` | Cliente singleton de `supabase-js`. Uso exclusivo: `signIn`/`signOut`/`getSession`. |
| `frontend/src/lib/api/presupuestacion.ts` | Fetch wrapper para `services/presupuestacion` (puerto 8001). Inyecta `Authorization: Bearer <access_token>` leyendo la sesión en cada llamada. Error shape `{detail}` (FastAPI), distinto del `{error}` de `extraccionFetch`. |
| `frontend/src/features/auth/AuthContext.tsx` | Contexto React: sesión, perfil (rol, drogueria_id, nombre, activo), `signIn`/`signOut`. |
| `frontend/src/features/auth/LoginForm.tsx` | Formulario email/password. |
| `frontend/src/features/auth/routeGuards.ts` | `requireAuth` (en uso) y `requireRole(...roles)` (armado, sin call site). |
| `frontend/src/routes/login.tsx` | Ruta pública, soporta `?redirect=`. |
| `frontend/src/routes/_authenticated.tsx` | Layout pathless con `beforeLoad: requireAuth`. Acá vive el `Sidebar`. |
| `frontend/src/routes/_authenticated.index.tsx` | Reemplaza al viejo `routes/index.tsx`. |
| `frontend/src/routes/__root.tsx` | `createRootRouteWithContext<{ auth }>()`. |
| `frontend/src/main.tsx` | `InnerApp` llama `useAuth()` y pasa `context={{ auth }}` al `RouterProvider`. |
| `frontend/src/features/shell/Sidebar.tsx` | Footer muestra `perfil.nombre` real + botón "Cerrar sesión" (reemplaza el placeholder "Sesión sin autenticación"). |
| `frontend/.env` (gitignored) | `VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_PRESUPUESTACION_API_URL=http://localhost:8001`. |

## Resolución de rol

El JWT de Supabase NO trae `rol` como claim. El frontend llama `GET /usuarios/{session.user.id}`
contra `services/presupuestacion` (endpoint preexistente, protegido solo con `get_current_user` —
cualquier autenticado, sin `require_roles` específico) para traer
`{rol, drogueria_id, nombre, activo}`. Mismo patrón que usa el propio backend en
`core/auth.py:get_current_user`.

## Scenarios

### Scenario: acceso sin sesión a ruta protegida
```
Given: no hay sesión activa
When: el usuario navega a "/"
Then: el guard `beforeLoad` de _authenticated.tsx redirige a "/login?redirect=%2F"
```

### Scenario: login exitoso
```
Given: el usuario ingresa email/password válidos en LoginForm
When: se envía el formulario
Then: supabase-js autentica y persiste la sesión
  AND redirige a la ruta original (?redirect=) o a "/"
  AND GET /usuarios/{id} devuelve 200 con el JWT inyectado
  AND el Sidebar muestra perfil.nombre real
```

### Scenario: persistencia de sesión
```
Given: hay una sesión activa
When: se recarga la página
Then: la sesión persiste (comportamiento default de supabase-js, sin código adicional)
```

### Scenario: logout
```
Given: hay una sesión activa
When: el usuario hace click en "Cerrar sesión"
Then: signOut() limpia la sesión
  AND redirige a "/login"
```

### Scenario: llamada a services/presupuestacion sin backend
No aplica bypass: TODAS las llamadas a `presupuestacionFetch` requieren JWT real. No existe modo
de desarrollo sin auth para este backend (a diferencia de `services/extraccion`, que sí tiene un
bypass opcional documentado como excepción puntual por tener HTML legacy en producción).

## Verificación (no solo compiló — se ejercitó en Chrome real)

Verificado end-to-end el 2026-07-15 con `services/extraccion` (:8000) y `services/presupuestacion`
(:8001) corriendo: guard redirige sin sesión → login con usuario real → `GET /usuarios/{id}` 200 →
Sidebar con nombre real → sesión persiste tras reload → logout limpia y redirige. Usuario de
prueba creado vía Admin API (`SUPABASE_SERVICE_KEY`, autorización explícita del usuario) y borrado
después de la prueba — no quedó basura en la BD.

---

## Actualización 2026-07-23 — invitación, reset, accept-invite, mi cuenta

### Archivos nuevos/modificados

| Archivo | Responsabilidad |
|---|---|
| `frontend/src/routes/reset-password.tsx` | Ruta pública. Sin sesión: `SolicitarResetForm` (email → `supabase.auth.resetPasswordForEmail`). Con sesión temporal (link ya abierto): `SetPasswordForm`. |
| `frontend/src/routes/accept-invite.tsx` | Ruta pública. Con sesión temporal: `SetPasswordForm` (activa la cuenta). Sin sesión temporal (link inválido/expirado): mensaje de error, sin formulario. |
| `frontend/src/features/auth/useSessionFromLink.ts` | Hook compartido por ambas rutas: detecta si el link de Supabase (recovery o invite) dejó una sesión temporal activa. Expone `{checking, hasSession}`. |
| `frontend/src/features/auth/SetPasswordForm.tsx` | Formulario compartido (`password`/`confirmación` con validación de igualdad) usado por `reset-password` y `accept-invite`; `title`/`submitLabel` parametrizables. |
| `frontend/src/routes/_authenticated.mi-cuenta.tsx` | Ruta protegida, sin `requireRole` propio (hereda `requireAuth` de `_authenticated.tsx`) — cualquier autenticado accede a su propia cuenta. |
| `frontend/src/features/mi-cuenta/MiCuenta.tsx` | 3 formularios: `EditarNombreForm` (`PATCH /usuarios/me`), `CambiarPasswordForm` (`supabase.auth.updateUser({password})`, sin `signOut()` posterior), `CambiarEmailForm` (`supabase.auth.updateUser({email})`, doble confirmación nativa de Supabase). Botón "Cerrar sesión" explícito. |
| `frontend/src/lib/api/usuarios.ts` | `invitarUsuario`, `actualizarPerfilPropio`, `cambiarRolUsuario`, `cambiarActivoUsuario`, `eliminarUsuario` — consumidos por `gestion-usuarios/` y `gestion-empresas/`, no por este módulo directamente salvo `actualizarPerfilPropio`. |
| `services/presupuestacion/usuarios/service.py`, `repository.py`, `models.py`, `router.py` | `crear_usuario` pasa a invitar por email (`invite_user_by_email`); nuevos `cambiar_activo`, `eliminar_usuario`, `actualizar_perfil_propio`. Contrato completo en `docs/modulos/usuarios/api.md`. |

### Resolución de rol y de perfil — timing corregido

`AuthContext.tsx` expone `perfilLoading` además de `loading`; `main.tsx` (`InnerApp`) espera
`auth.loading || auth.perfilLoading` antes de montar `<RouterProvider>` (D-LOGIN-005). El redirect
post-login usa `window.location.href` (hard navigation), no `router.navigate()` (D-LOGIN-007). Un
401/404 al resolver el perfil dispara `signOut()` automático, y `_authenticated.tsx` tiene un
`useEffect` reactivo que redirige a `/login` si `isAuthenticated` pasa a `false` con la pantalla ya
montada (D-LOGIN-006). Detalle completo de las 3 causas raíz en
`docs/modulos/frontend_login/decisiones.md`.

### Scenarios

#### Scenario: alta de usuario por invitación (no por password directa)
```
Given: un admin/superadmin invita un usuario nuevo desde "Gestión de usuarios"
When: POST /usuarios con {email, nombre, apellido, rol, drogueria_id?} (sin password)
Then: se crea la cuenta en auth.users vía invite_user_by_email, sin contraseña asignada por el
  backend
  AND Supabase envía un email de invitación con redirect_to = {frontend_url}/accept-invite
  AND recién entonces se inserta la fila de perfil en `usuarios`
```

#### Scenario: aceptar invitación con link válido
```
Given: el usuario recién invitado abre el link de invitación recibido por email
When: navega a /accept-invite
Then: useSessionFromLink detecta la sesión temporal dejada por el link (hasSession=true)
  AND se muestra SetPasswordForm ("Creá tu contraseña para activar tu cuenta")
  AND al definir la contraseña, la cuenta queda activa y utilizable
```

#### Scenario: link de invitación inválido o expirado
```
Given: el link de invitación ya fue usado, o expiró
When: el usuario navega a /accept-invite
Then: useSessionFromLink no encuentra sesión temporal (hasSession=false)
  AND se muestra el mensaje "Este link de invitación no es válido o ya expiró..." sin formulario
```

#### Scenario: recuperación de contraseña — solicitud
```
Given: un usuario con cuenta activa olvidó su contraseña
When: en /reset-password, sin sesión, ingresa su email y confirma
Then: supabase.auth.resetPasswordForEmail(email, {redirectTo: origin + "/reset-password"})
  AND se muestra "Si el email existe en el sistema, te enviamos un link..." (mismo mensaje exista
  o no la cuenta, sin filtrar existencia de emails)
```

#### Scenario: recuperación de contraseña — definir nueva
```
Given: el usuario abrió el link de recuperación recibido por email
When: navega a /reset-password
Then: useSessionFromLink detecta la sesión temporal (hasSession=true)
  AND se muestra SetPasswordForm ("Elegí tu nueva contraseña")
  AND al confirmar, la contraseña queda actualizada
```

#### Scenario: mi cuenta — editar nombre/apellido
```
Given: un usuario autenticado en /mi-cuenta
When: edita nombre y/o apellido y confirma EditarNombreForm
Then: PATCH /usuarios/me con solo los campos provistos
  AND refrescarPerfil() actualiza el perfil en memoria (AuthContext) sin recargar la página
  AND el Sidebar refleja el nombre nuevo sin reload
```

#### Scenario: mi cuenta — cambiar contraseña sin perder la sesión
```
Given: un usuario autenticado en /mi-cuenta
When: completa CambiarPasswordForm con password === confirmación y confirma
Then: supabase.auth.updateUser({password}) resuelve OK
  AND, a diferencia de SetPasswordForm (accept-invite/reset-password), NO se hace signOut()
  AND el usuario sigue logueado con la sesión actual
```

#### Scenario: mi cuenta — cambiar email requiere doble confirmación
```
Given: un usuario autenticado en /mi-cuenta
When: ingresa un email nuevo en CambiarEmailForm y confirma
Then: supabase.auth.updateUser({email}) dispara el flujo nativo de Supabase (confirmar desde el
  email actual y desde el nuevo)
  AND el cambio NO se aplica de inmediato
  AND la UI solo confirma que el mail de verificación se envió, sin reflejar el email nuevo hasta
  completar la doble confirmación
```

#### Scenario: reload directo (deep-link) a una ruta con requireRole no rebota incorrectamente
```
Given: un usuario con rol "superadmin" ya autenticado recarga directamente /superadmin/empresas
When: main.tsx monta la app
Then: InnerApp espera auth.loading Y auth.perfilLoading antes de montar <RouterProvider>
  AND requireRole('superadmin') evalúa beforeLoad con perfil ya resuelto (no null)
  AND el usuario permanece en /superadmin/empresas, sin rebote a "/" (bug real corregido,
  D-LOGIN-005)
```

#### Scenario: redirect post-login a una ruta con requireRole aterriza en el destino pedido
```
Given: un usuario navega sin sesión a /superadmin/empresas y es redirigido a
  /login?redirect=%2Fsuperadmin%2Fempresas
When: se loguea con credenciales de un superadmin
Then: irA(destino) hace window.location.href = destino (hard navigation), no
  router.navigate(...)
  AND la app se remonta desde cero con el context ya resuelto
  AND el usuario aterriza en /superadmin/empresas, no en "/" (bug real corregido, D-LOGIN-007)
```

#### Scenario: usuario desactivado o borrado queda deslogueado, no en "Cargando…" infinito
```
Given: un usuario con sesión de Supabase técnicamente vigente, pero desactivado (activo=false) o
  borrado del lado del backend
When: AuthContext intenta resolver su perfil vía GET /usuarios/{id}
Then: el backend responde 401 (desactivado) o 404 (borrado)
  AND AuthContext llama a supabase.auth.signOut() automáticamente
  AND el useEffect reactivo de _authenticated.tsx redirige a /login (bug real corregido,
  D-LOGIN-006), en vez de quedar mostrando "Cargando…" indefinidamente
```

### Verificación (actualización 2026-07-23)

Tests de backend (`tests/usuarios/test_service.py`) en verde para `crear_usuario` (invitación),
`cambiar_rol`, `cambiar_activo`, `eliminar_usuario`, `actualizar_perfil_propio` — incluye el caso
de eliminación con actividad asociada (`ConflictError`, verificado contra FK real). Los 3 bugs de
timing (D-LOGIN-005/006/007) fueron reproducidos y corregidos en vivo con Chrome real y un
superadmin real: reload directo a ruta protegida, login→redirect a ruta protegida, y
desactivación/borrado con sesión de Supabase aún vigente. El mapeo de errores 429/otros de la
invitación por email fue verificado manualmente contra Supabase Auth real (rate limit real y un
email inválido), sin test automatizado que lo cubra.
