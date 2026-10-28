import { useId } from 'react'
import { useQuery } from '@tanstack/react-query'
import clsx from 'clsx'
import { listarClientes } from '@/lib/api/extraccion'

export type ClaseProceso = 'licitacion' | 'cotizacion'

const CLASES: { value: ClaseProceso; label: string }[] = [
  { value: 'licitacion', label: 'Licitación' },
  { value: 'cotizacion', label: 'Directa' },
]

interface Props {
  clase: ClaseProceso | null
  onClase: (clase: ClaseProceso) => void
  clienteId: string
  onClienteId: (clienteId: string) => void
  nombreLicitacion: string
  onNombreLicitacion: (nombre: string) => void
}

/** presupuestador-v1 T2b (S2, S8) -- a licitación or a directa starts its
 * proceso comercial when validated: the user picks the class, the cliente
 * (required) and, for a licitación, its name. The backend names a directa
 * "<cliente> - <n>" with the next number for that cliente. */
export function NuevoProcesoForm({
  clase,
  onClase,
  clienteId,
  onClienteId,
  nombreLicitacion,
  onNombreLicitacion,
}: Props) {
  const clienteInputId = useId()
  const nombreInputId = useId()
  const clientesQuery = useQuery({ queryKey: ['clientes'], queryFn: listarClientes })
  const cliente = clientesQuery.data?.find((opcion) => opcion.id === clienteId)
  const nombre = nombreLicitacion.trim()

  const nombreProceso =
    clase === null || !cliente
      ? null
      : clase === 'cotizacion'
        ? `${cliente.nombre} - (número siguiente de directa)`
        : nombre
          ? `${cliente.nombre} - ${nombre}`
          : null

  return (
    <div className="space-y-4">
      <div>
        <span className="mb-1 block text-sm text-slate-600">Tipo de proceso</span>
        <div className="flex gap-2">
          {CLASES.map((opcion) => (
            <button
              key={opcion.value}
              type="button"
              aria-pressed={clase === opcion.value}
              onClick={() => onClase(opcion.value)}
              className={clsx(
                'cursor-pointer rounded-full px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1',
                clase === opcion.value
                  ? 'bg-navy text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
              )}
            >
              {opcion.label}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-wrap gap-3">
        <div className="min-w-64 flex-1 text-sm">
          <label htmlFor={clienteInputId} className="mb-1 block text-slate-600">
            Cliente
          </label>
          <select
            id={clienteInputId}
            value={clienteId}
            onChange={(event) => onClienteId(event.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="" disabled>
              Seleccioná un cliente
            </option>
            {clientesQuery.data?.map((opcion) => (
              <option key={opcion.id} value={opcion.id}>
                {opcion.nombre}
              </option>
            ))}
          </select>
        </div>

        {clase === 'licitacion' && (
          <div className="min-w-64 flex-1 text-sm">
            <label htmlFor={nombreInputId} className="mb-1 block text-slate-600">
              Nombre de la licitación
            </label>
            <input
              id={nombreInputId}
              value={nombreLicitacion}
              onChange={(event) => onNombreLicitacion(event.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </div>
        )}
      </div>

      {nombreProceso && (
        <p className="text-sm text-slate-600">Se va a crear el proceso: {nombreProceso}</p>
      )}
    </div>
  )
}
