# Design: Modelo de terceros

## Technical Approach

Reescritura clean-slate en **una migración SQL** (`supabase/migrations/0008_terceros_modelo.sql`),
habilitada por el estado de 0 filas. `terceros` concentra la identidad; `clientes` y `proveedores`
quedan como tablas de rol angostas cuyo `id` es a la vez PK y FK compuesta hacia
`terceros(id, drogueria_id)`. El código nuevo vive en `services/terceros/`, módulo de nivel superior
con submódulos por subdominio, consumido por `services/presupuestacion/` mediante una fachada
Python de un solo punto de entrada.

**Corrección al brief (verificada):** este repositorio **no usa Alembic ni SQLAlchemy**. `grep -i
alembic|sqlalchemy` sobre todo el árbol devuelve 0 coincidencias; el acceso a datos es
`supabase-py` sobre PostgREST y las migraciones son SQL plano numerado en `supabase/migrations/`
(`0001_initial.sql` … `0007_apellido_y_planes.sql`). El plan de migración de abajo respeta esa
convención real en lugar de introducir Alembic, que sería una dependencia nueva sin ningún
consumidor.

---

## Architecture Decisions

### D1 — `codigo_interno` se muda a `terceros`; la idempotencia del import se ancla en `terceros_legacy_map`

| Opción | Trade-off | Decisión |
|---|---|---|
| Mantener `codigo_interno` en cada tabla de rol | Reintroduce la duplicación de identidad que motiva el change; dos códigos para una empresa | Rechazada |
| `codigo_interno` único en `terceros`, import keyed por ese código | Un mismo código en el CSV de clientes y en el de proveedores del sistema legado son espacios de códigos **distintos**: colisionarían y fusionarían dos empresas | Rechazada |
| `codigo_interno` único en `terceros` + clave de import en `terceros_legacy_map (drogueria_id, sistema_origen, entidad_legacy, codigo_legacy)` | Una columna y una tabla más; a cambio, los dos espacios de códigos legados conviven sin colisión y la reejecución del CSV es idempotente por construcción | **Elegida** |

**Contrato cruzado:** el change `orden-compra` resuelve el cliente por `clientes.codigo_interno`
(`uq_cli_codigo`, verificado en vivo). Tras esta migración esa columna vive en `terceros`. Como
`terceros-modelo` se aplica primero, `orden-compra` debe hacer el lookup contra `terceros` y
verificar el rol en `clientes`. **Es un cambio de contrato, no un detalle de implementación.**

### D2 — Submódulos por subdominio, no paquete plano

`services/presupuestacion/catalogo/` es la evidencia en contra del paquete plano: acumula productos,
categorías, costos, stock **y** proveedores en un solo `service.py` de 24 funciones
(D-CATALOGO-001), al punto de que `proveedores` quedó sepultado en un módulo llamado "catálogo".
`services/terceros/` gobierna 8 tablas y 4 raíces de agregado; en plano repetiría exactamente ese
defecto. Cada subdominio conserva el cuarteto `models.py / repository.py / service.py / router.py`
ya vigente en `clientes/`.

### D3 — Un único patrón de error (deuda D-CLIENTES-004 / P2.1 / P3.1 no se replica)

Regla del módulo, sin excepciones:

| Situación | Excepción | Status |
|---|---|---|
| La fila no existe **o** pertenece a otra droguería (y el solicitante no es `superadmin`) | `NotFoundError` | 404 |
| Rol insuficiente **dentro de la misma droguería** | `ForbiddenError` | 403 |
| Input malformado o regla de negocio violada | `ValidationError` | 422 |
| Violación de unicidad (código o nombre repetido) | `ConflictError` | 409 |

Un solo guard, `services/terceros/errors.py::asegurar_tercero_de_la_drogueria(...)`, invocado
**una sola vez y solo en la capa de servicio**. Los routers **no** revalidan pertenencia: eso
elimina la doble query con excepciones divergentes de `clientes/`. No se agregan tipos de
excepción nuevos: se reusa `services/presupuestacion/core/exceptions.py` (reexportado por
`services/shared/exceptions.py`).

### D4 — `activo` con semántica real y obligatoria

`cliente_contactos.activo` es hoy escribible y expuesto pero ningún query lo filtra
(clientes/pendientes.md P3.2). Regla para **toda** tabla nueva que lleve `activo`:

1. Todo `listar_*` acepta `activo: bool | None` y lo aplica como filtro; la fachada de consumo
   (D5) fuerza `activo=True` por defecto, de modo que un contacto o dirección dado de baja nunca
   se filtra hacia presupuestación.
2. Existe un endpoint de baja lógica (`PATCH .../{id}` con `activo=false`). No hay `DELETE` físico
   en la API para sub-recursos — la contracara de D-CLIENTES-003, que dejaba a los sub-recursos
   sin ninguna forma de retiro.
3. Los índices únicos parciales ignoran filas inactivas (`WHERE es_principal AND activo`).
4. **Invariante testeable:** por cada tabla nueva con `activo`, un test afirma que una fila
   desactivada desaparece del listado por defecto. Sin ese test, la columna no se agrega.

`deleted_at`/`deleted_by` (soft delete auditado) existen **solo** en `terceros`, la raíz. Los hijos
se retiran con `activo`. La división es explícita, no accidental.

### D5 — Frontera de consumo: fachada unidireccional `services/terceros/api.py`

`services/presupuestacion/**` importa **exclusivamente** `services.terceros.api`, nunca un
`repository` o un `service` interno. `services/terceros/**` **nunca** importa
`services.presupuestacion.**`. La dependencia es de una sola dirección, así que
`imports/ → terceros.api` no puede formar ciclo (`terceros` no conoce `imports`).

Bloqueo real: `terceros` necesita `core/database.py`, `core/config.py` y `core/exceptions.py`, que
hoy viven bajo `presupuestacion/`. Se extraen a `services/shared/` y
`services/presupuestacion/core/{config,database,exceptions}.py` quedan como shims de reexport
explícito — **cero cambios** en los ~20 módulos que ya los importan.

```
services/presupuestacion/main.py ──(include_router)──▶ services/terceros/router.py
services/presupuestacion/imports/service.py ──▶ services.terceros.api ──▶ terceros/*/service.py
services/presupuestacion/clientes/service.py ──▶ services.terceros.api          │
services/presupuestacion/catalogo/service.py ──▶ services.terceros.api          ▼
                                                              services/shared/{config,database,exceptions}.py
```

Guard automatizado: `tests/terceros/test_dependencias.py` recorre con `ast` todos los `.py` bajo
`services/terceros/` y falla si aparece cualquier `import services.presupuestacion`.

### D6 — Sin vistas de compatibilidad nuevas; las vistas existentes se recrean con `security_invoker`

No se crea ninguna vista de compatibilidad de lectura. Pero la migración **debe** recrear cinco
vistas preexistentes que dependen de columnas que se eliminan (ver M4); esas vistas hoy **no**
declaran `security_invoker` y por lo tanto evaden RLS. Recrearlas es la oportunidad de corregirlo.

**La versión de Postgres no se pudo verificar** (sin acceso a Supabase MCP en esta sesión; el
change `orden-compra` tampoco lo logró). En vez de asumirla, la migración la **impone**:

```sql
DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'terceros-modelo requiere PostgreSQL 15+ para WITH (security_invoker = true); '
                    'version detectada: %', current_setting('server_version');
  END IF;
END $$;
```

Si la base fuera PG14 la migración aborta entera (transacción única) con un mensaje accionable, en
lugar de crear silenciosamente vistas que evaden RLS.

---

## Data Flow

```
CSV legado ──▶ imports/service.py ──▶ terceros.api.upsert_terceros_legacy()
                                            │
                                            ▼  (1 RPC, 1 transacción, N filas)
                              rpc upsert_tercero_legacy(...)
                                 ├─ 1. lookup terceros_legacy_map (FOR UPDATE) ─── hit ──▶ reusa tercero_id
                                 ├─ 2. miss: lookup terceros por (drogueria_id, cuit) ──▶ reusa (misma empresa, otro rol)
                                 ├─ 3. miss: INSERT terceros
                                 ├─ 4. INSERT terceros_legacy_map ON CONFLICT DO NOTHING
                                 └─ 5. INSERT clientes|proveedores (id = tercero_id) ON CONFLICT (id) DO UPDATE
                                            │
API nativa ──▶ terceros/router.py ──▶ */service.py ──▶ */repository.py ──▶ PostgREST
```

Reejecutar el mismo CSV recorre siempre la rama 1: cero filas nuevas en `terceros`, en el mapa y en
la tabla de rol; solo `UPDATE` de campos mutables.

---

## Interfaces / Contracts — DDL

### 1. Catálogos por droguería

```sql
CREATE TABLE sectores_contacto (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID        NOT NULL,
    nombre          TEXT        NOT NULL,
    descripcion     TEXT        NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_sec_id_drog  UNIQUE (id, drogueria_id),
    CONSTRAINT uq_sec_nombre   UNIQUE (drogueria_id, nombre),
    CONSTRAINT fk_sec_drog     FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);

CREATE TABLE condiciones_pago (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID        NOT NULL,
    nombre          TEXT        NOT NULL,                       -- '30/60/90', 'contado'
    plazos_dias     SMALLINT[]  NOT NULL DEFAULT '{}'::smallint[],
    descripcion     TEXT        NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_cp_id_drog   UNIQUE (id, drogueria_id),
    CONSTRAINT uq_cp_nombre    UNIQUE (drogueria_id, nombre),
    CONSTRAINT ck_cp_plazos    CHECK (0 <= ALL (plazos_dias)),
    CONSTRAINT fk_cp_drog      FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
COMMENT ON COLUMN condiciones_pago.plazos_dias IS
  'Reemplaza plazo_pago_dias (INTEGER) de clientes/proveedores: un pago en cuotas se expresa como {30,60,90}.';

CREATE TABLE formas_pago (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID        NOT NULL,
    nombre          TEXT        NOT NULL,
    tipo            TEXT        NOT NULL DEFAULT 'otro',
    descripcion     TEXT        NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_fp_id_drog   UNIQUE (id, drogueria_id),
    CONSTRAINT uq_fp_nombre    UNIQUE (drogueria_id, nombre),
    CONSTRAINT ck_fp_tipo      CHECK (tipo IN ('transferencia','cheque','echeq','efectivo','deposito','otro')),
    CONSTRAINT fk_fp_drog      FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
```

### 2. Identidad

```sql
CREATE TABLE terceros (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID        NOT NULL,
    codigo_interno  TEXT        NULL,
    razon_social    TEXT        NOT NULL,
    nombre_fantasia TEXT        NULL,
    cuit            TEXT        NULL,
    email           TEXT        NULL,
    telefono        TEXT        NULL,
    sitio_web       TEXT        NULL,
    notas           TEXT        NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_by      UUID        NULL,
    updated_by      UUID        NULL,
    deleted_at      TIMESTAMPTZ NULL,
    deleted_by      UUID        NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_terceros_id_drog UNIQUE (id, drogueria_id),
    CONSTRAINT uq_terceros_codigo  UNIQUE (drogueria_id, codigo_interno),
    CONSTRAINT ck_terceros_cuit    CHECK (cuit IS NULL OR cuit ~ '^[0-9]{11}$'),
    CONSTRAINT fk_terceros_drog      FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT fk_terceros_createdby FOREIGN KEY (created_by) REFERENCES usuarios (id),
    CONSTRAINT fk_terceros_updatedby FOREIGN KEY (updated_by) REFERENCES usuarios (id),
    CONSTRAINT fk_terceros_deletedby FOREIGN KEY (deleted_by) REFERENCES usuarios (id)
);

-- Un CUIT identifica una sola empresa viva por droguería. Parcial: permite CUIT NULL repetido
-- y no bloquea recrear un tercero borrado lógicamente.
CREATE UNIQUE INDEX uq_terceros_cuit
    ON terceros (drogueria_id, cuit)
    WHERE cuit IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX idx_terceros_drog_activo ON terceros (drogueria_id) WHERE activo AND deleted_at IS NULL;

CREATE TABLE terceros_legacy_map (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    tercero_id      UUID        NOT NULL,
    drogueria_id    UUID        NOT NULL,
    sistema_origen  TEXT        NOT NULL DEFAULT 'legacy',
    entidad_legacy  TEXT        NOT NULL,
    codigo_legacy   TEXT        NOT NULL,
    datos_legacy    JSONB       NULL,
    importado_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_tlm_id_drog  UNIQUE (id, drogueria_id),
    CONSTRAINT uq_tlm_codigo   UNIQUE (drogueria_id, sistema_origen, entidad_legacy, codigo_legacy),
    CONSTRAINT ck_tlm_entidad  CHECK (entidad_legacy IN ('cliente','proveedor')),
    CONSTRAINT fk_tlm_tercero  FOREIGN KEY (tercero_id, drogueria_id)
                               REFERENCES terceros (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_tlm_drog     FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
COMMENT ON CONSTRAINT uq_tlm_codigo ON terceros_legacy_map IS
  'Clave de idempotencia del import: el espacio de codigos de clientes y el de proveedores del sistema legado son independientes y pueden colisionar entre si.';
```

### 3. Direcciones y usos

```sql
CREATE TABLE tercero_direcciones (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    tercero_id      UUID        NOT NULL,
    drogueria_id    UUID        NOT NULL,
    etiqueta        TEXT        NULL,
    calle           TEXT        NOT NULL,
    numero          TEXT        NULL,
    piso_depto      TEXT        NULL,
    ciudad          TEXT        NULL,
    provincia       TEXT        NULL,
    codigo_postal   TEXT        NULL,
    pais            TEXT        NOT NULL DEFAULT 'AR',
    observaciones   TEXT        NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_tdir_id_drog    UNIQUE (id, drogueria_id),
    CONSTRAINT uq_tdir_id_tercero UNIQUE (id, tercero_id),   -- destino de fk_du_dir_tercero
    CONSTRAINT fk_tdir_tercero    FOREIGN KEY (tercero_id, drogueria_id)
                                  REFERENCES terceros (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_tdir_drog       FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
CREATE INDEX idx_tdir_tercero ON tercero_direcciones (tercero_id) WHERE activo;

CREATE TABLE direccion_usos (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    direccion_id    UUID        NOT NULL,
    tercero_id      UUID        NOT NULL,   -- denormalizado: habilita uq_du_principal
    drogueria_id    UUID        NOT NULL,
    uso             TEXT        NOT NULL,
    es_principal    BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_du_id_drog      UNIQUE (id, drogueria_id),
    CONSTRAINT uq_du_dir_uso      UNIQUE (direccion_id, uso),
    CONSTRAINT ck_du_uso          CHECK (uso IN ('facturacion','entrega','documentacion','otra')),
    CONSTRAINT fk_du_dir_drog     FOREIGN KEY (direccion_id, drogueria_id)
                                  REFERENCES tercero_direcciones (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_du_dir_tercero  FOREIGN KEY (direccion_id, tercero_id)
                                  REFERENCES tercero_direcciones (id, tercero_id) ON DELETE CASCADE,
    CONSTRAINT fk_du_drog         FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);

-- Como maximo una direccion principal por uso y por tercero, garantizado por la base.
CREATE UNIQUE INDEX uq_du_principal ON direccion_usos (tercero_id, uso) WHERE es_principal;
CREATE INDEX idx_du_uso ON direccion_usos (tercero_id, uso);
```

### 4. Contactos

```sql
CREATE TABLE terceros_contactos (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    tercero_id      UUID        NOT NULL,
    drogueria_id    UUID        NOT NULL,
    nombre          TEXT        NOT NULL,
    apellido        TEXT        NULL,
    sector_id       UUID        NULL,
    cargo           TEXT        NULL,
    email           TEXT        NULL,
    telefono        TEXT        NULL,
    celular         TEXT        NULL,
    es_principal    BOOLEAN     NOT NULL DEFAULT FALSE,
    notas           TEXT        NULL,
    activo          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_tc_id_drog   UNIQUE (id, drogueria_id),
    CONSTRAINT fk_tc_tercero   FOREIGN KEY (tercero_id, drogueria_id)
                               REFERENCES terceros (id, drogueria_id) ON DELETE CASCADE,
    CONSTRAINT fk_tc_sector    FOREIGN KEY (sector_id, drogueria_id)
                               REFERENCES sectores_contacto (id, drogueria_id),
    CONSTRAINT fk_tc_drog      FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);

-- 'activo' en el predicado: dar de baja al contacto principal libera el lugar (regla D4).
CREATE UNIQUE INDEX uq_tc_principal ON terceros_contactos (tercero_id) WHERE es_principal AND activo;
CREATE INDEX idx_tc_tercero ON terceros_contactos (tercero_id) WHERE activo;
```

### 5. `clientes` / `proveedores` como tablas de rol

```sql
ALTER TABLE clientes
    DROP COLUMN nombre,
    DROP COLUMN direccion,
    DROP COLUMN ciudad,
    DROP COLUMN provincia,
    DROP COLUMN codigo_postal,
    DROP COLUMN plazo_pago_dias,
    DROP COLUMN condiciones_pago,
    DROP COLUMN codigo_interno,                       -- arrastra uq_cli_codigo
    ADD  COLUMN condicion_pago_id UUID NULL,
    ADD  COLUMN forma_pago_id     UUID NULL,
    ALTER COLUMN id DROP DEFAULT;                     -- el id lo provee terceros, no gen_random_uuid()

ALTER TABLE clientes
    ADD CONSTRAINT fk_cli_tercero   FOREIGN KEY (id, drogueria_id)
                                    REFERENCES terceros (id, drogueria_id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_cli_condpago  FOREIGN KEY (condicion_pago_id, drogueria_id)
                                    REFERENCES condiciones_pago (id, drogueria_id),
    ADD CONSTRAINT fk_cli_formapago FOREIGN KEY (forma_pago_id, drogueria_id)
                                    REFERENCES formas_pago (id, drogueria_id);

-- Sobreviven: id, drogueria_id, tipo (+ck_clientes_tipo), activo, created_by, updated_by,
-- deleted_at, deleted_by, created_at, updated_at, uq_cli_id_drog.

ALTER TABLE proveedores
    DROP COLUMN codigo_interno,
    DROP COLUMN razon_social,
    DROP COLUMN nombre_comercial,
    DROP COLUMN cuit,
    DROP COLUMN plazo_pago_dias,
    DROP COLUMN condiciones_pago,
    ADD  COLUMN condicion_pago_id UUID NULL,
    ADD  COLUMN forma_pago_id     UUID NULL,
    ALTER COLUMN id DROP DEFAULT;

ALTER TABLE proveedores
    ADD CONSTRAINT fk_prov_tercero   FOREIGN KEY (id, drogueria_id)
                                     REFERENCES terceros (id, drogueria_id) ON DELETE CASCADE,
    ADD CONSTRAINT fk_prov_condpago  FOREIGN KEY (condicion_pago_id, drogueria_id)
                                     REFERENCES condiciones_pago (id, drogueria_id),
    ADD CONSTRAINT fk_prov_formapago FOREIGN KEY (forma_pago_id, drogueria_id)
                                     REFERENCES formas_pago (id, drogueria_id);

-- Sobreviven: id, drogueria_id, tipo (+ck_prov_tipo), es_competidor, es_proveedor_compra,
-- activo, auditoría, uq_prov_id_drog.

DROP TABLE cliente_contactos;   -- reemplazada por terceros_contactos
```

### 6. RLS

`terceros`, `tercero_direcciones`, `direccion_usos`, `terceros_contactos`, `terceros_legacy_map`
llevan el **conjunto unión** de roles de escritura de `clientes` y `proveedores` — un tercero puede
cumplir ambos roles, así que restringir a uno solo bloquearía al otro:

```sql
ALTER TABLE terceros ENABLE ROW LEVEL SECURITY;
CREATE POLICY terceros_sel ON terceros FOR SELECT
    USING ((select mismo_tenant(drogueria_id)));
CREATE POLICY terceros_ins ON terceros FOR INSERT
    WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
                AND (select mismo_tenant(drogueria_id)));
CREATE POLICY terceros_upd ON terceros FOR UPDATE
    USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
                AND (select mismo_tenant(drogueria_id)))
    WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial','compras')
                AND (select mismo_tenant(drogueria_id)));
CREATE POLICY terceros_del ON terceros FOR DELETE USING ((select es_superadmin()));
-- idéntico para tercero_direcciones, direccion_usos, terceros_contactos, terceros_legacy_map.

-- Catálogos: lectura para el tenant, escritura acotada.
-- sectores_contacto / condiciones_pago / formas_pago: SELECT mismo_tenant;
-- INSERT/UPDATE en ('admin','gerencia'); DELETE es_superadmin().

GRANT SELECT, INSERT, UPDATE, DELETE ON <las 8 tablas> TO service_role;
GRANT SELECT, INSERT, UPDATE          ON <las 8 tablas> TO authenticated;
NOTIFY pgrst, 'reload schema';
```

`GRANT` explícito porque Supabase no autoexpone tablas nuevas al Data API (precedente:
`0007_apellido_y_planes.sql:99-103`).

### 7. RPC de upsert idempotente

```sql
CREATE OR REPLACE FUNCTION upsert_terceros_legacy(
    p_drogueria_id   UUID,
    p_sistema_origen TEXT,
    p_entidad_legacy TEXT,      -- 'cliente' | 'proveedor'
    p_filas          JSONB,     -- array de objetos: codigo_legacy, razon_social, cuit, tipo, ...
    p_usuario_id     UUID
) RETURNS TABLE (codigo_legacy TEXT, tercero_id UUID, accion TEXT)
LANGUAGE plpgsql AS $$
DECLARE fila JSONB; v_tid UUID; v_accion TEXT;
BEGIN
  FOR fila IN SELECT * FROM jsonb_array_elements(p_filas) LOOP
    -- 1) clave de idempotencia
    SELECT m.tercero_id INTO v_tid FROM terceros_legacy_map m
     WHERE m.drogueria_id = p_drogueria_id AND m.sistema_origen = p_sistema_origen
       AND m.entidad_legacy = p_entidad_legacy AND m.codigo_legacy = fila->>'codigo_legacy'
     FOR UPDATE;
    v_accion := 'reusado';

    -- 2) misma empresa ya cargada bajo el otro rol
    IF v_tid IS NULL AND nullif(fila->>'cuit','') IS NOT NULL THEN
      SELECT t.id INTO v_tid FROM terceros t
       WHERE t.drogueria_id = p_drogueria_id AND t.cuit = fila->>'cuit' AND t.deleted_at IS NULL
       FOR UPDATE;
      IF v_tid IS NOT NULL THEN v_accion := 'vinculado'; END IF;
    END IF;

    -- 3) alta
    IF v_tid IS NULL THEN
      INSERT INTO terceros (drogueria_id, codigo_interno, razon_social, cuit, created_by, updated_by)
      VALUES (p_drogueria_id, fila->>'codigo_legacy', fila->>'razon_social',
              nullif(fila->>'cuit',''), p_usuario_id, p_usuario_id)
      RETURNING id INTO v_tid;
      v_accion := 'creado';
    ELSE
      UPDATE terceros SET razon_social = coalesce(fila->>'razon_social', razon_social),
                          cuit = coalesce(nullif(fila->>'cuit',''), cuit),
                          updated_by = p_usuario_id, activo = TRUE
       WHERE id = v_tid;
    END IF;

    -- 4) mapa (idempotente)
    INSERT INTO terceros_legacy_map (tercero_id, drogueria_id, sistema_origen,
                                     entidad_legacy, codigo_legacy, datos_legacy)
    VALUES (v_tid, p_drogueria_id, p_sistema_origen, p_entidad_legacy,
            fila->>'codigo_legacy', fila)
    ON CONFLICT (drogueria_id, sistema_origen, entidad_legacy, codigo_legacy) DO NOTHING;

    -- 5) tabla de rol (id compartido)
    IF p_entidad_legacy = 'cliente' THEN
      INSERT INTO clientes (id, drogueria_id, tipo, activo, created_by, updated_by)
      VALUES (v_tid, p_drogueria_id, coalesce(fila->>'tipo','otro'), TRUE, p_usuario_id, p_usuario_id)
      ON CONFLICT (id) DO UPDATE SET tipo = excluded.tipo, activo = TRUE, updated_by = p_usuario_id;
    ELSE
      INSERT INTO proveedores (id, drogueria_id, tipo, es_competidor, es_proveedor_compra,
                               activo, created_by, updated_by)
      VALUES (v_tid, p_drogueria_id, coalesce(fila->>'tipo','otro'),
              coalesce((fila->>'es_competidor')::bool, TRUE),
              coalesce((fila->>'es_proveedor_compra')::bool, FALSE),
              TRUE, p_usuario_id, p_usuario_id)
      ON CONFLICT (id) DO UPDATE SET tipo = excluded.tipo, activo = TRUE, updated_by = p_usuario_id;
    END IF;

    codigo_legacy := fila->>'codigo_legacy'; tercero_id := v_tid; accion := v_accion;
    RETURN NEXT;
  END LOOP;
END $$;

REVOKE ALL ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION upsert_terceros_legacy(UUID,TEXT,TEXT,JSONB,UUID) TO service_role;
```

**Sin `SECURITY DEFINER`** (mismo criterio que `reserve_extraction`, `0002_rpc_reserve.sql:16-51`):
la invoca `get_service_client()`, que ya bypasea RLS, y una función `SECURITY DEFINER` en un schema
expuesto es un antipatrón del checklist de seguridad de Supabase. Todo el cuerpo corre en una
transacción, así que un fallo en el paso 5 revierte los pasos 3 y 4 — no quedan `terceros`
huérfanos.

La desactivación por ausencia (`desactivar_clientes`/`desactivar_proveedores`, hoy en
`imports/repository.py`) se mantiene **fuera** del RPC y opera sobre `terceros_legacy_map` para
resolver los códigos ausentes; desactiva la **fila de rol**, no el `tercero` (una empresa que
desaparece del CSV de clientes puede seguir activa como proveedor).

---

## File Changes

| Archivo | Acción | Descripción |
|---|---|---|
| `supabase/migrations/0008_terceros_modelo.sql` | Crear | Migración única (M1–M10) |
| `supabase/migrations/0008_terceros_modelo.down.sql` | Crear | Reversión manual (no la ejecuta `db push`) |
| `docs/schema/extractor_final.sql`, `docs/schema/rls_final.sql` | Modificar | Snapshot de referencia al día |
| `services/shared/{__init__,config,database,exceptions}.py` | Crear | Núcleo compartido extraído |
| `services/presupuestacion/core/{config,database,exceptions}.py` | Modificar | Shims de reexport explícito |
| `services/terceros/{__init__,router,api,errors}.py` | Crear | Fachada, router agregador, guard único |
| `services/terceros/identidad/{models,repository,service,router}.py` | Crear | `terceros` + roles cliente/proveedor |
| `services/terceros/direcciones/{models,repository,service,router}.py` | Crear | `tercero_direcciones` + `direccion_usos` |
| `services/terceros/contactos/{models,repository,service,router}.py` | Crear | `terceros_contactos` |
| `services/terceros/catalogos/{models,repository,service,router}.py` | Crear | 3 catálogos |
| `services/presupuestacion/main.py` | Modificar | `include_router(terceros_router)` |
| `services/presupuestacion/clientes/*` | Modificar | Pierde identidad y contactos; consume `terceros.api` |
| `services/presupuestacion/catalogo/*` | Modificar | Pierde proveedores; consume `terceros.api` |
| `services/presupuestacion/imports/{service,repository}.py` | Modificar | Un RPC por lote en lugar de insert/upsert directos |
| `services/extraccion/routers/clientes.py` | **Modificar** | Ver nota abajo |
| `tests/terceros/**` | Crear | Incluye `test_dependencias.py` e idempotencia |
| `tests/test_clientes_api.py`, `tests/catalogo/`, `tests/imports/` | Modificar | Afirman la forma plana actual |
| `docs/modulos/terceros/**` | Crear | Documentación del módulo, con D3 y D4 como decisiones explícitas |

**Corrección a `proposal.md`:** el proposal marca `services/extraccion/routers/clientes.py` como
"sin cambios" porque `id` y `nombre` "sobreviven a la división". Es incorrecto: `clientes.nombre`
se elimina, la fuente canónica pasa a ser `terceros.razon_social`. El archivo requiere un cambio de
una línea usando el embedding de PostgREST, habilitado por `fk_cli_tercero`:

```python
client.table("clientes").select("id, terceros(razon_social)")
```

**Conteo:** el proposal dice "7 tablas nuevas"; son **8**. La octava es `direccion_usos`, la tabla
puente N:M que el proposal describe en prosa ("usos N:M") pero no cuenta en `Affected Areas`.

---

## Migration / Rollout

Un solo archivo = una sola transacción (`supabase db push` aplica cada migración envuelta en
transacción; **no** agregar `BEGIN`/`COMMIT` explícitos, entra en conflicto con ese envoltorio).
Cada paso es individualmente reversible por el `.down.sql` espejo.

| # | Paso | Reversión |
|---|---|---|
| M0 | `DO $$ ... server_version_num >= 150000 ... $$` (D6) | n/a — aborta antes de tocar nada |
| M1 | `sectores_contacto`, `condiciones_pago`, `formas_pago` | `DROP TABLE` |
| M2 | `terceros` + índices | `DROP TABLE` |
| M3 | `terceros_legacy_map` | `DROP TABLE` |
| M4 | `DROP VIEW v_presupuesto_revision, v_matching_pendiente, v_renglones_ganados, v_entregas_pendientes, v_precios_especiales_vigentes` | Recrear desde el snapshot en git |
| M5 | `ALTER TABLE clientes` / `ALTER TABLE proveedores` (sección 5) | `ALTER` inverso desde el snapshot |
| M6 | `tercero_direcciones`, `direccion_usos` | `DROP TABLE` |
| M7 | `terceros_contactos`; `DROP TABLE cliente_contactos` | `DROP` / recrear desde el snapshot |
| M8 | Recrear las 5 vistas `WITH (security_invoker = true)`, leyendo el nombre desde `terceros` y el plazo desde `condiciones_pago.plazos_dias` | Recrear la versión previa |
| M9 | Triggers `trg_set_updated_at`, RLS, políticas, `GRANT`, `NOTIFY pgrst` | `DROP POLICY` / `REVOKE` |
| M10 | `upsert_terceros_legacy` + `REVOKE`/`GRANT` | `DROP FUNCTION` |

**M4 es obligatorio y bloqueante**, no una optimización: cuatro vistas seleccionan `cl.nombre` y
`v_precios_especiales_vigentes` selecciona `prov.razon_social`, `prov.nombre_comercial` y
`prov.plazo_pago_dias`. Sin el `DROP VIEW` previo, el `ALTER TABLE ... DROP COLUMN` de M5 falla con
error de dependencia y la migración entera revierte.

**Secuenciación:** `terceros-modelo` se aplica y mergea **antes** que `orden-compra` (ver D1).

**Rollback:** seguro mientras las 8 tablas nuevas sigan vacías. Con terceros ya cargados de forma
nativa, exportar antes del `DROP`: direcciones, contactos y catálogos no tienen destino en el
esquema plano.

**Corte para `auto-chain`** (presupuesto de 1000 líneas por PR):
PR1 migración + `services/shared/` · PR2 `terceros/catalogos` + `terceros/identidad` ·
PR3 `terceros/direcciones` + `terceros/contactos` · PR4 consumidores
(`clientes/`, `catalogo/`, `extraccion/routers/clientes.py`) · PR5 `imports/` + RPC.

---

## Testing Strategy

| Capa | Qué se testea | Cómo |
|---|---|---|
| Unit | Servicios de los 4 subdominios: el guard de D3 lanza `NotFoundError` (nunca `ValidationError` ni `ForbiddenError`) ante otra droguería | Funciones puras con `client` mockeado, como `tests/catalogo/test_service.py` |
| Unit | D4: cada `listar_*` oculta filas `activo=false` por defecto | Un test por tabla nueva con `activo` |
| Unit | D5: ningún `.py` bajo `services/terceros/` importa `services.presupuestacion` | `ast` sobre el árbol, `tests/terceros/test_dependencias.py` |
| Integración | **Idempotencia**: correr el mismo CSV dos veces deja igual el conteo de `terceros`, `terceros_legacy_map`, `clientes` y `proveedores` | Cobertura hoy inexistente — riesgo de regresión silenciosa más alto del change |
| Integración | Doble rol: el mismo CUIT importado como cliente y luego como proveedor produce **un** `tercero` con dos filas de rol | RPC contra base de test |
| Integración | Colisión de códigos: `codigo_legacy='001'` en el CSV de clientes y en el de proveedores produce **dos** terceros distintos | Justifica D1 |
| Integración | Los `es_principal` únicos rebotan con `ConflictError`, y dar de baja al principal libera el lugar | Índices parciales |
| API | CRUD completo de las 5 capacidades nuevas; el `GET` de `services/extraccion/routers/clientes.py` sigue devolviendo `id` + nombre | FastAPI `TestClient` |

## Threat Matrix

N/A — este change no introduce enrutamiento dinámico, comandos de shell, subprocesos, automatización
de VCS/PR, clasificación de archivos ejecutables ni integración de procesos. La superficie sensible
es RLS/`GRANT`/RPC, cubierta explícitamente por la sección 6, la sección 7 (sin `SECURITY DEFINER`)
y D6 (`security_invoker`).

## Open Questions

- [ ] **Versión de Postgres sin verificar.** Sin acceso a Supabase MCP en esta sesión. Mitigado —
      no asumido — por el guard M0, que aborta la migración si es < 15. Confirmar con
      `list_extensions` o `select version()` antes de aplicar acorta el ciclo de feedback.
- [ ] ¿`es_competidor` / `es_proveedor_compra` se mantienen como booleanos en `proveedores`
      (decisión actual, heredada del proposal) o se pliegan al modelo de roles en un change futuro?
- [ ] `datos_legacy JSONB` en `terceros_legacy_map` guarda la fila cruda del CSV. Confirmar que no
      contiene datos personales que obliguen a una política de retención.

## Key Learnings

1. El proyecto no usa Alembic ni SQLAlchemy: las migraciones son SQL plano numerado bajo `supabase/migrations/` y el acceso a datos es `supabase-py` sobre PostgREST.
2. Cinco vistas existentes dependen de `clientes.nombre` y de columnas de `proveedores` que este change elimina, así que el `DROP VIEW` previo es un paso bloqueante de la migración.
3. Anclar la idempotencia del import en `terceros_legacy_map` en lugar de en `codigo_interno` evita fusionar empresas distintas cuando los espacios de códigos legados de clientes y proveedores colisionan.
4. El proposal subestima el alcance en dos puntos verificables: son ocho tablas nuevas, no siete, y `services/extraccion/routers/clientes.py` sí requiere cambio porque `clientes.nombre` desaparece.
5. Extraer `services/shared/` con shims de reexport permite que `services/terceros/` sea un módulo de nivel superior real sin que ningún import existente de `presupuestacion/core/` se rompa.
