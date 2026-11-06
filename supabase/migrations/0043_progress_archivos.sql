-- =============================================================================
-- Migration 0043: registro de archivos de la integración con Progress
-- (odd/tasks/integracion-progress.md T2, S3; docs/arquitectura/integracion-progress.md
-- "Registro de archivos")
--
-- Cada archivo que entra (presupuestos) o sale (OC) por la carpeta de Progress
-- queda registrado en progress_archivos: droguería, sentido, tipo, nombre,
-- SHA-256 del contenido crudo, origen, estado (recibido -> procesado | error),
-- filas, errores por línea, usuario y fechas.
--
-- 1. uq_parch_contenido UNIQUE (drogueria_id, sentido, tipo, sha256): es la
--    garantía de "el mismo contenido nunca se procesa dos veces". Si dos
--    recepciones del mismo archivo compiten (escaneo automático + carga
--    manual), una sola inserta; la otra recibe 23505 y relee la ganadora
--    (services/integracion_progress/registro/service.py::registrar_entrada).
-- 2. origen solo aplica a las entradas (carpeta = escaneo automático,
--    manual = subida desde la pantalla). Las salidas las genera la
--    plataforma: origen NULL (ck_parch_origen).
-- 3. procesado_at NOT NULL si y solo si estado = 'procesado' (ck_parch_procesado).
-- 4. usuario_id NOT NULL: la recepción automática usa el usuario de sistema
--    (services/shared/config.py::usuario_sistema_id), la manual el usuario del
--    request. FK a usuarios(id), mismo criterio que fk_oc_exportadopor (0032).
-- 5. errores: lista JSON de {linea, mensaje} (ck_parch_errores exige array).
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'esta migracion requiere PostgreSQL 15+; version detectada: %',
                    current_setting('server_version');
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS progress_archivos (
    id              UUID        NOT NULL DEFAULT gen_random_uuid(),
    drogueria_id    UUID        NOT NULL,
    sentido         TEXT        NOT NULL,
    tipo            TEXT        NOT NULL,
    nombre_archivo  TEXT        NOT NULL,
    sha256          TEXT        NOT NULL,
    origen          TEXT        NULL,
    estado          TEXT        NOT NULL DEFAULT 'recibido',
    filas           INTEGER     NULL,
    errores         JSONB       NULL,
    usuario_id      UUID        NOT NULL,
    intentos        INTEGER     NOT NULL DEFAULT 0,
    procesado_at    TIMESTAMPTZ NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (id),
    CONSTRAINT uq_parch_id_drog    UNIQUE (id, drogueria_id),
    CONSTRAINT uq_parch_contenido  UNIQUE (drogueria_id, sentido, tipo, sha256),
    CONSTRAINT ck_parch_sentido    CHECK (sentido IN ('entrada', 'salida')),
    CONSTRAINT ck_parch_origen     CHECK (
        (sentido = 'entrada' AND origen IN ('carpeta', 'manual'))
        OR (sentido = 'salida' AND origen IS NULL)
    ),
    CONSTRAINT ck_parch_estado     CHECK (estado IN ('recibido', 'procesado', 'error')),
    CONSTRAINT ck_parch_procesado  CHECK ((estado = 'procesado') = (procesado_at IS NOT NULL)),
    CONSTRAINT ck_parch_sha256     CHECK (sha256 ~ '^[0-9a-f]{64}$'),
    CONSTRAINT ck_parch_filas      CHECK (filas IS NULL OR filas >= 0),
    CONSTRAINT ck_parch_intentos   CHECK (intentos >= 0),
    CONSTRAINT ck_parch_errores    CHECK (errores IS NULL OR jsonb_typeof(errores) = 'array'),
    CONSTRAINT fk_parch_drog       FOREIGN KEY (drogueria_id) REFERENCES droguerias (id),
    CONSTRAINT fk_parch_usuario    FOREIGN KEY (usuario_id) REFERENCES usuarios (id)
);

COMMENT ON TABLE progress_archivos IS
  'Registro de archivos intercambiados con Progress 9.1D (entrada y salida). uq_parch_contenido (drogueria_id, sentido, tipo, sha256) impide procesar dos veces el mismo contenido; un archivo en estado error se puede reprocesar. Agregada en 0043.';
COMMENT ON COLUMN progress_archivos.sha256 IS
  'SHA-256 en hexadecimal (minúsculas) de los bytes crudos del archivo, antes de decodificar. Agregada en 0043.';
COMMENT ON COLUMN progress_archivos.origen IS
  'Solo entradas: carpeta (escaneo automático) o manual (subida desde la pantalla). NULL en las salidas (ck_parch_origen). Agregada en 0043.';
COMMENT ON COLUMN progress_archivos.errores IS
  'Errores por línea del último intento: lista JSON de {linea, mensaje}. NULL si no hubo errores. Agregada en 0043.';
COMMENT ON COLUMN progress_archivos.intentos IS
  'Cantidad de intentos de procesamiento fallidos (se incrementa al marcar error). Agregada en 0043.';

-- Listado del registro por droguería, más reciente primero.
CREATE INDEX IF NOT EXISTS idx_parch_drog_created
    ON progress_archivos (drogueria_id, created_at DESC);

DROP TRIGGER IF EXISTS trg_progress_archivos_updated_at ON progress_archivos;
CREATE TRIGGER trg_progress_archivos_updated_at
  BEFORE UPDATE ON progress_archivos
  FOR EACH ROW EXECUTE FUNCTION trg_set_updated_at();

-- ---------- RLS: progress_archivos ----------
-- Lectura: unión de los roles que hoy operan cada sentido del intercambio con
-- Progress, más superadmin:
--   - entrada (presupuestos): los que leen presupuesto_legacy_map (prelm_sel,
--     0015): superadmin, admin, gerencia, compras.
--   - salida (OC): los que exportan la OC (oc_export/router.py::_ROLES_OC):
--     admin, gerencia, lider_comercial, comercial.
-- Escritura: sin políticas INSERT/UPDATE para authenticated (deny by default).
-- El registro lo escribe solo el backend con service_role (recepción
-- automática, carga manual y exportación pasan por
-- services/integracion_progress/registro), así un usuario no puede marcar un
-- archivo como procesado ni borrar su rastro desde el Data API
-- (docs/reglas-globales.md 2.3: escrituras vía get_service_client()).
ALTER TABLE progress_archivos ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS parch_sel ON progress_archivos;
CREATE POLICY parch_sel ON progress_archivos FOR SELECT
  USING ((select get_rol()) IN ('superadmin','admin','gerencia','compras','lider_comercial','comercial')
         AND (select mismo_tenant(drogueria_id)));
DROP POLICY IF EXISTS parch_del ON progress_archivos;
CREATE POLICY parch_del ON progress_archivos FOR DELETE USING ((select es_superadmin()));

-- ---------- GRANTs explicitos ----------
-- Supabase no autoexpone tablas nuevas al Data API (precedente: 0015).
-- authenticated solo lee; service_role escribe y mantiene.
GRANT SELECT, INSERT, UPDATE, DELETE ON progress_archivos TO service_role;
GRANT SELECT ON progress_archivos TO authenticated;

-- Forzar reload de PostgREST para que detecte la tabla nueva
NOTIFY pgrst, 'reload schema';
