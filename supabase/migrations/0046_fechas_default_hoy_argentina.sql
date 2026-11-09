-- 0046: las columnas de fecha toman "hoy" en hora argentina por defecto.
--
-- DEFAULT CURRENT_DATE es la fecha UTC de Supabase: un registro creado entre las
-- 21:00 y las 24:00 (UTC-3) quedaba con la fecha de mañana. En precios_proveedor
-- además rompía el alta: con fecha_oferta = mañana, un precio negociado con
-- mantenimiento_hasta = hoy no pasaba ck_pp_mant (mantenimiento_hasta >=
-- fecha_oferta). Mismo criterio que las vistas de 0045. Solo cambia el valor
-- por defecto de las filas nuevas; las existentes no se tocan.

ALTER TABLE compras_proveedor ALTER COLUMN fecha_compra SET DEFAULT (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date;
ALTER TABLE precios_proveedor ALTER COLUMN fecha_oferta SET DEFAULT (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date;
ALTER TABLE procesos_comerciales ALTER COLUMN fecha SET DEFAULT (now() AT TIME ZONE 'America/Argentina/Buenos_Aires')::date;
