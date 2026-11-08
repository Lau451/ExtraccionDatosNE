import { createFileRoute } from '@tanstack/react-router'
import { requireCapacidad } from '@/features/auth/routeGuards'
import { ImportarPresupuestosLegacy } from '@/features/presupuestos-import/ImportarPresupuestosLegacy'

/** Misma capacidad que `/pcp/imports/presupuestos-legacy` (spec S6: solo
 * `admin`); ya no coincide con `pcp.escribir`. */
export const Route = createFileRoute('/_authenticated/presupuestos/importar')({
  beforeLoad: requireCapacidad('presupuestos.importar_legacy'),
  component: ImportarPresupuestosLegacy,
})
