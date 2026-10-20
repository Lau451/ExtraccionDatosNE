-- =============================================================================
-- 0040: solo el backend da de alta filas en usuarios
-- (odd/tasks/login-usuario-alta-admin.md S7, T10).
--
-- Hueco que cierra: el guard de 0039 (trg_usuarios_protege_credenciales) solo
-- cubre UPDATE. Bajo las políticas usuarios_ins/usuarios_del
-- (docs/schema/rls_final.sql) un superadmin/admin con su propio JWT podía, por
-- PostgREST, borrar una fila y reinsertarla con debe_cambiar_password = false o
-- con cualquier username, saltándose S3/S5 igual que el UPDATE que 0039 bloquea.
--
-- 0039 ya está aplicada en el proyecto real, por eso este guard va en una
-- migración nueva en vez de editar 0039. Función y trigger propios: 0039 no se
-- toca.
--
-- Quién puede insertar (mismas excepciones que 0039):
--   - service_role: el backend (POST /usuarios usa el service client). Bajo
--     PostgREST, current_user es el rol del JWT (SET ROLE) y auth.role() es el
--     claim role del JWT firmado.
--   - Dueños de la base (postgres, supabase_admin): migraciones y SQL manual.
-- Cualquier otro (authenticated, anon) recibe SQLSTATE 42501
-- (insufficient_privilege). UPDATE, DELETE, SELECT y las políticas RLS no
-- cambian.
--
-- SECURITY INVOKER a propósito: current_user tiene que ser el rol que hace el
-- INSERT, no el dueño de la función.
-- Re-ejecutable: CREATE OR REPLACE + DROP TRIGGER IF EXISTS.
-- =============================================================================

CREATE OR REPLACE FUNCTION trg_usuarios_protege_alta()
RETURNS TRIGGER
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = public, pg_temp
AS $$
BEGIN
    IF current_user NOT IN ('service_role', 'postgres', 'supabase_admin')
       AND coalesce(auth.role(), '') <> 'service_role' THEN
        RAISE EXCEPTION 'Solo el sistema puede dar de alta usuarios.'
            USING ERRCODE = '42501';
    END IF;
    RETURN NEW;
END;
$$;

COMMENT ON FUNCTION trg_usuarios_protege_alta() IS
  'Guard de usuarios: rechaza (SQLSTATE 42501) cualquier INSERT salvo service_role o un dueño de la base (postgres, supabase_admin). Agregada en 0040.';

REVOKE EXECUTE ON FUNCTION trg_usuarios_protege_alta() FROM PUBLIC;

DROP TRIGGER IF EXISTS trg_usuarios_protege_alta ON usuarios;
CREATE TRIGGER trg_usuarios_protege_alta
    BEFORE INSERT ON usuarios
    FOR EACH ROW
    EXECUTE FUNCTION trg_usuarios_protege_alta();
