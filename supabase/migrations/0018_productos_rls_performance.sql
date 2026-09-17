-- =============================================================================
-- Migration 0018: performance de RLS en productos (prod_sel/prod_ins/prod_upd)
--
-- Encontrado al cargar el maestro legacy real (7144 productos): listar
-- productos tardaba ~1.3s de ejecucion en Postgres (medido con EXPLAIN
-- ANALYZE), contra 7ms para la misma query sin RLS. Causa: las policies
-- usaban `(select mismo_tenant(productos.drogueria_id))`. El truco de
-- envolver en `select` para que Postgres cachee el resultado (initPlan, una
-- sola evaluacion) SOLO funciona si la expresion no depende de la fila.
-- Pasarle `productos.drogueria_id` como argumento la vuelve una subconsulta
-- CORRELACIONADA -- Postgres no puede cachearla y la re-ejecuta por cada
-- fila (verificado: SubPlan con loops=7144 en el plan real).
--
-- mismo_tenant(p_drogueria) internamente es
-- `es_superadmin() OR p_drogueria = get_drogueria_id()` (mismo significado,
-- cero cambio de semantica). Reescrito como
-- `drogueria_id = (select get_drogueria_id()) OR (select es_superadmin())`:
-- ahora lo que esta en el select NO depende de la fila, Postgres si lo
-- cachea, y la comparacion por fila es un `=` simple (ademas usa indice).
-- Verificado en vivo con EXPLAIN ANALYZE antes de aplicar: 1336ms -> 8.4ms.
--
-- Alcance deliberadamente acotado a productos (la tabla con volumen real
-- hoy). El mismo patron `mismo_tenant(tabla.columna)` esta en pg_policies
-- de otras ~57 tablas del esquema (categorias, pcp y relacionadas,
-- presupuestos, terceros, etc.) -- no tocadas aca a proposito: es un cambio
-- de RLS a nivel de todo el sistema multi-tenant, se trata como su propia
-- migracion separada, no colada en esta.
--
-- prod_del no se toca: solo usa es_superadmin(), sin mismo_tenant, no tiene
-- el problema.
-- =============================================================================

DROP POLICY IF EXISTS prod_sel ON productos;
CREATE POLICY prod_sel ON productos FOR SELECT
  USING (drogueria_id = (select get_drogueria_id()) OR (select es_superadmin()));

DROP POLICY IF EXISTS prod_ins ON productos;
CREATE POLICY prod_ins ON productos FOR INSERT
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (drogueria_id = (select get_drogueria_id()) OR (select es_superadmin())));

DROP POLICY IF EXISTS prod_upd ON productos;
CREATE POLICY prod_upd ON productos FOR UPDATE
  USING      ((select get_rol()) IN ('admin','gerencia','compras')
              AND (drogueria_id = (select get_drogueria_id()) OR (select es_superadmin())))
  WITH CHECK ((select get_rol()) IN ('admin','gerencia','compras')
              AND (drogueria_id = (select get_drogueria_id()) OR (select es_superadmin())));

NOTIFY pgrst, 'reload schema';
