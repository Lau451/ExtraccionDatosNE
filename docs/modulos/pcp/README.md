# Módulo PCP — `services/pcp/`

## Qué es

Un PCP ("pedido de mejora de precio", término de dominio que se deja sin
traducir) es una solicitud de mejora de precio a proveedores, elevada desde
una `presupuesto` comercial hacia Compras. Hoy Comercial elige a mano los
renglones y Compras negocia por fuera del sistema: sin worklist centralizado,
sin catálogo de proveedores, sin historial trazable de negociación, y una
consulta por producto en vez de una por proveedor. Nace del change
`gestor-pcp` (`openspec/changes/gestor-pcp/`) para centralizar ese flujo.

> **No es una "orden de compra"**: el change `orden-compra` (diferido) modela
> pedidos de venta cliente→droguería. Ningún nombre, tabla ni código se
> comparte entre ambos.

Es un módulo de **nivel superior**, propiedad de Compras, hermano de
`services/terceros/`, `services/productos/` y `services/presupuestacion/`
bajo `services/` — no un submódulo de presupuestación (D1, ver
[`decisiones.md`](./decisiones.md)). `presupuestacion` es solo una
dependencia de lectura (para derivar `drogueria_id`/`proceso_comercial_id`
del `presupuesto_id` de origen) más dos llamadas de servicio (`pricing` para
el repricing automático y `notificaciones` para el aviso interno).

Gobierna **9 tablas** nuevas (migraciones `0011_pcp_modelo.sql` +
`0012_pcp_extras.sql`, ver [`base_de_datos.md`](./base_de_datos.md)) y se
organiza en **9 subdirectorios** bajo `services/pcp/`:

| Subdirectorio | Rol |
|---|---|
| `gestion/` | Header del PCP, máquina de estados, listado y filtros. |
| `renglones/` | Detalle de renglón, contexto producto/proveedor, selección de proveedores. |
| `catalogo/` | Asociación producto↔proveedor ("proveedores disponibles"). |
| `negociacion/` | Registro del resultado de negociación (incluye `no_cotiza`) y cierre del PCP. |
| `historial/` | Auditoría dedicada, append-only. |
| `consultas/` | Agrupamiento cross-PCP por proveedor + generación de PDF. |
| `sugerencias/` | Sugerencias de agrupación por cantidad y de reutilización de precio reciente. |
| `mensajeria/` | Puerto de envío saliente (`MensajeriaPort`) + adaptador por defecto que no envía nada. |
| `documentos/` | Renderer de PDF (`reportlab`) + plantillas Jinja2 — soporte, no una capacidad propia. |

`documentos/` y `mensajeria/` no exponen router propio (son soporte de
`consultas`/`negociacion`); `historial/` tampoco tiene router propio (ver más
abajo). Los 6 subdirectorios restantes sí lo tienen, agregados en
`services/pcp/router.py` y montados una sola vez en
`services/presupuestacion/main.py` (`app.include_router(pcp_router,
tags=["pcp"])`).

## Estado real de la implementación (PR1-PR12, completo)

Implementado y probado en producción de test: **PR1-PR12** (97/97 tareas del
`tasks.md`). `pcp-legacy-import` (Fase 8, tareas 8.1-8.8) fue el último en
cerrarse: el contrato del export legado (13 columnas, fila por renglón) se
confirmó con el usuario (D8), y `services/pcp/imports/` implementa el
find-or-create de `procesos_comerciales`/`presupuestos`/`items_proceso` para
los PCP legados que todavía no tienen contraparte en el presupuestador nuevo
— reutilizando `pcp_legacy_map` como única ancla de idempotencia (sin tabla
de mapeo adicional). La RPC `upsert_pcp_legacy` (0012_pcp_extras.sql)
predata esa expansión de alcance y quedó sin usar; el flujo real vive en
Python, igual que el resto de los submódulos de `services/pcp/`.

## La máquina de estados del PCP

Secuencia fija, sin saltos ni retrocesos (D2, `gestion/service.py`):

```
nueva → en_gestion → esperando_respuesta → cerrada
```

`cerrada` no tiene transiciones salientes: es terminal. Cada transición
escribe un evento `estado_cambiado` en `pcp_historial` con estado
anterior/nuevo y usuario (nunca un valor de costo). El cierre real
(`negociacion/service.py::cerrar_pcp`) no es un simple cambio de estado: es
un orquestador que valida, delega la transición en
`gestion_service.cambiar_estado` (reusa el mapa de transiciones, nunca lo
bypasea) y dispara el feedback loop a Comercial — ver la sección siguiente y
[`decisiones.md`](./decisiones.md) D10.

## El feedback loop de dos fases hacia Comercial

Cuando un PCP se cierra, Comercial necesita enterarse del resultado. El
módulo lo resuelve en dos fases, ambas ya implementadas:

- **Fase A — email, siempre activa**: `cerrar_pcp` arma el PDF con el
  resultado completo del PCP (todos los renglones, todos los resultados de
  negociación) y lo envía por email a quien solicitó el PCP
  (`pcp.solicitante_id`, resuelto vía `auth.admin.get_user_by_id` porque
  `usuarios` no tiene columna `email` — vive en `auth.users`). Con el
  adaptador de mensajería por defecto (`log`) esto es un no-op registrado:
  el módulo funciona completo sin ningún proveedor de mensajería real
  configurado.
- **Fase B — notificación interna + repricing automático, detrás de un
  flag**: si `PCP_REPRICING_AUTOMATICO` está activo, además se crea una
  `notificaciones` interna (`tipo='pcp_cerrada'`, reusando
  `services/presupuestacion/notificaciones/`) y, si el `presupuesto` de
  origen todavía está `generado`/`en_revision` (nunca si ya está
  `aprobado`/`presentado`), se dispara automáticamente
  `pricing.service.generar_presupuesto_para_endpoint` para recalcular el
  presupuesto con el precio mejorado. Ambas cosas quedan registradas como
  evento `notificacion_enviada` en `pcp_historial`.

Las dos fases están implementadas ya (no es "fase A ahora, fase B después"
como sugería el proposal original) — la Fase B simplemente vive apagada por
defecto (`PCP_REPRICING_AUTOMATICO=False`) hasta que `presupuestacion` sea el
sistema de referencia primario.

## Qué NO hace

- **No importa nada de otro `repository` de `services/pcp/**` desde
  `services/presupuestacion/`** — la única puerta es `services.pcp.router`
  (montaje) o, para un consumidor futuro fuera de `main.py`,
  `services.pcp.api` (D1, [`decisiones.md`](./decisiones.md)). Verificado por
  `tests/pcp/test_dependencias.py` (`ast`, mismo criterio que
  `tests/terceros/test_dependencias.py`).
- **No importa el legado**: ver "Estado real de la implementación" arriba.
- **No expone un endpoint HTTP de historial**: `pcp-historial` es append-only
  por ausencia de métodos de servicio (`agregar_evento`/`listar_eventos`
  únicamente, sin `actualizar_*`/`eliminar_*`), no por un router que rechace
  un verbo. Ningún requisito de spec fuerza todavía una superficie HTTP
  dedicada.
- **No guarda ningún campo de costo** en ninguna tabla del módulo (D2, D6) —
  el valor siempre se deriva en lectura desde `precios_proveedor`/
  `costos_productos`, nunca se cachea.
- **No nombra ningún proveedor de mensajería** en código ni en el valor por
  defecto de configuración (D9) — el adaptador `log` no envía nada realmente.

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `services/pcp/roles.py` | `ROLES_LECTURA_PCP`/`ROLES_ESCRITURA_PCP` (D11) — compartidas por los 6 routers. |
| `services/pcp/errors.py` | Códigos Postgres compartidos (`UNIQUE_VIOLATION`, `CHECK_VIOLATION`) — no lógica de traducción. |
| `services/pcp/router.py` | Agrega los 6 routers de submódulo en un único `APIRouter`. |
| `services/pcp/api.py` | Fachada unidireccional: reexporta modelos/funciones de servicio de todos los submódulos. |
| `services/pcp/gestion/*` | `Pcp` + máquina de estados + listado. |
| `services/pcp/renglones/*` | `PcpRenglon` + selección de proveedores. |
| `services/pcp/catalogo/*` | `ProductoProveedor`. |
| `services/pcp/negociacion/*` | `RegistrarResultadoNegociacion` + `cerrar_pcp`. |
| `services/pcp/historial/*` | `agregar_evento`/`listar_eventos`, sin router. |
| `services/pcp/consultas/*` | `AgruparConsultaCreate` + envío. |
| `services/pcp/sugerencias/*` | Consultas puras de sugerencia, sin schema propio (D12). |
| `services/pcp/mensajeria/*` | `MensajeriaPort` + `LoggingMensajeriaAdapter` + `get_mensajeria()`. |
| `services/pcp/documentos/*` | `PdfRenderer` (Protocol) + `ReportlabPdfRenderer` + plantillas Jinja2. |

## Quién lo consume

- `services/presupuestacion/main.py` monta `pcp_router` (`app.include_router(pcp_router, tags=["pcp"])`).
- `services/pcp/**` consume, como dependencia de solo lectura permitida por
  D1: `services.presupuestacion.pricing.service`,
  `services.presupuestacion.notificaciones.service`, `services.terceros.api`
  y `services.productos` — nunca el `repository` de otro módulo.
- Ningún otro módulo consume `services.pcp.api` todavía; existe como punto de
  entrada preparado para un consumidor futuro (mismo criterio que
  `services/terceros/api.py`).

## Documentos del módulo

- [`base_de_datos.md`](./base_de_datos.md) — las 9 tablas nuevas, la
  columna FK agregada a `precios_proveedor`, RLS y el mecanismo de selección
  reusado.
- [`decisiones.md`](./decisiones.md) — D1-D12 de `design.md`, en palabras
  propias, más los hallazgos reales de esta corrida de SDD.

Para `UsuarioPerfil`, `require_roles`, `get_service_client`/`get_user_client`
y las excepciones compartidas, ver `services/shared/` (ya extraído por el
change `terceros-modelo`) — `services/pcp/` las consume sin depender de
`services/presupuestacion/core/`.
