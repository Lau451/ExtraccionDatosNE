# Documentación técnica — ExtraccionDatosNE (Drogueria Nueva Era)

Este directorio documenta el monorepo `ExtraccionDatosNE`, la aplicación de extracción
y presupuestación de documentos comerciales (licitaciones, cotizaciones, comparativas de
precios) de Drogueria Nueva Era. El repositorio contiene cuatro piezas:

- **`services/extraccion/`** — backend legacy (FastAPI): sube un documento (PDF/Excel/
  imagen/HTML), lo parsea y usa Google Gemini para extraer datos estructurados a CSV.
  Sirve además la interfaz HTML antigua (Jinja2).
- **`services/presupuestacion/`** — backend nuevo (FastAPI, 16 módulos de negocio + Core):
  toma esos datos ya extraídos y corre el ciclo comercial completo — matching de
  productos, pricing, generación y aprobación de presupuestos, órdenes de compra,
  eventos, notificaciones y automatizaciones.
- **`services/shared/`** — código compartido entre ambos backends (hoy, el kernel de
  verificación JWT, `auth_jwt.py`).
- **`frontend/`** — SPA nueva (Vite + React + TanStack Router), en desarrollo activo;
  hoy solo "Login" y "Carga de documentos" tienen pantalla funcional.

Los dos backends están desacoplados a nivel de código Python (ninguno importa al otro)
pero comparten la misma base de datos Supabase.

## Cómo está organizada esta documentación

| Carpeta/archivo | Contenido |
|---|---|
| [`modulos/`](./modulos/) | Un subdirectorio por módulo técnico (22 en total), cada uno con `README.md`, `arquitectura.md`, `base_de_datos.md` (si aplica), `reglas.md`, `flujo.md`, `estados.md` (si aplica), `casos_de_uso.md`, `api.md`, `decisiones.md` y `pendientes.md` — algunos módulos chicos (`planes`, `frontend_mi_cuenta`) omiten deliberadamente los documentos que no aportarían contenido verificable adicional, ver sus respectivos `README.md`. |
| [`ia/README.md`](./ia/README.md) | Documentación transversal de los componentes de IA (Gemini): modelos, prompts, flujo técnico, manejo de errores y riesgos. |
| [`reglas-globales.md`](./reglas-globales.md) | Reglas técnicas transversales a todo el repo: autenticación, autorización/RLS, auditoría, manejo de fechas, logging, manejo de errores, convenciones de API. |
| [`glosario.md`](./glosario.md) | Términos de negocio y técnicos usados en el resto de la documentación. |
| [`schema/README.md`](./schema/README.md) | DDL (`extractor_final.sql`) y políticas RLS (`rls_final.sql`) de referencia, tal como están aplicadas en el proyecto Supabase de test. |
| `guia_usuario.html` | Guía de usuario preexistente (no forma parte de este proyecto de documentación técnica). |

## Índice de módulos

### Backend nuevo — `services/presupuestacion/`

**Infraestructura**

- [`core/`](./modulos/core/README.md) — utilidades transversales (errores de dominio, auth, clientes Supabase, stock, auditoría, config); fusiona también `auditoria/` y `services/shared/auth_jwt.py`.

**Pipeline comercial principal**

- [`procesos_comerciales/`](./modulos/procesos_comerciales/README.md) — punto de entrada del pipeline: crea y lista licitaciones/cotizaciones.
- [`extraccion_validacion/`](./modulos/extraccion_validacion/README.md) — puente entre la extracción IA (backend legacy) y las tablas de negocio: materializa `items_proceso` o `comparativas`/`ofertas_items`.
- [`matching/`](./modulos/matching/README.md) — resuelve a qué producto del catálogo corresponde la descripción libre de un renglón (alias de cliente + fuzzy matching).
- [`pricing/`](./modulos/pricing/README.md) — motor de cálculo de precio por ítem y generador del presupuesto inicial.
- [`presupuestos/`](./modulos/presupuestos/README.md) — ciclo de vida del presupuesto ya generado: aprobar, ajustar ítems, presentar (compromete stock).
- [`comparativas/`](./modulos/comparativas/README.md) — lectura curada de renglones ganados/ofertas sin matchear, más asignación manual de proveedor.
- [`compras/`](./modulos/compras/README.md) — ciclo de vida de la orden de compra: crear, confirmar (adjudica), registrar entregas y ajustar stock.

**Maestros y soporte**

- [`catalogo/`](./modulos/catalogo/README.md) — maestro de productos, categorías, proveedores, costos y stock por depósito.
- [`clientes/`](./modulos/clientes/README.md) — maestro de clientes, contactos, formato de documentos por cliente (instrucciones para el prompt de IA) y observaciones.
- [`usuarios/`](./modulos/usuarios/README.md) — alta de cuentas por invitación, cambio de rol, activar/desactivar, eliminar y autoservicio de perfil propio.
- [`droguerias/`](./modulos/droguerias/README.md) — CRUD de "empresas" (tenants): raíz del multi-tenant, de la que dependen 36 tablas vía `drogueria_id`.
- [`planes/`](./modulos/planes/README.md) — catálogo de solo lectura de planes de suscripción por droguería; sin CRUD ni enforcement de límites todavía.
- [`imports/`](./modulos/imports/README.md) — ingesta masiva por lote de productos/costos/stock/proveedores/clientes desde sistemas externos.
- [`eventos/`](./modulos/eventos/README.md) — motor de tareas operativas (puntuales y recurrentes) y el calendario del sistema.
- [`notificaciones/`](./modulos/notificaciones/README.md) — centro de notificaciones internas multi-canal (hoy, sin envío real por ningún canal).
- [`automatizaciones/`](./modulos/automatizaciones/README.md) — motor de reglas evento-condición-acción (hoy, sin disparador real en producción).

### Backend legacy — `services/extraccion/`

- [`extraccion_api/`](./modulos/extraccion_api/README.md) — capa HTTP y de persistencia: recibe el archivo, deduplica, persiste metadata en Supabase, expone CRUD de licitaciones/clientes/extraction results.
- [`extraccion_ia/`](./modulos/extraccion_ia/README.md) — pipeline de IA: parsea el documento y llama a Gemini para extraer datos estructurados a CSV.

### Frontend — `frontend/`

- [`frontend_login/`](./modulos/frontend_login/README.md) — autenticación (Supabase Auth), resolución de rol, guard de rutas, reset de contraseña y aceptación de invitación.
- [`frontend_carga_documentos/`](./modulos/frontend_carga_documentos/README.md) — única pantalla funcional del MVP además de Login: sube documentos y muestra cargas recientes; incluye también el Shell/Navegación (`Sidebar.tsx`).
- [`frontend_mi_cuenta/`](./modulos/frontend_mi_cuenta/README.md) — autogestión de la cuenta propia: editar nombre/apellido, cambiar contraseña, cambiar email y cerrar sesión.

## Estado de la documentación

Las 6 fases del proyecto de documentación original están completas, más una fase de
actualización posterior:

1. Descubrimiento/inventario del repositorio (insumo interno, sin archivo propio).
2. Documentación de los 19 módulos técnicos iniciales (`docs/modulos/`).
3. Documentación transversal de IA (`docs/ia/README.md`).
4. Reglas técnicas transversales (`docs/reglas-globales.md`).
5. Glosario de negocio y técnico (`docs/glosario.md`).
6. Este índice general (`docs/README.md`).
7. **Actualización (esta sesión)**: documentación nueva/ampliada de `usuarios/`
   (invitación por email, activar/desactivar, eliminar, autoservicio de perfil, y
   protección de auto-modificación), `droguerias/` (nuevo), `planes/` (nuevo),
   `core/` (gate de `activo`), `frontend_login/` (reset de contraseña, aceptación de
   invitación y 3 bugs de timing corregidos) y `frontend_mi_cuenta/` (nuevo) — 22 módulos
   en total ahora. `docs/reglas-globales.md` y `docs/glosario.md` fueron revisados y
   ampliados en la misma sesión para reflejar los patrones transversales nuevos.

Toda la documentación (`docs/modulos/`, `docs/ia/`, `docs/reglas-globales.md`,
`docs/glosario.md`) fue generada en julio de 2026 y, al momento de escribir este índice,
todavía no está commiteada al repositorio (solo `docs/schema/` está versionado, desde el
15 de julio de 2026). La actualización de la fase 7 se hizo el 23 de julio de 2026.

## Pendientes y hallazgos relevantes

Resumen de los hallazgos de mayor riesgo/impacto encontrados durante la documentación.
El detalle completo (evidencia de archivo:línea) está en la fuente enlazada — no se
repite acá.

- **RLS incompleta por rol en varias tablas** (`presupuestos`/`presupuesto_items` vía
  `ajustar_item`, `stock_productos`, `cliente_formato_documentos`): las políticas de
  `INSERT`/`UPDATE` no incluyen todos los roles que `require_roles` autoriza a nivel de
  router, y el `service.py` lo resuelve bypaseando RLS con `service_client` — RLS solo es
  fuente de verdad real para lecturas. Ver
  [`reglas-globales.md` §2.3](./reglas-globales.md#23-enforcement-en-rls--y-la-inconsistencia-real-rol-router-vs-rol-rls).
- **`pricing/repository.py` sin validar formato UUID** en `_alcance_or`, el helper de
  filtro dinámico por interpolación directa de string sobre PostgREST — riesgo de
  injection si `cliente_id`/`categoria_id` no tienen formato UUID válido. Ver
  [`modulos/pricing/pendientes.md`](./modulos/pricing/pendientes.md).
- **Bug de negocio: `ajustar_item` no tiene guarda sobre el estado del presupuesto** —
  se puede ajustar un ítem de un presupuesto ya presentado (con stock comprometido) sin
  ninguna validación. Ver [`modulos/presupuestos/pendientes.md`](./modulos/presupuestos/pendientes.md).
- **Bug de UI: el badge de estado de "Cargas recientes" nunca matchea** —
  `STATUS_STYLES` (frontend, claves en inglés) compara contra `doc.status`, que llega en
  español; el badge siempre cae al estilo por default. Ver
  [`modulos/frontend_carga_documentos/pendientes.md`](./modulos/frontend_carga_documentos/pendientes.md).
- **`imports/` duplica lógica de negocio con `catalogo/` y `clientes/`** (versionado de
  costo reimplementado de forma independiente; CRUD paralelo sobre `clientes`), con
  riesgo de drift entre ambas implementaciones. Ver
  [`modulos/imports/pendientes.md`](./modulos/imports/pendientes.md).
- **`automatizaciones/` completo pero sin disparador real en producción** — ningún
  cron/worker llama a `disparar_reglas()` ni `procesar_acciones_pendientes()` fuera de
  los tests. Ver [`modulos/automatizaciones/pendientes.md`](./modulos/automatizaciones/pendientes.md).
- **`procesos_comerciales.estado` escrito sin guardas de transición** — el único
  `UPDATE` de esa columna en todo el repositorio vive en `presupuestos/repository.py`
  (disparado por `presentar_presupuesto`), sin verificar el estado anterior del proceso.
  Ver [`modulos/presupuestos/README.md`](./modulos/presupuestos/README.md#escritura-cruzada-hacia-procesos_comerciales)
  y [`modulos/procesos_comerciales/estados.md`](./modulos/procesos_comerciales/estados.md).
- **`parsers.py` (Vision): el fallback de OCR siempre usa la misma API key**, sin
  round-robin — a diferencia de `robot.py`/`robot_comparativas.py`, que sí rotan keys
  con `get_next_client()`. Todo el tráfico de PDFs escaneados/imágenes se concentra en
  una sola key. Ver [`ia/README.md` §11](./ia/README.md#11-riesgos) (hallazgo 3).
- **Logging asimétrico entre backends**: `services/extraccion` (legacy) tiene 115
  llamadas de logging en 13 archivos; `services/presupuestacion` (nuevo) tiene 1 sola
  llamada en todo el backend. Ver [`reglas-globales.md` §5](./reglas-globales.md#5-logging).
- **Dos contratos de error distintos coexisten**: `presupuestacion/` usa `DomainError`
  con mapeo centralizado a HTTP; `extraccion/` (legacy) levanta `HTTPException`
  directamente, ad hoc por endpoint. Ver
  [`reglas-globales.md` §6](./reglas-globales.md#6-manejo-de-errores).
- **Contradicción sin resolver sobre la tabla legacy `licitaciones`**:
  `procesos_comerciales_client.py:7-11` afirma que esa tabla "ya no existe", pero
  `routers/licitaciones.py` la sigue consultando activamente en 7 endpoints, y el HTML
  legacy (`static/licitaciones.js`, `calendario.js`) sigue llamando a esas rutas. No se
  verificó en esta sesión si la tabla fue eliminada de la base real. Ver
  [`modulos/extraccion_api/pendientes.md`](./modulos/extraccion_api/pendientes.md).

### Hallazgos de la sesión de actualización (julio 2026)

- **3 bugs reales de timing en el login del frontend, encontrados y corregidos en
  vivo**: (1) el router se montaba antes de que `perfil` estuviera resuelto, rebotando
  un deep-link con rol correcto — corregido esperando `perfilLoading` además de
  `loading` (D-LOGIN-005); (2) un usuario desactivado/borrado del lado del backend
  dejaba la UI en "Cargando…" infinito — corregido con logout automático en 401/404 más
  un guard reactivo (D-LOGIN-006); (3) el redirect post-login aterrizaba en `/` en vez
  del destino pedido por una carrera entre el re-render de React y el montaje del router
  — corregido usando hard navigation (`window.location.href`) en vez de
  `router.navigate()` (D-LOGIN-007). Ver
  [`modulos/frontend_login/decisiones.md`](./modulos/frontend_login/decisiones.md)
  D-LOGIN-005/006/007.
- **Bug de autorización corregido: un `admin` podía autopromoverse/autodegradarse,
  autodesactivarse o autoeliminarse** — `cambiar_rol`, `cambiar_activo` y
  `eliminar_usuario` no tenían ninguna guarda contra `usuario_id == creador.id`. Sin
  esta guarda, un único `admin` podía quedar bloqueado sin nadie que pudiera revertirlo.
  Corregido con el mismo chequeo repetido en las tres funciones. Ver
  [`reglas-globales.md` §2.5](./reglas-globales.md#25-protección-de-auto-modificación-y-roles-protegidos-por-diseño)
  y [`modulos/usuarios/reglas.md`](./modulos/usuarios/reglas.md)
  RN-USUARIOS-014/017/023.
- **Bug real reproducido: el usuario técnico `SYSTEM` podía desactivarse por error** —
  antes de esta sesión, la protección de rol solo cubría `superadmin`; el rol `sistema`
  no tenía ninguna protección en `cambiar_activo`. Un admin desactivó por error al
  usuario técnico real `SYSTEM` durante testing manual, lo que motivó extender la
  protección a `sistema` en las tres funciones de gestión de usuarios (`cambiar_rol`,
  `cambiar_activo`, `eliminar_usuario`). Ver
  [`modulos/usuarios/reglas.md`](./modulos/usuarios/reglas.md) RN-USUARIOS-009/019/025.
- **Excepciones no mapeadas de servicios externos rompían CORS en el navegador** —
  corregido, con recomendación de aplicar el mismo patrón a futuras integraciones
  externas: una excepción cruda de un SDK externo (Supabase Auth) no capturada como
  `DomainError` cae al handler `500` que corre fuera de `CORSMiddleware`; el navegador la
  ve como `Failed to fetch` sin mensaje, en vez de un error de dominio legible. Se agregó
  traducción explícita a `ConflictError`/`ValidationError` en la capa de `repository.py`
  de `usuarios` y `droguerias`. Ver
  [`reglas-globales.md` §6.5](./reglas-globales.md#65-recomendación-transversal-mapear-errores-de-servicios-externos-a-domainerror-en-repositorypy).
- **`planes` no tiene ningún enforcement real todavía** — la estructura (tabla, columnas
  de límites, policies RLS) está lista, pero no hay CRUD ni código en ningún backend que
  lea esas columnas para bloquear o limitar algo; decisión explícita documentada en el
  comentario de la propia migración SQL. Ver
  [`modulos/planes/README.md`](./modulos/planes/README.md).
- **RLS más permisiva que la API, también en `droguerias`** — la policy `droguerias_upd`
  permitiría a un `admin` editar su propia droguería, pero el router la restringe a
  `superadmin` únicamente y corre siempre con `service_client`, sin que la policy más
  amplia llegue a ejecutarse — mismo patrón ya documentado para otras tablas (ver punto
  de RLS incompleta más arriba). Ver
  [`modulos/droguerias/decisiones.md`](./modulos/droguerias/decisiones.md)
  D-DROGUERIAS-003.
