-- =============================================================================
-- Migration 0014: persisted, non-exclusive PCP result selection
-- =============================================================================

DO $$ BEGIN
  IF current_setting('server_version_num')::int < 150000 THEN
    RAISE EXCEPTION 'pcp frontend requires PostgreSQL 15+; detected version: %',
                    current_setting('server_version');
  END IF;
END $$;

ALTER TABLE pcp_renglon_resultados
  ADD COLUMN IF NOT EXISTS seleccionado BOOLEAN NOT NULL DEFAULT false;

COMMENT ON COLUMN pcp_renglon_resultados.seleccionado IS
  'Persisted supplier selection for a PCP row; multiple suppliers may be selected.';

CREATE INDEX IF NOT EXISTS idx_ppr_renglon_seleccionado
  ON pcp_renglon_resultados (pcp_renglon_id)
  WHERE seleccionado;

NOTIFY pgrst, 'reload schema';
