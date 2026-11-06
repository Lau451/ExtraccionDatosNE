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

| Sentido | Qué viaja | Cómo funciona hoy | Evidencia |
|---------|-----------|-------------------|-----------|
| Nosotros → Progress | OC del cliente | **[IMPLEMENTADO]** CSV escrito en `<PROGRESS_DOCS_DIR>/oc` (en producción, `C:\SACPro\documentos_ia\oc`). La escritura es atómica (temporal + renombre) y nunca pisa un archivo existente. Nombre: `OC_{codigo_cliente}_{numero_oc}_v{version}_{yyyyMMddHHmmss}.csv`. | `services/presupuestacion/oc_export/escritor.py:32-66`, `docker-compose.yml` |
| Progress → nosotros | Presupuestos legacy | **[IMPLEMENTADO]** Un admin sube el CSV exportado por Progress; el frontend lo parsea y envía las filas al backend. La idempotencia se apoya en `presupuesto_legacy_map`. | `frontend/src/features/presupuestos-import/parsearCsvPresupuestos.ts`, `services/pcp/imports/router.py:40-55`, `services/pcp/imports/repository.py:133-143` |
| Configuración | Carpeta de intercambio | `progress_docs_dir`; si no está configurada, la exportación responde 503. | `services/shared/config.py:35-37` |

**Desvíos respecto del objetivo:**

- El conocimiento de Progress está repartido en tres lugares (`oc_export`, `pcp/imports` y un parser en el frontend), sin un dueño.
- El formato del archivo de presupuestos se interpreta en el frontend. En el objetivo, el parser vive en el adaptador del backend y es único.
- La recepción es manual. En el objetivo, la plataforma detecta los archivos nuevos (la carga manual puede seguir existiendo como alternativa).

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
