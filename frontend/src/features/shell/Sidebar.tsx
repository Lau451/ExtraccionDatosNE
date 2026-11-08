import { Link, useNavigate } from '@tanstack/react-router'
import { useAuth } from '@/features/auth/AuthContext'

interface NavItem {
  label: string
  to: string
  disabled?: boolean
}

// Placeholder: los 6 items y sus rutas finales vienen del mockup Figma
// (SEjXiBEMxprppdgmlNHKO8), todavía sin validar por screenshot en esta sesión.
const NAV_ITEMS: NavItem[] = [
  // Todos los roles de negocio tienen `productos.leer` (services/shared/
  // permisos.py), así que no hace falta gate acá.
  { label: 'Productos', to: '/productos' },
  // Idem — `terceros.leer` cubre los 6 roles de negocio.
  { label: 'Terceros', to: '/terceros' },
  { label: 'Licitaciones', to: '/licitaciones', disabled: true },
  { label: 'Calendario', to: '/calendario', disabled: true },
  { label: 'Historial', to: '/historial', disabled: true },
  { label: 'Presupuestos', to: '/presupuestos', disabled: true },
  { label: 'Comparativas', to: '/comparativas', disabled: true },
]

export function Sidebar() {
  const { perfil, puede, signOut } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await signOut()
    navigate({ to: '/login' })
  }

  const navItems: NavItem[] = [
    // Carga y validación de extracciones: compras y superadmin no participan
    // (specs S1/S2), mismas capacidades que los guards de "/" y /validar-extraccion.
    ...(puede('extraccion.extraer') ? [{ label: 'Carga de documentos', to: '/' }] : []),
    ...(puede('extraccion.validar')
      ? [{ label: 'Validar extracción', to: '/validar-extraccion' }]
      : []),
    // presupuestador-v1 T3c: procesos with renglones still to match against
    // the catalog; same capability as the matching endpoints.
    ...(puede('matching.usar') ? [{ label: 'Matching de catálogo', to: '/matching' }] : []),
    ...NAV_ITEMS,
    // Misma capacidad que el endpoint de importación legacy (spec S6: solo admin).
    ...(puede('presupuestos.importar_legacy')
      ? [{ label: 'Importar presupuestos', to: '/presupuestos/importar' }]
      : []),
    ...(puede('compromisos.ver_pantalla')
      ? [{ label: 'Compromisos de entrega', to: '/compromisos' }]
      : []),
    ...(puede('pcp.leer') ? [{ label: 'PCP', to: '/pcp' }] : []),
    ...(puede('usuarios.gestionar') ? [{ label: 'Usuarios', to: '/admin/usuarios' }] : []),
    ...(puede('droguerias.gestionar') ? [{ label: 'Empresas', to: '/superadmin/empresas' }] : []),
  ]

  return (
    <aside className="flex w-64 shrink-0 flex-col bg-navy text-slate-100">
      <div className="px-6 py-6 text-lg font-semibold tracking-tight">Droguería Nueva Era</div>

      <nav className="flex-1 space-y-1 px-3">
        {navItems.map((item) =>
          item.disabled ? (
            <span
              key={item.to}
              className="block cursor-not-allowed rounded-md px-3 py-2 text-sm text-slate-500"
            >
              {item.label}
            </span>
          ) : (
            <Link
              key={item.to}
              to={item.to}
              activeOptions={{ exact: true }}
              className="block rounded-md px-3 py-2 text-sm text-slate-200 hover:bg-white/5"
              activeProps={{ className: 'bg-accent/20 text-white' }}
            >
              {item.label}
            </Link>
          ),
        )}
      </nav>

      <div className="border-t border-white/10 px-6 py-4 text-xs text-slate-400">
        <p className="mb-2 truncate text-slate-300">{perfil?.nombre ?? 'Cargando…'}</p>
        <Link to="/mi-cuenta" className="mb-2 block hover:text-white">
          Mi cuenta
        </Link>
        <button type="button" onClick={handleLogout} className="hover:text-white">
          Cerrar sesión
        </button>
      </div>
    </aside>
  )
}
