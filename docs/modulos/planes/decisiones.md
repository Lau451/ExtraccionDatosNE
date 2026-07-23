# Decisiones de diseño — Planes

Numeración D-PLANES-NNN, verificada contra el código y la migración en esta sesión.

### D-PLANES-001 — El módulo se implementó deliberadamente sin CRUD, solo lectura

- **Decisión**: `planes/` expone únicamente `GET /planes`. No hay `POST`, `PATCH` ni
  `DELETE`, y no existen `repository.py` ni `service.py` — la carga de planes se hace
  por SQL directo contra la base.
- **Motivo**: cita textual del encabezado de la migración que crea la tabla
  (`supabase/migrations/0007_apellido_y_planes.sql:2-7`):

  > "Soporte de schema para el módulo de autenticación/gestión de usuarios completo
  > [...] y estructura de planes por droguería (sin lógica de facturación todavía)."

  y el comentario final de la misma migración (línea 106):

  > "Catálogo de planes por droguería. Solo estructura: sin lógica de facturación ni
  > enforcement de límites todavía."

  Es una decisión explícita y documentada en el propio SQL, a diferencia de la mayoría
  de las decisiones de otros módulos de este proyecto, que no suelen tener un
  comentario tan directo.
- **Ventajas**: la tabla, las columnas de límites (`max_usuarios`,
  `max_documentos_mes`, `almacenamiento_mb`, `funcionalidades`) y las 4 policies RLS
  (`planes_sel`/`ins`/`upd`/`del`) ya existen y están listas para cuando se implemente
  el CRUD y el enforcement, sin necesitar otra migración de schema.
- **Desventajas**: hoy el catálogo de planes es responsabilidad exclusiva de quien
  tenga acceso directo a la base de datos (fuera de la aplicación) — no hay ninguna UI
  ni API para gestionarlo, ni siquiera restringida a `superadmin`, a pesar de que las
  policies `planes_ins`/`upd`/`del` ya están preparadas para ese rol. Ver
  [`pendientes.md`](./pendientes.md) P1.

### D-PLANES-002 — El listado usa `user_client` (RLS) igual que los `GET` de Droguerías, sin capa de servicio

- **Decisión**: `listar_planes_endpoint` consulta `planes` directo con `user_client`
  (`router.py:11-18`), sin pasar por ninguna función intermedia.
- **Motivo**: comentario explícito en el propio código (`router.py:16-17`):

  > "Solo lectura: catálogo de planes, sin CRUD todavía (sin lógica de facturación).
  > RLS (planes_sel) ya permite SELECT a cualquier autenticado."

- **Ventajas**: mínimo código posible para un catálogo de solo lectura sin reglas de
  negocio propias.
- **Desventajas**: ninguna identificada más allá de las generales de no tener una capa
  de servicio (dificulta agregar lógica futura, como filtros adicionales o
  paginación, sin tocar el router directamente) — impacto bajo dado el tamaño actual
  del módulo.
