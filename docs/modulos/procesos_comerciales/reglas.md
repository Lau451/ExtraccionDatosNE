# Reglas — Procesos Comerciales

Todas las reglas fueron verificadas contra el código real (`service.py`,
`repository.py`) y sus tests (`tests/procesos_comerciales/test_service.py`) en esta
sesión.

### RN-PROCESOS-001 — Una cotización no admite campos de seguimiento formal de licitación

- **Descripción**: si `clase == "cotizacion"` y alguno de `apertura`, `vencimiento`,
  `modalidad`, `tipo_gestion` o `comparativa_pedida` viene seteado (truthy), la
  creación se rechaza antes de tocar la base de datos.
- **Condición**: `body.clase == "cotizacion"` y al menos uno de los 5 campos de
  seguimiento es truthy (`comparativa_pedida` se evalúa como `body.comparativa_pedida
  or None`, para que el valor `False` por defecto no dispare la guarda).
- **Resultado**: `ValidationError("Una cotización no admite campos de seguimiento de
  licitación: " + campos_ofensores)`, listando por nombre cada campo seteado.
- **Prioridad**: Alta.
- **Archivo**: `services/presupuestacion/procesos_comerciales/service.py:12-34`
  (`_validar_campos_de_seguimiento`).
- **Observaciones**: [IMPLEMENTADO]. Cita textual verificada del comentario que precede
  la función, `service.py:13-16`:

  > "# Constraint real de la tabla (ck_proc_cotizacion_sin_seguimiento, no versionada
  > # como migración en el repo -- confirmada empíricamente contra la BD de test):
  > # una cotización no puede tener ninguno de los campos de seguimiento formal de
  > # una licitación (apertura, vencimiento, modalidad, tipo_gestion, comparativa_pedida)."

  El comentario documenta un `CHECK` de base de datos (`ck_proc_cotizacion_sin_seguimiento`)
  que no tiene una migración versionada en este repositorio — ver D-PROCESOS-003 en
  [`decisiones.md`](./decisiones.md). El test
  `tests/procesos_comerciales/test_service.py:39-57`
  (`test_crear_cotizacion_con_apertura_rechaza_con_validation_error`) tiene un docstring
  (`:42-46`) que referencia `docs/schema/extractor_final.sql` como fuente del `CHECK`;
  esa referencia se menciona acá tal cual mas **no** fue verificada línea por línea
  contra ese SQL en esta sesión (fuera del alcance definido para esta documentación).
  Cobertura adicional: `tests/procesos_comerciales/test_service.py:18-35`
  (cotización sin campos de seguimiento, `ValidationError` no se dispara) y
  `tests/procesos_comerciales/test_service.py:60-80`
  (licitación con `apertura`+`modalidad`, se crea sin problema).

### RN-PROCESOS-002 — El listado "activos" excluye por defecto los estados terminales

- **Descripción**: `listar_procesos_comerciales` con `activos=True` (el default)
  excluye los procesos cuyo `estado` sea `adjudicado`, `perdido`, `cerrado` o
  `cancelado`.
- **Condición**: `activos=True` (query param del endpoint, default `True`).
- **Resultado**: `query.not_.in_("estado", _ESTADOS_TERMINALES)`, con
  `_ESTADOS_TERMINALES = ("adjudicado", "perdido", "cerrado", "cancelado")`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/procesos_comerciales/repository.py:9`
  (constante), `:25-26` (aplicación condicional).
- **Observaciones**: [IMPLEMENTADO]. Cita textual verificada del comentario que precede
  la constante, `repository.py:5-8`:

  > "# Estados que ya no aceptan nuevos documentos/comparativas vinculados -- mismo
  > # criterio que usaba el legacy services/extraccion/routers/licitaciones.py:listar_activas
  > # (filtraba fuera de la tabla vieja lo que no estuviera 'abierta'/'en_evaluacion'),
  > # adaptado al vocabulario de estados de procesos_comerciales."

  **Matiz verificado sobre este comentario**: releyendo
  `services/extraccion/routers/licitaciones.py:listar_activas` (`:119-130`), la
  implementación legacy usa una **allowlist positiva de 2 estados**
  (`.in_("estado", ["abierta", "en_evaluacion"])`) sobre la tabla vieja `licitaciones`,
  mientras que este módulo usa una **blocklist de 4 estados** sobre un vocabulario de
  8 estados en `procesos_comerciales`. El criterio conceptual coincide (excluir del
  listado por defecto lo que ya no está en curso), pero la implementación es inversa
  (allowlist vs. blocklist) y el vocabulario de estados no es 1:1 entre ambas tablas —
  el comentario del código es correcto en espíritu, pero no describe una migración
  literal del código legacy. Verificada en
  `tests/procesos_comerciales/test_service.py:83-105`
  (`test_listar_activos_excluye_estados_terminales`, confirma que un proceso en
  `cerrado` desaparece con `activos=True` y reaparece con `activos=False`).

### RN-PROCESOS-003 — Toda creación de proceso comercial se audita como evento de ciclo de vida

- **Descripción**: inmediatamente después del INSERT, se registra un evento de
  auditoría de tipo "creación" para el proceso comercial recién creado.
- **Condición**: cualquier llamada exitosa a `crear_proceso_comercial` (que haya
  pasado RN-PROCESOS-001 y el INSERT).
- **Resultado**: `registrar_evento_ciclo_vida(client, entidad="proceso_comercial",
  entidad_id=proceso["id"], drogueria_id=drogueria_id, tipo_cambio="creacion",
  origen="usuario", usuario_id=usuario_id)`.
- **Prioridad**: Media.
- **Archivo**: `services/presupuestacion/procesos_comerciales/service.py:60-68`.
- **Observaciones**: [IMPLEMENTADO]. `registrar_evento_ciclo_vida` es de
  `core/audit.py` — ver [`../core/`](../core/) para el mecanismo. No hay un test en
  `tests/procesos_comerciales/test_service.py` que verifique el contenido del evento de
  auditoría directamente, pero los fixtures de limpieza de los 3 tests que crean
  procesos (`_borrar_proceso`, `test_service.py:11-15`, y
  `seed_proceso_comercial_factory` en `conftest.py:19-24`) borran explícitamente de
  `historial_cambios`, evidencia indirecta de que la auditoría efectivamente escribe
  ahí en el flujo real.

### RN-PROCESOS-004 — El estado inicial `"abierto"` lo asigna la base de datos, no el service

- **Descripción**: el service nunca envía la clave `"estado"` en el dict que inserta;
  el valor inicial es un default de columna en la BD, invisible desde este código
  Python.
- **Condición**: cualquier alta de proceso comercial (licitación o cotización).
- **Resultado**: `estado = "abierto"` tras el INSERT, confirmado empíricamente por
  `tests/procesos_comerciales/test_service.py:30`
  (`assert proceso["estado"] == "abierto"`).
- **Prioridad**: Baja.
- **Archivo**: `services/presupuestacion/procesos_comerciales/service.py:41-58` (el
  dict insertado no incluye `"estado"` en ninguna de sus 14 claves).
- **Observaciones**: [IMPLEMENTADO] el hecho de que el service no lo envía. El origen
  del default (`DEFAULT 'abierto'` en el DDL, presumiblemente) es "Pendiente de
  definición funcional" — vive fuera de este código Python, en un schema no leído en
  esta sesión. Hallazgo adicional confirmado al releer el mismo dict de inserción: la
  columna `fecha` (`models.py:49`) tampoco aparece entre las claves insertadas — mismo
  patrón que `estado`, no verificado como default de BD pero consistente con la misma
  ausencia. Ver [`base_de_datos.md`](./base_de_datos.md).
