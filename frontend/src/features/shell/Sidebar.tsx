import { Link, useNavigate } from '@tanstack/react-router'
import { useAuth, type Rol } from '@/features/auth/AuthContext'
import { CARGA_DOCUMENTOS_ROLES } from '@/features/carga-documentos/roles'
import { COMPROMISOS_READ_ROLES } from '@/features/compromisos/roles'
import { USUARIOS_ROLES } from '@/features/gestion-usuarios/roles'
import { PCP_READ_ROLES, puedeRol } from '@/features/pcp/roles'
import { PRESUPUESTOS_LEGACY_IMPORT_ROLES } from '@/features/presupuestos-import/roles'
import { MATCHING_ROLES } from '@/features/proceso-matching/roles'
import { VALIDAR_EXTRACCION_ROLES } from '@/features/validar-extraccion/roles'

interface NavItem {
  label: string
  to: string
  disabled?: boolean
}

// Placeholder: los 6 items y sus rutas finales vienen del mockup Figma
// (SEjXiBEMxprppdgmlNHKO8), todavía sin validar por screenshot en esta sesión.
const NAV_ITEMS: NavItem[] = [
  // Todos los roles de negocio tienen lectura de catálogo (ver
  // features/productos/roles.ts), así que no hace falta gate por rol acá.
  { label: 'Productos', to: '/productos' },
  // Idem — TERCEROS_READ_ROLES en features/terceros/roles.ts cubre los 6
  // roles de negocio.
  { label: 'Terceros', to: '/terceros' },
  { label: 'Licitaciones', to: '/licitaciones', disabled: true },
  { label: 'Calendario', to: '/calendario', disabled: true },
  { label: 'Historial', to: '/historial', disabled: true },
  { label: 'Presupuestos', to: '/presupuestos', disabled: true },
  { label: 'Comparativas', to: '/comparativas', disabled: true },
]

export function muestraNavegacionPcp(rol: Rol | undefined): boolean {
  return puedeRol(rol, PCP_READ_ROLES)
}

export function Sidebar() {
  const { perfil, signOut } = useAuth()
  const navigate = useNavigate()

  async function handleLogout() {
    await signOut()
    navigate({ to: '/login' })
  }

  const navItems: NavItem[] = [
    // Carga y validación de extracciones: compras y superadmin no participan
    // (specs S1/S2), mismos roles que los guards de "/" y /validar-extraccion.
    ...(puedeRol(perfil?.rol, CARGA_DOCUMENTOS_ROLES) ? [{ label: 'Carga de documentos', to: '/' }] : []),
    ...(puedeRol(perfil?.rol, VALIDAR_EXTRACCION_ROLES)
      ? [{ label: 'Validar extracción', to: '/validar-extraccion' }]
      : []),
    // presupuestador-v1 T3c: procesos with renglones still to match against
    // the catalog; same roles as the matching endpoints.
    ...(puedeRol(perfil?.rol, MATCHING_ROLES) ? [{ label: 'Matching de catálogo', to: '/matching' }] : []),
    ...NAV_ITEMS,
    // Mismos roles que el endpoint de importación legacy (spec S6: solo admin).
    ...(puedeRol(perfil?.rol, PRESUPUESTOS_LEGACY_IMPORT_ROLES)
      ? [{ label: 'Importar presupuestos', to: '/presupuestos/importar' }]
      : []),
    ...(puedeRol(perfil?.rol, COMPROMISOS_READ_ROLES)
      ? [{ label: 'Compromisos de entrega', to: '/compromisos' }]
      : []),
    ...(muestraNavegacionPcp(perfil?.rol) ? [{ label: 'PCP', to: '/pcp' }] : []),
    ...(puedeRol(perfil?.rol, USUARIOS_ROLES) ? [{ label: 'Usuarios', to: '/admin/usuarios' }] : []),
    ...(perfil?.rol === 'superadmin' ? [{ label: 'Empresas', to: '/superadmin/empresas' }] : []),
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
