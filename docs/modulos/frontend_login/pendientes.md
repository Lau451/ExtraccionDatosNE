# Pendientes — Auditoría técnica de Login

Clasificación P1 (crítico/bloqueante) / P2 (deuda técnica relevante) / P3 (menor), verificada
contra el código real en esta sesión.

## P1 — Crítico

1. **No hay ningún test de frontend en todo el repositorio, incluido este módulo.** Confirmado en
   esta sesión: no existe `vitest.config.*` en `frontend/`; `package.json` no tiene script `test`
   (no se repitió el grep de archivos `*.test.*`/`*.spec.*` en esta sesión, pero no apareció
   ninguno en la lectura de los 12 archivos del alcance). Esto aplica ahora a más superficie que
   antes — cero cobertura de `AuthContext` (secuencia `loading`→`perfilLoading`, `signOut`
   automático en 401/404, `refrescarPerfil`), `LoginForm`, `SetPasswordForm` (validación de
   contraseñas coincidentes), `useSessionFromLink`, `routeGuards` (`requireAuth` y `requireRole`,
   este último **ahora con call sites reales** — ver ítem 1 de P2 abajo), o las rutas (`login.tsx`,
   `reset-password.tsx`, `accept-invite.tsx`, `_authenticated.tsx`, incluido su nuevo `useEffect`
   reactivo). Se mantiene P1: la ausencia sigue siendo total, y el bug de timing corregido en esta
   sesión (ver [`decisiones.md`](./decisiones.md) D-LOGIN-005) es exactamente el tipo de
   regresión silenciosa que un test hubiera detectado antes de llegar a producción.
   [RECOMENDACIÓN]: como mínimo, un test de integración de `requireRole` con `perfil` no resuelto
   todavía (para fijar el comportamiento esperado tras D-LOGIN-005) y uno de `AuthContext` que
   cubra el `signOut` automático en 401/404 (D-LOGIN-006).

## P2 — Deuda técnica relevante

1. **`requireRole` ahora tiene call sites reales, pero sigue sin ningún test — corrige el ítem
   anterior de este documento.** Antes se describía como "código sin call site, riesgo
   hipotético". Ya no es así: `routes/_authenticated.admin.usuarios.tsx:6` y
   `routes/_authenticated.superadmin.empresas.tsx:6` lo usan en producción. El bug de timing
   corregido en esta sesión (`perfilLoading`, ver [`decisiones.md`](./decisiones.md) D-LOGIN-005)
   es la prueba directa de que la divergencia silenciosa que este ítem advertía ya ocurrió una vez
   — `requireRole` dependía de un `perfil` que podía no estar resuelto, y nada lo detectó hasta que
   se reprodujo manualmente. [RECOMENDACIÓN]: al menos un test de integración que cubra
   `requireRole` con `perfil: null` y con `perfil` resuelto pero sin el rol requerido, para evitar
   que una futura regresión de `perfilLoading`/`main.tsx` vuelva a pasar desapercibida.

2. **`Rol` está duplicado entre frontend y backend sin mecanismo de sincronización.** Ver
   [`decisiones.md`](./decisiones.md) D-LOGIN-002: `AuthContext.tsx:6` y `usuarios/models.py:5`
   (backend) declaran la misma lista de 6 roles de forma completamente independiente. No hay
   generación de tipos ni test de contrato entre ambos proyectos que detecte una divergencia si
   alguno de los dos cambia. [RECOMENDACIÓN]: al menos un comentario cruzado en ambos archivos que
   apunte al otro, o un test que compare ambas listas si en algún momento se automatiza.

3. ~~No hay recuperación de contraseña ni registro de usuarios en el frontend.~~ **Resuelto en esta
   sesión**: la recuperación de contraseña está implementada (`/reset-password`, ver
   [`decisiones.md`](./decisiones.md) D-LOGIN-004, ahora marcada como superada, y
   [`flujo.md`](./flujo.md) #5). El registro libre (auto-signup) sigue sin existir, pero por
   diseño: el alta la hace un admin/superadmin vía invitación (`/accept-invite`), no un
   autoservicio de "crear cuenta" — ver [`flujo.md`](./flujo.md) #6. Se retira como pendiente.

4. **`SetPasswordForm` no valida fuerza de contraseña más allá de `minLength=8`.** No hay chequeo
   de mayúsculas/números/símbolos ni en el frontend ni evidencia de uno en la respuesta de
   `updateUser` en el código leído en esta sesión (`SetPasswordForm.tsx:52`). [SUPOSICIÓN, no
   verificada]: es posible que Supabase Auth aplique alguna política de contraseña propia del lado
   del servidor (configuración del proyecto, no del código de este repo) — no se confirmó en esta
   sesión. [RECOMENDACIÓN]: si se requiere una política más estricta, documentarla explícitamente
   en vez de depender de configuración externa no versionada en este repositorio.

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

2. **`LoginForm` no distingue el motivo real de un error de login (RN-LOGIN-003).** Todo error de
   `signIn` — credenciales inválidas, red caída, servicio de Supabase Auth no disponible, rate
   limit — se muestra con el mismo mensaje `'Email o contraseña incorrectos'`
   (`LoginForm.tsx:19-20`), sin `console.error` ni ningún registro del error original. Mismo patrón
   en `SetPasswordForm` (`SetPasswordForm.tsx:33-34`, mensaje genérico "No pudimos guardar la
   contraseña") y en `CambiarPasswordForm`/`CambiarEmailForm` de Mi cuenta. No es necesariamente
   incorrecto (evita filtrar detalles de la causa a un atacante que intente enumerar usuarios), pero
   dificulta el diagnóstico si el error real fuera, por ejemplo, de red o de configuración
   (`VITE_SUPABASE_URL` mal seteada). [RECOMENDACIÓN]: al menos loguear el error original a la
   consola en desarrollo, sin cambiar el mensaje mostrado al usuario.

3. **Posible carrera entre navegación post-login y resolución de `perfil` para rutas con
   `requireRole` — parcialmente mitigada, no descartada del todo (ver `flujo.md` #1).**
   `onSuccess()` navega apenas `signInWithPassword` resuelve, en paralelo con el `useEffect` que
   resuelve `perfil` vía `GET /usuarios/{id}`. El fix de esta sesión (`perfilLoading`, D-LOGIN-005)
   cubre el **montaje inicial** del router (reload/deep-link), pero en este flujo de login
   interactivo el router ya está montado — `onSuccess()` podría redirigir a una ruta con
   `requireRole` antes de que `perfil` esté resuelto. [SUPOSICIÓN] razonada a partir de la lectura
   del código; no reproducida ni descartada en runtime en esta sesión — a diferencia de los otros
   dos bugs de este módulo, corregidos y confirmados en vivo, este permanece como riesgo abierto.
   [RECOMENDACIÓN]: reproducir intencionalmente (login → redirect a `/admin/usuarios` con
   `?redirect=`) antes de asumir que no ocurre.

4. **`signOut()` automático ante 401/404 no distingue el motivo exacto del error (ver
   `decisiones.md` D-LOGIN-006).** Cualquier `ApiError` con `status` 401 o 404 al resolver `perfil`
   dispara logout, no solo "usuario desactivado" o "usuario borrado" — no hay forma de diferenciar,
   desde el frontend, un 401/404 real de otro escenario que devolviera el mismo status. Bajo riesgo
   dado que `presupuestacionFetch` solo usa el `status` real de la respuesta HTTP
   (`lib/api/presupuestacion.ts:35-38`), pero se deja registrado como asunción no verificada
   exhaustivamente.
