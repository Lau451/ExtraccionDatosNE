DROP INDEX IF EXISTS idx_ppr_renglon_seleccionado;

ALTER TABLE pcp_renglon_resultados
  DROP COLUMN IF EXISTS seleccionado;

NOTIFY pgrst, 'reload schema';
