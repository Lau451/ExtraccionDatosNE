# Proposal: Gestión de empresas (SuperAdmin)

**Estado: activo, no archivado.** Pantalla nueva, fuera de las 8 pantallas originales del MVP
(ver `frontend/PROGRESS.md`). Documentado el 2026-07-23, código ya implementado y verificado antes
de escribir este proposal.

## Intent

`services/presupuestacion` es multi-tenant (`drogueria_id` en la mayoría de las tablas), pero
antes de esta sesión no existía ningún backend para crear/administrar una droguería (empresa
cliente) — la única forma de dar de alta una era insertar directo en la base. Con el módulo nuevo
`droguerias/` (CRUD completo, solo `superadmin`) ya construido, faltaba la pantalla de frontend
para que un `superadmin` pudiera crear empresas nuevas, asignarles un plan, suspenderlas/
reactivarlas, eliminarlas, y crear el primer usuario `admin` de cada una — sin ese primer admin,
una droguería recién creada no tiene forma de autogestionarse (todo el resto de `usuarios/` exige
ya tener un `admin`/`superadmin` existente para invitar al siguiente usuario).

## Scope

### Incluido
- Ruta protegida `/superadmin/empresas` (`_authenticated.superadmin.empresas.tsx`), con
  `beforeLoad: requireRole('superadmin')`.
- `GestionEmpresas.tsx`: tabla de empresas (nombre, CUIT, plan, estado), con cambio de plan
  inline (`<select>`), suspender/reactivar y eliminar (con `ConfirmDialog`).
- `CrearDrogueriaDialog.tsx`: modal de alta de empresa (nombre, razón social, CUIT con
  autoformato `NN-NNNNNNNN-N` mientras se escribe, ciudad, provincia, email/teléfono de
  contacto).
- `CrearPrimerAdminDialog.tsx`: modal por fila, invita al primer usuario `admin` de esa empresa
  específica (reusa `POST /usuarios` con `rol: 'admin'` fijo y `drogueria_id` de la fila, mismo
  mecanismo de invitación por email que `gestion-usuarios/`).
- Consumo de `GET/POST/PATCH/DELETE /droguerias` y `GET /planes`
  (`frontend/src/lib/api/droguerias.ts`, `frontend/src/lib/api/planes.ts`).

### Explícitamente fuera de scope
- Cualquier regla de negocio nueva de backend para `droguerias/` o `planes/` — ambos módulos ya
  existían completos antes de esta pantalla; wiring de frontend puro.
- CRUD de planes: `planes/` solo expone `GET /planes` (catálogo, sin alta/edición vía API — se
  gestiona por SQL directo, ver `docs/modulos/planes/decisiones.md`). Esta pantalla solo permite
  **asignar** un plan existente a una empresa, no crear ni editar planes.
- Validación de dígito verificador real del CUIT — tanto el backend
  (`_validar_formato_cuit`, RN-DROGUERIAS-001) como el autoformato del frontend solo validan la
  forma `NN-NNNNNNNN-N`, no el checksum.

## Approach

Mismo patrón de wiring que `gestion-usuarios/`: TanStack Query con invalidación de `['droguerias']`
tras cada mutación. `CrearPrimerAdminDialog` no agrega ningún endpoint nuevo — reusa
`invitarUsuario` de `frontend/src/lib/api/usuarios.ts` (el mismo que consume
`gestion-usuarios/InvitarUsuarioDialog.tsx`) fijando `rol: 'admin'` y el `drogueria_id` de la fila,
en vez de duplicar lógica de invitación.

## Riesgos

Ninguno relevante — mismo patrón ya validado por `gestion-usuarios/` y por
`openspec/changes/archive/procesos-comerciales/`. El riesgo real de negocio (eliminar una
droguería con datos asociados) ya está resuelto en el backend con `ConflictError` (409,
RN-DROGUERIAS-004), no es responsabilidad de esta pantalla más que mostrar el mensaje de error.
