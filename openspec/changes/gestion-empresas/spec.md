# Specification: Gestión de empresas (SuperAdmin)

## Archivos

| Archivo | Responsabilidad |
|---|---|
| `frontend/src/routes/_authenticated.superadmin.empresas.tsx` | Ruta `/superadmin/empresas`, `beforeLoad: requireRole('superadmin')`. |
| `frontend/src/features/gestion-empresas/GestionEmpresas.tsx` | Tabla de empresas + orquestación de mutaciones (`actualizarDrogueria`, `eliminarDrogueria`). |
| `frontend/src/features/gestion-empresas/CrearDrogueriaDialog.tsx` | Modal de alta de empresa, con autoformato de CUIT. |
| `frontend/src/features/gestion-empresas/CrearPrimerAdminDialog.tsx` | Modal por fila: invita al primer `admin` de esa empresa. |
| `frontend/src/lib/api/droguerias.ts` | `listarDroguerias`, `crearDrogueria`, `actualizarDrogueria`, `eliminarDrogueria`. |
| `frontend/src/lib/api/planes.ts` | `listarPlanes` (catálogo de solo lectura). |
| `services/presupuestacion/droguerias/`, `services/presupuestacion/planes/` | Backend consumido, ya existente y documentado en `docs/modulos/droguerias/` y `docs/modulos/planes/` (no se toca en este change). |

## Comportamiento observable

### Autoformato de CUIT en el modal de creación

`formatearCuit` (`CrearDrogueriaDialog.tsx`) recorta a 11 dígitos y va insertando los guiones a
medida que se escribe (`NN-NNNNNNNN-N`), con `pattern="\d{2}-\d{8}-\d"` como validación HTML
adicional. Coincide exactamente con lo que exige `_validar_formato_cuit` del backend
(RN-DROGUERIAS-001) — ninguno de los dos valida el dígito verificador real.

### Asignar plan — `<select>` inline por fila

`FilaDrogueria` muestra un `<select>` con "Sin plan" + los planes activos (`GET /planes`,
RN-PLANES-001: solo devuelve `activo=true`). Cambiar la selección dispara
`PATCH /droguerias/{id}` con `{plan_id}` únicamente (actualización parcial, RN-DROGUERIAS-003) —
no reenvía el resto de los campos de la empresa.

### Suspender/reactivar — mismo endpoint que el resto de los campos

No hay un endpoint dedicado de `activa` en `droguerias/` (a diferencia de `usuarios/`, que sí
tiene `PATCH /usuarios/{id}/activo` separado) — el botón "Suspender"/"Reactivar" llama al mismo
`PATCH /droguerias/{id}` con `{activa: !drogueria.activa}`.

### Crear el primer admin de una empresa reusa la invitación de usuarios

`CrearPrimerAdminDialog` no llama a ningún endpoint de `droguerias/` — llama a `invitarUsuario`
(el mismo de `frontend/src/lib/api/usuarios.ts` que usa `gestion-usuarios/`) con
`{rol: 'admin', drogueria_id: <id de la fila>}` fijo, sin selector de rol ni de empresa (ambos ya
resueltos por el contexto de la fila). Solo un `superadmin` puede promover a `admin`
(RN-USUARIOS-002/015), consistente con que esta pantalla entera está detrás de
`requireRole('superadmin')`.

## Scenarios

### Scenario: crear una empresa nueva
```
Given: un usuario autenticado con rol "superadmin" en /superadmin/empresas
When: abre "+ Nueva empresa", completa nombre/razón social/CUIT/ciudad/provincia/contacto y
  confirma
Then: POST /droguerias con el payload completo
  AND se invalida la query ["droguerias"] y el modal se cierra y limpia su estado
```

### Scenario: CUIT con formato inválido es rechazado por el backend
```
Given: un superadmin crea o edita una empresa
When: el CUIT no matchea NN-NNNNNNNN-N (el autoformato del frontend dificulta esto, pero el
  backend valida igual, RN-DROGUERIAS-001)
Then: el backend responde 422 (ValidationError de Pydantic)
  AND el modal muestra el mensaje de error en vez de cerrarse
```

### Scenario: asignar un plan a una empresa
```
Given: una empresa sin plan asignado (plan_id: null, se muestra "Sin plan")
When: el superadmin elige un plan del <select>
Then: PATCH /droguerias/{id} con {plan_id: <id del plan>}
  AND al resolver, se invalida ["droguerias"] y la fila muestra el nombre del plan elegido
```

### Scenario: solo se listan planes activos para asignar
```
Given: existe un plan con activo=false en la base
When: se renderiza el <select> de plan de cualquier fila
Then: ese plan no aparece entre las opciones (RN-PLANES-001: GET /planes excluye activo=false)
```

### Scenario: suspender y reactivar una empresa
```
Given: una empresa activa (activa: true)
When: el superadmin hace click en "Suspender"
Then: PATCH /droguerias/{id} con {activa: false}
  AND la fila pasa a mostrar "Suspendida" y el botón cambia a "Reactivar"
```

### Scenario: eliminar una empresa sin datos asociados
```
Given: una empresa sin usuarios/clientes/procesos comerciales asociados
When: el superadmin confirma "Eliminar" en el ConfirmDialog
Then: DELETE /droguerias/{id}
  AND se invalida ["droguerias"] y el ConfirmDialog se cierra
```

### Scenario: eliminar una empresa con datos asociados muestra el error del backend
```
Given: una empresa con usuarios asociados (por ejemplo, el admin creado por
  CrearPrimerAdminDialog)
When: el superadmin confirma "Eliminar"
Then: el backend responde 409 (ConflictError, RN-DROGUERIAS-004: "la empresa tiene datos
  asociados...")
  AND la pantalla muestra ese mensaje (eliminarMutation.error.message), no un error genérico
  AND la empresa NO se elimina
```

### Scenario: crear el primer admin de una empresa recién creada
```
Given: una empresa recién creada, sin ningún usuario todavía
When: el superadmin hace click en "Crear admin" en la fila de esa empresa, completa
  email/nombre/apellido y confirma
Then: POST /usuarios se envía con {rol: 'admin', drogueria_id: <id de la fila>} más los datos
  ingresados — sin selector de rol ni de empresa en este modal
  AND el nuevo admin recibe el mismo email de invitación que documenta
  openspec/changes/archive/login-frontend/ (actualización 2026-07-23)
  AND se invalida la query ["usuarios"] (no ["droguerias"] — la tabla de empresas no cambia)
```

### Scenario: ruta protegida por rol
```
Given: un usuario autenticado con rol "admin" (no superadmin)
When: navega a /superadmin/empresas
Then: requireRole('superadmin') en beforeLoad rechaza el acceso
```

## Verificación

Implementado y verificado en esta sesión contra el backend real de `droguerias/` y `planes/`
(`tests/droguerias/test_service.py` en verde, incluyendo el caso de eliminación con FK real —
ver `docs/modulos/droguerias/reglas.md` RN-DROGUERIAS-004). No hay test automatizado propio de
frontend para esta pantalla (mismo patrón que el resto de `frontend/` — ver
`docs/modulos/frontend_login/pendientes.md` P1). `planes/` no tiene tests automatizados en
absoluto (no existe `tests/planes/`, ver `docs/modulos/planes/reglas.md`) — el catálogo de planes
consumido por esta pantalla está verificado solo por lectura de código.
