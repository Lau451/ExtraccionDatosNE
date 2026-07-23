# Módulo Mi cuenta — `frontend/src/features/mi-cuenta/` + `routes/_authenticated.mi-cuenta.tsx`

Módulo liviano de **frontend**, documentado en un único archivo (a diferencia de
[`../frontend_login/`](../frontend_login/README.md), que usa la estructura completa de 8 archivos).
Criterio: 2 archivos fuente, 246 líneas en total (`MiCuenta.tsx` 240, `_authenticated.mi-cuenta.tsx`
6 — verificado leyendo ambos completos en esta sesión), sin reglas de negocio propias del backend
(delega todo en endpoints y en `supabase-js`), sin flujo con ramificaciones complejas y sin
decisiones de diseño no triviales — no amerita partir la documentación en 8 archivos separados.

## Qué es

Pantalla de autogestión de la cuenta del usuario ya autenticado: editar nombre/apellido, cambiar
contraseña, cambiar email (con verificación nativa de Supabase) y cerrar sesión. Accesible desde
`Sidebar.tsx:67-69` (`<Link to="/mi-cuenta">`, fuera del alcance de archivos de esta documentación)
y montada bajo el layout `/_authenticated` (ver [`../frontend_login/`](../frontend_login/README.md)
para el guard de sesión).

## Qué NO hace

- **No permite editar el email sin pasar por la verificación nativa de Supabase.** El cambio de
  email no aplica al instante: `supabase.auth.updateUser({ email })` (`MiCuenta.tsx:193`) dispara el
  flujo estándar de Supabase Auth, que exige confirmar el cambio tanto desde el email actual como
  desde el nuevo antes de que se aplique — comportamiento del SDK, no lógica propia de este código.
  El comentario visible al usuario lo advierte explícitamente (`MiCuenta.tsx:206-209`).
- **No permite editar el rol ni la droguería propios.** Esos campos no aparecen en ningún formulario
  de esta pantalla — solo `nombre`/`apellido` son editables (`ActualizarPerfilPayload`,
  `lib/api/usuarios.ts:16-19`, acota los campos aceptados por `PATCH /usuarios/me`). Cambiar rol o
  desactivar usuarios es responsabilidad del módulo `usuarios/` (gestión de otros usuarios, no de la
  cuenta propia).
- **No tiene tests.** Mismo hallazgo que el resto del frontend — ver
  [`../frontend_login/pendientes.md`](../frontend_login/pendientes.md) P1(1); no se repite acá como
  hallazgo separado, es la misma ausencia total del proyecto.

## Componentes y qué hacen

| Pieza | Archivo | Qué hace |
|---|---|---|
| `MiCuenta` (componente de página) | `features/mi-cuenta/MiCuenta.tsx:7-37` | Lee `perfil`/`session`/`signOut` de `useAuth()`; si `perfil` es `null` no renderiza nada (`:16`, guard simple sin loader propio — depende de que `_authenticated.tsx` ya haya esperado la resolución del perfil, ver `../frontend_login/arquitectura.md`); compone los 3 formularios + botón de logout. |
| `EditarNombreForm` | `MiCuenta.tsx:39-101` | Formulario controlado de `nombre`/`apellido`, prellenado con `perfil.nombre`/`perfil.apellido` (`:22`, con `apellido ?? ''` porque el campo es nullable). `PATCH /usuarios/me` vía `actualizarPerfilPropio` (`lib/api/usuarios.ts:29-35`), y tras el éxito llama a `refrescarPerfil()` de `AuthContext` (`MiCuenta.tsx:53`) para que el resto de la app (p. ej. `Sidebar`) vea el nombre actualizado sin recargar la página. |
| `CambiarPasswordForm` | `MiCuenta.tsx:103-179` | Valida `password === confirmacion` (mismo patrón que `SetPasswordForm` del módulo Login, `:115-118`) y llama a `supabase.auth.updateUser({ password })` (`:122`). A diferencia de `SetPasswordForm`, **no** hace `signOut()` después — el usuario sigue logueado con la sesión actual tras cambiar la contraseña. |
| `CambiarEmailForm` | `MiCuenta.tsx:181-240` | Pide el email nuevo y llama a `supabase.auth.updateUser({ email })` (`:193`); muestra el email actual (`session?.user.email`, pasado como prop desde `MiCuenta`) y un aviso de que Supabase pedirá doble confirmación. No hay feedback de que el cambio ya se aplicó — solo confirma que el mail de verificación se envió (`:225-229`). |
| Botón "Cerrar sesión" | `MiCuenta.tsx:26-34` (botón), `handleLogout` en `:11-14` | `await signOut()` (de `AuthContext`, ver `../frontend_login/`) seguido de `navigate({ to: '/login' })` — a diferencia del logout automático de `AuthContext` en 401/404 (ver `../frontend_login/decisiones.md` D-LOGIN-006), acá la navegación es explícita porque no hay un guard reactivo montado en esta pantalla que la dispare por sí solo (ese guard vive en `_authenticated.tsx`, y de todos modos correría después). |
| Ruta `/mi-cuenta` | `routes/_authenticated.mi-cuenta.tsx:1-6` | `createFileRoute('/_authenticated/mi-cuenta')({ component: MiCuenta })` — sin `beforeLoad` propio; hereda `requireAuth` del layout padre `_authenticated.tsx`. No usa `requireRole`: cualquier usuario autenticado puede acceder a su propia cuenta. |

[IMPLEMENTADO] todo lo anterior, verificado leyendo ambos archivos completos en esta sesión.

## Dependencias

- **`../frontend_login/`** — `useAuth()` (`perfil`, `session`, `signOut`, `refrescarPerfil`) y el
  guard de sesión de `_authenticated.tsx`. Este módulo no define ningún mecanismo de autenticación
  propio, reusa el de Login por completo.
- **Supabase Auth (directo, vía `supabase-js`)** — `updateUser({ password })` y
  `updateUser({ email })` (`MiCuenta.tsx:122`, `:193`). Mismo cliente único que documenta
  `../frontend_login/arquitectura.md` (`lib/supabase.ts`).
- **`services/presupuestacion` — módulo Usuarios** — `PATCH /usuarios/me` vía
  `actualizarPerfilPropio` (`lib/api/usuarios.ts:29-35`). Contrato completo (payload, autorización)
  documentado en [`../usuarios/api.md`](../usuarios/api.md).

## Reglas verificadas

- **Solo `nombre`/`apellido` son editables desde esta pantalla** — `ActualizarPerfilPayload` acota
  los campos a esos dos (`lib/api/usuarios.ts:16-19`); el backend decide qué exige/permite en
  `PATCH /usuarios/me` (ver `../usuarios/reglas.md` si existe una regla específica de ese endpoint;
  no se investigó el lado backend en esta sesión, fuera del alcance de esta actualización).
  [IMPLEMENTADO] el hecho del lado frontend; [SUPOSICIÓN] que el backend no acepte más campos de
  los que el frontend envía — no verificado en esta sesión.
- **`refrescarPerfil()` es la única vía por la que esta pantalla actualiza el estado global de
  `perfil`** tras un cambio — `CambiarPasswordForm` y `CambiarEmailForm` no la llaman (no hace
  falta: ninguno de los dos cambia un campo reflejado en `Perfil`). [IMPLEMENTADO].

## Pendientes

- **P3**: `CambiarEmailForm` no refleja el nuevo email en la UI hasta que el usuario complete la
  doble confirmación y recargue — el campo "Email actual" sigue mostrando el viejo hasta el próximo
  fetch de `session`. No se verificó en runtime en esta sesión si `onAuthStateChange` actualiza
  `session.user.email` automáticamente tras completar la verificación. [SUPOSICIÓN, no verificada].
- **P3**: sin loading state propio si `perfil` es `null` (`MiCuenta.tsx:16` retorna `null` sin
  spinner ni mensaje) — depende por completo de que `_authenticated.tsx` ya haya esperado
  `perfilLoading` antes de montar la ruta (ver `../frontend_login/`). Consistente con el resto del
  módulo Login, pero deja esta pantalla sin manejo propio si esa garantía cambiara en el futuro.
- Ver también [`../frontend_login/pendientes.md`](../frontend_login/pendientes.md) P1(1) (ausencia
  total de tests, aplica también acá) y P3(2) (mensajes de error genéricos sin logging, mismo
  patrón en los 3 formularios de esta pantalla).
