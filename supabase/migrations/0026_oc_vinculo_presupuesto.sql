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
