-- Down migration para 0019_rls_performance_sistema.sql
-- Revierte mecanicamente al patron viejo mismo_tenant(tabla.columna), mas
-- lento pero semanticamente identico. Mismo criterio de seguridad: aborta
-- si alguna policy no matchea el patron nuevo esperado.

DO $$
DECLARE
  pol RECORD;
  vieja_qual TEXT;
  viejo_with_check TEXT;
  ddl TEXT;
  total INT := 0;
BEGIN
  FOR pol IN
    SELECT schemaname, tablename, policyname, cmd, qual, with_check
    FROM pg_policies
    WHERE schemaname = 'public'
      AND (qual ILIKE '%get_drogueria_id()%' OR with_check ILIKE '%get_drogueria_id()%')
    ORDER BY tablename, policyname
  LOOP
    vieja_qual := regexp_replace(
      pol.qual,
      '\(([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+) = \( SELECT get_drogueria_id\(\) AS get_drogueria_id\) OR \( SELECT es_superadmin\(\) AS es_superadmin\)\)',
      '( SELECT mismo_tenant(\1) AS mismo_tenant)',
      'g'
    );
    viejo_with_check := regexp_replace(
      pol.with_check,
      '\(([a-zA-Z0-9_]+\.[a-zA-Z0-9_]+) = \( SELECT get_drogueria_id\(\) AS get_drogueria_id\) OR \( SELECT es_superadmin\(\) AS es_superadmin\)\)',
      '( SELECT mismo_tenant(\1) AS mismo_tenant)',
      'g'
    );

    IF (vieja_qual ILIKE '%get_drogueria_id()%') OR (viejo_with_check ILIKE '%get_drogueria_id()%') THEN
      RAISE EXCEPTION 'Policy % en % no matchea el patron nuevo esperado, abortando revert: qual=% with_check=%',
        pol.policyname, pol.tablename, pol.qual, pol.with_check;
    END IF;

    EXECUTE format('DROP POLICY %I ON public.%I', pol.policyname, pol.tablename);

    ddl := format('CREATE POLICY %I ON public.%I FOR %s', pol.policyname, pol.tablename, pol.cmd);
    IF vieja_qual IS NOT NULL THEN
      ddl := ddl || format(' USING (%s)', vieja_qual);
    END IF;
    IF viejo_with_check IS NOT NULL THEN
      ddl := ddl || format(' WITH CHECK (%s)', viejo_with_check);
    END IF;
    EXECUTE ddl;

    total := total + 1;
  END LOOP;

  RAISE NOTICE 'Down 0019: % policies revertidas', total;
END $$;

NOTIFY pgrst, 'reload schema';
