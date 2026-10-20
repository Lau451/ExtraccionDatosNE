-- =============================================================================
-- 0041: un usuario con debe_cambiar_password = true no lee nada por PostgREST
-- salvo su propia fila de usuarios, y usuarios.id solo lo cambia el backend
-- (odd/tasks/login-usuario-alta-admin.md S14, S15, T13).
--
-- Hueco que cierra (S14): el backend ya rechaza con 403 a un usuario con el
-- cambio de contraseña pendiente (S3), pero con su propio JWT podía consultar
-- PostgREST directo y leer todo lo que la RLS le permitía a su rol.
--
-- Cómo:
--   1. Los helpers de RLS get_drogueria_id(), get_rol() y es_superadmin()
--      ignoran la fila del usuario mientras tenga debe_cambiar_password = true:
--      devuelven NULL / NULL / false, lo mismo que para alguien sin fila en
--      usuarios. Casi todas las políticas pasan por ellos (directo o vía
--      mismo_tenant(), que no cambia porque se arma con los otros dos), así que
--      quedan sin acceso: lectura y también escritura (intencional).
--   2. Helper nuevo password_al_dia() (SECURITY DEFINER, sin recursión de RLS)
--      para las ramas de lectura que no pasan por los helpers:
--        - planes_sel            auth.role() = 'authenticated'
--        - no_sel                destinatario_id = auth.uid()
--        - ne_sel                EXISTS (... n.destinatario_id = auth.uid())
--        - np_sel                usuario_id = auth.uid()
--        - licitaciones_all_access USING (true), solo si la tabla legada existe
--   3. Se mantiene a propósito la rama id = auth.uid() de usuarios_sel: el
--      backend lee la propia fila con el JWT del usuario para saber que tiene
--      el cambio pendiente (services/shared/auth.py:_cargar_perfil), y es lo que
--      deja funcionar las rutas permitidas de S3.
--   Cuando el flag vuelve a false todo queda exactamente como antes.
--
-- Supuesto (verificar ANTES de aplicar): los helpers no están en ninguna
-- migración; la base real se armó con docs/schema/rls_final.sql:55-88. Acá se
-- recrean con la misma firma, LANGUAGE sql, STABLE, SECURITY DEFINER y
-- SET search_path = public de ese archivo. CREATE OR REPLACE conserva dueño y
-- GRANTs existentes (no se re-otorgan). Comparar en el SQL Editor:
--   SELECT p.proname, pg_get_functiondef(p.oid), p.proowner::regrole, p.proacl
--   FROM pg_proc p
--   WHERE p.pronamespace = 'public'::regnamespace
--     AND p.proname IN ('get_drogueria_id', 'get_rol', 'es_superadmin', 'mismo_tenant');
-- y las políticas que se reescriben (deben coincidir con 0041 .down.sql):
--   SELECT tablename, policyname, cmd, roles, qual, with_check
--   FROM pg_policies
--   WHERE schemaname = 'public'
--     AND policyname IN ('planes_sel', 'no_sel', 'ne_sel', 'np_sel', 'licitaciones_all_access');
--
-- S15: el guard de 0039 (trg_usuarios_protege_credenciales) también rechaza
-- cambiar usuarios.id, con las mismas excepciones (service_role y dueños de la
-- base). Hueco: un superadmin podía borrar la fila B y hacer UPDATE id = B
-- sobre otra fila sin referencias, apropiándose de la identidad de auth.users B.
-- El mensaje de 0039 para username/flag no cambia.
--
-- Re-ejecutable: CREATE OR REPLACE + ALTER POLICY.
-- =============================================================================

-- ---------- Helpers de RLS (S14) ----------
CREATE OR REPLACE FUNCTION get_drogueria_id()
RETURNS UUID LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT drogueria_id FROM usuarios WHERE id = auth.uid() AND NOT debe_cambiar_password; $$;

CREATE OR REPLACE FUNCTION get_rol()
RETURNS TEXT LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT rol FROM usuarios WHERE id = auth.uid() AND NOT debe_cambiar_password; $$;

CREATE OR REPLACE FUNCTION es_superadmin()
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT EXISTS (SELECT 1 FROM usuarios WHERE id = auth.uid() AND rol = 'superadmin' AND NOT debe_cambiar_password); $$;

-- FALSE solo si quien consulta tiene fila en usuarios con el cambio de
-- contraseña pendiente. TRUE para todos los demás, incluido anon (auth.uid()
-- NULL) y un autenticado sin fila: así las políticas que lo usan no cambian
-- para nadie más.
CREATE OR REPLACE FUNCTION password_al_dia()
RETURNS BOOLEAN LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public
AS $$ SELECT NOT EXISTS (SELECT 1 FROM usuarios WHERE id = auth.uid() AND debe_cambiar_password); $$;

COMMENT ON FUNCTION password_al_dia() IS
  'FALSE si el usuario del JWT tiene debe_cambiar_password = true (S14): lo usan las políticas de lectura que no pasan por get_rol()/get_drogueria_id()/es_superadmin(). Agregada en 0041.';

-- Igual que los otros helpers (rls_final.sql:72-88): fuera de PUBLIC, EXECUTE
-- a authenticated. También a anon, a diferencia de los otros: lo evalúa
-- licitaciones_all_access, que anon puede leer, y sin EXECUTE esa lectura
-- fallaría con permission denied. Devuelve TRUE para anon.
REVOKE EXECUTE ON FUNCTION password_al_dia() FROM PUBLIC;
GRANT EXECUTE ON FUNCTION password_al_dia() TO anon;
GRANT EXECUTE ON FUNCTION password_al_dia() TO authenticated;

-- ---------- Lecturas que no pasan por los helpers (S14) ----------
-- Mismo texto que hoy (las ramas de tenant en la forma que les dejó 0019) más
-- password_al_dia() en la rama propia. ALTER POLICY no toca comando ni roles.
ALTER POLICY planes_sel ON planes
  USING (auth.role() = 'authenticated' AND (select password_al_dia()));

ALTER POLICY no_sel ON notificaciones
  USING (
    (destinatario_id = (select auth.uid()) AND (select password_al_dia()))
    OR ((select get_rol()) IN ('admin','gerencia')
        AND (drogueria_id = (select get_drogueria_id()) OR (select es_superadmin())))
    OR (select es_superadmin())
  );

ALTER POLICY ne_sel ON notificacion_entregas
  USING (
    (EXISTS (SELECT 1 FROM notificaciones n
             WHERE n.id = notificacion_id AND n.destinatario_id = (select auth.uid()))
     AND (select password_al_dia()))
    OR ((select get_rol()) IN ('admin','gerencia')
        AND (drogueria_id = (select get_drogueria_id()) OR (select es_superadmin())))
    OR (select es_superadmin())
  );

ALTER POLICY np_sel ON notificacion_preferencias
  USING (
    (usuario_id = (select auth.uid()) AND (select password_al_dia()))
    OR ((select get_rol()) = 'admin'
        AND (drogueria_id = (select get_drogueria_id()) OR (select es_superadmin())))
    OR (select es_superadmin())
  );

-- licitaciones (0004) es legada (reemplazada por procesos_comerciales en el
-- schema v15) y puede no existir en la base real. Si existe con su política
-- FOR ALL USING (true), solo se cambia el USING; WITH CHECK (true) queda.
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM pg_policies
    WHERE schemaname = 'public'
      AND tablename = 'licitaciones'
      AND policyname = 'licitaciones_all_access'
  ) THEN
    ALTER POLICY licitaciones_all_access ON public.licitaciones
      USING ((select password_al_dia()));
  END IF;
END
$$;

-- ---------- Guard de usuarios.id (S15) ----------
-- Misma función y trigger de 0039 (el trigger no se recrea: CREATE OR REPLACE
-- de la función alcanza).
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
    IF NEW.id IS DISTINCT FROM OLD.id
       AND current_user NOT IN ('service_role', 'postgres', 'supabase_admin')
       AND coalesce(auth.role(), '') <> 'service_role' THEN
        RAISE EXCEPTION 'Solo el sistema puede cambiar el id de un usuario.'
            USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION trg_usuarios_protege_credenciales() IS
  'Guard de usuarios: rechaza (SQLSTATE 42501) cambios de debe_cambiar_password, username o id salvo service_role o un dueño de la base (postgres, supabase_admin). Agregada en 0039; id agregado en 0041.';

NOTIFY pgrst, 'reload schema';
