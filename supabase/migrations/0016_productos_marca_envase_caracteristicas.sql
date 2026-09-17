-- =============================================================================
-- Migration 0016: marca/envase normalizados + caracteristicas multiples de producto
--
-- Extiende el modulo productos (services/productos/) sin tocar su forma
-- basica. Contexto: productos.laboratorio era TEXT libre; se reemplaza por
-- marca_id -> marcas (catalogo por drogueria, mismo patron que categorias).
-- Se agrega envase_id -> envases (catalogo separado de forma_farmaceutica:
-- un producto tiene forma farmaceutica -comprimido, ampolla- Y envase fisico
-- -caja, frasco-, son dos ejes distintos) y alicuota_iva (dato fiscal ausente
-- hasta ahora, necesario para presupuestos/facturacion).
--
-- Caracteristicas especiales (psicotropico, heladera, vale, libre de gluten,
-- etc.) pasan a ser m:m via producto_caracteristicas en vez de un campo de
-- texto unico: un producto puede tener 0..N caracteristicas, y agregar una
-- caracteristica nueva es una fila de catalogo, no un cambio de esquema.
--
-- Verificado en vivo (grnamollopxdlstcpxhc, proyecto de test) antes de
-- escribir: forma real de categorias (id, drogueria_id, nombre, activa,
-- created_at; sin updated_at, sin trigger) y sus RLS (cat_sel abierto al
-- tenant, cat_ins/upd admin+gerencia, cat_del superadmin) se usan como
-- plantilla exacta para marcas/envases/caracteristicas. RLS de productos
-- (prod_ins/upd admin+gerencia+compras, prod_del superadmin) se usa como
-- plantilla para producto_caracteristicas.
--
-- productos.laboratorio NO se elimina en esta migracion: al verificar antes
-- de escribir esto, la tabla productos ya tenia 15 filas (fixtures de test
-- de PCP/matching, todas con laboratorio NULL) en el proyecto de test, no 0
-- como se esperaba. Se deja la columna nullable y sin uso nuevo (el codigo
-- de aplicacion deja de leerla/escribirla) en vez de un DROP, para no asumir
-- que ninguna fila real depende de ella. Retiro definitivo de la columna:
-- pendiente, a resolver en una migracion aparte una vez confirmado que nada
-- la usa.
--
-- Esquema aditivo (salvo el ALTER de productos, que solo agrega columnas):
-- no toca ninguna tabla existente mas alla de eso. Un solo archivo = una
-- sola transaccion (ver 0011).
--
-- Pasos (M0-M6):
--   M0  Guard de version de Postgres (>=15, consistente con 0011)
--   M1  marcas
--   M2  envases
--   M3  caracteristicas
--   M4  producto_caracteristicas
--   M5  ALTER productos: marca_id, envase_id, alicuota_iva
--   M6  RLS + politicas + GRANTs + NOTIFY pgrst
-- =============================================================================

-- =============================================================================
-- M0 — Guard de version de Postgres
-- =============================================================================
DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

-- =============================================================================
-- M1 — marcas
-- Catalogo por drogueria. Mismo shape que categorias (id, drogueria_id,
-- nombre, activa, created_at) — sin updated_at/trigger, igual que categorias.
-- =============================================================================
CREATE TABLE IF NOT EXISTS marcas (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID            NOT NULL,
    nombre          TEXT            NOT NULL,
    activa          BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_marcas    UNIQUE (drogueria_id, nombre),
    CONSTRAINT fk_marc_drog FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
COMMENT ON TABLE marcas IS 'Marcas/laboratorios normalizados por drogueria. Reemplaza productos.laboratorio (TEXT libre). Evita texto libre inconsistente en productos y reglas futuras ("todos los articulos de tal marca").';

-- =============================================================================
-- M2 — envases
-- Catalogo por drogueria, mismo shape que marcas/categorias. Concepto
-- distinto de productos.forma_farmaceutica: envase es el contenedor fisico
-- (caja, frasco, blister, ampolla, sachet), forma_farmaceutica es la forma
-- del producto en si (comprimido, suspension, crema). Ver analisis del
-- maestro legacy: "Envase" mezclaba ambos conceptos + una caracteristica
-- especial (HELADERA), de ahi la separacion en tres piezas distintas
-- (envases, forma_farmaceutica ya existente, caracteristicas mas abajo).
-- =============================================================================
CREATE TABLE IF NOT EXISTS envases (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID            NOT NULL,
    nombre          TEXT            NOT NULL,
    activa          BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_envases   UNIQUE (drogueria_id, nombre),
    CONSTRAINT fk_env_drog  FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
COMMENT ON TABLE envases IS 'Envases normalizados por drogueria (caja, frasco, blister, ampolla, sachet...). Distinto de productos.forma_farmaceutica (forma del producto, no su contenedor).';

-- =============================================================================
-- M3 — caracteristicas
-- Catalogo por drogueria, mismo shape que marcas/envases/categorias.
-- =============================================================================
CREATE TABLE IF NOT EXISTS caracteristicas (
    id              UUID            NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID            NOT NULL,
    nombre          TEXT            NOT NULL,
    activa          BOOLEAN         NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    PRIMARY KEY (id),
    CONSTRAINT uq_caracteristicas UNIQUE (drogueria_id, nombre),
    CONSTRAINT fk_car_drog        FOREIGN KEY (drogueria_id) REFERENCES droguerias (id)
);
COMMENT ON TABLE caracteristicas IS 'Catalogo de caracteristicas especiales de producto (psicotropico, heladera, vale, libre de gluten, libre de latex...). Un producto puede tener 0..N via producto_caracteristicas; agregar una caracteristica nueva es un insert de catalogo, no un cambio de esquema.';

-- =============================================================================
-- M4 — producto_caracteristicas (puente N:M)
-- FK simple a productos.id (sin UNIQUE(id, drogueria_id) compuesto): productos
-- no tiene ese patron -confirmado en vivo antes de escribir esta migracion,
-- igual que dejo constancia 0011 para producto_id en pcp_renglones/
-- producto_proveedores-, asi que se mantiene la misma excepcion aqui.
-- =============================================================================
CREATE TABLE IF NOT EXISTS producto_caracteristicas (
    id                  UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id        UUID        NOT NULL,
    producto_id         UUID        NOT NULL,
    caracteristica_id   UUID        NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_by          UUID        NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_prodcar_producto_car UNIQUE (producto_id, caracteristica_id),
    CONSTRAINT fk_prodcar_drog         FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT fk_prodcar_producto     FOREIGN KEY (producto_id) REFERENCES productos (id),
    CONSTRAINT fk_prodcar_car          FOREIGN KEY (caracteristica_id) REFERENCES caracteristicas (id),
    CONSTRAINT fk_prodcar_createdby    FOREIGN KEY (created_by) REFERENCES usuarios (id)
);
COMMENT ON TABLE producto_caracteristicas IS 'Asociacion N:M producto<->caracteristica. Sin campo mutable propio (solo existe/no existe la asignacion): no tiene politica de UPDATE, a diferencia de otras tablas puente con estado (ej. producto_proveedores.preferido).';

CREATE INDEX IF NOT EXISTS idx_prodcar_producto ON producto_caracteristicas (drogueria_id, producto_id);

-- =============================================================================
-- M5 — ALTER productos: marca_id, envase_id, alicuota_iva
-- laboratorio NO se toca en esta migracion (ver nota de cabecera).
-- =============================================================================
ALTER TABLE productos
  ADD COLUMN IF NOT EXISTS marca_id      UUID           NULL,
  ADD COLUMN IF NOT EXISTS envase_id     UUID           NULL,
  ADD COLUMN IF NOT EXISTS alicuota_iva  NUMERIC(5, 2)  NULL;

ALTER TABLE productos
  ADD CONSTRAINT fk_prod_marca  FOREIGN KEY (marca_id) REFERENCES marcas (id),
  ADD CONSTRAINT fk_prod_envase FOREIGN KEY (envase_id) REFERENCES envases (id),
  ADD CONSTRAINT ck_prod_alicuota_iva CHECK (alicuota_iva IS NULL OR alicuota_iva >= 0);

COMMENT ON COLUMN productos.marca_id IS 'FK a marcas. Reemplaza (para altas nuevas) el uso de productos.laboratorio, que queda deprecado sin datos reales conocidos pero no se elimina todavia (ver cabecera de esta migracion).';
COMMENT ON COLUMN productos.envase_id IS 'FK a envases. Distinto de forma_farmaceutica (ver comentario en tabla envases).';
COMMENT ON COLUMN productos.alicuota_iva IS 'Aliquota de IVA del producto (0, 10.5, 21...). Dato fiscal necesario para presupuestos/facturacion, ausente hasta esta migracion.';

-- =============================================================================
-- M6 — RLS + politicas + GRANTs + NOTIFY pgrst
-- marcas/envases/caracteristicas: misma politica que categorias (cat_sel/
-- cat_ins/cat_upd/cat_del). producto_caracteristicas: misma politica que
-- productos (prod_sel/prod_ins/prod_del), sin UPDATE (ver comentario de tabla).
-- =============================================================================

-- ---------- marcas ----------
ALTER TABLE marcas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS marc_sel ON marcas;
CREATE POLICY marc_sel ON marcas FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS marc_ins ON marcas;
CREATE POLICY marc_ins ON marcas FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS marc_upd ON marcas;
CREATE POLICY marc_upd ON marcas FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS marc_del ON marcas;
CREATE POLICY marc_del ON marcas FOR DELETE USING ((select es_superadmin()));

-- ---------- envases ----------
ALTER TABLE envases ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS env_sel ON envases;
CREATE POLICY env_sel ON envases FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS env_ins ON envases;
CREATE POLICY env_ins ON envases FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS env_upd ON envases;
CREATE POLICY env_upd ON envases FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS env_del ON envases;
CREATE POLICY env_del ON envases FOR DELETE USING ((select es_superadmin()));

-- ---------- caracteristicas ----------
ALTER TABLE caracteristicas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS car_sel ON caracteristicas;
CREATE POLICY car_sel ON caracteristicas FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS car_ins ON caracteristicas;
CREATE POLICY car_ins ON caracteristicas FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS car_upd ON caracteristicas;
CREATE POLICY car_upd ON caracteristicas FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia')
              AND (select mismo_tenant(drogueria_id)))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS car_del ON caracteristicas;
CREATE POLICY car_del ON caracteristicas FOR DELETE USING ((select es_superadmin()));

-- ---------- producto_caracteristicas ----------
ALTER TABLE producto_caracteristicas ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS prodcar_sel ON producto_caracteristicas;
CREATE POLICY prodcar_sel ON producto_caracteristicas FOR SELECT
  USING ((select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS prodcar_ins ON producto_caracteristicas;
CREATE POLICY prodcar_ins ON producto_caracteristicas FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS prodcar_del ON producto_caracteristicas;
CREATE POLICY prodcar_del ON producto_caracteristicas FOR DELETE
  USING ((select get_rol()) IN ('admin','gerencia','compras')
         AND (select mismo_tenant(drogueria_id)));

-- ---------- GRANTs explicitos ----------
-- Supabase no autoexpone tablas nuevas al Data API (precedente: 0007, 0008, 0011).
GRANT SELECT, INSERT, UPDATE, DELETE ON marcas, envases, caracteristicas TO service_role;
GRANT SELECT, INSERT, UPDATE ON marcas, envases, caracteristicas TO authenticated;

GRANT SELECT, INSERT, DELETE ON producto_caracteristicas TO service_role;
GRANT SELECT, INSERT ON producto_caracteristicas TO authenticated;

-- Forzar reload de PostgREST para que detecte las tablas y columnas nuevas
NOTIFY pgrst, 'reload schema';
