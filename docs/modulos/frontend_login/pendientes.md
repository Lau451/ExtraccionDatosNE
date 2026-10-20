# Pendientes — Auditoría técnica de Login

Clasificación P1 (crítico/bloqueante) / P2 (deuda técnica relevante) / P3 (menor), verificada
contra el código real en esta sesión.

**[RETIRADO] SMTP propio para Supabase Auth**: ya no aplica. Desde
odd/tasks/login-usuario-alta-admin.md el frontend no usa `invite_user_by_email` ni
`resetPasswordForEmail`; no se envía ningún email de Auth.

**Abiertos del login con nombre de usuario** (detalle en
[`../usuarios/pendientes.md`](../usuarios/pendientes.md) P1):

- `routeTree.gen.ts` se editó a mano (`@tanstack/router-generator` 1.167.19 vs plugin 1.167.38):
  se agregó `/cambiar-password` y se quitaron `/reset-password` y `/accept-invite`. Revisar el diff
  cuando el plugin lo regenere.
- El guard de `debe_cambiar_password` (RN-LOGIN-011) es UX: la garantía es el 403 del backend. Por
  PostgREST directo, desde `0039` el usuario ya no puede limpiar el flag (RN-USUARIOS-042) y, con
  `0041` aplicada, tampoco leer nada salvo su propia fila de `usuarios` (RN-USUARIOS-048).
  **`0041` está escrita pero no aplicada** (ver [`../usuarios/pendientes.md`](../usuarios/pendientes.md)
  P1-3): hasta aplicarla, la lectura sigue abierta.
- El login depende de las migraciones `0038`, `0039` y `0040` (aplicadas) y del backend desplegado
  (orden: `0038`, `0039`, `0040`, backend). `0041` no es requisito del login.
- ~~Un 429 de Supabase Auth en el login se ve como "Usuario o contraseña incorrectos".~~
  **Resuelto** (commits `2b4bf79` y `0c8052c`): el backend responde 429 y el login y el cambio de
  contraseña muestran su mensaje (RN-LOGIN-013). El límite por IP compartido sigue existiendo.
- ~~Supabase Auth caído (502-504, 429 no JSON, 500 JSON) salía como 500 o como "Usuario o
  contraseña incorrectos".~~ **Resuelto** (commit `34bcc44`): el backend responde 503 (o 429) igual
  para todo username (RN-LOGIN-014, RN-USUARIOS-047). El login muestra su texto genérico de
  reintento, no el `detail` del 503.

## P1 — Crítico

1. ~~No hay ningún test de frontend en todo el repositorio, incluido este módulo.~~ **Resuelto**:
   se agregó `vitest` + `@testing-library/react` + `@testing-library/jest-dom` + `jsdom`
   (`frontend/vitest.config.ts`, `frontend/src/test/setup.ts`, script `npm run test`). Cobertura
   nueva: `routeGuards.test.ts` (`requireAuth`, `requireRole` con `perfil: null` — el caso exacto
   de D-LOGIN-005/007 — y con rol no permitido/permitido), `AuthContext.test.tsx` (secuencia
   `loading`→`perfilLoading`, `signOut` automático en 401 y en 404, ausencia de `signOut` en otros
   errores, `refrescarPerfil`), `LoginForm.test.tsx` y `SetPasswordForm.test.tsx` (éxito, error,
   validaciones). 16 tests, todos en verde en esa revisión. Con login-usuario-alta-admin se
   eliminó `SetPasswordForm.test.tsx` y se agregaron `CambiarPasswordPage.test.tsx`,
   `cambiarPasswordRoute.test.ts`, `lib/api/auth.test.ts` y `MiCuenta.test.tsx` (suite completa
   `vitest run`: 66 archivos / 644 tests en verde según odd/tasks/login-usuario-alta-admin.md T4). No se
   agregaron tests de `login.tsx` — son integración de TanStack Router sobre piezas ya cubiertas; queda como
   posible ampliación futura, no como pendiente crítico.

## P2 — Deuda técnica relevante

1. ~~`requireRole` ahora tiene call sites reales, pero sigue sin ningún test.~~ **Resuelto**: ver
   `routeGuards.test.ts` (ítem 1 de P1 arriba) — cubre `perfil: null`, rol no permitido y rol
   permitido.

2. ~~`Rol` está duplicado entre frontend y backend sin mecanismo de sincronización.~~ **Resuelto
   parcialmente**: se agregó un comentario cruzado en `AuthContext.tsx:6` apuntando a
   `usuarios/models.py:5` (backend) y viceversa, para que un cambio en una lista recuerde revisar
   la otra. Sigue sin haber generación de tipos ni test de contrato automático entre ambos
   proyectos — si eso se necesita en el futuro, es trabajo aparte.

3. ~~No hay recuperación de contraseña ni registro de usuarios en el frontend.~~ **Resuelto en esta
   sesión**: la recuperación de contraseña está implementada (`/reset-password`, ver
   [`decisiones.md`](./decisiones.md) D-LOGIN-004, ahora marcada como superada, y
   [`flujo.md`](./flujo.md) #5). El registro libre (auto-signup) sigue sin existir, pero por
   diseño: el alta la hace un admin/superadmin vía invitación (`/accept-invite`), no un
   autoservicio de "crear cuenta" — ver [`flujo.md`](./flujo.md) #6. Se retira como pendiente.
   **Nota posterior**: con login-usuario-alta-admin se eliminaron `/reset-password` y
   `/accept-invite` a propósito (D-LOGIN-008): la recuperación es un blanqueo por el admin y el
   alta es con username + contraseña temporal. No es una regresión.

4. ~~`SetPasswordForm` no valida fuerza de contraseña más allá de `minLength=8`.~~ **Resuelto**: se
   agregó una validación mínima (al menos una letra y un número, además del `minLength=8` ya
   existente) en `SetPasswordForm.tsx`, cubierta por test. [SUPOSICIÓN, no verificada]: sigue sin
   confirmarse si Supabase Auth aplica alguna política de contraseña propia del lado del servidor
   — no se investigó en esta sesión, no era necesario para cerrar este ítem.
   **Nota posterior**: `SetPasswordForm` se eliminó. `CambiarPasswordForm` exige solo mínimo 8 y
   distinta de la actual (RN-LOGIN-012, decisión L3 del usuario), sin la regla de letra + número.

## P3 — Menor

1. **No hay manejo explícito de expiración/refresh de sesión en el código del módulo.** No se
   encontró, en los archivos leídos en esta sesión, ninguna llamada explícita a
   `supabase.auth.refreshSession()` ni ningún manejo específico del evento `TOKEN_REFRESHED` de
   `onAuthStateChange` (el handler de `AuthContext.tsx:49-53` trata todos los eventos por igual,
   simplemente actualizando `session` con lo que reciba). [SUPOSICIÓN, no verificado en esta
   sesión]: es razonable esperar que `supabase-js` maneje el refresh de tokens automáticamente por
   detrás (comportamiento por defecto del SDK) y que `onAuthStateChange` reciba la sesión renovada
   sin que el código de este módulo tenga que hacer nada explícito — pero esto no fue confirmado
   leyendo la implementación interna de `supabase-js` ni ejercitado en runtime en esta sesión.
   Tampoco hay ningún manejo visible de lo que pasa si el refresh falla (por ejemplo, sesión
   revocada del lado del servidor) más allá de que `onAuthStateChange` eventualmente entregaría
   `session: null`, y ahora sí hay dos mecanismos que reaccionan a eso: el `useEffect` reactivo de
   `_authenticated.tsx:17-29` (redirect inmediato si la pantalla ya está montada) y `requireAuth`
   en el próximo `beforeLoad`. Esto reduce, pero no elimina, el riesgo original de este ítem.

2. ~~`LoginForm` no distingue el motivo real de un error de login (RN-LOGIN-003).~~ **Resuelto**:
   se agregó `console.error` con el error original (sin cambiar el mensaje genérico mostrado al
   usuario) en `LoginForm.tsx`, `SetPasswordForm.tsx`, `MiCuenta.tsx`
   (`CambiarPasswordForm`/`CambiarEmailForm`) y `reset-password.tsx` (`SolicitarResetForm`). El
   caso de `LoginForm` quedó cubierto por test (`LoginForm.test.tsx`).

3. ~~Posible carrera entre navegación post-login y resolución de `perfil`~~ **Resuelto y verificado
   en vivo después de escribir este documento** — ver [`decisiones.md`](./decisiones.md)
   D-LOGIN-007. Se reprodujo exactamente el escenario que este ítem preveía (login → redirect a
   `/superadmin/empresas` con `?redirect=` aterrizaba en `/`) y se corrigió reemplazando
   `router.navigate()` por `window.location.href` en `routes/login.tsx`. Confirmado en Chrome real
   con logout, redirect a ruta protegida, login, aterriza directo en el destino. Se retira como
   pendiente.

4. **`signOut()` automático ante 401/404 no distingue el motivo exacto del error (ver
   `decisiones.md` D-LOGIN-006).** Cualquier `ApiError` con `status` 401 o 404 al resolver `perfil`
   dispara logout, no solo "usuario desactivado" o "usuario borrado" — no hay forma de diferenciar,
   desde el frontend, un 401/404 real de otro escenario que devolviera el mismo status. Bajo riesgo
   dado que `presupuestacionFetch` solo usa el `status` real de la respuesta HTTP
   (`lib/api/presupuestacion.ts:35-38`), pero se deja registrado como asunción no verificada
   exhaustivamente.
