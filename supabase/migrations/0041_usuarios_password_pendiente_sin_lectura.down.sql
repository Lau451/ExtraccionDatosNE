-- Down migration para 0041: los helpers de RLS vuelven a la definición de
-- docs/schema/rls_final.sql, las políticas de lectura propias a su forma
-- posterior a 0019, se quita password_al_dia() y el guard de usuarios deja de
-- cubrir id (vuelve a la función de 0039). Dueño y GRANTs de los helpers no
-- cambian (CREATE OR REPLACE los conserva).

ALTER POLICY planes_sel ON planes
  USING (auth.role() = 'authenticated');

ALTER POLICY no_sel ON notificaciones
  USING (
    destinatario_id = (select auth.uid())
    OR ((select get_rol()) IN ('admin','gerencia')
        AND (drogueria_id = (select get_drogueria_id()) OR (select es_superadmin())))
    OR (select es_superadmin())
  );

ALTER POLICY ne_sel ON notificacion_entregas
  USING (
    EXISTS (SELECT 1 FROM notificaciones n
            WHERE n.id = notificacion_id AND n.destinatario_id = (select auth.uid()))
    OR ((select get_rol()) IN ('admin','gerencia')
        AND (drogueria_id = (select get_drogueria_id()) OR (select es_superadmin())))
    OR (select es_superadmin())
  );

ALTER POLICY np_sel ON notificacion_preferencias
  USING (
    usuario_id = (select auth.uid())
    OR ((select get_rol()) = 'admin'
        AND (drogueria_id = (select get_drogueria_id()) OR (select es_superadmin())))
    OR (select es_superadmin())
  );

DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'licitaciones'
      AND policyname = 'licitaciones_all_access'
  ) THEN
    ALTER POLICY licitaciones_all_access ON public.licitaciones
      USING (true);
  END IF;
END
$$;

-- Después de las políticas: ninguna depende ya de la función.
DROP FUNCTION IF EXISTS password_al_dia();

CREATE OR REPLACE FUNCTION get_drogueria_id()
RETURNS UUID LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT drogueria_id FROM usuarios WHERE id = auth.uid(); $$;

CREATE OR REPLACE FUNCTION get_rol()
RETURNS TEXT LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT rol FROM usuarios WHERE id = auth.uid(); $$;

CREATE OR REPLACE FUNCTION es_superadmin()
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT EXISTS (SELECT 1 FROM usuarios WHERE id = auth.uid() AND rol = 'superadmin'); $$;

CREATE OR REPLACE FUNCTION trg_usuarios_protege_credenciales()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF (NEW.debe_cambiar_password IS DISTINCT FROM OLD.debe_cambiar_password
        OR NEW.username IS DISTINCT FROM OLD.username)
       AND current_user NOT IN ('service_role', 'postgres', 'supabase_admin')
       AND coalesce(auth.role(), '') <> 'service_role' THEN
        RAISE EXCEPTION 'Solo el sistema puede cambiar el nombre de usuario o el cambio de contraseña pendiente.'
            USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION trg_usuarios_protege_credenciales() IS
  'Guard de usuarios: rechaza (SQLSTATE 42501) cambios de debe_cambiar_password o username salvo service_role o un dueño de la base (postgres, supabase_admin). Agregada en 0039.';

NOTIFY pgrst, 'reload schema';
