import { Link } from '@tanstack/react-router'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { listarCondicionesPago, listarFormasPago, listarSectoresContacto } from '@/lib/api/catalogosComerciales'
import { obtenerTercero } from '@/lib/api/terceros'
import { CrearTerceroDialog } from './CrearTerceroDialog'
import { RolClienteSection } from './RolClienteSection'
import { RolProveedorSection } from './RolProveedorSection'
import { DireccionesSection } from './DireccionesSection'
import { ContactosSection } from './ContactosSection'
import { TERCEROS_WRITE_ROLES, puedeRol } from './roles'

export function TerceroDetalle({ terceroId }: { terceroId: string }) {
  const { perfil } = useAuth()
  const puedeEscribir = puedeRol(perfil?.rol, TERCEROS_WRITE_ROLES)

  const { data: tercero, isPending } = useQuery({
    queryKey: ['terceros', terceroId],
    queryFn: () => obtenerTercero(terceroId),
  })

  // Catálogos de apoyo para los selects de rol cliente/proveedor y de
  // contactos — pueden venir vacíos en una droguería nueva, lo cual no debe
  // bloquear la carga de esos formularios (ver prompt de la tarea).
  const { data: condicionesPago } = useQuery({
    queryKey: ['condiciones-pago'],
    queryFn: listarCondicionesPago,
  })
  const { data: formasPago } = useQuery({ queryKey: ['formas-pago'], queryFn: listarFormasPago })
  const { data: sectores } = useQuery({
    queryKey: ['sectores-contacto'],
    queryFn: listarSectoresContacto,
  })

  if (isPending) {
    return <p className="p-8 text-sm text-slate-500">Cargando…</p>
  }

  return (
    <div className="p-8">
      <Link to="/terceros" className="mb-4 inline-block text-sm text-accent hover:underline">
        ← Volver a terceros
      </Link>

      <div className="mb-6 flex items-start justify-between">
        <div>
          <h1 className="mb-1 text-xl font-semibold text-navy">{tercero?.razon_social}</h1>
          <p className="text-sm text-slate-500">
            {tercero?.codigo_interno ? `Código interno: ${tercero.codigo_interno}` : 'Sin código interno'}
            {tercero?.cuit ? ` · CUIT: ${tercero.cuit}` : ''}
          </p>
        </div>
        {puedeEscribir && tercero && (
          <CrearTerceroDialog
            tercero={tercero}
            trigger={
              <button
                type="button"
                className="rounded-md border border-slate-300 px-3 py-2 text-sm font-medium text-slate-700"
              >
                Editar datos generales
              </button>
            }
          />
        )}
      </div>

      <section className="mb-8">
        <h2 className="mb-3 text-sm font-semibold text-slate-700">Datos generales</h2>
        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm md:grid-cols-3">
          <Campo etiqueta="Nombre de fantasía" valor={tercero?.nombre_fantasia} />
          <Campo etiqueta="Email" valor={tercero?.email} />
          <Campo etiqueta="Teléfono" valor={tercero?.telefono} />
          <Campo etiqueta="Sitio web" valor={tercero?.sitio_web} />
          <Campo etiqueta="Estado" valor={tercero?.activo ? 'Activo' : 'Inactivo'} />
        </dl>
        {tercero?.notas && (
          <p className="mt-3 text-sm text-slate-600">
            <span className="font-medium text-slate-700">Notas: </span>
            {tercero.notas}
          </p>
        )}
      </section>

      <div className="grid gap-8 md:grid-cols-2">
        <RolClienteSection
          terceroId={terceroId}
          condicionesPago={condicionesPago ?? []}
          formasPago={formasPago ?? []}
          puedeEscribir={puedeEscribir}
        />
        <RolProveedorSection
          terceroId={terceroId}
          condicionesPago={condicionesPago ?? []}
          formasPago={formasPago ?? []}
          puedeEscribir={puedeEscribir}
        />
      </div>

      <div className="mt-8">
        <DireccionesSection terceroId={terceroId} puedeEscribir={puedeEscribir} />
      </div>

      <div className="mt-8">
        <ContactosSection terceroId={terceroId} sectores={sectores ?? []} puedeEscribir={puedeEscribir} />
      </div>
    </div>
  )
}

function Campo({ etiqueta, valor }: { etiqueta: string; valor: string | null | undefined }) {
  return (
    <div>
      <dt className="text-slate-500">{etiqueta}</dt>
      <dd className="text-slate-800">{valor || '—'}</dd>
    </div>
  )
}
