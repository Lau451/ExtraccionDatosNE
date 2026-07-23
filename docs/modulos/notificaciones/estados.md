# Estados — Notificaciones

Dos máquinas de estado independientes conviven en este módulo: la de la
**notificación** en sí (leída/archivada, dos flags booleanos-por-timestamp) y la de
cada **entrega por canal** (`notificacion_entregas.estado`, un `CHECK` de 5 valores
del que solo se usa 1).

## Estado de `notificaciones`: no hay columna `estado`, son dos timestamps independientes

`notificaciones` no tiene una columna `estado` — el estado de lectura/archivado se
deriva de `leida_at`/`archivada_at`, ambas `NULL` por defecto:

```
                    crear_notificacion (RN-NOTIFICACIONES-001)
                              │
                              ▼
                    (leida_at=NULL, archivada_at=NULL)
                        "no leída, activa"
                    │                        │
     marcar_leida   │                        │  marcar_archivada
     (service.py:69-75)                      │  (service.py:78-84)
                    ▼                        ▼
        (leida_at=now(),          (leida_at=NULL o now(),
         archivada_at=NULL)        archivada_at=now())
         "leída, activa"           "archivada" (leída o no)
                    │                        │
     marcar_archivada                        │  marcar_leida
     (aplicable igual)                       │  (aplicable igual,
                    ▼                        ▼   no bloqueado por estar archivada)
        (leida_at=now(),          (leida_at=now(),
         archivada_at=now())       archivada_at=now())
         "leída y archivada"
```

**No hay ninguna transición inversa** (desarchivar, marcar como no leída) — ni
endpoint HTTP ni función de `service.py` revierte `leida_at`/`archivada_at` a `NULL`.
Confirmado por lectura completa de `router.py` (4 endpoints, ninguno hace `UPDATE ...
SET leida_at = NULL`) y de `service.py` (ninguna función además de `marcar_leida`/
`marcar_archivada` toca esas dos columnas).

**Marcar archivada no exige haber marcado leída primero**: `marcar_archivada` no
verifica `leida_at` antes de setear `archivada_at` — una notificación puede archivarse
directamente sin pasar por "leída". `listar_no_leidas` excluye por `archivada_at IS
NOT NULL` igual que por `leida_at IS NOT NULL` (ambos condicionan el mismo `SELECT`,
`repository.py:33-43`), así que a efectos de "aparece en la bandeja" da igual cuál de
los dos timestamps se setee primero.

**Ambas operaciones son idempotentes en el sentido de que no fallan si se repiten**:
llamar `marcar_leida` sobre una notificación ya leída vuelve a hacer `UPDATE leida_at =
now()` (pisa el timestamp anterior con uno nuevo) — no hay guarda de "ya estaba leída,
no hacer nada" ni error. No verificado con un test específico que llame `marcar_leida`
dos veces seguidas en esta sesión.

[IMPLEMENTADO] para todo lo anterior, confirmado por lectura completa de
`service.py:65-84` y `repository.py:33-63`.

## Estado de `notificacion_entregas.estado`: 5 valores declarados, 1 usado por código

`CHECK ck_ne_estado` (`extractor_final.sql:1029`) declara 5 valores: `pendiente,
enviando, enviada, fallida, cancelada`. El código Python de este módulo (único
escritor de la tabla, junto con el bypass externo de `extraccion/repository.py` que no
toca esta tabla en absoluto) **solo escribe 1**: `pendiente`, fijado como literal en
`service.py:58`, sin ningún parámetro que permita especificar otro valor al crear una
entrega.

```
                    crear_notificacion → crear_entrega (por cada canal)
                              │
                              ▼
                          pendiente
                              │
                              ▼
                        (fin del camino)

  enviando, enviada, fallida, cancelada: valores válidos del CHECK de BD,
  NINGÚN código del repositorio (módulo notificaciones, ni ningún otro
  módulo, confirmado por Grep de "notificacion_entregas" + ".update(" en
  todo el repositorio) los escribe jamás.
```

Confirmado por `Grep` de `"enviando"`, `"enviada"`, `"fallida"`, `"cancelada"` sobre
`services/presupuestacion/notificaciones/` y sobre `tests/notificaciones/` en esta
sesión — cero resultados en ambos casos para los 4 valores no usados. Los otros 3
campos operativos de la fila (`destino`, `proveedor_externo`, `referencia_externa`,
`enviado_at`, `error_msg`, `intentos` más allá del `0` inicial) tampoco se escriben
nunca — ver [`base_de_datos.md`](./base_de_datos.md).

**Quién escribiría cada transición si existiera un worker de envío** (inferencia de
diseño, no código existente): `pendiente → enviando` al tomar la fila de la cola;
`enviando → enviada` con `enviado_at` seteado en éxito, o `enviando → fallida` con
`error_msg` en error; `pendiente/enviando → cancelada` si se cancelara manualmente.
Ninguna de estas transiciones tiene código hoy — [SUPOSICIÓN] de cómo se completaría
el modelo, no una descripción de comportamiento actual. Ver
[`decisiones.md`](./decisiones.md) D-NOTIFICACIONES-001 y
[`pendientes.md`](./pendientes.md), P1.

## Relación entre los dos estados

Son independientes entre sí: una notificación puede estar "leída" mientras su(s)
entrega(s) siguen en `pendiente` para siempre (de hecho, es el único caso posible
hoy, dado que ninguna entrega avanza de estado). El modelo no tiene ninguna regla que
condicione `leida_at`/`archivada_at` al estado de las entregas, ni viceversa — leer la
notificación en la UI web (que consulta `notificaciones`, no
`notificacion_entregas`) no depende de que exista una entrega `web` exitosa, porque
tampoco hay un concepto de entrega "exitosa" en el canal web hoy (la fila de entrega
`web` es un registro sin efecto, no un requisito para que la notificación sea
visible vía `GET /notificaciones/no-leidas`).
