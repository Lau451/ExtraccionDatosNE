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
