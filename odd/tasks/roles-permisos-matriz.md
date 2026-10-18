# Role permissions: apply the user's permission matrix

Apply the role/screen/action matrix the user edited in `docs/seguridad/matriz-roles.xlsx` (sheet `Propuesta`)
across frontend guards, backend `require_roles` and the affected RLS policies.
Delivery strategy: ask-on-risk. Branch: `feat/roles-permisos-matriz` (from `dev`).

## Specs

Source of truth: sheet `Propuesta` of `docs/seguridad/matriz-roles.xlsx`, plus the clarifications in L3-L4.
Each spec must hold in the frontend (route guard / visible controls) AND in the backend API (403 for denied roles).

- S1 Carga de documentos (view + "Subir documento (extracción con IA)"): only `admin`, `gerencia`, `lider_comercial`, `comercial`. `compras` and `superadmin` denied. User note (verbatim): "Por ahora compras no participa en ninguno de los procesos de extraccion, en un futuro si agregamos documentos de su seccion se lo desbloquemos". Clarification L3: superadmin "Que no la vea".
- S2 Validar extracción, "Ver listado de extracciones": only `admin`, `gerencia`, `lider_comercial`, `comercial` (`superadmin` and `compras` denied). Detail/agrupar/validar keep their current roles (same four).
- S3 Productos, "Ver costos": `superadmin`, `admin`, `gerencia`, `lider_comercial`, `compras` (adds `lider_comercial`; `comercial` still denied). Confirmed in L3: "Confirmo".
- S4 Terceros, "Crear / editar terceros, direcciones y contactos": only `admin`, `gerencia`, `lider_comercial` (`comercial` and `compras` lose write; reading unchanged for all 6).
- S5 Terceros, "Gestionar catálogos de apoyo (sectores, condiciones y formas de pago)": `admin`, `gerencia`, `lider_comercial` (adds `lider_comercial`).
- S6 "Importar presupuestos legacy": only `admin` (`gerencia` and `compras` lose it). "Importar PCP" is unchanged (`admin`, `gerencia`, `compras`).
- S7 Usuarios: `gerencia` can view AND manage users (L3: "No, también gestiona"), limited to lower roles (L4: "Solo roles inferiores"): gerencia invites and modifies only `gerencia`, `lider_comercial`, `comercial`, `compras` of its own droguería; it cannot modify `admin` users nor assign `admin`. Existing rules stay: nobody modifies themselves, `superadmin`/`sistema` are protected, only `superadmin` assigns `admin`, admin keeps its current powers.
- S8 Órdenes de compra, "Planificar entregas": only `admin`, `gerencia`, `lider_comercial`, `comercial` (the API currently also lets `compras` register deliveries; close it).
- S9 Routes without a role guard get one matching the matrix: `/compromisos` (all except `superadmin`), `/ordenes-compra/$id` resumen (all 6), `/ordenes-compra/$id/matching` and `/entregas` (`admin`, `gerencia`, `lider_comercial`, `comercial`), `/validar-extraccion/*` (S2 roles), `/` carga (S1 roles). A role denied the landing screen `/` must still land somewhere it can use (no redirect loop).
- S10 Every other row of the matrix is unchanged; existing role behavior for untouched rows must keep working.

## Tasks

Exploration map (explore task mvdxsoog-1-ypjg): almost every write and the cost/stock reads use `get_service_client()` (bypasses RLS), so `require_roles` is the effective guard; RLS is aligned as defense in depth where a migration owns the policy (terceros/catálogos in `0008_terceros_modelo.sql`). `costos_productos` and `entregas_oc*` policies exist only in `docs/schema/rls_final.sql` (no migration) — out of scope, reported.

- T1 [S1, S2, S8] Backend: role guard on every `services/extraccion` endpoint (`POST /procesar`, `GET /api/documentos[/{id}]`, `PATCH /api/extraction-results/{id}`, `GET /api/clientes`) with the S1 roles; `GET /extracciones` lectura roles = S2; `POST /ordenes-compra/{id}/entregas` drops `compras`. Route: worker A. Commit: d9afd75 (shared with T2).
- T2 [S3, S4, S5, S6] Backend: costs read adds `lider_comercial`; terceros/direcciones/contactos write = admin, gerencia, lider_comercial; catálogos write adds lider_comercial; `/pcp/imports/presupuestos-legacy` admin only (PCP import unchanged). Migration `0037` (+ down) aligning terceros/catálogos RLS INSERT/UPDATE. Route: worker A. Commit: d9afd75. Evidence T1+T2: RED 48 failed / 109 passed in tests/test_roles_matriz_backend.py; GREEN 157 passed; focused non-integration 482 passed; `pytest tests -m "not integration"` 935 passed, 1 failed pre-existing (`tests/core/test_database.py::test_service_client_no_se_importa_en_ningun_router` on untouched oc_resumen/router.py). Integration tests not run (write to real Supabase). Migration 0037 not applied. `tlm_*` left unchanged (legacy import writes it). S4 constant also gates /terceros/{id}/clientes|proveedores and direcciones usos/delete.
- T3 [S7] Backend usuarios: gerencia can list/invite/change role/toggle/delete within its droguería, only over and to roles gerencia/lider_comercial/comercial/compras; cannot touch admin users nor assign admin. Route: worker B. Commit: da988ff. Evidence: RED 16 failed (gerencia allow cases 403), GREEN tests/usuarios/test_router.py 42 passed; tests/usuarios 4 invite integration tests failed on Supabase 429 email rate limit (unchanged admin/superadmin create path, rerun pending).
- T4 [S1-S9] Frontend: role constants mirror the backend, route guards for unguarded routes, role-aware landing (no `/` redirect loop for compras/superadmin), sidebar items, usuarios screen for gerencia. Route: worker C. Commit: 9b7cb61. Evidence: RED 28 failed; GREEN focused 120 passed, full `npm test` 62 files / 598 passed, `tsc -p tsconfig.app.json --noEmit` exit 0. `homeForRol`: compras -> /productos, superadmin -> /superadmin/empresas, no profile -> /mi-cuenta.
- T5 [S10] Docs (`docs/reglas-globales.md` §2, module READMEs), reference sheet of the Excel, full suites, independent verify. Route: parent + gentle-ai-verify. Commit: 67638ed (fix), bdb1ce4 (docs). Evidence: verify mvdyaof8 PASS S1-S9, S10 PARTIAL (admin 403 text changed in usuarios/service.py) -> fixed test-first (RED 3 failed, GREEN), admin keeps "Un admin solo puede modificar/eliminar usuarios de su droguería"; `pytest tests -m "not integration"` 938 passed, 1 pre-existing failure; frontend 598 passed, tsc exit 0 (verify run).

## Log

- L1 (user, original request): "me podes decir los roles que hay actualmente y a que pantallas tiene acceso cada uno? porque uiero afinar la seguridad"
- L2 (user): "te parece si pienso quein tiene que ver cada pantalla y que hacer y te lo paso para tomar una desicion?" → "bien creame un excel que pueda editar asi lo hago ccomo queres" → "listo ya lo modifiqué". Diff Propuesta vs Actual: carga docs ver (compras Sí->No), subir (superadmin, compras Sí->No), listado extracciones (superadmin, compras Sí->No), ver costos (lider_comercial No->Sí), terceros write (comercial, compras Sí->No), catálogos de apoyo (lider_comercial No->Sí), importar presupuestos legacy (gerencia, compras Sí->No), ver usuarios (gerencia No->Sí).
- L3 (user answers): superadmin en Carga de documentos → "Que no la vea"; gerencia en usuarios → "No, también gestiona"; líder comercial ve costos → "Confirmo".
- L5 (verify): no privilege-escalation path for gerencia; migration 0037 keeps `mismo_tenant`, down matches 0008. Pending outside this branch: apply 0037, rerun 4 invite integration tests (Supabase 429), integration suites not run (write to real Supabase).
- L4 (user answer): alcance de gerencia sobre usuarios → "Solo roles inferiores" (invita y modifica gerencia/lider_comercial/comercial/compras; no puede tocar admins ni asignar admin).
- L-docs: Module docs updated by worker mvdyb756 (37 files under docs/modulos, S1-S9 role statements re-cited). Open questions surfaced, not acted on: (a) 0037 comment says tlm_* = admin/gerencia/compras while 0008 grants tlm_ins to 5 roles; (b) clientes/router.py:36 still lets `comercial` write — outside S4 as written; (c) presupuestos/arquitectura.md:74 "comercial y lider_comercial NO deben consultar costos_productos" reads in tension with S3. Pending: independent verify mvdyaof8, then T5 commit.
