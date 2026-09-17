-- =============================================================================
-- Migration 0019: performance de RLS en todo el sistema multi-tenant
--
-- Continuacion de 0018 (productos): el mismo patron
-- `(select mismo_tenant(tabla.columna))` esta en ~170 policies de otras 57
-- tablas (categorias, marcas, envases, caracteristicas, pcp y sus 6 tablas
-- relacionadas, presupuestos, presupuesto_items, items_proceso, terceros y
-- sus relacionadas, ordenes_compra, precios_proveedor, reglas_pricing,
-- etc.) -- practicamente todo el esquema multi-tenant. Mismo problema en
-- las 57: pasarle `tabla.columna` como argumento a mismo_tenant() la vuelve
-- una subconsulta correlacionada, Postgres no puede cachearla via el truco
-- de envolver en `select` (initPlan), y la re-ejecuta por cada fila.
--
-- Se aplica mecanicamente en vez de transcribir 170 policies a mano:
-- verificado antes de escribir esta migracion que el argumento de
-- mismo_tenant() es SIEMPRE `<tabla>.drogueria_id` en las 57 tablas (sin
-- excepciones, chequeado con regexp_matches sobre pg_policies) y que
-- ninguna policy del esquema usa roles distintos de {public} (chequeado
-- aparte). Con esas dos garantias, la transformacion textual
--   ( SELECT mismo_tenant(T.drogueria_id) AS mismo_tenant)
--   -> (T.drogueria_id = ( SELECT get_drogueria_id() AS get_drogueria_id)
--       OR ( SELECT es_superadmin() AS es_superadmin))
-- es equivalente en todas -- mismo significado que mismo_tenant() ya tiene
-- internamente (es_superadmin() OR p_drogueria = get_drogueria_id()), solo
-- que ahora lo que esta en el select no depende de la fila.
--
-- productos queda afuera del loop (ya arreglada en 0018, ya no matchea el
-- patron mismo_tenant().
--
-- Seguridad de la migracion: el loop aborta toda la transaccion
-- (RAISE EXCEPTION) si para alguna policy el regexp_replace no logra
-- eliminar mismo_tenant( del texto resultante -- señal de que esa policy
-- no calza con el patron verificado y no debe tocarse a ciegas. Al final
-- hay una segunda verificacion, independiente del loop, que confirma que
-- no queda ninguna policy con el patron viejo.
-- =============================================================================

DO $$
DECLARE
  pol RECORD;
  nueva_qual TEXT;
  nuevo_with_check TEXT;
  ddl TEXT;
  total INT := 0;
BEGIN
  FOR pol IN
    SELECT schemaname, tablename, policyname, cmd, qual, with_check
    FROM pg_policies
    WHERE schemaname = 'public'
      AND (qual ILIKE '%mismo_tenant(%' OR with_check ILIKE '%mismo_tenant(%')
    ORDER BY tablename, policyname
  LOOP
    nueva_qual := regexp_replace(
      pol.qual,
      '\( SELECT mismo_tenant\(([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)\) AS mismo_tenant\)',
      '(\1 = ( SELECT get_drogueria_id() AS get_drogueria_id) OR ( SELECT es_superadmin() AS es_superadmin))',
      'g'
    );
    nuevo_with_check := regexp_replace(
      pol.with_check,
      '\( SELECT mismo_tenant\(([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+)\) AS mismo_tenant\)',
      '(\1 = ( SELECT get_drogueria_id() AS get_drogueria_id) OR ( SELECT es_superadmin() AS es_superadmin))',
      'g'
    );

    IF (nueva_qual ILIKE '%mismo_tenant(%') OR (nuevo_with_check ILIKE '%mismo_tenant(%') THEN
      RAISE EXCEPTION 'Policy % en % no matchea el patron esperado, abortando: qual=% with_check=%',
        pol.policyname, pol.tablename, pol.qual, pol.with_check;
    END IF;

    EXECUTE format('DROP POLICY %I ON public.%I', pol.policyname, pol.tablename);

    ddl := format('CREATE POLICY %I ON public.%I FOR %s', pol.policyname, pol.tablename, pol.cmd);
    IF nueva_qual IS NOT NULL THEN
      ddl := ddl || format(' USING (%s)', nueva_qual);
    END IF;
    IF nuevo_with_check IS NOT NULL THEN
      ddl := ddl || format(' WITH CHECK (%s)', nuevo_with_check);
    END IF;
    EXECUTE ddl;

    total := total + 1;
  END LOOP;

  RAISE NOTICE 'Migration 0019: % policies actualizadas', total;
END $$;

-- Verificacion final, independiente del loop: no debe quedar ninguna
-- policy con el patron viejo en todo el esquema public.
DO $$
DECLARE
  restantes INT;
BEGIN
  SELECT count(*) INTO restantes
  FROM pg_policies
  WHERE schemaname = 'public'
    AND (qual ILIKE '%mismo_tenant(%' OR with_check ILIKE '%mismo_tenant(%');

  IF restantes > 0 THEN
    RAISE EXCEPTION 'Quedaron % policies sin migrar con el patron mismo_tenant(tabla.columna)', restantes;
  END IF;
END $$;

NOTIFY pgrst, 'reload schema';
