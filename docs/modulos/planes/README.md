# Módulo Planes — `services/presupuestacion/planes/`

## Qué es

Planes es un catálogo de solo lectura de planes de suscripción por droguería. El
módulo es deliberadamente mínimo: introducido junto con `droguerias.plan_id` en la
migración `supabase/migrations/0007_apellido_y_planes.sql` para "dejar preparada la
estructura para soportar en el futuro límites de uso, sin implementar facturación ni
gestión de planes en esta iteración" (comentario del propio archivo de migración,
líneas 2-7).

El módulo tiene 2 archivos con código, 27 líneas en total (`models.py` 11,
`router.py` 18, `__init__.py` no verificado como parte de un directorio de tests —
no existe `tests/planes/`, confirmado con Glob en esta sesión), 1 solo endpoint.

## Qué NO hace

- **No tiene CRUD.** Solo existe `GET /planes`. No hay `POST`, `PATCH` ni `DELETE` de
  planes en `router.py` — no hay `repository.py` ni `service.py` en este módulo, a
  diferencia de todos los demás módulos de `presupuestacion/`. Los planes se cargan
  manualmente por SQL directo contra la tabla `planes`. Ver
  [`decisiones.md`](./decisiones.md) y [`pendientes.md`](./pendientes.md) P1.
- **No hace ningún enforcement de los límites que declara.** Las columnas
  `max_usuarios`, `max_documentos_mes`, `almacenamiento_mb` y `funcionalidades` existen
  en la tabla y se exponen en `PlanOut`, pero no se encontró en todo el repositorio (ni
  en `presupuestacion/` ni en `extraccion/`) ningún código que las lea para bloquear o
  limitar algo — confirmado por grep en esta sesión. Ver
  [`pendientes.md`](./pendientes.md) P1.
- **No tiene lógica de negocio propia.** `router.py` consulta la tabla `planes`
  directo, sin pasar por ninguna capa intermedia — mismo patrón que los `GET` de
  [`../droguerias/`](../droguerias/).
- **No tiene `arquitectura.md`, `flujo.md`, `casos_de_uso.md` ni `estados.md`
  dedicados.** Con 1 solo endpoint de solo lectura, sin reglas de negocio más allá del
  filtro `activo=True` y sin ninguna capa propia (`repository.py`/`service.py`), esos
  documentos no aportarían contenido verificable adicional al que ya está en
  [`api.md`](./api.md) y [`reglas.md`](./reglas.md) — mismo criterio de omisión
  aplicado a otros módulos chicos del proyecto (ver `docs/modulos/frontend_login/` para
  un precedente de módulo con menos de 9 archivos).

## Mapa rápido de archivos

| Archivo | Qué hace |
|---|---|
| `planes/__init__.py` | Vacío. |
| `planes/models.py` | 1 modelo Pydantic, `PlanOut` — solo lectura, sin `PlanCreate` ni `PlanUpdate`. |
| `planes/router.py` | 1 endpoint HTTP: `GET /planes`. |

## Quién lo consume

Montado en `services/presupuestacion/main.py:56`
(`app.include_router(planes_router, tags=["planes"])`), sin prefijo adicional. Ningún
otro módulo de `presupuestacion/` importa `planes/` como módulo Python (confirmado por
grep en esta sesión).

Acoplamiento a nivel de esquema: `droguerias.plan_id` (FK nullable a `planes`, agregada
por la misma migración) es el único vínculo con otro módulo, y se gestiona enteramente
desde [`../droguerias/`](../droguerias/) (`PATCH /droguerias/{id}` con `plan_id` en el
body) — este módulo no expone ninguna forma de asignar un plan a una droguería.

## Documentos del módulo

- [`base_de_datos.md`](./base_de_datos.md) — la tabla `planes`, columnas, RLS.
- [`reglas.md`](./reglas.md) — la única regla de negocio del módulo (RN-PLANES-001).
- [`api.md`](./api.md) — API pública de cada archivo.
- [`decisiones.md`](./decisiones.md) — decisiones de diseño (D-PLANES-NNN).
- [`pendientes.md`](./pendientes.md) — auditoría técnica P1/P2/P3.

Para `UsuarioPerfil`, `get_current_user` y `user_client`, ver [`../core/`](../core/) —
no se repite esa documentación acá.
