import { Link } from '@tanstack/react-router'
import clsx from 'clsx'

interface NavItem {
  label: string
  to: string
  disabled?: boolean
}

// Placeholder: los 6 items y sus rutas finales vienen del mockup Figma
// (SEjXiBEMxprppdgmlNHKO8), todavía sin validar por screenshot en esta sesión.
const NAV_ITEMS: NavItem[] = [
  { label: 'Carga de documentos', to: '/' },
  { label: 'Licitaciones', to: '/licitaciones', disabled: true },
  { label: 'Calendario', to: '/calendario', disabled: true },
  { label: 'Historial', to: '/historial', disabled: true },
  { label: 'Presupuestos', to: '/presupuestos', disabled: true },
  { label: 'Comparativas', to: '/comparativas', disabled: true },
]

export function Sidebar() {
  return (
    <aside className="flex w-64 shrink-0 flex-col bg-navy text-slate-100">
      <div className="px-6 py-6 text-lg font-semibold tracking-tight">Droguería Nueva Era</div>

      <nav className="flex-1 space-y-1 px-3">
        {NAV_ITEMS.map((item) =>
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

      <div className={clsx('border-t border-white/10 px-6 py-4 text-xs text-slate-400')}>
        Sesión sin autenticación (fase de transición)
      </div>
    </aside>
  )
}
