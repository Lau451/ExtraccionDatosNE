# Módulo Clientes — `services/presupuestacion/clientes/`

## Qué es

Clientes gestiona el maestro de clientes de una droguería (hospitales, obras sociales,
municipios, etc.) y 3 sub-recursos asociados: contactos, formato de documentos por
`doc_type` (instrucciones que se inyectan al prompt de extracción de Gemini) y
observaciones de texto libre. Es el módulo dueño de las 4 tablas `clientes`,
`cliente_contactos`, `cliente_formato_documentos` y `cliente_observaciones`.

El módulo tiene 5 archivos, 686 líneas en total (`models.py` 114, `repository.py` 142,
`service.py` 232, `router.py` 198, `__init__.py` 0 — verificado leyendo cada archivo en
esta sesión), 12 endpoints, sin máquina de estados propia.

## Qué NO hace

- **No ejecuta auditoría.** Se confirmó por grep en esta sesión: 0 referencias a
  `core.audit`, `registrar_cambio`, `registrar_cambios` o
  `registrar_evento_ciclo_vida` en los 4 archivos fuente. Ninguna mutación (alta y baja
  de cliente, upsert de instrucciones de IA, alta/edición de contacto, alta de
  observación) queda registrada en `historial_cambios` — ver
  [`../core/`](../core/) para el mecanismo de auditoría que otros módulos sí usan, y
  [`pendientes.md`](./pendientes.md) P1.
- **`cliente_contactos.activo` no tiene efecto funcional.** El campo existe en el
  modelo (`ClienteContactoUpdate.activo`, `ClienteContactoOut.activo`) y es escribible
  vía `PATCH .../contactos/{id}`, pero ningún query de este módulo lo usa como filtro
  — mismo patrón de deuda ya documentado para `usuarios.activo` en
  [`../usuarios/README.md`](../usuarios/README.md). Ver [`pendientes.md`](./pendientes.md) P3.
- **No borra ningún sub-recurso ni edita/borra observaciones.** Solo `clientes` tiene
  soft-delete (`DELETE /clientes/{id}`); `cliente_contactos`,
  `cliente_formato_documentos` y `cliente_observaciones` no tienen operación de borrado
  en `repository.py`, y `cliente_observaciones` tampoco tiene edición.
- **No tiene `estados.md`.** No hay una máquina de estados: el único campo que podría
  sugerirlo es `clientes.activo`, que sí tiene efecto observable (filtro opcional en
  listado, forzado a `False` por el soft-delete) pero es un booleano de negocio, no un
  enum de estados con transiciones — mismo criterio de omisión ya aplicado en Core y
  Usuarios.

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `clientes/__init__.py` | Vacío. |
| `clientes/models.py` | 3 `Literal` (`DocType`, `CategoriaObservacion`, `TipoCliente`) y 10 modelos Pydantic para `Cliente`, `ClienteContacto`, `ClienteFormatoDocumento` y `ClienteObservacion` (`Create`/`Update`/`Out` según el sub-recurso). |
| `clientes/repository.py` | Acceso a datos puro sobre las 4 tablas, recibe siempre un `Client` inyectado (sin resolverlo internamente). |
| `clientes/service.py` | Reglas de negocio (tenant isolation, upsert, altas parciales) más 7 wrappers `*_para_endpoint` que fijan `get_service_client()`. |
| `clientes/router.py` | 12 endpoints HTTP más el helper `_validar_cliente_y_obtener_drogueria_id` (`router.py:123-139`), que revalida pertenencia de forma independiente de `service.py`. |

## Quién lo consume

Montado en `services/presupuestacion/main.py:48`
(`app.include_router(clientes_router, tags=["clientes"])`), sin prefijo adicional. Ningún
otro módulo de `presupuestacion/` **importa** `clientes/` como módulo Python (confirmado
por grep en esta sesión).

Sin embargo hay dos formas de acoplamiento a nivel de tabla que no pasan por este código:

- **Intra-servicio**: `services/presupuestacion/imports/repository.py:141-185` hace
  CRUD masivo directo sobre la tabla `clientes` (`mapear_clientes_por_codigo`,
  `codigos_activos_clientes`, `insertar_clientes`, `actualizar_cliente`,
  `desactivar_clientes`) para la importación en lote por `codigo_interno`, sin pasar por
  `clientes/repository.py`. Este hallazgo no estaba en el descubrimiento previo del
  módulo — ver [`arquitectura.md`](./arquitectura.md).
- **Cross-servicio**: `services/extraccion/routers/clientes.py` lee la tabla `clientes`
  directo (`.eq("activo", True)`, línea 47) para poblar el selector de cliente del
  formulario de carga; `services/extraccion/main.py` (`_resolver_formato_prompt`,
  líneas 122-149) lee `cliente_formato_documentos` directo (`.eq("activo", True)`,
  línea 137) para inyectar `instrucciones_prompt` al prompt de Gemini al procesar un
  documento. Este módulo controla indirectamente qué le dice el prompt de extracción a
  la IA — ver [`arquitectura.md`](./arquitectura.md) para el diagrama.

Se descartó `procesos_comerciales_client.py` como consumidor: 0 matches en el grep de
esta sesión sobre las 4 tablas del módulo.

## Documentos del módulo

- [`arquitectura.md`](./arquitectura.md) — dependencias hacia Core, patrón de doble
  validación de tenant (router + service), acoplamiento a nivel de tabla con
  `imports/` y con `services/extraccion/`.
- [`base_de_datos.md`](./base_de_datos.md) — las 4 tablas, columnas, CRUD y soft-delete.
- [`reglas.md`](./reglas.md) — reglas de negocio (RN-CLIENTES-NNN).
- [`flujo.md`](./flujo.md) — los 5 flujos principales paso a paso.
- [`casos_de_uso.md`](./casos_de_uso.md) — los 12 endpoints y quién puede invocarlos.
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-CLIENTES-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.

Para `UsuarioPerfil`, `require_roles`, `service_client`/`user_client` y el mecanismo de
auditoría que este módulo NO usa, ver [`../core/`](../core/) — no se repite esa
documentación acá.
