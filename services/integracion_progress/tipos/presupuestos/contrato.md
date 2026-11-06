# Contrato de archivo — `presupuestos` (Progress → plataforma)

**Versión:** 1 · **Sentido:** entrada · **Dueño en la plataforma:** `services/pcp` (import legado de presupuestos)

Este documento es la especificación que se le entrega al proveedor de Progress.
Describe el archivo tal como la plataforma lo acepta hoy
(`services/integracion_progress/tipos/presupuestos/parser.py`). Las reglas comunes a
todos los archivos están en
[`docs/arquitectura/integracion-progress.md`](../../../../docs/arquitectura/integracion-progress.md#estándar-de-archivos-para-el-proveedor).

## Entrega

| Tema | Regla |
|------|-------|
| Carpeta | `<carpeta de entrada>/presupuestos/`. En producción: `C:\SACPro\documentos_ia\entrada\presupuestos\` (configurable, `PROGRESS_ENTRADA_DIR`). |
| Escritura | Escribir con un nombre que empiece con `.` o termine en `.tmp` y renombrar al terminar, o dejar al lado un `<nombre>.ok`. La plataforma ignora los archivos ocultos (nombre con `.` o atributo oculto de Windows), los `.tmp`, los modificados en los últimos 30 segundos y los que cambian mientras los lee (los reintenta en la próxima revisión). Sin `.ok` ni renombrado, un archivo cuya escritura se pausa más de 30 segundos puede leerse incompleto. |
| Nombre | Recomendado: `PRESUPUESTOS_<yyyyMMddHHmmss>.csv`. El nombre no se usa para identificar el contenido. |
| Después de leerlo | La plataforma lo mueve a `procesados/` o a `errores/` dentro de la misma carpeta (a `errores/` también un duplicado de un archivo que quedó con error). Nunca lo borra. Si no lo puede leer (por ejemplo, porque sigue abierto por quien lo escribe) o no lo puede registrar, lo deja en la carpeta y lo reintenta en la próxima revisión. |
| Duplicados | Un archivo con exactamente el mismo contenido que otro ya recibido no se vuelve a procesar. |
| Carga manual | También se puede subir desde la pantalla de importación (`POST /integracion-progress/presupuestos`). Tamaño máximo: 10 MB; un archivo más grande se rechaza con HTTP 413 y el mensaje "El archivo supera el tamaño máximo de 10 MB", sin registrarlo. |

## Formato

| Tema | Regla |
|------|-------|
| Encoding | `cp1252` o UTF-8 (con o sin BOM). |
| Separador | `;` (también se acepta `,`; se detecta en la primera línea). |
| Encabezados | Primera línea, sin distinguir mayúsculas. El orden de las columnas es libre. |
| Comillas | Estilo CSV estándar: un campo entre `"` puede contener separadores y saltos de línea; `""` es una comilla literal. |
| Números | Coma decimal y sin separador de miles: `1250,50`. |
| Fechas | `dd/mm/aaaa` o `aaaa-mm-dd`. |
| Filas vacías | Se ignoran. |

## Columnas

| Columna | Obligatoria | Contenido |
|---------|-------------|-----------|
| `codigo_cliente` | Sí | Código del cliente en Progress. |
| `razon_social_cliente` | Sí (columna) | Razón social del cliente. |
| `numero_presupuesto` | Sí | Número del presupuesto en Progress. Agrupa las filas de un mismo presupuesto. |
| `renglon` | Sí | Número de renglón, entero. |
| `descripcion_producto` | Sí | Descripción del producto. |
| `cantidad_producto` | Sí | Cantidad, número. |
| `proceso_comercial` | No | `1` o `2`. |
| `fecha_generacion` | No | Fecha del presupuesto. |
| `codigo_producto` | No | Código interno del producto. Si no coincide con un producto de la plataforma, la fila se importa sin producto. |
| `precio_producto` | No | Precio unitario, número. |
| `importe_total` | No | Importe total del presupuesto, número. |

## Validación y resultado

- **El archivo se acepta o se rechaza entero.** Con un solo error no se importa ninguna fila.
- Los errores se informan por línea del archivo, por ejemplo: `falta codigo_cliente`, `renglón no es un número entero`, `cantidad_producto no es numérica (formato esperado: 1250,50)`, `fecha_generacion inválida (use dd/mm/aaaa o aaaa-mm-dd)`, `proceso_comercial debe ser 1 o 2`, `Falta la columna requerida "<columna>"`.
- Un presupuesto que ya fue importado (mismo `numero_presupuesto` para la misma droguería) no se vuelve a crear: se informa como `existente`.
- Cada archivo queda en el registro de archivos (`progress_archivos`) con su estado: `procesado` o `error`, con el detalle de los errores.
- Pendiente: un archivo de respuesta hacia Progress con el resultado.
