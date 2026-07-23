# Flujos — Eventos

Los 3 flujos principales del módulo. Cada paso cita `archivo:línea` verificado en esta
sesión.

## Flujo 1 — Alta de evento con dependencia (`POST /eventos`, `depende_de_id` seteado)

1. El router exige `require_roles(*_ROLES_ESCRITURA)` —
   `("admin", "gerencia", "lider_comercial", "comercial", "compras")`
   (`router.py:33`, `:55`).
2. `crear_evento_endpoint` llama a `crear_evento_para_endpoint(drogueria_id=
   usuario.drogueria_id, body=body, usuario_id=usuario.id)` (`router.py:57`) — sin pasar
   `origen`, así que el default `"usuario"` de `crear_evento` (`service.py:39`) aplica.
3. `crear_evento_para_endpoint` resuelve `get_service_client()` y delega en `crear_evento`
   (`service.py:214-215`).
4. Como `body.depende_de_id is not None` (`:42`), se busca la dependencia con
   `repo.obtener_evento` (`:43`):
   - Si no existe → `ValidationError("El evento del que depende no existe")` (`:44-45`),
     corta acá. El INSERT nunca se ejecuta (RN-EVENTOS-001).
   - Si existe con `estado != "completado"` → `estado = "bloqueado"` (`:46-47`).
5. `repo.crear_evento` hace el INSERT con las 17 columnas del dict de `:51-71`
   (incluye `estado` ya resuelto en el paso 4, `origen`, y las 6 FKs opcionales sin
   validar salvo `depende_de_id` — RN-EVENTOS-005).
6. `registrar_evento_ciclo_vida(tipo_cambio="creacion", origen=
   _ORIGEN_EVENTO_A_ORIGEN_CAMBIO["usuario"] == "usuario", ...)` audita la creación
   (`:73-81`, RN-EVENTOS-004 — mapeo trivial para `"usuario"`, sin traducción real).
7. El endpoint responde con `EventoOut`, `estado` en `"bloqueado"` o `"pendiente"` según
   el paso 4 (`router.py:53`).

## Flujo 2 — Completar un evento con dependientes (`POST /eventos/{id}/completar`)

1. El router exige `require_roles(*_ROLES_ESCRITURA)` (`router.py:80`).
2. `completar_evento_endpoint` llama a `completar_evento_para_endpoint(evento_id=
   evento_id, drogueria_id=usuario.drogueria_id, usuario_id=usuario.id)` (`:82-84`).
3. `completar_evento_para_endpoint` resuelve `get_service_client()` y delega en
   `completar_evento` (`service.py:226-229`).
4. `completar_evento` obtiene el evento con `obtener_evento` (valida tenant vía
   `NotFoundError` si no coincide `drogueria_id`, `:85-89`) y guarda su `estado`
   anterior (`:142-143`).
5. `repo.actualizar_evento` fija `estado = "completado"`, `fecha_real = now()`
   (`:144-152`).
6. `registrar_cambio(campo="estado", valor_anterior=estado_anterior,
   valor_nuevo="completado", origen="usuario", batch_id=uuid4())` audita el propio
   evento (`:153-164`).
7. `repo.listar_bloqueados_por_dependencia(depende_de_id=evento_id)` trae los IDs de
   todos los eventos `bloqueado` que dependían de este (`:166`, RN-EVENTOS-002).
8. Por cada uno: `repo.actualizar_evento(estado="pendiente")` (`:167-169`) +
   `registrar_cambio(campo="estado", valor_anterior="bloqueado",
   valor_nuevo="pendiente", batch_id=uuid4() nuevo por cada dependiente)`
   (`:170-181`). Ningún tercer nivel de dependencia se resuelve en esta misma llamada
   (ver nota de RN-EVENTOS-002).
9. El endpoint responde con el `EventoOut` del evento recién completado —
   `router.py:78` no devuelve la lista de dependientes desbloqueados; para verlos hace
   falta un `GET /eventos?estado=pendiente` aparte o `GET /eventos/{id}/bloqueo` sobre
   cada uno.

## Flujo 3 — Generación de instancias recurrentes (`generar_instancias_recurrentes`, sin endpoint HTTP)

Esta función **no tiene endpoint HTTP ni disparador real** (RN-EVENTOS-006) — el flujo
se documenta igual porque es funcionalmente completo y testeado; solo falta lo que lo
invoque. Así funcionaría si algo la llamara:

1. Un llamador externo (hoy: solo un test) invoca
   `generar_instancias_recurrentes(client, usuario_scheduler_id=...)` (`service.py:316`)
   — `client` debe ser `service_client` (sin RLS): no hay wrapper `_para_endpoint` para
   esta función, a diferencia de las demás operaciones de `eventos`.
2. `repo.listar_recurrentes_a_ejecutar(client)` trae todas las plantillas de **todas las
   droguerías** con `activa = True AND proxima_ejecucion <= now()` (`repository.py:119-
   128`) — sin filtro de `drogueria_id`, coherente con ser un job de sistema, no una
   operación por-tenant.
3. Por cada plantilla (`service.py:321-376`):
   a. Se arma el dict de la instancia con los campos heredados de la plantilla
      (`tipo`, `titulo`, `descripcion`, `prioridad`, `cliente_id`, `proveedor_id`,
      `responsable_id`, `metadata`), `estado="pendiente"`, `origen="sistema"`,
      `evento_recurrente_id=plantilla["id"]`, `fecha_programada=
      plantilla["proxima_ejecucion"]` (`:322-341`).
   b. `repo.crear_evento` inserta la instancia (`:322`).
   c. `registrar_evento_ciclo_vida(tipo_cambio="creacion", origen="sistema", ...)`
      audita la creación de la instancia (`:342-350`) — usa `usuario_scheduler_id` como
      `usuario_id`, un ID que debe existir en `usuarios` (o la auditoría fallaría por
      `FK`, no verificado en esta sesión si `historial_cambios.usuario_id` tiene `FK`).
   d. `regla = rrulestr(plantilla["rrule"], dtstart=ejecutada_en)`,
      `proxima = regla.after(ejecutada_en)` recalcula la siguiente ocurrencia
      (`:353-355`, RN-EVENTOS-003).
   e. Si `fecha_fin` está seteada y `proxima` la supera (o ya no hay `proxima`), la
      plantilla se desactiva (`:357-365`).
   f. `repo.actualizar_evento_recurrente` persiste `proxima_ejecucion`,
      `ultima_generacion=now()`, `instancias_generadas += 1`, `activa` (`:367-376`).
4. La función devuelve la cantidad de instancias generadas en la corrida (`:378`) — sin
   distinguir por drogueria ni loguear cuáles plantillas se desactivaron.

Ver [`pendientes.md`](./pendientes.md) para el análisis de riesgo de que este flujo no
esté conectado a nada.
