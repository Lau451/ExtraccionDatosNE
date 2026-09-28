-- Down migration para 0030.

ALTER TABLE oc_items DROP COLUMN IF EXISTS numero_renglon_documento;

NOTIFY pgrst, 'reload schema';
