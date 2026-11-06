# Contrato de archivo — `oc` (plataforma → Progress)

**Versión:** 1 · **Sentido:** salida · **Dueño en la plataforma:** `services/presupuestacion/oc_export` (arma las filas); la escritura es de `services/integracion_progress/salida`

Este documento es la especificación que se le entrega al proveedor de Progress.
Describe el archivo tal como la plataforma lo escribe hoy
(`services/presupuestacion/oc_export/filas.py` y
`services/integracion_progress/salida/escritor.py`). Las reglas comunes a todos los
archivos están en
[`docs/arquitectura/integracion-progress.md`](../../../../docs/arquitectura/integracion-progress.md#estándar-de-archivos-para-el-proveedor).

## Entrega

| Tema | Regla |
|------|-------|
| Carpeta | `<PROGRESS_DOCS_DIR>/oc/`. En producción: `C:\SACPro\documentos_ia\oc\`. |
| Nombre | `OC_<codigo_cliente>_<numero_oc>_v<version>_<yyyyMMddHHmmss>.csv`, hora de Buenos Aires. Los caracteres que no son letras, números o `-` se reemplazan por `-`. |
| Escritura | Atómica: la plataforma escribe `.<nombre>.tmp` en la misma carpeta y lo renombra al terminar. Progress debe ignorar los archivos que empiezan con `.`. |
| Unicidad | Nunca se pisa un archivo existente. La OC exportada queda marcada (`exportado_at`, `archivo_exportado`) y su plan de entregas queda bloqueado. |
| Disparo | Una persona exporta la OC desde la plataforma (`POST /ordenes-compra/{id}/exportar-progress`). |

## Formato

| Tema | Regla |
|------|-------|
| Encoding | `cp1252` (configurable con `OC_EXPORT_ENCODING`). Un carácter que no existe en el encoding sale como `?`. |
| Separador | `;` |
| Fin de línea | CRLF |
| Encabezados | Primera línea, con los nombres de la tabla de abajo, en ese orden. |
| Comillas | Solo cuando el campo contiene `;`, comillas o saltos de línea. |
| Números | Punto decimal y dos decimales: `1250.50`. |
| Fechas | `dd/mm/aaaa`. |

## Columnas

Una fila por renglón × entrega planificada con cantidad mayor a 0, ordenadas por
`numero_renglon` y luego `numero_entrega`.

| # | Columna | Contenido |
|---|---------|-----------|
| 1 | `id_oc` | Identificador de la OC en la plataforma. |
| 2 | `numero_oc` | Número de la OC del cliente. |
| 3 | `numero_presupuesto` | Presupuesto del que viene el renglón (puede variar por renglón). |
| 4 | `version` | Versión de la OC. |
| 5 | `fecha_emision` | Fecha de emisión de la OC. |
| 6 | `codigo_cliente` | Código del cliente en Progress. |
| 7 | `cuit_cliente` | CUIT del cliente. |
| 8 | `direccion_entrega` | Dirección de entrega. |
| 9 | `codigo_postal_entrega` | Código postal de entrega. |
| 10 | `notas` | Notas de la entrega. |
| 11 | `numero_renglon` | Número de renglón de la OC. |
| 12 | `codigo_articulo` | Código interno del producto. |
| 13 | `descripcion` | Descripción del renglón. |
| 14 | `cantidad_total` | Cantidad total del renglón. |
| 15 | `precio_unitario` | Precio unitario. |
| 16 | `numero_entrega` | Número de la entrega planificada. |
| 17 | `fecha_entrega` | Fecha de la entrega. |
| 18 | `cantidad_entrega` | Cantidad de esa entrega. |

## Pendiente

- **Archivo de respuesta de Progress** (estándar, regla "Respuesta"): mismo identificador que la OC enviada y el resultado (aceptada / rechazada y motivo). Con eso la OC pasa de *enviada* a *confirmada* o *rechazada* en la plataforma.
- **Diferencia de formato a unificar con el proveedor:** este archivo usa punto decimal y el de presupuestos usa coma decimal.
