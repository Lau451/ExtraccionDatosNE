import type { DocumentType } from '@/lib/api/extracciones'
import type { Clase, ProcesoComercialResumen } from '@/lib/api/procesosComerciales'
import { NuevaLiciCotiDialog } from './NuevaLiciCotiDialog'

interface Props {
  documentType: DocumentType
  procesoComercialId: string | null
  procesos: ProcesoComercialResumen[]
  onChange: (id: string) => void
}

/** clase derivada de document_type (design.md §9.2): licitacion -> 'licitacion',
 * cualquier otro tipo con selector -> 'cotizacion'. `comparativa` no ofrece
 * "+ Nueva" -- reemplaza la comparativa de un proceso YA existente (creado al
 * validar la licitación/cotización), crear uno vacío acá no tiene sentido de
 * negocio. */
export function ProcesoComercialSelector({ documentType, procesoComercialId, procesos, onChange }: Props) {
  const permiteCrearNuevo = documentType === 'licitacion' || documentType === 'cotizacion'
  const clase: Clase = documentType === 'licitacion' ? 'licitacion' : 'cotizacion'

  return (
    <div className="flex items-end gap-3">
      <label className="block flex-1 text-sm">
        <span className="mb-1 block text-slate-600">Proceso comercial</span>
        <select
          value={procesoComercialId ?? ''}
          onChange={(event) => onChange(event.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        >
          <option value="" disabled>
            Seleccioná un proceso
          </option>
          {procesos.map((proceso) => (
            <option key={proceso.id} value={proceso.id}>
              {proceso.nombre}
            </option>
          ))}
        </select>
      </label>

      {permiteCrearNuevo && (
        <NuevaLiciCotiDialog clase={clase} onCreated={(proceso) => onChange(proceso.id)} />
      )}
    </div>
  )
}
