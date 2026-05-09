-- =============================================================================
-- Migration 0001: Persistencia de chunks + resultado final en Supabase
--
-- Crea las 5 tablas del dominio de persistencia:
--   processing_sessions   — sesiones de procesamiento chunked
--   chunk_results         — resultado por chunk (parcial, permite reanudación)
--   extraction_results    — resultado final de cada extracción (tabla base)
--   comparativas_results  — detalle JSONB para comparativas de precios
--   licitaciones_results  — detalle JSONB para licitaciones
--
-- Incluye: trigger updated_at, índices GIN en JSONB, UNIQUE(source_sha256)
-- =============================================================================

-- ======================
-- Sesiones de procesamiento (V1: chunks)
-- ======================
CREATE TABLE processing_sessions (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_name        TEXT        NOT NULL,
  client_id       TEXT        NOT NULL,
  doc_type        TEXT        NOT NULL
                              CHECK (doc_type IN ('comparativa', 'licitacion', 'orden_compra')),
  total_chunks    INT         NOT NULL DEFAULT 0,
  status          TEXT        NOT NULL DEFAULT 'running'
                              CHECK (status IN ('running', 'completed', 'partial', 'failed')),
  error_msg       TEXT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  completed_at    TIMESTAMPTZ
);

-- Índices en processing_sessions
CREATE INDEX idx_sessions_status_created
  ON processing_sessions (status, created_at DESC);

CREATE INDEX idx_sessions_client
  ON processing_sessions (client_id, created_at DESC);

-- ======================
-- Chunks parciales (V1)
-- ======================
CREATE TABLE chunk_results (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id      UUID        NOT NULL
                              REFERENCES processing_sessions (id) ON DELETE CASCADE,
  chunk_number    INT         NOT NULL,
  resultado       JSONB       NOT NULL,
  status          TEXT        NOT NULL DEFAULT 'completed'
                              CHECK (status IN ('completed', 'failed')),
  attempts        INT         NOT NULL DEFAULT 1,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Previene duplicados de chunk; permite upsert con ON CONFLICT
  UNIQUE (session_id, chunk_number)
);

-- Índice compuesto para recuperación de chunks por sesión
CREATE INDEX idx_chunks_session
  ON chunk_results (session_id, chunk_number);

-- ======================
-- Resultado final (tabla base)
-- ======================
CREATE TABLE extraction_results (
  id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id      UUID        REFERENCES processing_sessions (id),
  document_type   TEXT        NOT NULL
                              CHECK (document_type IN ('comparativa', 'licitacion', 'orden_compra')),
  source_filename TEXT        NOT NULL,
  source_sha256   TEXT        NOT NULL,
  client_id       TEXT        NOT NULL,
  row_count       INT         NOT NULL,
  csv_disk_path   TEXT        NOT NULL,
  status          TEXT        NOT NULL DEFAULT 'completed'
                              CHECK (status IN ('completed', 'partial', 'failed')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- Clave de deduplicación: un SHA256 → un resultado final completado
  CONSTRAINT uq_extraction_sha UNIQUE (source_sha256)
);

-- Índices en extraction_results
CREATE INDEX idx_extr_client_date
  ON extraction_results (client_id, created_at DESC);

CREATE INDEX idx_extr_doctype
  ON extraction_results (document_type);

-- Nota: UNIQUE(source_sha256) ya genera índice implícito — no se duplica.

-- ======================
-- Detalle por tipo: Comparativas
-- ======================
CREATE TABLE comparativas_results (
  extraction_id   UUID  PRIMARY KEY
                        REFERENCES extraction_results (id) ON DELETE CASCADE,
  rows            JSONB NOT NULL
  -- Estructura de cada elemento del array:
  -- { renglon, descripcion, proveedor, marca, precio, cliente }
);

-- Índice GIN con jsonb_path_ops para queries tipo: rows @> '[{"proveedor": "X"}]'
CREATE INDEX idx_comp_rows_gin
  ON comparativas_results USING GIN (rows jsonb_path_ops);

-- ======================
-- Detalle por tipo: Licitaciones
-- ======================
CREATE TABLE licitaciones_results (
  extraction_id   UUID  PRIMARY KEY
                        REFERENCES extraction_results (id) ON DELETE CASCADE,
  rows            JSONB NOT NULL
  -- Estructura de cada elemento del array:
  -- { item, cantidad, descripcion, origen }
);

CREATE INDEX idx_licit_rows_gin
  ON licitaciones_results USING GIN (rows jsonb_path_ops);

-- ======================
-- Función trigger: actualiza updated_at automáticamente
-- ======================
CREATE OR REPLACE FUNCTION trg_set_updated_at()
RETURNS trigger AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Trigger solo en extraction_results (la única tabla con updated_at)
CREATE TRIGGER tr_extraction_updated
  BEFORE UPDATE ON extraction_results
  FOR EACH ROW
  EXECUTE FUNCTION trg_set_updated_at();
