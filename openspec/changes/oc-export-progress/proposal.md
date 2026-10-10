# Propuesta: Exportación de orden de compra a Progress + calendario de compromisos

> Idioma: sigue la convención de `openspec/changes/orden-compra/` y de los cambios archivados
> (español neutro/profesional, igual que los comentarios del código).

> **Cambio derivado de `orden-compra`.** Reemplaza la mitad saliente del "Tramo 3" de
> `openspec/changes/orden-compra/proposal.md` (capacidad `nota-pedido-export`). La mitad entrante
> (`entregas-import`, CSV de retorno de Progress) sigue diferida y fuera de alcance.

## Intent

Una OC hoy ya se extrae, se valida, se ancla al cliente, se vincula contra el presupuesto
(`oc_presupuesto/`) y se planifica en entregas (`oc_entregas/`). Pero no sale del sistema: el
personal la vuelve a tipear en Progress 9.1D (sin API, solo CSV).

La propuesta original asumía que nosotros generábamos la **nota de pedido**. Eso cambió por decisión
de negocio:

- Nosotros exportamos la **OC con su cronograma de entregas**.
- Progress tiene un **gestor de OC** propio donde la aloja, y es Progress quien genera las NOP
  cuando corresponde. Nosotros **no** disparamos ni enviamos la NOP.
- Las entregas futuras (por ejemplo, 2 de 3 entregas en los meses siguientes) tienen que verse en un
  **calendario de compromisos** para que Compras tenga panorama de compras. En esta primera versión
  Compras solo **ve**; acciona en Progress.

> **Corrección de nombre**: notas y propuestas previas mencionan "Progress v8". La versión real es
> **Progress 9.1D**.

## Scope

### En alcance

- Exportación de una OC planificada a un archivo CSV (formato de la sección siguiente) depositado en
  una carpeta del servidor compartida con Progress.
- Transición de `ordenes_compra.estado` de `pendiente` a `emitida` al exportar.
- Precondiciones de exportación (ver Approach) que bloquean con error claro si no se cumplen.
- Calendario de compromisos de solo lectura: vista sobre `entregas_oc` pendientes con fecha
  planificada, más endpoint de lectura y pantalla en el frontend.
- Configuración externa de carpeta de destino y encoding (sin valores fijos en el código).

### Fuera de alcance

- CSV de retorno de Progress (entregado / rechazado / descuento de stock) — formato aún no definido
  por el sistema viejo.
- Generación de NOP — responsabilidad de Progress.
- Acciones sobre compromisos (avisos, responsables, estados propios) — no se usa la tabla `eventos`
  en esta versión.
- Reexportación de OC modificadas (versionado vía `version_numero` / `reemplaza_id`) — el formato
  ya trae la columna `version`, pero el flujo de modificación no se implementa acá.

## Formato del CSV de salida

Definido por nosotros, con las mismas convenciones que el import de presupuestos ya acordado con
Sistemas.

| Aspecto | Valor |
|---|---|
| Forma | Archivo plano, **una fila por renglón × entrega**; cabecera de OC repetida en cada fila |
| Fila de encabezados | Sí |
| Delimitador | `,` |
| Decimal | `,`, y todo número va entre comillas dobles: `"1234,50"` |
| Textos | Entre comillas si contienen `,`, `"` o salto de línea; comillas internas duplicadas (RFC 4180, módulo `csv` de Python) |
| Fecha | `dd/mm/yyyy` |
| Encoding | Windows-1252 por defecto, **configurable**. Caracteres no representables se reemplazan, nunca abortan la exportación |
| Nombre | `OC_{codigo_cliente}_{numero_oc}_v{version}_{yyyyMMddHHmmss}.csv`, con `numero_oc` saneado para ser nombre de archivo válido |
| Escritura | Archivo temporal en la misma carpeta + renombrado atómico al terminar |

### Columnas

| # | Columna | Origen |
|---|---|---|
| 1 | `id_oc` | `ordenes_compra.id` |
| 2 | `numero_oc` | `ordenes_compra.numero_oc` |
| 3 | `version` | `ordenes_compra.version_numero` |
| 4 | `fecha_emision` | `ordenes_compra.fecha_emision` |
| 5 | `codigo_cliente` | `terceros_legacy_map.codigo_legacy` (entidad `cliente`) — código de cliente de Progress |
| 6 | `cuit_cliente` | `terceros.cuit` |
| 7 | `direccion_entrega` | `ordenes_compra.direccion_entrega` |
| 8 | `numero_renglon` | `oc_items.numero_renglon` |
| 9 | `codigo_articulo` | `productos.codigo_interno` — código de artículo de Progress |
| 10 | `descripcion` | `oc_items.descripcion` |
| 11 | `cantidad_total` | `oc_items.cantidad` |
| 12 | `precio_unitario` | `oc_items.precio_unitario` |
| 13 | `numero_entrega` | `entregas_oc.numero_entrega` |
| 14 | `fecha_entrega` | `entregas_oc.fecha_entrega_planificada` |
| 15 | `cantidad_entrega` | `entregas_oc_items.cantidad_planificada` |

## Capabilities

### Nuevas capacidades

- `oc-export-progress`: generar y depositar el CSV de una OC planificada, y marcarla `emitida`.
- `calendario-compromisos`: listar entregas pendientes con fecha planificada, solo lectura.

### Capacidades modificadas

- `orden-compra` (no archivado): su capacidad `nota-pedido-export` queda reemplazada por esta.
  Reconciliar al archivar.

## Approach

**Módulo nuevo** `services/presupuestacion/oc_export/`, con la misma estructura de los módulos
hermanos (`models`, `repository`, `service`, `router`). Dos piezas separadas a propósito:

1. **Construcción de filas** (pura, sin I/O): recibe la OC con renglones, entregas y códigos ya
   resueltos y devuelve las filas del CSV. Es lo que se testea en detalle.
2. **Escritura del archivo** (I/O): serializa con `csv`, aplica encoding, escribe temporal y
   renombra. Es lo único que conoce la carpeta.

Si el día de mañana Progress cambia el formato, o aparece otra vía de integración, se toca una sola
pieza.

**Precondiciones de exportación** (todas bloquean con `ValidationError` y mensaje claro):

- La OC está en estado `pendiente` (no exportada antes, no cancelada).
- Todos los renglones tienen `producto_id` y ese producto tiene `codigo_interno`. Sin código de
  artículo Progress no puede ubicar el producto.
- El cliente tiene código en `terceros_legacy_map`.
- La OC tiene entregas planificadas y, por cada renglón, la suma de `cantidad_planificada` es igual a
  `oc_items.cantidad`.
- Todas las entregas tienen `fecha_entrega_planificada`.

**Orden de efectos**: primero se escribe el archivo, después se pasa la OC a `emitida`. Si el cambio
de estado falla, se borra el archivo recién escrito (mismo criterio de compensación manual que ya usa
`oc_entregas/service.py`).

**Registro de la exportación**: tres columnas nuevas en `ordenes_compra`: `exportado_at`,
`exportado_por` (FK a `usuarios`) y `archivo_exportado` (nombre del CSV). Se escriben en el mismo
`UPDATE` que pasa la OC a `emitida`. Columnas y no tabla aparte porque una OC se exporta una sola vez
por versión; si más adelante se habilita la reexportación, se evalúa una tabla de historial.

**Roles**: exporta el rol `comercial`. Por convención del proyecto, las operaciones de escritura sobre
OC incluyen también a los roles superiores (`_ROLES_OC` en `compras/router.py`: `admin`,
`gerencia`, `lider_comercial`, `comercial`); se sigue ese patrón. El calendario es de lectura y usa
el patrón `_ROLES_LECTURA`, que incluye `compras`.

**Calendario**: una vista SQL `v_compromisos_entregas` sobre `entregas_oc` + `ordenes_compra` +
cliente, con **solo OC `emitida`** (exportada = el usuario completó el flujo y Progress ya la
tiene) y entregas `pendiente`. Es la única fuente de verdad: no se copia nada a `eventos`. Cada
entrega se clasifica en la vista como:

- `futura`: `fecha_entrega_planificada` posterior a hoy.
- `vencida`: fecha pasada y Progress no informó su cumplimiento. Se sigue mostrando, marcada, para
  que se vea que falta la confirmación. En v1, sin CSV de retorno, toda entrega pasada queda así.

Endpoint `GET` de lectura con filtro por rango de fechas, y pantalla en `frontend/src/features/`.

## Affected Areas

| Área | Impacto | Descripción |
|---|---|---|
| `services/presupuestacion/oc_export/` | Nuevo | Construcción de filas, escritura atómica, endpoint de exportación |
| `services/presupuestacion/main.py` | Modificado | Registrar router(s) nuevos |
| `supabase/migrations/0032_*` | Nuevo | Columnas de registro de exportación + vista `v_compromisos_entregas` (+ down) |
| `docs/schema/extractor_final.sql` | Modificado | Snapshot con la vista nueva |
| `docker-compose.yml` / configuración | Modificado | Carpeta de destino montada y variables de configuración |
| `frontend/src/features/` | Nuevo/Modificado | Botón "Exportar a Progress" en la OC + pantalla de calendario |
| `tests/oc_export/` | Nuevo | Unitarios de filas/formato + integración de precondiciones y estado |

## Risks

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| El contenedor no tiene permisos de escritura sobre la carpeta montada | Media | Verificar el montaje con un archivo de prueba al desplegar; carpeta configurable |
| Encoding equivocado (Progress usa otra codepage) | Media | Encoding configurable; se cambia sin deploy de código |
| El importador de Progress no respeta comillas y una descripción con coma corre las columnas | Media | Archivo de prueba con comas, comillas y ñ para Sistemas antes de producción |
| Progress lee un archivo a medio escribir | Baja | Escritura temporal + renombrado atómico |
| Desfase calendario/realidad: sin el CSV de retorno, una entrega cumplida sigue figurando pendiente | Segura en v1 | Se muestran como `vencida` en lugar de ocultarse; se resuelve con `entregas-import` |

## Rollback Plan

Todo es aditivo. Revertir el código quita el endpoint y la pantalla; la vista se elimina con su
migración `down`. Las OC que ya quedaron en `emitida` pueden volver a `pendiente` con un `UPDATE`
puntual. Los archivos ya depositados en la carpeta los gestiona Progress.

## Success Criteria

- [ ] Una OC planificada se exporta a un CSV con el formato acordado y queda en estado `emitida`.
- [ ] Una OC con algún renglón sin producto, sin código de cliente o con entregas que no cierran
      contra el total no se exporta, y el usuario ve el motivo exacto.
- [ ] Una OC ya `emitida` no se puede volver a exportar.
- [ ] Una descripción con coma, comillas y ñ se escribe correctamente en Windows-1252.
- [ ] Cambiar la carpeta o el encoding no requiere tocar código.
- [ ] La OC exportada registra quién la exportó, cuándo y el nombre del archivo.
- [ ] Solo los roles de escritura de OC (incluido `comercial`) pueden exportar.
- [ ] Compras ve en el calendario todas las entregas pendientes de OC emitidas, con cliente, OC,
      fecha y cantidades; las de fecha pasada aparecen marcadas como vencidas.
- [ ] Una OC planificada pero no exportada no aparece en el calendario.

## Open Questions (a resolver antes o durante el diseño)

1. ~~Dónde corre el backend respecto de la carpeta del servidor.~~ **Resuelto**: Progress y los
   contenedores Docker (Windows, aislamiento Hyper-V) corren en el mismo servidor. La carpeta se
   expone a `presupuestacion-api` con un **bind mount** a una ruta del host (no un volumen con
   nombre como `extraccion-output`, que Progress no puede ver), y la ruta dentro del contenedor se
   pasa por variable de entorno. Ruta del host: `C:\SACPro\documentos_ia` (debe existir antes de
   levantar el contenedor: Docker en Windows no crea la carpeta del host). Se monta la carpeta base y
   la aplicación crea la subcarpeta `oc` si no existe, lo que deja lugar a otras subcarpetas de
   integración (por ejemplo, el retorno de Progress) sin tocar `docker-compose.yml`:

   ```yaml
   presupuestacion-api:
     environment:
       - PROGRESS_DOCS_DIR=C:/app/documentos_ia
       - OC_EXPORT_ENCODING=cp1252
     volumes:
       - C:/SACPro/documentos_ia:C:/app/documentos_ia
   ```

> **Antecedente**: `Integracion_Progress_Sistemas.pdf` (30/09/2026) proponía una API REST consumida
> por Progress (OC planificadas, NP informadas, cobertura FIFO, pendientes vencidos). Se decidió
> arrancar por CSV para simplificar; ese diseño queda como evolución futura y sus reglas (NP sin
> referencia a entrega, cobertura FIFO, excedentes, fecha de entrega obligatoria) se retoman cuando
> se aborde el retorno de Progress.
2. ~~Qué OC muestra el calendario.~~ **Resuelto**: solo `emitida`.
3. ~~Entregas vencidas sin confirmación.~~ **Resuelto**: se muestran marcadas como `vencida`.
4. ~~Roles que exportan.~~ **Resuelto**: `comercial` (más superiores, por convención `_ROLES_OC`).
5. ~~Registro de la exportación.~~ **Resuelto**: sí, columnas en `ordenes_compra`.
