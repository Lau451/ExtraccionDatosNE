# Pendientes — Auditoría técnica de Login

Clasificación P1 (crítico/bloqueante) / P2 (deuda técnica relevante) / P3 (menor), verificada
contra el código real en esta sesión.

**Pendiente explícito, fuera de este cierre**: configuración de SMTP propio para Supabase Auth
(hoy usa el SMTP compartido de Supabase, con rate limit bajo para `invite_user_by_email` y
`resetPasswordForEmail`). Es un paso de configuración operacional del proyecto de Supabase, no un
cambio de código — decisión explícita del usuario de dejarlo pendiente por ahora.

## P1 — Crítico

1. ~~No hay ningún test de frontend en todo el repositorio, incluido este módulo.~~ **Resuelto**:
   se agregó `vitest` + `@testing-library/react` + `@testing-library/jest-dom` + `jsdom`
   (`frontend/vitest.config.ts`, `frontend/src/test/setup.ts`, script `npm run test`). Cobertura
   nueva: `routeGuards.test.ts` (`requireAuth`, `requireRole` con `perfil: null` — el caso exacto
   de D-LOGIN-005/007 — y con rol no permitido/permitido), `AuthContext.test.tsx` (secuencia
   `loading`→`perfilLoading`, `signOut` automático en 401 y en 404, ausencia de `signOut` en otros
   errores, `refrescarPerfil`), `LoginForm.test.tsx` y `SetPasswordForm.test.tsx` (éxito, error,
   validaciones). 16 tests, todos en verde (`npm run test`, verificado en esta sesión). No se
   agregaron tests de rutas (`login.tsx`, `reset-password.tsx`, `accept-invite.tsx`) ni de
   `MiCuenta.tsx` — son integración de TanStack Router sobre piezas ya cubiertas; queda como
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

4. ~~`SetPasswordForm` no valida fuerza de contraseña más allá de `minLength=8`.~~ **Resuelto**: se
   agregó una validación mínima (al menos una letra y un número, además del `minLength=8` ya
   existente) en `SetPasswordForm.tsx`, cubierta por test. [SUPOSICIÓN, no verificada]: sigue sin
   confirmarse si Supabase Auth aplica alguna política de contraseña propia del lado del servidor
   — no se investigó en esta sesión, no era necesario para cerrar este ítem.

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
   `_authenticated.tsx:16-24` (redirect inmediato si la pantalla ya está montada) y `requireAuth`
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
