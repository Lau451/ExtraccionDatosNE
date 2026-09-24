# Diseño: Matching de orden de compra contra presupuesto

> Idioma: sigue la convención ya establecida en `openspec/changes/orden-compra/` (proposal.md,
> design.md y los specs están en español, igual que los comentarios del código). Registro
> neutro/profesional.

> **Cambio derivado de `orden-compra`.** Este diseño asume implementados y mergeados a `dev` los
> Tramos 1 y 2 del cambio padre, y se apoya directamente en sus decisiones: D3 (el ancla siempre la
> pone un click humano), D11 (`oc_items.producto_id` es nullable y su ausencia es visible) y D13.1
> (`oc_items.numero_renglon` es un ordinal interno 1..N asignado al confirmar). Cuando este
> documento dice "D*n* del cambio padre" se refiere a `openspec/changes/orden-compra/design.md`.

## Technical Approach

El matching se implementa como **una pantalla de reconciliación y cuatro endpoints**, sobre
**cuatro columnas aditivas en `oc_items`** y **cero tablas nuevas**. No hay motor, no hay batch, no
hay estado intermedio que mantener: el servidor calcula sugerencias en cada lectura y solo persiste
lo que un humano confirmó.

Tres capas, en el orden en que el operador las recorre:

1. **Ranking de presupuestos candidatos** (`oc_presupuesto/service.py`): dada una OC ya confirmada
   con su `cliente_id` resuelto, se buscan los presupuestos de ese cliente y se puntúa cada uno por
   cuántos renglones de la OC tienen un `precio_unitario` que coincide **exacto** con algún renglón
   suyo. El filtro de precio se **empuja a Postgres** como un `in_()` sobre el conjunto de precios
   distintos de la OC (D3), así que la consulta devuelve solo coincidencias reales.
2. **Vínculo renglón a renglón** dentro del presupuesto elegido: mismo filtro de precio exacto. Un
   match único es una sugerencia; varios matches al mismo precio se **ordenan** por similitud de
   descripción con `rapidfuzz` + `normalizar_descripcion` (D7). Ninguno se aplica solo.
3. **Confirmación granular**: un click escribe `oc_items.presupuesto_item_id` y hereda
   `producto_id` del lado del presupuesto, en una sola operación. Sin "guardar todo".

El principio que ordena todo el diseño, y que es el mismo del cambio padre: **el precio es la clave
de join, la descripción es solo el orden de presentación, y el humano es siempre la compuerta**.
De ahí se derivan dos invariantes que valen para todo el documento:

- **Nada se escribe sin un click.** El estado `sugerido` no existe en la base: se calcula en cada
  lectura. Lo único persistido es la decisión humana (D4).
- **El precio sugiere, no autoriza.** Un vínculo manual contra un renglón cuyo precio no coincide es
  legal y se marca como tal (D4, `vinculo_origen`). El precio nunca convierte un problema blando
  (no matchea por redondeo) en uno duro (el renglón no se puede vincular nunca).

Specs cubiertos: `oc-presupuesto-candidato` (§ D2, D3), `oc-presupuesto-vinculacion` (§ D4–D9) y el
delta de `orden-compra-validacion` (§ D10).

---

## Correcciones de hechos sobre la propuesta

Verificadas contra el código y el esquema reales durante esta fase. No invalidan la propuesta, pero
cambian el fundamento de varias decisiones y deben propagarse a tasks.

| # | Afirmación de la propuesta | Hecho verificado | Impacto |
|---|---|---|---|
| **C1** | (implícito) "un presupuesto se identifica en pantalla por su número" | `presupuestos` **no tiene ninguna columna de número legible** (`docs/schema/extractor_final.sql:677-701`). El `numero_presupuesto` del import legado vive en `presupuesto_legacy_map.codigo_legacy` (`0015_presupuesto_legacy_map.sql:30,36`). Peor: la política `prelm_sel` (`docs/schema/rls_final.sql`) restringe el SELECT a `('superadmin','admin','gerencia','compras')` — **excluye a `comercial` y `lider_comercial`**, que son justamente los roles que hacen matching | La etiqueta del candidato necesita fallback y un camino de lectura propio. Ver **D2.1** |
| **C2** | (implícito en "FK nullable en `oc_items`") "se puede poner una FK compuesta como las demás" | `presupuesto_items` **no tiene `UNIQUE (id, drogueria_id)`**: solo `PRIMARY KEY (id)` y `uq_pi (presupuesto_id, item_proceso_id)` (`extractor_final.sql:703-736`). Sus hermanas sí lo tienen (`uq_pre_id_drog`, `uq_ip_id_drog`, `uq_oc_id_drog`) | La FK compuesta de **D4** exige agregar `uq_pi_id_drog` en la migración 0026. Es aditivo y **no puede fallar**: `id` ya es PK, así que el par `(id, drogueria_id)` es único por construcción |
| **C3** | (implícito) "una tabla/columna nueva necesita RLS nueva" | `oc_items` **ya tiene política de UPDATE** para exactamente `('admin','gerencia','lider_comercial','comercial')` (`rls_final.sql:298`, `oci_upd`) — la misma tupla literal que `_ROLES_VALIDAR` del cambio padre. Y `presupuestos`, `presupuesto_items`, `items_proceso` y `procesos_comerciales` tienen SELECT **solo por tenant, sin filtro de rol** (`rls_final.sql:209,235,259,270`) | **Cero políticas RLS nuevas en todo el cambio.** Las columnas nuevas heredan `oci_upd`, y todo el camino de lectura funciona con el *user client*. Ver **D12** |
| **C4** | "el join es `oc_items.precio_unitario = presupuesto_items.precio_unitario`" | Cierto, con dos filtros obligatorios que la propuesta no menciona: `presupuesto_items.precio_unitario` es **nullable** y existe `excluido BOOLEAN NOT NULL DEFAULT FALSE` + `motivo_exclusion` | El conjunto de candidatos se acota a `excluido = FALSE AND precio_unitario IS NOT NULL` (**D3**). Un renglón excluido nunca se cotizó al cliente, así que no puede ser el origen de un renglón de su OC |
| **C5** | "el presupuesto tiene la descripción y el `producto_id`" | Repartido en dos tablas: `presupuesto_items` tiene precio y `producto_id`, **pero no descripción**; la descripción y el `numero_renglon` viven en `items_proceso`, alcanzable por `presupuesto_items.item_proceso_id` (**NOT NULL**). Y `producto_id` existe en **ambas** tablas | La columna izquierda exige un segundo `select` contra `items_proceso` (**D3**), y la herencia de producto es un `COALESCE` de dos orígenes (**D6**) |
| **C6** | "falta una consulta *presupuestos de un cliente* en `presupuestos/repository.py`" | `presupuestos` **no tiene `cliente_id`**: tiene `proceso_comercial_id NOT NULL`, y el cliente vive en `procesos_comerciales.cliente_id` (nullable) | La consulta es de **dos pasos** y vive en el repository del módulo nuevo. **`presupuestos/repository.py` no se modifica**: se reutiliza `listar_items_presupuesto` tal cual, como la propuesta ya anticipaba. Corrige la tabla § Affected Areas de la propuesta |
| **C7** | "`ResultadoValidarExtraccion` gana `orden_compra_id`" | **El backend ya lo tiene**: `extraccion/models.py:101`, junto con `entregas_creadas`, `renglones_sin_producto` y `extracciones_validadas` (commit `3b37fca3`, parte del cambio padre). `_materializar_orden_compra` ya lo propaga (`service.py:758,825`). El desincronizado es el **espejo TypeScript**: `frontend/src/lib/api/extracciones.ts:104-113` no tiene ninguno de los cuatro | **D10 no es un cambio de contrato de API**, es sincronización de tipos del frontend más el cableado de la navegación. Corrige dos filas de § Affected Areas (`extraccion/models.py` y `extraccion/service.py` pasan de "Modificado" a **sin cambios**) |

---

## Architecture Decisions

### D1 — El vínculo apunta a `presupuesto_items`, no a `items_proceso`

**Choice**: la FK nueva es `oc_items.presupuesto_item_id → presupuesto_items (id, drogueria_id)`.
La descripción, el `numero_renglon` y el `producto_id` de respaldo se alcanzan por el hop ya
existente `presupuesto_items.item_proceso_id → items_proceso.id`, que es **NOT NULL** (C5).

**Alternatives considered**:

- *(a)* FK a `items_proceso.id`. **Rechazada por pérdida de información**: `items_proceso` pertenece
  al **proceso comercial**, no al presupuesto. Un proceso puede tener varios presupuestos
  (`presupuestos.proceso_comercial_id` no es único; `pricing/repository.py:160-169` busca
  explícitamente "el presupuesto abierto" de un proceso, lo que solo tiene sentido si puede haber
  más de uno). Apuntar al `item_proceso` deja sin registrar **contra qué cotización** se reconcilió
  la OC, que es exactamente el hecho de negocio que este cambio produce. Además, el precio — la
  clave de todo el mecanismo — no vive ahí (`items_proceso` solo tiene `monto_estimado`,
  `extractor_final.sql:611`).
- *(b)* Las dos FK (`presupuesto_item_id` + `item_proceso_id`). **Rechazada**: la segunda es
  derivable de la primera por una columna NOT NULL, así que sería un dato duplicado que puede
  divergir. Es el mismo criterio que el cambio padre aplicó para no guardar
  `proceso_comercial_id` en `presupuesto_legacy_map` (`0015:5-8`).
- *(c)* Tabla puente `oc_item_presupuesto_item`. **Rechazada — ver D4**.

**Rationale**: `presupuesto_items` es el único lado que tiene simultáneamente el precio (la clave de
join), la pertenencia a un presupuesto concreto (el hecho que queremos registrar) y un camino NOT
NULL hacia la descripción. `presupuesto_items` **implica** `items_proceso`; lo inverso no es cierto.

### D2 — Ranking de presupuestos: sin filtro de estado, sin ventana de fecha, tope de 5

> Resuelve la Open Question #3 de la propuesta.

**Choice**: se consideran **todos** los presupuestos del cliente, sin filtrar por `estado` ni por
proximidad a `ordenes_compra.fecha_emision`. Se devuelven solo los que puntúan (≥ 1 coincidencia
exacta de precio), ordenados por:

| Orden | Criterio | Motivo |
|---|---|---|
| 1 | `renglones_oc_con_coincidencia` DESC | Es la señal validada con datos reales |
| 2 | `generado_at` DESC | Ante empate, la cotización más reciente es la que el cliente tuvo a la vista |
| 3 | `presupuesto_id` ASC | Desempate final **determinista**, para que la respuesta sea estable entre llamadas |

Tope: **5 candidatos**. El primero es `presupuesto_sugerido_id`; sugerido no es elegido.

**Alternatives considered**:

- *(a)* Filtrar por `estado IN ('aprobado','presentado','adjudicado')`. **Rechazada**: hoy todos los
  presupuestos van a entrar por el import legado, que nace en el `estado` que el import le ponga
  (`presupuestos.estado DEFAULT 'generado'`). Filtrar por estado tiene una probabilidad alta de
  ocultar **el único presupuesto que existe** y dejar la pantalla vacía sin explicación. El puntaje
  por precio ya es un filtro mucho más fuerte y mucho más honesto que el estado.
- *(b)* Ventana de fecha respecto de `fecha_emision` de la OC. **Rechazada**: `fecha_emision` es
  nullable y proviene de una extracción de Gemini sobre un documento de terceros (D6 del cambio
  padre la declara opcional). Filtrar por un dato opcional y potencialmente mal extraído descarta
  candidatos correctos en silencio. La fecha **se muestra** en la lista de candidatos — informa al
  humano, no decide por él.
- *(c)* Devolver todos los que puntúan, sin tope. **Rechazada**: la lista es un selector de
  pantalla; más de 5 opciones deja de ayudar a decidir. El tope se aplica **después** del orden, así
  que nunca esconde al mejor. `presupuestos_del_cliente` (total sin puntaje) viaja en la respuesta
  para que la UI pueda decir "hay 12 presupuestos de este cliente, ninguno coincide en precio" en
  vez de "no hay presupuestos", que sería falso.

**Rationale**: el ranking es una ayuda de navegación, no una regla de negocio. Cualquier filtro
adicional agrega una forma de equivocarse en silencio, y el humano elige igual.

**Semántica de casos vacíos** — ninguno es un error:

| Situación | Respuesta | HTTP |
|---|---|---|
| El cliente no tiene ningún presupuesto | `candidatos=[]`, `presupuestos_del_cliente=0`, advertencia explícita | 200 |
| Tiene presupuestos pero ninguno coincide en precio | `candidatos=[]`, `presupuestos_del_cliente=N`, advertencia distinta de la anterior | 200 |
| La OC está anclada por proceso comercial (`cliente_id IS NULL`) | `ValidationError` — el mecanismo no aplica | 422 |

#### D2.1 — La etiqueta del candidato: `numero_presupuesto` con fallback y lectura por service client

**Choice**: `CandidatoPresupuesto.numero_presupuesto` se resuelve contra
`presupuesto_legacy_map.codigo_legacy` **con el service client**, acotado a los `presupuesto_id` que
el endpoint **ya autorizó**. Si no hay fila (presupuesto cargado a mano, no importado), el campo
viaja `null` y la UI cae a `nombre_proceso` + `generado_at`.

**Rationale**: C1 — `presupuestos` no tiene número legible y la RLS de `presupuesto_legacy_map`
excluye a `comercial` y `lider_comercial`, que son la mayoría de los usuarios de esta pantalla. Las
alternativas eran peores: aflojar `prelm_sel` toca la RLS de un módulo ajeno (el import legado) por
una etiqueta; y mostrar un UUID truncado obliga al operador a adivinar. El service client acá no
amplía el alcance de datos — solo traduce ids que el usuario ya puede leer — y el valor traducido
(un número de presupuesto) no es sensible. Queda anotado como deuda: cuando el import legado se
construya, conviene evaluar mover `numero_presupuesto` a `presupuestos` como columna propia.

### D3 — El precio exacto se empuja a Postgres como filtro, no se resuelve con un join

**Choice**: el acceso a datos es PostgREST, igual que todo el backend. El "join" se arma así:

```python
# oc_presupuesto/repository.py -- pseudocódigo del camino de lectura
precios = {q2(i["precio_unitario"]) for i in oc_items}            # set de Decimal, escala 2
proc_ids  = procesos_comerciales.select("id").eq(drogueria).eq(cliente)
pres_ids  = presupuestos.select(...).in_("proceso_comercial_id", proc_ids)
candidatos = (presupuesto_items
    .select("id, presupuesto_id, item_proceso_id, producto_id, precio_unitario, cantidad_ofertada")
    .in_("presupuesto_id", pres_ids)
    .in_("precio_unitario", [str(p) for p in precios])   # <-- el filtro ES el join
    .eq("excluido", False))                              # C4
```

Tres puntos que no son negociables en la implementación:

1. **Normalización de escala.** Ambas columnas son `NUMERIC(15,2)`, pero el `in_()` de PostgREST
   compara texto. Todo precio se `quantize(Decimal("0.01"))` y se serializa con `str()` antes de
   entrar al filtro, y la comparación en Python se hace sobre `Decimal`, nunca sobre `float`.
   `109.750` y `109.75` son el mismo precio y **deben** producir la misma cadena.
2. **`precio_unitario IS NULL` se excluye solo**: un `NULL` nunca entra en un `in_(...)`. El filtro
   `excluido = FALSE` sí hay que escribirlo (C4).
3. **Troceo del `in_()`**: los `in_()` sobre `proceso_comercial_id` y `presupuesto_id` se emiten en
   lotes de **200 ids**, y los resultados se concatenan. Es el mismo criterio de paginación
   defensiva que `identidad/repository.py:40-66` ya aplica con sus páginas de 1000: PostgREST viaja
   por querystring y una lista larga revienta el límite de URL.

La descripción de cada candidato se trae en un segundo `select` contra `items_proceso`
(`in_("id", item_proceso_ids)`, mismo troceo) y se une en Python (C5).

**Alternatives considered**:

- *(a)* Traer todos los `presupuesto_items` del cliente y filtrar en Python. **Rechazada**: un
  cliente grande con años de cotizaciones puede tener decenas de miles de renglones, y traerlos
  todos para descartar el 99% es exactamente el patrón que C7 del cambio padre marcó como problema
  en `listar_terceros`. Con el `in_()` de precios, lo que vuelve **son** las coincidencias.
- *(b)* Una vista SQL o una función RPC que haga el join en la base. **Rechazada por consistencia**:
  ningún repository del backend hace joins; todos son `select`/`filter` de PostgREST con la
  composición en el service (`presupuestos/repository.py`, `pricing/repository.py`). Una vista nueva
  agregaría un objeto de base que hay que versionar, migrar y mantener fuera del código, para un
  join de dos tablas que el filtro ya resuelve.
- *(c)* PostgREST embedded resource (`select("*, items_proceso(*)")`). **Rechazada**: no hay
  precedente en el repositorio, depende de que PostgREST detecte la FK y hace ilegible la forma del
  `dict` que devuelve el repository. Dos selects explícitos son más largos y más predecibles.

**Rationale**: el mecanismo ya se validó corriendo este join contra la base real (SAMCo Rafaela,
2 renglones, cero ambigüedad). Lo que este diseño aporta es **cómo se expresa ese join en el stack
que el proyecto ya usa**, sin introducir una forma nueva de hablar con la base.

### D4 — El vínculo son cuatro columnas aditivas en `oc_items`: sin tabla puente y sin columna `estado`

> Resuelve las Open Questions #1 y #2 de la propuesta.

**Choice**: `oc_items` gana cuatro columnas. No hay tabla nueva.

| Columna | Tipo | Significado |
|---|---|---|
| `presupuesto_item_id` | `UUID NULL` | El renglón del presupuesto del que este renglón de OC hereda. FK compuesta contra `presupuesto_items (id, drogueria_id)` (C2) |
| `vinculo_descartado` | `BOOLEAN NOT NULL DEFAULT FALSE` | El humano declaró que este renglón **no está** en el presupuesto elegido. Es una afirmación, no una ausencia |
| `vinculo_origen` | `TEXT NULL` | `'precio_exacto'` \| `'manual'`. Cómo se llegó al vínculo, congelado al confirmar |
| `vinculo_confirmado_por` / `vinculo_confirmado_at` | `UUID NULL` / `TIMESTAMPTZ NULL` | Quién apretó el botón y cuándo |

```sql
CONSTRAINT ck_oci_vinculo_excluyente CHECK (NOT (vinculo_descartado AND presupuesto_item_id IS NOT NULL)),
CONSTRAINT ck_oci_vinculo_origen     CHECK ((presupuesto_item_id IS NULL) = (vinculo_origen IS NULL)),
CONSTRAINT ck_oci_vinculo_origen_val CHECK (vinculo_origen IS NULL OR vinculo_origen IN ('precio_exacto','manual'))
```

**El estado de tres valores del spec se deriva, no se guarda**:

| `presupuesto_item_id` | `vinculo_descartado` | `estado` expuesto por la API |
|---|---|---|
| NOT NULL | FALSE (forzado por el CHECK) | `confirmado` |
| NULL | TRUE | `sin_presupuesto` |
| NULL | FALSE | `pendiente` (estado cero, el default de toda fila) |

**Alternatives considered**:

- *(a)* **Tabla puente** `oc_item_presupuesto_item`. **Rechazada por innecesaria.** Una FK nullable
  en `oc_items` ya expresa N:1 de forma nativa: N filas de `oc_items` pueden apuntar a la misma fila
  de `presupuesto_items`, que es literalmente el caso de negocio pedido (el cliente parte en su
  documento un renglón que cotizamos como uno solo). Una tabla puente solo hace falta para 1:N o
  M:N — que un renglón de OC se alimente de **varios** renglones de presupuesto — y nadie lo pidió.
  El costo de agregarla igual no es neutro: una tabla más con su RLS, sus GRANTs, su join extra en
  cada lectura, y la posibilidad estructural de dos filas para un mismo renglón de OC, que habría
  que prohibir con otro índice único. Se agrega el día que aparezca el caso 1:N, no antes.
- *(b)* Una columna `vinculo_estado TEXT NOT NULL DEFAULT 'pendiente'` con los tres valores.
  **Rechazada por redundante y por peligrosa**: `confirmado` es exactamente
  `presupuesto_item_id IS NOT NULL`, así que la columna guardaría dos veces el mismo hecho — y dos
  copias del mismo hecho **divergen** (una actualización parcial deja `estado='confirmado'` con la
  FK en NULL, o al revés, y ninguna consulta sabe cuál creer). Lo único que la FK no puede expresar
  es la diferencia entre "todavía no lo miré" y "lo miré y no está", que es **un** bit. El booleano
  guarda ese bit y nada más, y el CHECK hace imposible el estado contradictorio.
- *(c)* Persistir también la **confianza del desempate** (`confianza_vinculo NUMERIC(5,2)`), como la
  propuesta sugería en OQ #1. **Rechazada**: la confianza es una propiedad de la *sugerencia*, no de
  la *decisión*, y es recomputable en cualquier momento a partir de las dos descripciones. Lo que no
  es recomputable — y por eso sí se guarda — es **si el humano aceptó una sugerencia respaldada por
  el precio o la pasó por arriba**: eso es `vinculo_origen`, un valor discreto que sobrevive incluso
  si alguien después edita `presupuesto_items.precio_unitario`
  (`presupuestos/repository.py::actualizar_presupuesto_item` existe y esa columna es mutable), que
  es justamente el escenario en el que derivarlo daría la respuesta equivocada.
- *(d)* Reutilizar `items_proceso.estado_matching` / `confianza_matching`. **Fuera de alcance por
  decisión explícita de la propuesta**, y además incorrecto: esos campos pertenecen al motor de
  catálogo y viven del lado del presupuesto, que es el lado compartido — N renglones de OC apuntando
  al mismo renglón de presupuesto no pueden tener cada uno su propio estado en una sola fila. El
  estado **tiene** que vivir del lado de `oc_items`. Este cambio no lee ni escribe esos campos.

**Rationale**: cuatro columnas aditivas sobre una tabla que ya tiene la RLS correcta (C3) tienen el
blast radius más chico posible: ninguna tabla nueva, ninguna política nueva, ningún GRANT nuevo,
ningún join extra en las lecturas existentes. Y el diseño hace **estructuralmente imposible** el bug
que más importa en un mecanismo con confirmación humana: que la base diga "confirmado" sin que haya
un vínculo, o que haya un vínculo que la base llame "pendiente".

**Índice**:

```sql
CREATE INDEX idx_oci_presupuesto_item ON oc_items (presupuesto_item_id)
  WHERE presupuesto_item_id IS NOT NULL;
```

Parcial porque la enorme mayoría de las filas son NULL y siguen siéndolo. Este índice **es** el que
sostiene el aviso de reutilización de D5: la consulta es siempre "quién más apunta a este renglón".

### D5 — N:1 se permite; el aviso es una consulta, nunca un constraint

**Choice**: no hay ninguna restricción de base que limite cuántos `oc_items` apuntan a un mismo
`presupuesto_item_id`. El aviso se calcula en cada lectura de la pantalla y viaja en el modelo del
renglón de presupuesto:

| Campo | Cómo se calcula |
|---|---|
| `renglones_oc_vinculados` | `count(oc_items WHERE presupuesto_item_id = X)`, **sin excluir la OC actual** |
| `renglones_oc_vinculados_otras_oc` | De los anteriores, cuántos pertenecen a otra `orden_compra_id` |
| `cantidad_vinculada` | `sum(oc_items.cantidad)` de todos ellos, comparable contra `cantidad_ofertada` |

La UI muestra el aviso cuando `renglones_oc_vinculados >= 2`, o cuando
`cantidad_vinculada > cantidad_ofertada`. **Nunca deshabilita el botón de confirmar.**

**Alcance: toda la droguería, no solo la OC actual.** El riesgo que la propuesta nombra es
sobre-comprometer un renglón cotizado, y ese riesgo no se detiene en el borde de una OC: el mismo
presupuesto puede ser consumido por dos OC distintas del mismo cliente en compras parciales. Un
aviso que solo mira la OC en pantalla daría "todo bien" en el caso más caro.

**Alternatives considered**:

- *(a)* `UNIQUE (presupuesto_item_id)` y permitir N:1 con una excepción manual. **Rechazada**:
  invierte el default contra el caso de negocio real y confirmado.
- *(b)* `CHECK` de cantidad (`sum(cantidad) <= cantidad_ofertada`). **Rechazada dos veces**: es
  imposible como CHECK (es una agregación entre filas y tablas) y sería incorrecto como regla — un
  cliente puede legítimamente comprar más de lo cotizado, y bloquear eso obligaría al operador a
  mentir en la pantalla para poder seguir.
- *(c)* Calcular el aviso en el frontend, sobre los datos ya cargados. **Rechazada**: el frontend
  solo tiene los renglones de **esta** OC, así que sería ciego justo en el caso de (b) de arriba.

**Rationale**: la propuesta pidió "suave y no bloqueante" y esa es una decisión de producto, no una
limitación técnica. Expresarla como consulta en vez de constraint mantiene esa promesa literal: no
hay ningún camino en el que el sistema impida registrar lo que el cliente realmente pidió. Y
`cantidad_vinculada` convierte el aviso de "ojo, esto se repite" en "ojo, esto se pasó de lo
cotizado", que es la información que efectivamente importa.

### D6 — Confirmar hereda `producto_id`; que no haya producto **no** es un caso especial

**Choice**: confirmar un vínculo escribe, en un solo `UPDATE`:

```python
producto_heredado = presupuesto_item["producto_id"] or item_proceso["producto_id"]  # C5

campos = {
    "presupuesto_item_id": presupuesto_item_id,
    "vinculo_descartado": False,
    "vinculo_origen": "precio_exacto" if coincide_precio else "manual",
    "vinculo_confirmado_por": usuario_id,
    "vinculo_confirmado_at": now,
    "producto_id": producto_heredado,   # puede quedar None; no es un error
}
```

`COALESCE(presupuesto_items.producto_id, items_proceso.producto_id)` en ese orden: el del
presupuesto es más específico (es el producto con el que efectivamente se coti­zó ese renglón en
esa cotización), el del `item_proceso` es el del proceso comercial y sirve de respaldo (C5).

**Cuando los dos son `NULL`, el renglón de OC queda con `producto_id = NULL` y no pasa nada más.**
Sin precondición, sin validación, sin estado de UI propio, sin advertencia dedicada.

**Alternatives considered**:

- *(a)* Bloquear el vínculo cuando el lado del presupuesto no tiene producto. **Rechazada por
  decisión explícita de producto** ("por ahora el caso en el que no tengamos `producto_id` no lo
  vamos a tocar"). Y sería un retroceso respecto de D11 del cambio padre, que decidió exactamente lo
  contrario para el mismo dato: no bloquear la digitalización detrás de la calidad del catálogo.
- *(b)* Permitir el vínculo con un estado de UI especial ("vinculado sin producto"). **Rechazada por
  la misma razón**, con el agregado de que inventa un cuarto estado que el spec no tiene y que
  habría que arrastrar por toda la pantalla y por la fase futura de entregas.

**Rationale**: `oc_items.producto_id` **ya** puede ser NULL después de confirmar una OC hoy — es el
estado normal de toda OC validada (D11 del cambio padre). Un vínculo que no hereda producto deja el
renglón exactamente como estaba: no lo empeora. El origen real del hueco es el import legado, que
todavía no existe, y diseñar un mecanismo de bloqueo contra una tabla que hoy está vacía es
construir sobre una hipótesis. La ausencia **ya es visible** por el camino que el cambio padre
construyó (`renglones_sin_producto`), y esa visibilidad alcanza.

> Consecuencia declarada, no oculta: si el import legado llega sin resolver `producto_id` (riesgo
> Alto de la propuesta, y el precedente de `services/pcp/imports/service.py` dice que es lo
> probable), el matching produce vínculos correctos que **no mueven stock**. Eso sigue siendo
> estrictamente mejor que hoy: el vínculo queda registrado y resolver el producto después es un
> `UPDATE` sobre el presupuesto, no volver a reconciliar los documentos.

### D7 — El desempate por descripción **ordena**, nunca excluye: sin umbral y sin top-K

> Resuelve la Open Question #4 de la propuesta.

**Choice**: cuando un renglón de OC tiene **más de un** candidato al mismo precio, se ordenan por
`fuzz.WRatio` sobre `normalizar_descripcion(...)` y se devuelven **todos**, sin umbral mínimo y sin
recorte. Se reutilizan las mismas primitivas que `_generar_candidatos`
(`matching/service.py:17-36`), sin llamar ni modificar `procesar_matching_item`:

```python
# oc_presupuesto/service.py
from rapidfuzz import fuzz, process
from services.presupuestacion.core.texto import normalizar_descripcion

def _ordenar_por_similitud(descripcion_oc: str, candidatos: dict[str, str]) -> list[tuple[str, Decimal]]:
    """`candidatos`: presupuesto_item_id -> descripción (de items_proceso, C5).

    Deliberadamente SIN _UMBRAL_SUGERIDO y SIN _TOP_K (design.md D7): el filtro
    de precio ya hizo la selección; la similitud solo define el orden de la lista.
    """
    choices = {pid: normalizar_descripcion(desc) for pid, desc in candidatos.items()}
    return process.extract(
        normalizar_descripcion(descripcion_oc), choices, scorer=fuzz.WRatio, limit=None
    )
```

Con **un solo** candidato no se calcula similitud (`similitud = None`): no hay nada que desempatar.

**Alternatives considered**:

- *(a)* Heredar `_UMBRAL_SUGERIDO = 70` de `matching/service.py`. **Rechazada, y el motivo es el que
  la propuesta pedía que se justificara.** Ese umbral existe para un problema distinto: elegir entre
  **miles** de productos del catálogo, donde un score bajo casi siempre significa "ninguno sirve".
  Acá el universo ya está acotado a los renglones que coinciden **exacto** en precio dentro de un
  presupuesto que le cotizamos a **este** cliente — típicamente dos o tres filas. Un umbral en ese
  universo no protege de nada y sí puede esconder al correcto: la OC la redacta el cliente y escribe
  el mismo medicamento con otras palabras ("HIDROCLOROTIAZIDA 50MG COMP" contra "HCT 50MG X30"
  puntúa muy por debajo de 70 y es el renglón correcto). Esconder al único candidato correcto por un
  score deja al renglón en `pendiente` sin salida, que es el peor resultado posible.
- *(b)* Heredar `_TOP_K = 5`. **Rechazada por lo mismo, en versión más leve**: la lista de empatados
  al mismo precio dentro de un presupuesto raramente pasa de 3. Un recorte que nunca se activa es
  código muerto; uno que se activa, esconde.
- *(c)* Usar la similitud también como sugerencia cuando **no** hay coincidencia de precio.
  **Rechazada**: rompe el orden de autoridad del cambio ("el precio es la clave de join, la
  descripción es solo el desempate") y reintroduce por la ventana el falso positivo plausible que
  D3 del cambio padre ya rechazó para la resolución de cliente. Sin precio, el renglón queda
  `pendiente` y el humano lo vincula a mano si quiere (D4, `vinculo_origen='manual'`).

**Rationale**: el precio ya hizo la selección. La descripción solo contesta "¿cuál de estos dos
mostrás primero?", y para eso un orden alcanza; un filtro sería una decisión que no le corresponde
tomar.

### D8 — El presupuesto elegido vive en la URL y en los vínculos, no en una columna nueva

**Choice**: no se agrega `ordenes_compra.presupuesto_id`. El presupuesto activo de la pantalla se
resuelve así, en orden:

1. **El presupuesto de los vínculos ya confirmados** de esa OC, si hay alguno. Es un hecho
   persistido, derivado de `oc_items.presupuesto_item_id → presupuesto_items.presupuesto_id`.
2. El `presupuesto_id` que viaje como query param (el usuario lo cambió en esta sesión; la ruta lo
   lleva como search param, así que sobrevive a un reload y es compartible por link).
3. El primero del ranking (`presupuesto_sugerido_id`, D2).

**Invariante duro, verificado en el servicio antes de escribir**: todos los vínculos confirmados de
una misma OC pertenecen al **mismo presupuesto**. Confirmar un vínculo contra un presupuesto
distinto del que ya tiene vínculos devuelve `ValidationError` (422) nombrando el presupuesto actual.
Para cambiar de presupuesto hay que deshacer los vínculos existentes (D9) — un acto explícito, no un
efecto lateral de un click en el selector.

**Alternatives considered**:

- *(a)* Columna `ordenes_compra.presupuesto_id`. **Rechazada**: sería una segunda fuente de verdad
  sobre el mismo hecho, y podría contradecir a los vínculos (una OC con `presupuesto_id = A` y
  renglones confirmados contra B). El invariante de arriba la vuelve redundante por construcción.
- *(b)* Guardar la elección en estado local de React. **Rechazada**: se pierde en cada reload, y una
  sesión de matching de una OC de 40 renglones no se termina de una sentada. El search param da
  persistencia y URL compartible sin tocar la base.

**Rationale**: elegir un presupuesto es navegación mientras no haya ningún vínculo, y deja de serlo
en el instante en que hay uno — porque ahí el hecho ya quedó escrito en el vínculo. Modelarlo así
elimina el estado intermedio que podría quedar inconsistente.

### D9 — Deshacer devuelve el renglón a `pendiente`, y revierte la herencia solo si sigue intacta

> Resuelve la Open Question #6 de la propuesta.

**Choice**: `DELETE .../vinculo` devuelve el renglón al estado cero (`pendiente`), sirva para
deshacer un `confirmado` o un `sin_presupuesto` — `pendiente` es el estado cero y el DELETE lleva
ahí. Sobre el `producto_id` heredado:

| Condición al deshacer | Qué pasa con `oc_items.producto_id` |
|---|---|
| Es igual al que el vínculo le dio (recalculado en el momento, D6) | Se pone en `NULL` — el vínculo era la única razón de ese valor |
| Es distinto (alguien lo cambió después por otro camino) | **Se deja intacto**, y la respuesta lo informa |
| Ya era `NULL` | No cambia nada |

**Alternatives considered**:

- *(a)* Nunca revertir el `producto_id`. **Rechazada**: deshacer un vínculo es la forma que tiene el
  operador de decir "esto estaba mal". Dejar el producto que ese vínculo equivocado trajo deja
  exactamente el dato malo que se quiso corregir, y sin rastro de dónde salió.
- *(b)* Siempre poner `producto_id = NULL`. **Rechazada**: pisaría trabajo humano posterior hecho
  por otro camino. La comparación cuesta una lectura que igual hay que hacer para validar la
  pertenencia del vínculo.
- *(c)* Una columna `producto_heredado_de_vinculo BOOLEAN` para saberlo sin recalcular.
  **Rechazada**: quinta columna para un dato que se obtiene comparando dos valores en el momento.

> Esto **no** contradice el § Rollback Plan de la propuesta ("los `producto_id` ya heredados no se
> revierten"). Ahí se habla de revertir **el cambio entero**, donde el vínculo nunca fue declarado
> incorrecto; acá se habla de que un humano declara **este** vínculo incorrecto. Son dos hechos
> distintos y merecen respuestas distintas.

### D10 — Navegación automática al confirmar la validación, y sincronización del espejo TypeScript

**Choice**: el `onSuccess` de la mutación de `ValidarExtraccionDetalle.tsx:81-85` pasa a leer la
respuesta:

```tsx
onSuccess: (resultado) => {
  queryClient.invalidateQueries({ queryKey: EXTRACCIONES_KEY })
  if (resultado.orden_compra_id) {
    // Mismo patrón que subir -> validar (carga-documentos): la fase siguiente
    // se abre sola, en vez de dejar al operador de vuelta en el listado sin
    // saber que falta un paso.
    navigate({
      to: '/ordenes-compra/$ordenCompraId/matching',
      params: { ordenCompraId: resultado.orden_compra_id },
    })
    return
  }
  navigate({ to: '/validar-extraccion' })
}
```

El backend **no se toca** (C7): `ResultadoValidarExtraccion` ya devuelve `orden_compra_id`. Lo que
falta es el espejo TypeScript, `frontend/src/lib/api/extracciones.ts:104-113`, al que le faltan
**los cuatro** campos que el modelo Pydantic ya tiene:

```ts
export interface ResultadoValidarExtraccion {
  extraction_id: string
  document_type: DocumentType
  proceso_comercial_id: string | null
  filas_creadas: number
  comparativa_id: string | null
  reemplazo_version_anterior: boolean
  // --- Sincronización con services/presupuestacion/extraccion/models.py:94-107.
  // Los cuatro existen en el backend desde 3b37fca3 (cambio padre); el espejo
  // quedó desactualizado. `orden_compra_id` es null en licitación/comparativa. ---
  orden_compra_id: string | null
  entregas_creadas: number
  renglones_sin_producto: number
  extracciones_validadas: number
}
```

**Alternatives considered**:

- *(a)* Navegar siempre al matching y que la pantalla resuelva el caso no-OC. **Rechazada**:
  licitación y comparativa no tienen orden de compra ni presupuesto que reconciliar. El `if` sobre
  `orden_compra_id` es la discriminación correcta y viene tipada.
- *(b)* Sincronizar solo `orden_compra_id` y dejar los otros tres desalineados. **Rechazada**: un
  espejo parcialmente sincronizado es peor que uno viejo, porque parece confiable. Los cuatro campos
  son aditivos y no rompen a ningún consumidor (hoy nadie lee la respuesta).

**Rationale**: cierra literalmente el callejón sin salida que la propuesta describe, con el patrón
que el proyecto ya shipeó para subir → validar, y sin tocar una línea de backend.

> `ValidarExtraccionDetalle.test.tsx` ya afirma la navegación actual al listado: ese test se
> **extiende** con el caso OC, no se reemplaza. La rama no-OC sigue navegando al listado y debe
> seguir verde.

### D11 — Re-entrada: la ruta es un permalink, y el listado gana una sección de OC validadas

> Resuelve la Open Question #7 de la propuesta.

**Choice**: dos caminos, ninguno nuevo desde cero.

1. **La ruta es la re-entrada.** `/ordenes-compra/$ordenCompraId/matching` no depende de ningún
   estado de navegación previo: toma la OC del path y el presupuesto de la URL o de los vínculos
   (D8). Es marcable, compartible y recargable.
2. **El listado de validación gana una sección "Órdenes de compra validadas".**
   `ValidarExtraccionListado` hoy consulta solo `{ validado: false }` (línea 52). Se agrega una
   segunda query `{ validado: true, limit: 50 }`, se filtra `document_type === 'orden_compra'` en el
   cliente y cada fila enlaza a su pantalla de matching. Para poder armar el link,
   `ExtraccionResumen` gana un campo aditivo `orden_compra_id: str | None`, resuelto con un lookup
   por `ordenes_compra.extraction_id` sobre las extracciones del lote.

**Alternatives considered**:

- *(a)* Un listado de órdenes de compra propio (`GET /ordenes-compra` + pantalla nueva).
  **Rechazada por alcance**: hoy no existe ninguna pantalla de OC en el frontend (no hay ruta
  `ordenes-compra` en `frontend/src/routes/`), así que sería una capacidad nueva entera — endpoint
  con filtros, paginación, estados — dentro de un cambio que es de matching. Queda anotado como
  trabajo futuro, y es el lugar natural al que esta pantalla debería colgar cuando exista.
- *(b)* Un endpoint `GET /ordenes-compra/pendientes-matching`. **Rechazada por lo mismo, en
  chico**: endpoint nuevo + pantalla nueva para resolver re-entrada, cuando el listado que el
  operador ya usa puede mostrarlo con un campo aditivo.
- *(c)* Solo el permalink. **Rechazada**: sin un camino visible, una sesión interrumpida solo se
  retoma si alguien guardó la URL, que es exactamente el callejón sin salida que este cambio vino a
  cerrar en la pantalla anterior.

> Nota sobre el grupo multi-archivo (D13 del cambio padre): `ordenes_compra.extraction_id` guarda
> **una** de las N extracciones del grupo, así que en un grupo las otras N-1 filas del listado
> quedan con `orden_compra_id = null`. Es aceptable — al menos una fila del grupo lleva al matching
> y las N ya se muestran agrupadas — pero tiene que estar en el spec, no descubrirse en producción.

### D12 — Módulo backend propio `oc_presupuesto/`, con una tupla de roles nueva declarada

> Resuelve las Open Questions #9 y #10 de la propuesta.

**Choice**: módulo nuevo `services/presupuestacion/oc_presupuesto/` con la estructura estándar del
backend (`models.py`, `repository.py`, `service.py`, `router.py`). Roles:

| Operación | Tupla | Valor |
|---|---|---|
| Todo el módulo (lectura y escritura) | `_ROLES_MATCHING` (nueva, en `oc_presupuesto/router.py`) | `admin, gerencia, lider_comercial, comercial` |

**Alternatives considered**:

- *(a)* Meterlo en `compras/`. **Rechazada**: `compras/` es el módulo de entregas y movimiento de
  stock, y su router expone `_ROLES_ENTREGA`, que **incluye `compras`** — un rol que por el criterio
  de D12 del cambio padre ("escribe quien valida, no quien entrega") no debería poder reconciliar
  documentos comerciales. Además, `compras/service.py` es el archivo que mueve stock: sumarle un
  mecanismo que no lo toca agranda su superficie de riesgo a cambio de nada.
- *(b)* Meterlo en `matching/`. **Rechazada**: ese nombre ya está tomado por el motor de catálogo
  (descripciones de `items_proceso` contra `productos`), que es otro concepto. Dos cosas distintas
  con el mismo nombre en el mismo árbol es el tipo de confusión que se paga durante años.
- *(c)* Meterlo en `presupuestos/`. **Rechazada**: ese módulo es sobre generar y revisar
  presupuestos. Acá el presupuesto es la **fuente**, no el objeto del cambio; lo que se escribe es
  `oc_items`.

**Rationale**: el módulo vive exactamente en la frontera que su nombre declara — lee presupuesto,
escribe OC — y no es sub-dominio de ninguno de los dos. El precio es **una tupla de roles nueva**,
que es una desviación explícita respecto de D12 del cambio padre ("cero tuplas nuevas"): su valor es
idéntico al de `_ROLES_VALIDAR` / `_ROLES_OC`, por el mismo criterio. Se declara local en vez de
importar un nombre privado de otro módulo (`extraccion/router.py::_ROLES_VALIDAR`), que es lo que
todos los routers del backend hacen hoy.

**Reúso y aislamiento**:

| Pieza | Trato |
|---|---|
| `core/texto.py::normalizar_descripcion` | Se **importa** tal cual. No se copia, no se parametriza (C9 del cambio padre) |
| `rapidfuzz` (`fuzz.WRatio`, `process.extract`) | Se usa directo, igual que `matching/service.py:25-27`. Ya es dependencia |
| `presupuestos/repository.py::listar_items_presupuesto` | Se **importa y reutiliza sin cambios** para la columna izquierda. El archivo **no se modifica** (C6) |
| `matching/service.py::procesar_matching_item` | **No se llama ni se modifica.** Está acoplado a `items_proceso` y al catálogo |
| `items_proceso.estado_matching` / `confianza_matching` | **Ni se leen ni se escriben.** Fuera de alcance |
| `compras/service.py` | **Sin cambios.** El matching no mueve stock |

**Autorización, por endpoint** (patrón `*_para_endpoint` ya establecido en el módulo de extracción):

1. `require_roles(_ROLES_MATCHING)` en la firma del endpoint.
2. Lectura de la OC con el *user client* → si no aparece, `NotFoundError` (la RLS ya filtró por
   tenant; un 404 no confirma la existencia de una OC de otra droguería).
3. Toda validación de pertenencia (`oc_item` ∈ OC, `presupuesto_item` ∈ presupuesto elegido ∈
   cliente de la OC) **antes del primer write**, igual que
   `_validar_orden_compra_override` del cambio padre.
4. El único uso del *service client* es el lookup de etiqueta de D2.1, acotado a ids ya autorizados.

### D13 — Superficie HTTP: una lectura de pantalla completa y tres escrituras puntuales

**Choice**: cinco endpoints, todos bajo `/ordenes-compra/{orden_compra_id}` y todos con
`_ROLES_MATCHING`.

| Método | Ruta | Respuesta | Para qué |
|---|---|---|---|
| `GET` | `/{id}/presupuestos-candidatos` | `PresupuestosCandidatosOut` | El ranking de D2. Query propia porque no cambia al confirmar un vínculo |
| `GET` | `/{id}/matching?presupuesto_id=` | `MatchingOut` | Las dos columnas completas. `presupuesto_id` **opcional**: si falta, lo resuelve el servidor (D8) y lo devuelve en la respuesta |
| `POST` | `/{id}/items/{oc_item_id}/vinculo` | `MatchingOut` | Confirmar un vínculo (body: `presupuesto_item_id`) |
| `DELETE` | `/{id}/items/{oc_item_id}/vinculo` | `MatchingOut` | Volver el renglón a `pendiente` (D9) |
| `POST` | `/{id}/items/{oc_item_id}/descartar` | `MatchingOut` | Marcar `sin_presupuesto` |

**Las tres escrituras devuelven el `MatchingOut` completo**, no solo el renglón tocado.

**Alternatives considered**:

- *(a)* Que las escrituras devuelvan solo el renglón modificado. **Rechazada**: confirmar un vínculo
  cambia **las dos** columnas — el estado del renglón de OC a la derecha y el contador de
  reutilización del renglón de presupuesto a la izquierda (D5). Devolver medio cambio obliga al
  frontend a un refetch inmediato después de cada click, que es un round trip extra por cada
  confirmación en una pantalla cuyo patrón de uso es "muchos clicks seguidos".
- *(b)* Un solo endpoint que devuelva ranking + columnas. **Rechazada**: el ranking no cambia al
  confirmar, así que compartir cache key obligaría a recalcularlo en cada click. Dos queries con dos
  cache keys es más barato y más claro.
- *(c)* Un `PUT .../vinculo` con un cuerpo polimórfico (`{presupuesto_item_id | null, estado}`).
  **Rechazada**: es una función con modos, que es exactamente lo que D2 del cambio padre rechazó
  para `crear_entrega`. Tres verbos con una semántica cada uno se leen solos en el log de acceso.

**Idempotencia y errores**:

| Situación | Comportamiento | HTTP |
|---|---|---|
| Confirmar sobre un renglón ya confirmado | Reemplaza el vínculo (equivale a DELETE + POST), sin error | 200 |
| Confirmar un `presupuesto_item` cuyo precio **no** coincide | **Se acepta**, con `vinculo_origen='manual'` | 200 |
| Confirmar contra un presupuesto distinto del que ya tiene vínculos | `ValidationError` nombrando el presupuesto actual (D8) | 422 |
| `oc_item_id` que no pertenece a `orden_compra_id` | `NotFoundError` | 404 |
| `presupuesto_item_id` de otra droguería o de otro cliente | `NotFoundError` (no 403: no se confirma existencia) | 404 |
| `presupuesto_item_id` con `excluido = TRUE` | `ValidationError` — nunca se cotizó (C4) | 422 |
| OC anclada por proceso comercial (`cliente_id IS NULL`) | `ValidationError` — el mecanismo no aplica | 422 |
| Cliente sin presupuestos, o sin coincidencias | Respuesta vacía con advertencia. **No es error** (D2) | 200 |

---

## Data Flow

```
                         ┌──────────────────────────────────────────┐
  POST /extracciones/     │  ValidarExtraccionDetalle (ya existe)    │
  {id}/validar     ──────►│  onSuccess → orden_compra_id ? matching  │  D10
                         └───────────────────┬──────────────────────┘
                                             │ navigate
                                             ▼
   ordenes_compra          ┌─────────────────────────────────────────┐
   (cliente_id ya          │ /ordenes-compra/$id/matching?presupuesto│
    resuelto, D3 padre)    └──────────┬──────────────┬───────────────┘
          │                           │              │
          │         GET presupuestos-candidatos      │ GET matching
          │                           │              │
          ▼                           ▼              ▼
   procesos_comerciales ──► presupuestos ──► presupuesto_items ──► items_proceso
     (cliente_id)            (por proceso)     (in_ precios, D3)     (descripción)
                                                     │
                                                     ▼
                                          ranking + sugerencias
                                        (nada escrito todavía)
                                                     │
                                       click humano  ▼
                              POST /items/{oc_item_id}/vinculo
                                                     │
                                                     ▼
                                      UPDATE oc_items SET
                                        presupuesto_item_id, vinculo_origen,
                                        vinculo_confirmado_*, producto_id   ◄── herencia (D6)
```

### Secuencia de una confirmación

```
Operador     Pantalla            Router                Service              Base
   │            │                  │                      │                  │
   │ click ─────►│                  │                      │                  │
   │            │ POST vinculo ────►│                      │                  │
   │            │                  │ require_roles         │                  │
   │            │                  │ + user client ───────►│ leer OC ────────►│
   │            │                  │                      │◄─── cliente_id ──│
   │            │                  │                      │ leer oc_item ───►│  (¿pertenece?)
   │            │                  │                      │ leer presup_item►│  (¿tenant? ¿excluido?)
   │            │                  │                      │ leer item_proceso│  (producto de respaldo)
   │            │                  │                      │ leer vínculos ──►│  (¿otro presupuesto? D8)
   │            │                  │                      │                  │
   │            │                  │        ── todas las validaciones OK ──  │
   │            │                  │                      │ UPDATE oc_items ►│  ← ÚNICO write
   │            │                  │                      │                  │
   │            │                  │                      │ recomputar vista │
   │            │                  │                      │ (ambas columnas) │
   │            │◄── MatchingOut ──┤◄─────────────────────┤                  │
   │◄── estado ─┤                  │                      │                  │
```

Nada se escribe antes de que **todas** las validaciones pasen, y el write es **uno solo** — no hay
estado intermedio observable ni necesidad de compensación si algo falla a mitad.

---

## File Changes

| Archivo | Acción | Descripción |
|---|---|---|
| `supabase/migrations/0026_oc_vinculo_presupuesto.sql` | Crear | 4 columnas + 3 CHECK + FK compuesta en `oc_items`, `uq_pi_id_drog` en `presupuesto_items` (C2), índice parcial. **Sin RLS ni GRANTs nuevos** (C3) |
| `supabase/migrations/0026_oc_vinculo_presupuesto.down.sql` | Crear | Reversa, con el aviso de datos antes que esquema |
| `docs/schema/extractor_final.sql` | Modificar | Reflejar las columnas nuevas. **Verificar contra la base viva antes de migrar** (C4 del cambio padre: el snapshot ya se comprobó desactualizado) |
| `services/presupuestacion/oc_presupuesto/__init__.py` | Crear | Módulo nuevo (D12) |
| `services/presupuestacion/oc_presupuesto/models.py` | Crear | `CandidatoPresupuesto`, `PresupuestosCandidatosOut`, `RenglonPresupuesto`, `RenglonOrdenCompra`, `CandidatoVinculo`, `MatchingOut`, `ConfirmarVinculoRequest` |
| `services/presupuestacion/oc_presupuesto/repository.py` | Crear | Selects PostgREST con troceo de `in_()` (D3); lookup de etiqueta por service client (D2.1) |
| `services/presupuestacion/oc_presupuesto/service.py` | Crear | Ranking (D2), sugerencias + desempate (D7), confirmar/deshacer/descartar (D6, D9), aviso N:1 (D5) |
| `services/presupuestacion/oc_presupuesto/router.py` | Crear | Los 5 endpoints de D13 + `_ROLES_MATCHING` |
| `services/presupuestacion/main.py` | Modificar | `include_router` del módulo nuevo |
| `services/presupuestacion/extraccion/models.py` | Modificar | Solo `ExtraccionResumen` gana `orden_compra_id: str \| None` (D11). `ResultadoValidarExtraccion` **no se toca** (C7) |
| `services/presupuestacion/extraccion/repository.py` | Modificar | Lookup de `ordenes_compra` por `extraction_id` para el listado (D11) |
| `services/presupuestacion/extraccion/service.py` | Modificar | Poblar `orden_compra_id` en el listado. `_materializar_orden_compra` **no se toca** (C7) |
| `services/presupuestacion/presupuestos/repository.py` | **Sin cambios** | `listar_items_presupuesto` se reutiliza tal cual (C6) |
| `services/presupuestacion/matching/service.py` · `core/texto.py` · `compras/service.py` | **Sin cambios** | Solo se importan primitivas (D12) |
| `frontend/src/lib/api/extracciones.ts` | Modificar | Sincronizar `ResultadoValidarExtraccion` (4 campos, D10) + `orden_compra_id` en `ExtraccionResumen` (D11) |
| `frontend/src/lib/api/ocMatching.ts` | Crear | Cliente HTTP de los 5 endpoints + espejos de tipos |
| `frontend/src/routes/_authenticated.ordenes-compra.$ordenCompraId.matching.tsx` | Crear | Ruta con `validateSearch` de `presupuesto` (D8) |
| `frontend/src/routeTree.gen.ts` | Generado | Regenerado por TanStack Router |
| `frontend/src/features/oc-matching/OcMatchingDetalle.tsx` | Crear | Container: queries, mutaciones, renglón seleccionado |
| `frontend/src/features/oc-matching/components/SelectorPresupuesto.tsx` | Crear | Lista de candidatos rankeados (D2) |
| `frontend/src/features/oc-matching/components/ColumnaPresupuesto.tsx` | Crear | Columna izquierda + aviso de reutilización |
| `frontend/src/features/oc-matching/components/ColumnaOrdenCompra.tsx` | Crear | Columna derecha |
| `frontend/src/features/oc-matching/components/RenglonOcFila.tsx` | Crear | Un renglón con su estado, candidatos y botones (confirmación granular) |
| `frontend/src/features/oc-matching/components/AvisoReutilizacion.tsx` | Crear | Aviso suave no bloqueante (D5) |
| `frontend/src/features/validar-extraccion/ValidarExtraccionDetalle.tsx` | Modificar | `onSuccess` navega al matching (D10) |
| `frontend/src/features/validar-extraccion/ValidarExtraccionListado.tsx` | Modificar | Sección "Órdenes de compra validadas" con link de re-entrada (D11) |
| `tests/oc_presupuesto/test_service.py` · `test_router.py` | Crear | RED primero (`strict_tdd: true`) |
| `tests/oc_presupuesto/fixtures/` | Crear | Caso real SAMCo Rafaela (OC 00104857 ↔ presupuesto 00246033) |
| `frontend/src/features/oc-matching/**/*.test.tsx` | Crear | RED primero |
| `frontend/src/features/validar-extraccion/ValidarExtraccionDetalle.test.tsx` | Modificar | **Extender** con el caso OC; la rama no-OC sigue verde (D10) |

Neto: **12 archivos nuevos de producción**, 8 modificados, 0 borrados, 1 tabla nueva (ninguna),
4 columnas nuevas.

---

## Interfaces / Contracts

### Modelos de respuesta (`oc_presupuesto/models.py`)

```python
EstadoVinculo = Literal["pendiente", "confirmado", "sin_presupuesto"]
OrigenVinculo = Literal["precio_exacto", "manual"]


class CandidatoPresupuesto(BaseModel):
    presupuesto_id: str
    proceso_comercial_id: str
    nombre_proceso: str
    # None cuando el presupuesto no vino del import legado (cargado a mano) o
    # cuando presupuesto_legacy_map no tiene fila para él (D2.1 / C1).
    numero_presupuesto: str | None
    estado: str
    generado_at: datetime
    cantidad_items: int
    # Puntaje del ranking (D2): cuántos renglones de ESTA OC coinciden exacto
    # en precio contra algún renglón de ESTE presupuesto.
    renglones_oc_con_coincidencia: int
    renglones_oc_totales: int


class PresupuestosCandidatosOut(BaseModel):
    orden_compra_id: str
    cliente_id: str
    razon_social_cliente: str
    # Total de presupuestos del cliente, coincidan o no. Permite distinguir
    # "no tiene presupuestos" de "tiene 12 y ninguno coincide" (D2).
    presupuestos_del_cliente: int
    candidatos: list[CandidatoPresupuesto]   # top 5, puntaje > 0, ya ordenados
    presupuesto_sugerido_id: str | None      # = candidatos[0] si hay; sugerido != elegido
    advertencias: list[str]


class RenglonPresupuesto(BaseModel):
    """Columna izquierda. Junta presupuesto_items + items_proceso (C5)."""
    presupuesto_item_id: str
    item_proceso_id: str
    numero_renglon: int
    descripcion: str
    cantidad_ofertada: Decimal | None
    precio_unitario: Decimal
    # COALESCE(presupuesto_items.producto_id, items_proceso.producto_id) -- lo
    # que se heredaría al confirmar. None es normal y no bloquea nada (D6).
    producto_id: str | None
    # Aviso N:1 (D5). Alcance: toda la droguería, no solo esta OC.
    renglones_oc_vinculados: int
    renglones_oc_vinculados_otras_oc: int
    cantidad_vinculada: Decimal


class CandidatoVinculo(BaseModel):
    presupuesto_item_id: str
    # fuzz.WRatio 0-100 sobre normalizar_descripcion(...). None cuando hay un
    # solo candidato: no hay nada que desempatar (D7). NUNCA filtra: ordena.
    similitud: Decimal | None


class RenglonOrdenCompra(BaseModel):
    """Columna derecha. `estado` se DERIVA, no está en la base (D4)."""
    oc_item_id: str
    numero_renglon: int
    descripcion: str
    cantidad: Decimal
    precio_unitario: Decimal
    producto_id: str | None
    estado: EstadoVinculo
    presupuesto_item_id: str | None
    vinculo_origen: OrigenVinculo | None
    # Solo cuando estado == "pendiente". Vacío = ningún renglón del presupuesto
    # comparte el precio; el renglón queda pendiente y NO bloquea al resto.
    candidatos: list[CandidatoVinculo]


class MatchingOut(BaseModel):
    orden_compra_id: str
    numero_oc: str
    cliente_id: str
    # El presupuesto efectivamente usado, resuelto por el servidor cuando el
    # query param no vino (D8). None solo si el cliente no tiene ninguno.
    presupuesto_id: str | None
    renglones_presupuesto: list[RenglonPresupuesto]
    renglones_oc: list[RenglonOrdenCompra]
    advertencias: list[str]


class ConfirmarVinculoRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    presupuesto_item_id: str
```

### Firmas del servicio

```python
def rankear_presupuestos_candidatos(
    client: Client, *, orden_compra_id: str, drogueria_id: str
) -> PresupuestosCandidatosOut:
    """Puntúa los presupuestos del cliente de la OC por coincidencia EXACTA de
    precio unitario (D2). No escribe nada. No filtra por estado ni por fecha.

    Raises:
        NotFoundError:   la OC no existe o es de otra droguería.
        ValidationError: la OC está anclada por proceso comercial (cliente_id NULL).
    """


def obtener_matching(
    client: Client, *, orden_compra_id: str, drogueria_id: str, presupuesto_id: str | None
) -> MatchingOut:
    """Estado completo de la pantalla. `presupuesto_id` None -> se resuelve:
    vínculos confirmados > query param > primero del ranking (D8).

    Calcula sugerencias y avisos en cada llamada; NO persiste ninguna (D4).
    """


def confirmar_vinculo(
    client: Client, *, orden_compra_id: str, oc_item_id: str,
    presupuesto_item_id: str, drogueria_id: str, usuario_id: str,
) -> MatchingOut:
    """Escribe el vínculo y hereda producto_id (D6). UN solo UPDATE, después de
    TODAS las validaciones. Acepta vínculos cuyo precio no coincide, marcándolos
    vinculo_origen='manual' -- el precio sugiere, no autoriza (D4).

    Raises:
        NotFoundError:   el oc_item no es de esta OC, o el presupuesto_item no
                         es de esta droguería / de un presupuesto de este cliente.
        ValidationError: el presupuesto_item está excluido, o pertenece a un
                         presupuesto distinto del que ya tiene vínculos (D8).
    """


def deshacer_vinculo(...) -> MatchingOut:
    """Vuelve el renglón a `pendiente`, venga de confirmado o de sin_presupuesto.
    Revierte producto_id a NULL SOLO si sigue siendo el que el vínculo le dio (D9).
    """


def descartar_renglon(...) -> MatchingOut:
    """Marca vinculo_descartado=True: el humano afirma que este renglón no está
    en el presupuesto. No es lo mismo que `pendiente` (todavía no lo miré), D4.
    """
```

### Espejos TypeScript (`frontend/src/lib/api/ocMatching.ts`)

Espejo literal de los modelos Pydantic, con la misma convención que
`extracciones.ts` (`snake_case` en los campos, comentario que nombra el modelo de origen y la
decisión de diseño). Funciones expuestas:

```ts
export function obtenerPresupuestosCandidatos(ordenCompraId: string): Promise<PresupuestosCandidatosOut>
export function obtenerMatching(ordenCompraId: string, presupuestoId?: string): Promise<MatchingOut>
export function confirmarVinculo(ordenCompraId: string, ocItemId: string, presupuestoItemId: string): Promise<MatchingOut>
export function deshacerVinculo(ordenCompraId: string, ocItemId: string): Promise<MatchingOut>
export function descartarRenglon(ordenCompraId: string, ocItemId: string): Promise<MatchingOut>
```

### Forma del frontend

Container/presentational, igual que `validar-extraccion/` (container en la raíz del feature,
presentacionales en `components/`, tests colocados):

```
features/oc-matching/
├── OcMatchingDetalle.tsx            CONTAINER: 2 queries, 3 mutaciones, estado
│                                    de selección. Decide qué se puede confirmar.
└── components/
    ├── SelectorPresupuesto.tsx      candidatos rankeados; el sugerido se muestra
    │                                primero pero NO viene elegido
    ├── ColumnaPresupuesto.tsx       izquierda: descripción/cantidad/precio/estado
    ├── ColumnaOrdenCompra.tsx       derecha: un RenglonOcFila por renglón
    ├── RenglonOcFila.tsx            estado + candidatos + "Confirmar" / "Deshacer"
    │                                / "No está en el presupuesto"
    └── AvisoReutilizacion.tsx       aviso suave; nunca deshabilita nada
```

Estado, todo en el container (mismo reparto que `ValidarExtraccionDetalle`, que decide
`puedeConfirmar` a partir de callbacks de sus hijos):

| Estado | Dónde vive | Por qué |
|---|---|---|
| `presupuestoId` | Search param de la ruta | Sobrevive al reload y es compartible (D8) |
| `renglonSeleccionadoId` | `useState` del container | Solo resalta; no tiene valor fuera de la sesión |
| Vínculos y estados | Cache de TanStack Query (`MatchingOut`) | Las mutaciones devuelven el `MatchingOut` completo y **reemplazan** la cache con `setQueryData` — sin refetch por click (D13) |

**Sin hook propio tipo `useFilasEditables`**: ese hook existe porque la tabla editable tiene estado
local complejo (celdas modificadas, borradas, agregadas, errores por celda). Acá el estado local es
un id seleccionado; un hook sería ceremonia.

**Cada confirmación es un click y un request.** No hay "guardar todo", no hay botón de confirmar
global, no hay estado sucio que perder si el operador cierra la pestaña — mismo patrón granular que
`OrdenCompraSelector` ya aplica para el cliente.

---

## Testing Strategy

`strict_tdd: true` (`openspec/config.yaml`): **todo test va en RED antes de la implementación que lo
pone en verde**.

| Capa | Qué se testea | Cómo |
|---|---|---|
| Unit (backend) | Ranking: orden por coincidencias, desempate por `generado_at`, desempate final por id, tope de 5, `presupuestos_del_cliente` con 0 candidatos | Funciones puras sobre `dict`s; sin cliente Supabase |
| Unit (backend) | Normalización de escala de precio: `109.750` ≡ `109.75`; `Decimal` nunca `float`; `precio_unitario NULL` fuera del conjunto | Tabla de casos |
| Unit (backend) | `_ordenar_por_similitud`: ordena descendente, **no filtra** por score, `None` con un solo candidato | Pares de descripciones reales, incluido un caso con score < 70 que **debe** aparecer (D7) |
| Unit (backend) | Derivación del `estado` desde `(presupuesto_item_id, vinculo_descartado)` — los 3 estados y el cuarto imposible | Función pura |
| Unit (backend) | Herencia de producto: `COALESCE` en los 4 casos (ambos, solo presupuesto, solo item_proceso, ninguno → `None` sin error, D6) | Tabla de casos |
| Unit (backend) | Guarda de deshacer: revierte si coincide, respeta si fue cambiado, no-op si ya era `NULL` (D9) | Tabla de casos |
| Unit (backend) | Troceo de `in_()` en lotes de 200 y concatenación de resultados (D3) | Lista de 450 ids → 3 llamadas |
| Integración (backend) | Los 5 endpoints con cliente Supabase mockeado (`unittest.mock`, igual que `tests/matching/`): roles, 404 por pertenencia, 422 de presupuesto cruzado / excluido / OC sin cliente, idempotencia del re-confirmar | Un test por fila de la tabla de errores de D13 |
| Integración (backend) | **Invariante duro**: `items_proceso.estado_matching` y `confianza_matching` **sin modificar** después de una sesión completa (confirmar + deshacer + descartar) | Snapshot antes/después |
| Integración (backend) | **Caso real SAMCo Rafaela**: OC 00104857 (2 renglones) ↔ presupuesto 00246033 (5 renglones) → ranking lo pone primero, 2 sugerencias únicas, cero ambigüedad | Fixture con los datos reales ya validados |
| Integración (backend) | N:1: dos `oc_items` al mismo `presupuesto_item` → se permite, `renglones_oc_vinculados = 2`, `cantidad_vinculada` suma, **ninguna excepción** (D5) | |
| Integración (backend) | Renglón sin coincidencia → `pendiente` con `candidatos=[]` y **los demás renglones se confirman igual** (no bloquea) | |
| Frontend (unit) | `RenglonOcFila`: un candidato → "Confirmar" habilitado y **nada preseleccionado**; varios → lista ordenada **sin preselección**; cero → estado pendiente visible | Vitest + Testing Library |
| Frontend (unit) | `AvisoReutilizacion` aparece con ≥2 vínculos o exceso de cantidad, y **no deshabilita** el botón | |
| Frontend (unit) | `SelectorPresupuesto`: el sugerido se muestra primero y **no viene elegido**; estado vacío distingue "sin presupuestos" de "ninguno coincide" | |
| Frontend (unit) | `OcMatchingDetalle`: una mutación por click; `setQueryData` con el `MatchingOut` devuelto, sin refetch | |
| Frontend (unit) | `ValidarExtraccionDetalle`: con `orden_compra_id` navega al matching; **sin** él sigue navegando al listado (regresión, D10) | Extiende el test existente |
| E2E | No disponible (`openspec/config.yaml`: `e2e.available: false`) | — |

**Invariante de test que atraviesa todo**: ninguna lectura escribe. Todo test de `GET` afirma que la
base queda igual (mock sin llamadas de `update`/`insert`).

---

## Threat Matrix

**N/A — este cambio no toca ninguno de los bordes de esa matriz.** No hay routing de comandos, ni
shell, ni subprocesos, ni automatización de git/PR, ni clasificación de archivos ejecutables, ni
integración con procesos externos: son cinco endpoints HTTP sobre PostgREST y una pantalla de React.

| Boundary | Aplicabilidad |
|---|---|
| Documentation-like paths | N/A — el cambio no clasifica ni ejecuta archivos |
| Git repository selection | N/A — sin automatización de VCS |
| Commit state | N/A — ídem |
| Push state | N/A — ídem |
| PR commands | N/A — ídem |

La superficie adversarial real de este cambio es **de autorización, no de proceso**, y se trata en
D12: aislamiento por tenant vía RLS ya existente (C3), verificación explícita de pertenencia de
`oc_item_id` y `presupuesto_item_id` **antes del primer write**, y `404` en vez de `403` para no
confirmar la existencia de recursos de otra droguería. Los tests de integración de esa fila de la
tabla de D13 son los RED que cubren esa superficie.

---

## Performance

`rules.design` pide considerar la latencia de Gemini: **acá no aplica y conviene decirlo explícito**
— esta pantalla no llama al extractor, no procesa documentos y no toca el pipeline de extracción.
Trabaja sobre datos ya materializados.

El costo real son round trips a PostgREST:

| Operación | Round trips | Cota |
|---|---|---|
| `GET presupuestos-candidatos` | 4 + troceo | `procesos_comerciales` → `presupuestos` → `presupuesto_items` (filtrado por precio) → `presupuesto_legacy_map` (etiqueta) |
| `GET matching` | 4 + troceo | `ordenes_compra` + `oc_items` → `presupuesto_items` del presupuesto → `items_proceso` → `oc_items` de la droguería con `presupuesto_item_id` en el conjunto (aviso N:1, usa `idx_oci_presupuesto_item`) |
| Confirmar / deshacer / descartar | 5-6 | Validaciones + 1 `UPDATE` + recomputar la vista |

Tres decisiones bajan el costo sin complejidad extra:

1. **El filtro de precio corre en Postgres** (D3), así que lo que viaja son coincidencias, no el
   catálogo de cotizaciones del cliente.
2. **El índice parcial** `idx_oci_presupuesto_item` (D4) hace que el aviso N:1 no barra `oc_items`.
3. **Las escrituras devuelven la vista completa** (D13), así que una sesión de N confirmaciones son
   N requests, no 2N.

El caso patológico previsible es un cliente institucional con cientos de procesos comerciales: lo
cubre el troceo de `in_()` en lotes de 200 (D3), que convierte un fallo por URL demasiado larga en
unas pocas llamadas más.

---

## Migration / Rollout

### `0026_oc_vinculo_presupuesto.sql`

```sql
-- =============================================================================
-- Migration 0026: vinculo renglon de OC <-> renglon de presupuesto
--
-- 1. presupuesto_items gana uq_pi_id_drog (id, drogueria_id). Sus hermanas ya
--    lo tienen (uq_pre_id_drog, uq_ip_id_drog, uq_oc_id_drog); esta quedo sin
--    el suyo. Es el objetivo de la FK compuesta del punto 2 (design.md C2).
-- 2. oc_items gana el vinculo: FK nullable + el bit que distingue "todavia no
--    lo mire" de "lo mire y no esta" + auditoria. El estado de 3 valores del
--    spec se DERIVA de estas columnas, no se guarda (design.md D4).
-- 3. Indice parcial que sostiene el aviso N:1 (design.md D5).
--
-- SIN RLS NI GRANTS NUEVOS: oc_items ya tiene oci_upd para exactamente
-- ('admin','gerencia','lider_comercial','comercial') y presupuesto_items ya
-- tiene SELECT por tenant sin filtro de rol (design.md C3).
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

-- 1) clave compuesta faltante en presupuesto_items -----------------------------
-- No puede fallar: id ya es PRIMARY KEY, asi que (id, drogueria_id) es unico
-- por construccion en cualquier fila existente.
ALTER TABLE presupuesto_items
  ADD CONSTRAINT uq_pi_id_drog UNIQUE (id, drogueria_id);

-- 2) el vinculo, del lado de oc_items -----------------------------------------
ALTER TABLE oc_items ADD COLUMN IF NOT EXISTS presupuesto_item_id    UUID        NULL;
ALTER TABLE oc_items ADD COLUMN IF NOT EXISTS vinculo_descartado     BOOLEAN     NOT NULL DEFAULT FALSE;
ALTER TABLE oc_items ADD COLUMN IF NOT EXISTS vinculo_origen         TEXT        NULL;
ALTER TABLE oc_items ADD COLUMN IF NOT EXISTS vinculo_confirmado_por UUID        NULL;
ALTER TABLE oc_items ADD COLUMN IF NOT EXISTS vinculo_confirmado_at  TIMESTAMPTZ NULL;

-- FK compuesta contra uq_pi_id_drog: impide que un renglon de OC quede
-- vinculado a un renglon de presupuesto de OTRA drogueria aunque la RLS falle.
-- Misma convencion que fk_oca_cliente (0025) y fk_prelm_presupuesto (0015).
-- ON DELETE SET NULL (no CASCADE): borrar un presupuesto NO puede borrar
-- renglones de una orden de compra real del cliente. El vinculo se pierde, el
-- renglon y su producto_id ya heredado sobreviven.
ALTER TABLE oc_items
  ADD CONSTRAINT fk_oci_presupuesto_item
  FOREIGN KEY (presupuesto_item_id, drogueria_id)
  REFERENCES presupuesto_items (id, drogueria_id) ON DELETE SET NULL;

-- Un renglon no puede estar vinculado Y descartado a la vez: el estado
-- contradictorio se vuelve imposible en la base, no solo improbable en el
-- codigo (design.md D4).
ALTER TABLE oc_items
  ADD CONSTRAINT ck_oci_vinculo_excluyente
  CHECK (NOT (vinculo_descartado AND presupuesto_item_id IS NOT NULL));

-- El origen existe si y solo si existe el vinculo.
ALTER TABLE oc_items
  ADD CONSTRAINT ck_oci_vinculo_origen
  CHECK ((presupuesto_item_id IS NULL) = (vinculo_origen IS NULL));

ALTER TABLE oc_items
  ADD CONSTRAINT ck_oci_vinculo_origen_val
  CHECK (vinculo_origen IS NULL OR vinculo_origen IN ('precio_exacto', 'manual'));

COMMENT ON COLUMN oc_items.presupuesto_item_id IS
  'Renglon del presupuesto del que este renglon hereda producto_id. NULL = sin vinculo. N renglones de OC pueden apuntar al MISMO renglon de presupuesto (N:1 permitido y avisado, nunca bloqueado -- design.md D5). No hay tabla puente: 1:N y M:N no son casos de negocio de este cambio (design.md D4).';
COMMENT ON COLUMN oc_items.vinculo_descartado IS
  'TRUE = un humano afirmo que este renglon NO esta en el presupuesto elegido. Es distinto de FALSE+FK NULL, que significa "todavia no se miro". Es el unico bit que la FK no puede expresar; por eso existe esta columna y NO una columna estado de 3 valores, que duplicaria el hecho que la FK ya guarda (design.md D4).';
COMMENT ON COLUMN oc_items.vinculo_origen IS
  'precio_exacto = el precio del renglon coincidia exacto con el del presupuesto. manual = el humano vinculo igual, sin coincidencia de precio (legitimo: el precio sugiere, no autoriza). Se congela al confirmar porque presupuesto_items.precio_unitario es mutable y derivarlo despues daria la respuesta equivocada (design.md D4).';

-- 3) indice del aviso N:1 ------------------------------------------------------
-- Parcial: la enorme mayoria de las filas tiene NULL y sigue teniendolo. El
-- acceso es siempre "quien mas apunta a este renglon de presupuesto".
CREATE INDEX IF NOT EXISTS idx_oci_presupuesto_item
  ON oc_items (presupuesto_item_id)
  WHERE presupuesto_item_id IS NOT NULL;

NOTIFY pgrst, 'reload schema';
```

### `0026_oc_vinculo_presupuesto.down.sql`

```sql
-- Down migration para 0026.
--
-- AVISO (datos antes que esquema): DROP COLUMN presupuesto_item_id borra TODO
-- el trabajo de reconciliacion humana. No es reconstruible: oc_items guarda el
-- producto_id heredado, no de que renglon de presupuesto salio. Exportar antes
-- si la baja puede revertirse:
--   COPY (SELECT id, orden_compra_id, presupuesto_item_id, vinculo_origen,
--                vinculo_confirmado_por, vinculo_confirmado_at
--           FROM oc_items WHERE presupuesto_item_id IS NOT NULL)
--     TO '/tmp/oc_vinculos.csv' CSV HEADER;
--
-- Los oc_items.producto_id ya heredados NO se tocan: son datos de negocio
-- legitimos, identicos a los que un operador podria haber cargado a mano
-- (proposal.md § Rollback Plan). El rollback quita el mecanismo, no su resultado.

DROP INDEX IF EXISTS idx_oci_presupuesto_item;

ALTER TABLE oc_items DROP CONSTRAINT IF EXISTS ck_oci_vinculo_origen_val;
ALTER TABLE oc_items DROP CONSTRAINT IF EXISTS ck_oci_vinculo_origen;
ALTER TABLE oc_items DROP CONSTRAINT IF EXISTS ck_oci_vinculo_excluyente;
ALTER TABLE oc_items DROP CONSTRAINT IF EXISTS fk_oci_presupuesto_item;

ALTER TABLE oc_items DROP COLUMN IF EXISTS vinculo_confirmado_at;
ALTER TABLE oc_items DROP COLUMN IF EXISTS vinculo_confirmado_por;
ALTER TABLE oc_items DROP COLUMN IF EXISTS vinculo_origen;
ALTER TABLE oc_items DROP COLUMN IF EXISTS vinculo_descartado;
ALTER TABLE oc_items DROP COLUMN IF EXISTS presupuesto_item_id;

-- uq_pi_id_drog se deja: es una clave correcta por si misma y otras FK futuras
-- pueden haberla tomado como objetivo. Dropearla solo si se verifico que nadie
-- la referencia:
--   SELECT conname FROM pg_constraint WHERE confrelid = 'presupuesto_items'::regclass;
```

### Verificación previa obligatoria

Contra la **base viva**, no contra `docs/schema/extractor_final.sql` (C4 del cambio padre: el
snapshot ya se comprobó desactualizado para al menos dos tablas):

1. Que `presupuesto_items` **no** tenga ya una constraint llamada `uq_pi_id_drog`.
2. Que `oc_items` no tenga ya ninguna de las cinco columnas nuevas.
3. Que `oc_items.drogueria_id` exista y sea `NOT NULL` — la FK compuesta lo asume.
4. Que la política `oci_upd` siga permitiendo UPDATE a los cuatro roles de `_ROLES_MATCHING` (C3);
   si cambió, la escritura tiene que pasar por service client y hay que revisar D12.
5. Que `presupuesto_items` tenga efectivamente `excluido` y `precio_unitario` nullable (C4).
6. Que `presupuesto_legacy_map` exista (migración 0015 aplicada) — si no, `numero_presupuesto` viaja
   siempre `null` y el fallback de D2.1 es el único camino. **No bloquea.**

### Rollout

Sin feature flag. El orden de despliegue importa:

1. **Migración 0026** primero. Es retrocompatible con el código viejo: las cinco columnas son
   aditivas y nullables (o con `DEFAULT FALSE`), los CHECK se cumplen trivialmente con todo NULL, y
   ningún código existente las lee ni las escribe.
2. **Backend** después. Los endpoints quedan accesibles por API pero sin pantalla: estado inerte,
   no roto.
3. **Frontend** último, y es el único paso que enciende la capacidad. Mientras la ruta nueva no
   exista y el `onSuccess` no navegue, nada de esto es alcanzable desde la UI — el frontend funciona
   como interruptor de facto, igual que en el cambio padre.

**Dependencia de datos, no de código**: hasta que existan presupuestos del cliente, la pantalla
muestra su estado vacío explícito (D2). El import legado está bloqueado esperando a Sistemas, pero
la carga manual de un presupuesto **ya se probó end-to-end y es un camino válido de producción**, no
solo de desarrollo. Este cambio se puede construir, testear y usar sin ese import.

---

## Open Questions

Las diez de la propuesta quedan resueltas acá:

| # | Pregunta | Resuelta en |
|---|---|---|
| 1 | Esquema exacto del vínculo y dónde vive el estado/confianza | **D4** — 4 columnas en `oc_items`; el estado se deriva; la confianza **no** se persiste y `vinculo_origen` sí |
| 2 | ¿N:1 obliga a tabla puente? | **D4** — no. FK nullable expresa N:1 nativamente |
| 3 | Cómo se listan los presupuestos antes de rankear | **D2** — todos, sin filtro de estado ni ventana de fecha, tope 5 después de ordenar |
| 4 | Umbral y corte del desempate | **D7** — ninguno de los dos. La similitud ordena, no filtra |
| 5 | Renglón de presupuesto sin `producto_id` | **D6** — cae por el flujo normal. Sin precondición ni UI especial (decisión explícita de producto) |
| 6 | ¿Se puede deshacer un vínculo? | **D9** — sí; vuelve a `pendiente` y revierte la herencia solo si sigue intacta |
| 7 | Re-entrada a la pantalla | **D11** — permalink + sección de OC validadas en el listado existente |
| 8 | ¿El estado de matching condiciona la fase de entregas? | **No se cierra ninguna puerta, y no se abre ninguna.** El esquema de D4 permite preguntar "¿cuántos renglones quedan `pendiente`?" con una consulta trivial, así que la fase de entregas podrá poner el gate que quiera. Este cambio **no** define ninguno: fuera de alcance |
| 9 | Ubicación del módulo backend | **D12** — módulo propio `oc_presupuesto/` |
| 10 | Roles | **D12** — `_ROLES_MATCHING` con el valor de `_ROLES_VALIDAR`; una tupla nueva declarada, desviación explícita respecto de D12 del cambio padre |

Quedan abiertas, y **ninguna bloquea la implementación**:

- [ ] **Deuda de D2.1**: cuando se construya el import de presupuestos legados, evaluar mover
      `numero_presupuesto` a una columna de `presupuestos`. Hoy el label depende de una tabla cuya
      RLS excluye a la mitad de los usuarios de esta pantalla, y se resuelve con service client.
- [ ] **`ordenes_compra.extraction_id` en grupos multi-archivo** (D11): guarda una sola de las N
      extracciones, así que N-1 filas del listado quedan sin link de re-entrada. Aceptado; debe
      quedar escrito en el spec.
- [ ] **Listado de órdenes de compra propio**: es el lugar natural del que esta pantalla debería
      colgar. Fuera de alcance por tamaño (D11 alternativa *(a)*).
- [ ] **Si el import legado llega sin resolver `producto_id`** (riesgo Alto de la propuesta), el
      matching produce vínculos correctos que no mueven stock. Es mejor que hoy y no invalida nada
      de este diseño, pero el valor de negocio completo del cambio depende de que ese import resuelva
      producto. **No es problema de este cambio y no lo bloquea.**
