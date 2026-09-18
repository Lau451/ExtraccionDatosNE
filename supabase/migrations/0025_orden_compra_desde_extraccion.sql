-- =============================================================================
-- Migration 0025: orden de compra originada en extraccion
--
-- 1. proceso_comercial_id pasa a nullable + CHECK de anclaje: una OC extraida de
--    un documento de cliente se ancla por cliente_id, no por proceso comercial.
-- 2. uq_oc (global) se reemplaza por dos indices unicos parciales, uno por ruta
--    de anclaje. Dos clientes distintos pueden numerar sus OC igual.
-- 3. entregas_oc_items.cantidad_planificada: el plan y el hecho comparten fila
--    (design.md D1). crear_entrega no la escribe -> queda 0 = "registrada
--    directo, sin plan previo", que es exactamente su semantica actual.
-- 4. oc_cliente_alias (TABLA NUEVA): el sistema aprende que encabezado de
--    documento corresponde a que cliente, a partir de cada confirmacion humana
--    (design.md D3.1). Reemplaza el anclaje por codigo_interno, que era
--    estructuralmente imposible (design.md C5).
-- 5. extraction_results.grupo_id: N archivos = una sola OC (design.md D13).
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

-- 1) anclaje ------------------------------------------------------------------
ALTER TABLE ordenes_compra ALTER COLUMN proceso_comercial_id DROP NOT NULL;

ALTER TABLE ordenes_compra
  ADD CONSTRAINT ck_oc_anclaje
  CHECK (proceso_comercial_id IS NOT NULL OR cliente_id IS NOT NULL);

COMMENT ON COLUMN ordenes_compra.proceso_comercial_id IS
  'NULL cuando la OC se origina en una extraccion de documento de cliente; en ese caso el anclaje es cliente_id. Garantizado por ck_oc_anclaje.';

-- 2) unicidad por ruta de anclaje ---------------------------------------------
-- uq_oc es (numero_oc, version_numero) GLOBAL. Ambos alcances nuevos son
-- estrictamente mas permisivos: cualquier par unico globalmente sigue siendo
-- unico dentro de cualquier subconjunto, asi que la creacion no puede fallar por
-- filas preexistentes. El riesgo de duplicados vive en la migracion inversa.
-- Ninguna FK depende de uq_oc: todas referencian id o (id, drogueria_id).
ALTER TABLE ordenes_compra DROP CONSTRAINT IF EXISTS uq_oc;

CREATE UNIQUE INDEX uq_oc_por_cliente
  ON ordenes_compra (drogueria_id, cliente_id, numero_oc, version_numero)
  WHERE cliente_id IS NOT NULL;

CREATE UNIQUE INDEX uq_oc_por_proceso
  ON ordenes_compra (drogueria_id, proceso_comercial_id, numero_oc, version_numero)
  WHERE cliente_id IS NULL;
-- ck_oc_anclaje garantiza que dentro de uq_oc_por_proceso (cliente_id IS NULL)
-- la columna proceso_comercial_id nunca es NULL: ninguna ruta queda sin cubrir.

-- 3) plan de entregas ---------------------------------------------------------
ALTER TABLE entregas_oc_items
  ADD COLUMN IF NOT EXISTS cantidad_planificada NUMERIC(12, 2) NOT NULL DEFAULT 0;

ALTER TABLE entregas_oc_items
  ADD CONSTRAINT ck_eoci_planificada CHECK (cantidad_planificada >= 0);

COMMENT ON COLUMN entregas_oc_items.cantidad_planificada IS
  'Lo que se prometio entregar en esta entrega. Se escribe al confirmar la OC (stock SIN tocar) y se compara contra cantidad_entregada al importar el retorno de Progress. 0 = entrega registrada directo, sin plan previo (camino de crear_entrega).';

-- 4) alias aprendido de cliente (D3.1) ----------------------------------------
-- La OC la redacta el cliente: nunca puede traer nuestro codigo_interno (C5).
-- El unico dato confiable para anclar es el que un humano YA confirmo. Esta
-- tabla lo persiste: encabezado normalizado -> cliente, por drogueria.
CREATE TABLE IF NOT EXISTS oc_cliente_alias (
    id                          UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id                UUID            NOT NULL,
    texto_extraido_normalizado  TEXT            NOT NULL,
    texto_extraido_original     TEXT            NOT NULL,
    cliente_id                  UUID            NOT NULL,
    veces_confirmado            INTEGER         NOT NULL DEFAULT 1,
    created_by                  UUID            NULL,
    updated_by                  UUID            NULL,
    created_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at                  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_oca UNIQUE (drogueria_id, texto_extraido_normalizado),
    CONSTRAINT ck_oca_texto CHECK (length(trim(texto_extraido_normalizado)) > 0),
    CONSTRAINT ck_oca_veces CHECK (veces_confirmado >= 1),
    CONSTRAINT fk_oca_drogueria FOREIGN KEY (drogueria_id)
        REFERENCES droguerias (id) ON DELETE CASCADE,
    -- FK compuesta contra uq_cli_id_drog (clientes: UNIQUE (id, drogueria_id)):
    -- misma convencion que fk_cli_condpago / fk_cli_formapago. Impide que un
    -- alias apunte a un cliente de otra drogueria aunque la RLS falle.
    CONSTRAINT fk_oca_cliente FOREIGN KEY (cliente_id, drogueria_id)
        REFERENCES clientes (id, drogueria_id) ON DELETE CASCADE
);

-- uq_oca ES el indice del nivel 1 (igualdad exacta sobre la clave unica).
-- Este otro existe solo para listar/limpiar los alias de un cliente dado.
CREATE INDEX IF NOT EXISTS idx_oca_cliente
    ON oc_cliente_alias (drogueria_id, cliente_id);

COMMENT ON TABLE oc_cliente_alias IS
  'Aprendizaje del pipeline de OC: que texto de encabezado de un documento de cliente corresponde a que cliente nuestro. Se escribe por UPSERT en cada confirmacion humana de la pantalla de validacion (design.md D3.1). La ultima confirmacion gana y resetea veces_confirmado.';
COMMENT ON COLUMN oc_cliente_alias.texto_extraido_normalizado IS
  'Clave de match del nivel 1. Producida por services/presupuestacion/core/texto.py::normalizar_descripcion (NFKD -> ascii, puntuacion -> espacio, espacios colapsados, UPPER). NO se reimplementa en SQL: la normalizacion vive en un solo lugar.';
COMMENT ON COLUMN oc_cliente_alias.veces_confirmado IS
  'Cuantas veces se reconfirmo este mapeo. Se resetea a 1 cuando el usuario CORRIGE el cliente: un alias corregido es un alias nuevo y no hereda la confianza del mapeo equivocado.';

ALTER TABLE oc_cliente_alias ENABLE ROW LEVEL SECURITY;

-- Misma convencion de aislamiento por tenant que terceros / tercero_direcciones
-- (0008_terceros_modelo.sql:608-638): mismo_tenant() + get_rol(), envueltos en
-- (select ...) por la optimizacion de 0019 (se evalua una vez, no por fila).
DROP POLICY IF EXISTS oca_sel ON oc_cliente_alias;
CREATE POLICY oca_sel ON oc_cliente_alias FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS oca_ins ON oc_cliente_alias;
CREATE POLICY oca_ins ON oc_cliente_alias FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial')
              AND (select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS oca_upd ON oc_cliente_alias;
CREATE POLICY oca_upd ON oc_cliente_alias FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','lider_comercial','comercial')
              AND (select mismo_tenant(drogueria_id)));

DROP POLICY IF EXISTS oca_del ON oc_cliente_alias;
CREATE POLICY oca_del ON oc_cliente_alias FOR DELETE USING ((select es_superadmin()));

-- Supabase no auto-expone tablas nuevas al Data API.
GRANT SELECT, INSERT, UPDATE, DELETE ON oc_cliente_alias TO service_role;
GRANT SELECT, INSERT, UPDATE           ON oc_cliente_alias TO authenticated;

-- 5) agrupacion multi-archivo (D13) -------------------------------------------
-- N filas con el mismo grupo_id son UNA sola OC. Nullable a proposito: el caso
-- de un archivo suelto (que es el 100% de las filas existentes y la mayoria de
-- las futuras) no cambia en nada. Sin FK ni tabla propia: el grupo no tiene
-- ningun atributo que no viva ya en sus miembros.
ALTER TABLE extraction_results ADD COLUMN IF NOT EXISTS grupo_id UUID NULL;

-- Parcial: solo indexa las filas agrupadas, que son una minoria. El acceso es
-- siempre "dame los miembros de este grupo".
CREATE INDEX IF NOT EXISTS idx_er_grupo
    ON extraction_results (grupo_id)
    WHERE grupo_id IS NOT NULL;

COMMENT ON COLUMN extraction_results.grupo_id IS
  'NULL = extraccion suelta (caso normal). No NULL = esta fila es una parte de un documento repartido en varios archivos; todas las filas con el mismo grupo_id se validan juntas y producen UNA sola orden_compra (design.md D13). Cada miembro conserva su propio csv_disk_path intacto: las filas se concatenan en la lectura, nunca en disco, y sin deduplicar ni renumerar (design.md D13.1).';

-- uq_er_sha256 no se toca. Sigue siendo global, asi que subir el mismo archivo
-- dos veces dentro de un grupo devuelve el 409 de duplicado que /procesar ya
-- emite. Es el comportamiento correcto: dos archivos binariamente identicos no
-- son dos entregas distintas.
