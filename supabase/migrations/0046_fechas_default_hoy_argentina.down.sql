-- Down migration para 0046: vuelve a DEFAULT CURRENT_DATE (UTC).

ALTER TABLE compras_proveedor ALTER COLUMN fecha_compra SET DEFAULT CURRENT_DATE;
ALTER TABLE precios_proveedor ALTER COLUMN fecha_oferta SET DEFAULT CURRENT_DATE;
ALTER TABLE procesos_comerciales ALTER COLUMN fecha SET DEFAULT CURRENT_DATE;
