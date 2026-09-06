import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import type { SectorContacto } from '@/lib/api/catalogosComerciales'
import { actualizarContacto, listarContactos, type TerceroContacto } from '@/lib/api/terceros'
import { CrearContactoDialog } from './CrearContactoDialog'

export function ContactosSection({
  terceroId,
  sectores,
  puedeEscribir,
}: {
  terceroId: string
  sectores: SectorContacto[]
  puedeEscribir: boolean
}) {
  const queryClient = useQueryClient()
  const [aDesactivar, setADesactivar] = useState<TerceroContacto | null>(null)

  const { data: contactos, isPending } = useQuery({
    queryKey: ['terceros', terceroId, 'contactos'],
    queryFn: () => listarContactos(terceroId),
  })

  const desactivarMutation = useMutation({
    mutationFn: (contactoId: string) => actualizarContacto(terceroId, contactoId, { activo: false }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['terceros', terceroId, 'contactos'] })
      setADesactivar(null)
    },
  })

  const nombreSector = (id: string | null) => sectores.find((s) => s.id === id)?.nombre ?? '—'

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-slate-700">Contactos</h2>
        {puedeEscribir && (
          <CrearContactoDialog
            terceroId={terceroId}
            sectores={sectores}
            trigger={
              <button
                type="button"
                className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium text-slate-700"
              >
                + Nuevo contacto
              </button>
            }
          />
        )}
      </div>

      {isPending ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-slate-500">
              <th className="py-2 font-medium">Nombre</th>
              <th className="py-2 font-medium">Sector</th>
              <th className="py-2 font-medium">Cargo</th>
              <th className="py-2 font-medium">Principal</th>
              <th className="py-2 font-medium">Estado</th>
              <th className="py-2 font-medium" />
            </tr>
          </thead>
          <tbody>
            {(contactos ?? []).map((contacto) => (
              <tr key={contacto.id} className="border-b border-slate-100">
                <td className="py-2">
                  {contacto.nombre} {contacto.apellido ?? ''}
                </td>
                <td className="py-2 text-slate-500">{nombreSector(contacto.sector_id)}</td>
                <td className="py-2 text-slate-500">{contacto.cargo ?? '—'}</td>
                <td className="py-2 text-slate-500">{contacto.es_principal ? 'Sí' : 'No'}</td>
                <td className="py-2">
                  <span className={contacto.activo ? 'text-emerald-600' : 'text-slate-400'}>
                    {contacto.activo ? 'Activo' : 'Inactivo'}
                  </span>
                </td>
                <td className="py-2 text-right space-x-3">
                  {puedeEscribir && (
                    <>
                      <CrearContactoDialog
                        terceroId={terceroId}
                        contacto={contacto}
                        sectores={sectores}
                        trigger={
                          <button
                            type="button"
                            className="text-sm font-medium text-accent hover:underline"
                          >
                            Editar
                          </button>
                        }
                      />
                      {contacto.activo && (
                        <button
                          type="button"
                          onClick={() => setADesactivar(contacto)}
                          className="text-sm font-medium text-red-600 hover:underline"
                        >
                          Desactivar
                        </button>
                      )}
                    </>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {(contactos ?? []).length === 0 && !isPending && (
        <p className="mt-2 text-sm text-slate-500">No hay contactos cargados.</p>
      )}

      {desactivarMutation.isError && (
        <p className="mt-2 text-sm text-red-600">No se pudo desactivar el contacto.</p>
      )}

      <ConfirmDialog
        open={aDesactivar !== null}
        onOpenChange={(open) => !open && setADesactivar(null)}
        title="Desactivar contacto"
        description={`¿Desactivar a "${aDesactivar?.nombre ?? ''} ${aDesactivar?.apellido ?? ''}"? No existe un borrado físico para contactos — esto solo lo marca como inactivo.`}
        confirmLabel="Desactivar"
        pendingLabel="Desactivando…"
        isPending={desactivarMutation.isPending}
        onConfirm={() => aDesactivar && desactivarMutation.mutate(aDesactivar.id)}
      />
    </section>
  )
}
