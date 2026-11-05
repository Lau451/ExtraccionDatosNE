# Integración con Progress 9.1D

Cómo se conecta la plataforma con Progress hoy, por intercambio de archivos CSV en
ambos sentidos, y cómo se prepara para otros canales sin que los módulos de negocio
cambien. Principios P4–P6 y decisión D-ARQ-004 en [`README.md`](./README.md).

## Decisión

Todo contacto con Progress pasa por **un único módulo, `integracion_progress`**, que
funciona como capa anticorrupción:

- Hacia adentro ofrece un **contrato estable** en términos de negocio (`enviar_oc`, `estado_envio`, `recibir_presupuestos`…).
- Hacia afuera tiene **adaptadores intercambiables**. Hoy el único es el de archivos; mañana puede sumarse una lectura SQL/ODBC o una API del proveedor.
- Lo propio de Progress queda **dentro del adaptador**: columnas, encoding `cp1252`, separador `;`, códigos internos y rutas de carpeta.

Que el canal cambie de archivo a API reemplaza el adaptador y no toca ningún módulo
de negocio. Esto funciona solo porque el contrato asume el canal más restrictivo (P6).

## Estado actual

**[IMPLEMENTADO]** Etapa 1 (`odd/tasks/integracion-progress.md`). Todo lo que conoce
Progress vive en `services/integracion_progress/` y se usa solo por
`services/integracion_progress/api.py` (lo verifica
`tests/integracion_progress/test_dependencias.py`).

| Sentido | Qué viaja | Cómo funciona hoy | Evidencia |
|---------|-----------|-------------------|-----------|
| Nosotros → Progress | OC del cliente | `oc_export` arma las filas y la fachada escribe el CSV en `<PROGRESS_DOCS_DIR>/oc` (en producción, `C:\SACPro\documentos_ia\oc`): escritura atómica, nunca pisa un archivo. Contrato: [`tipos/oc/contrato.md`](../../services/integracion_progress/tipos/oc/contrato.md). | `services/integracion_progress/salida/escritor.py`, `services/presupuestacion/oc_export/service.py` |
| Progress → nosotros | Presupuestos legacy | **Automática:** cada `PROGRESS_ESCANEO_INTERVALO_SEGUNDOS` (300 por defecto) la plataforma lee `<PROGRESS_ENTRADA_DIR>/presupuestos/` y mueve cada archivo a `procesados/` o `errores/`. Se saltean los ocultos (también con el atributo oculto de Windows) y los `.tmp`; un archivo bloqueado o cuyo procesamiento falló sin dejar el registro en error (ej. base caída) queda en la carpeta para el próximo escaneo. **Manual:** un admin sube el archivo en la pantalla de importación (`POST /integracion-progress/presupuestos`). Los dos caminos usan el mismo lector en el backend (UTF-8 o `cp1252`) y el mismo registro, y entregan las filas a `pcp.api`. Contrato: [`tipos/presupuestos/contrato.md`](../../services/integracion_progress/tipos/presupuestos/contrato.md). | `services/integracion_progress/recepcion/`, `services/integracion_progress/tipos/presupuestos/parser.py`, `services/integracion_progress/router.py` |
| Registro | Cada archivo recibido o escrito | Tabla `progress_archivos` (migración 0043): no procesa dos veces el mismo contenido, los archivos con error se pueden reprocesar y un `recibido` colgado más de una hora se reprocesa. Reprocesar reclama el registro (vuelve a `recibido`) para que dos llegadas simultáneas no lo procesen las dos. Listado: `GET /integracion-progress/archivos`. | `services/integracion_progress/registro/`, `supabase/migrations/0043_progress_archivos.sql` |
| Configuración | Carpetas y droguería | `PROGRESS_DOCS_DIR` (salida; sin ella la exportación responde 503), `PROGRESS_ENTRADA_DIR` y `PROGRESS_DROGUERIA_ID` (entrada; sin las dos, la recepción automática queda apagada). | `services/shared/config.py`, `docker-compose.yml` |

**Desvíos que quedan respecto del objetivo:**

- La fachada todavía expone funciones de escritura (`escribir_csv`, `carpeta_oc`…), no el contrato asincrónico `enviar_oc` / `estado_envio` de abajo. Hace falta cuando Progress devuelva archivos de confirmación.
- Las OC exportadas todavía no se anotan en el registro como `salida` (`registrar_salida` existe pero `oc_export` no lo llama).
- El import de PCP legacy (`POST /pcp/imports/legacy`) sigue recibiendo JSON y no pasa por esta capa: no está confirmado que venga de Progress.

## Contrato hacia los módulos

**[RECOMENDACIÓN]**

```
# Envíos (nosotros → Progress): siempre asincrónicos
integracion_progress.api.enviar_oc(oc_id)          -> envio_id
integracion_progress.api.estado_envio(envio_id)    -> pendiente | enviado | confirmado | rechazado
                                                      (+ detalle del rechazo)

# Recepciones (Progress → nosotros): entregadas al módulo dueño
productos.api.sincronizar_desde_progress(lote)      # el dueño aplica sus reglas
compras.api.registrar_presupuestos_legacy(lote)
```

Reglas del contrato:

1. **Ningún envío se confirma en el momento.** Devuelve un id y un estado. La confirmación llega después, por un archivo de respuesta o por el canal que exista en el futuro.
2. **Todo dato recibido lleva origen y antigüedad:** `origen = 'progress'`, `sincronizado_en` y la clave de Progress. La interfaz puede mostrar "actualizado hace 2 h".
3. **El adaptador no escribe tablas ajenas.** Entrega lotes ya validados a la fachada del dueño, que aplica sus propias reglas. Así se evita duplicar reglas como en X-ARQ-004 ([`mapa-modulos.md`](./mapa-modulos.md)).
4. **Mapa de identidades por entidad:** id propio ↔ código Progress. `presupuesto_legacy_map` es el antecedente y se generaliza.

## Flujo de archivos

```
        NOSOTROS → PROGRESS                          PROGRESS → NOSOTROS
módulo ─► enviar_oc()                          carpeta de entrada
              │                                       │
        envío registrado (pendiente)            1. detectar archivo nuevo (solo si está completo)
              │                                 2. registrarlo: nombre, hash, tipo, fecha
        adaptador escribe CSV (atómico)         3. descartar duplicados (mismo hash)
              │                                 4. parsear con el parser del tipo
        estado: enviado                         5. validar → errores por línea
              │                                 6. entregar el lote a la fachada del dueño
   ◄── archivo de confirmación/rechazo ──       7. marcar procesado | con error (reprocesable)
        estado: confirmado | rechazado
```

### Registro de archivos

Cada archivo que entra o sale queda registrado en una tabla propia del módulo:
nombre, hash, tipo, sentido, estado (`recibido → procesado | error`), cantidad de filas,
errores por línea y fechas. Sirve para tres cosas:

- **No procesar dos veces** el mismo archivo.
- **Ver y reprocesar** lo que falló, sin tocar la carpeta a mano.
- **Auditar** qué datos entraron, cuándo y desde qué archivo.

### Estructura del módulo

```
integracion_progress/
  api.py                 contrato hacia los módulos
  recepcion/             genérico, se escribe una vez: vigilar, registrar, deduplicar, reintentar, reportar
  envio/                 genérico: registrar envío, escribir atómico, correlacionar respuesta
  tipos/
    presupuestos/        hoy existe (migrar desde pcp/imports y el parser del frontend)
      contrato.md        especificación del archivo, la que se le entrega al proveedor
      parser.py          archivo → lote validado
      destino.py         a qué fachada se entrega
    oc/                  hoy existe (migrar desde oc_export)
    productos/           futuro: agregar un tipo = agregar una carpeta
    stock/               futuro
    confirmacion_oc/     futuro
```

**Agregar un archivo nuevo** = escribir su `contrato.md`, su parser y elegir el destino.
La recepción, la deduplicación, los errores y la auditoría ya están resueltos.

## Estándar de archivos para el proveedor

**[RECOMENDACIÓN]** Se acuerda con el proveedor de Progress y se aplica a todos los
archivos, en ambos sentidos. Nosotros escribimos cada `contrato.md` y el proveedor
implementa la exportación o la lectura.

| Regla | Detalle | Por qué |
|-------|---------|---------|
| Nombre | `<TIPO>_<identificadores>_<yyyyMMddHHmmss>.csv` | Saber qué es y cuándo se generó sin abrirlo. La OC ya lo cumple. |
| Escritura atómica | Escribir en `.tmp` y renombrar al terminar, o dejar un `.ok` al lado | Evita leer un archivo a medio escribir, el error más común de este tipo de integración. Nuestro escritor de OC ya lo hace. |
| Formato | Encoding `cp1252`, separador `;`, primera fila con encabezados; fechas `yyyy-MM-dd` y decimales con `.`, salvo que el `contrato.md` del tipo diga otra cosa | Un solo parser de bajo nivel para todos los tipos. |
| Identidad | Cada fila trae la clave de Progress de la entidad, siempre en la misma columna | Permite el mapa de identidades y las actualizaciones. |
| Alcance | El contrato declara si el archivo es **foto completa** o **solo cambios** | La foto completa permite detectar bajas; si son solo cambios, las bajas deben venir explícitas. |
| Control | Cantidad de filas en el `.ok` o en una última fila de control | Verificar que el archivo llegó entero. |
| Respuesta | Cada archivo enviado a Progress tiene un archivo de respuesta con el mismo identificador y el resultado (aceptado/rechazado y motivo) | Cerrar el ciclo de cada envío (estado `confirmado`/`rechazado`). |
| Versión | El contrato tiene versión; un cambio incompatible genera un tipo nuevo o `_v2` | Proveedor y plataforma pueden evolucionar sin romperse. |

## Evolución del canal

| Etapa | Canal | Qué cambia |
|-------|-------|------------|
| Hoy | Archivos CSV en ambos sentidos | Se ordena detrás de `integracion_progress` y se automatiza la recepción. |
| Futuro posible | Lectura SQL/ODBC de solo lectura | Nuevo adaptador de lectura; los datos dejan de tener horas de antigüedad. A validar con el proveedor qué permite 9.1D. |
| Futuro posible | Servicio o API del proveedor | Nuevo adaptador de envío y lectura; los envíos se confirman antes, pero el contrato sigue siendo el mismo. |

En ninguna de las etapas cambian los módulos de negocio.
