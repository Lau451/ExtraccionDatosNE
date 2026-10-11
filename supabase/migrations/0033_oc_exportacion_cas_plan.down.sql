-- Down migration para 0033.
-- AVISO: vuelve a ser posible replanificar una OC exportada y la marca de
-- exportación deja de verificar el plan. El service de exportación llama a
-- marcar_oc_exportada / hash_plan_oc, así que hay que volver también al código
-- anterior (CAS simple por exportado_at).

DROP TRIGGER IF EXISTS trg_eoci_congela_plan ON entregas_oc_items;
DROP TRIGGER IF EXISTS trg_eoc_congela_plan ON entregas_oc;
DROP FUNCTION IF EXISTS trg_oc_exportada_congela_plan();
DROP FUNCTION IF EXISTS marcar_oc_exportada(UUID,UUID,UUID,TEXT,TEXT);
DROP FUNCTION IF EXISTS hash_plan_oc(UUID);

NOTIFY pgrst, 'reload schema';
