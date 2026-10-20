-- =============================================================================
-- 0039: usuarios.debe_cambiar_password y usuarios.username solo los cambia el
-- backend (odd/tasks/login-usuario-alta-admin.md S7).
--
-- Hueco que cierra: la política usuarios_upd (docs/schema/rls_final.sql) deja
-- que un admin actualice filas de usuarios con su propio JWT a través de
-- PostgREST, así que podía limpiar su propio debe_cambiar_password (saltándose el cambio forzado de S3) o editar
-- usernames sin pasar por las reglas de S5. El backend escribe esas columnas
-- con el service client (service_role).
--
-- Por qué un trigger y no un REVOKE UPDATE por columna: Supabase otorga UPDATE
-- a nivel de TABLA a authenticated, y un privilegio de tabla alcanza todas las
-- columnas; REVOKE UPDATE (columna) no tiene efecto mientras exista el GRANT de
-- tabla. Revocar el de tabla y re-otorgar columna por columna rompería cada
-- columna nueva que se agregue después.
--
-- Quién puede cambiarlas:
--   - service_role: el backend. Bajo PostgREST, current_user es el rol del JWT
--     (SET ROLE) y auth.role() es el claim role del JWT firmado.
--   - Dueños de la base (postgres, supabase_admin): migraciones y SQL manual.
-- Cualquier otro (authenticated, anon) recibe SQLSTATE 42501
-- (insufficient_privilege). El resto de las columnas y las políticas RLS no
-- cambian.
--
-- SECURITY INVOKER a propósito: current_user tiene que ser el rol que hace el
-- UPDATE, no el dueño de la función.
-- Re-ejecutable: CREATE OR REPLACE + DROP TRIGGER IF EXISTS.
-- =============================================================================

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

REVOKE EXECUTE ON FUNCTION trg_usuarios_protege_credenciales() FROM PUBLIC;

DROP TRIGGER IF EXISTS trg_usuarios_protege_credenciales ON usuarios;
CREATE TRIGGER trg_usuarios_protege_credenciales
    BEFORE UPDATE ON usuarios
    FOR EACH ROW
    EXECUTE FUNCTION trg_usuarios_protege_credenciales();
