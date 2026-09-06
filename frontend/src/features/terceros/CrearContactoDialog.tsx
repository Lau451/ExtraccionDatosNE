import { useEffect, useState, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import type { SectorContacto } from '@/lib/api/catalogosComerciales'
import {
  actualizarContacto,
  crearContacto,
  type TerceroContacto,
  type TerceroContactoCreatePayload,
} from '@/lib/api/terceros'

const CAMPOS_VACIOS: TerceroContactoCreatePayload = {
  nombre: '',
  apellido: '',
  sector_id: '',
  cargo: '',
  email: '',
  telefono: '',
  celular: '',
  es_principal: false,
  notas: '',
}

function camposDesdeContacto(contacto: TerceroContacto): TerceroContactoCreatePayload {
  return {
    nombre: contacto.nombre,
    apellido: contacto.apellido ?? '',
    sector_id: contacto.sector_id ?? '',
    cargo: contacto.cargo ?? '',
    email: contacto.email ?? '',
    telefono: contacto.telefono ?? '',
    celular: contacto.celular ?? '',
    es_principal: contacto.es_principal,
    notas: contacto.notas ?? '',
  }
}

/** Alta o edición de un contacto — mismo criterio que `CrearProductoDialog`.
 * El catálogo de sectores puede venir vacío (drogueria nueva); el select
 * sigue disponible con "Sin sector" y no bloquea el guardado, ver prompt de
 * la tarea. */
export function CrearContactoDialog({
  terceroId,
  contacto,
  sectores,
  trigger,
}: {
  terceroId: string
  contacto?: TerceroContacto
  sectores: SectorContacto[]
  trigger: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [campos, setCampos] = useState<TerceroContactoCreatePayload>(
    contacto ? camposDesdeContacto(contacto) : CAMPOS_VACIOS,
  )
  const queryClient = useQueryClient()
  const esEdicion = !!contacto

  useEffect(() => {
    if (open) {
      setCampos(contacto ? camposDesdeContacto(contacto) : CAMPOS_VACIOS)
    }
  }, [open, contacto])

  function limpiarPayload(): TerceroContactoCreatePayload {
    return {
      ...campos,
      apellido: campos.apellido || undefined,
      sector_id: campos.sector_id || undefined,
      cargo: campos.cargo || undefined,
      email: campos.email || undefined,
      telefono: campos.telefono || undefined,
      celular: campos.celular || undefined,
      notas: campos.notas || undefined,
    }
  }

  const mutation = useMutation({
    mutationFn: () =>
      esEdicion
        ? actualizarContacto(terceroId, contacto.id, limpiarPayload())
        : crearContacto(terceroId, limpiarPayload()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['terceros', terceroId, 'contactos'] })
      setOpen(false)
    },
  })

  function campo(key: 'nombre' | 'apellido' | 'cargo' | 'email' | 'telefono' | 'celular', label: string, required = false) {
    return (
      <label className="block text-sm">
        <span className="mb-1 block text-slate-600">{label}</span>
        <input
          required={required}
          value={(campos[key] as string) ?? ''}
          onChange={(event) => setCampos((c) => ({ ...c, [key]: event.target.value }))}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </label>
    )
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>{trigger}</Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 max-h-[85vh] w-full max-w-md -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-slate-900">
            {esEdicion ? 'Editar contacto' : 'Nuevo contacto'}
          </Dialog.Title>

          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault()
              mutation.mutate()
            }}
          >
            {campo('nombre', 'Nombre', true)}
            {campo('apellido', 'Apellido')}

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Sector</span>
              <select
                value={campos.sector_id ?? ''}
                onChange={(event) => setCampos((c) => ({ ...c, sector_id: event.target.value }))}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">Sin sector</option>
                {sectores.map((sector) => (
                  <option key={sector.id} value={sector.id}>
                    {sector.nombre}
                  </option>
                ))}
              </select>
            </label>

            {campo('cargo', 'Cargo')}
            {campo('email', 'Email')}
            {campo('telefono', 'Teléfono')}
            {campo('celular', 'Celular')}

            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={campos.es_principal ?? false}
                onChange={(event) => setCampos((c) => ({ ...c, es_principal: event.target.checked }))}
              />
              <span className="text-slate-600">Contacto principal</span>
            </label>

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Notas</span>
              <textarea
                value={campos.notas ?? ''}
                onChange={(event) => setCampos((c) => ({ ...c, notas: event.target.value }))}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
                rows={2}
              />
            </label>

            {mutation.isError && (
              <p className="text-sm text-red-600">
                {mutation.error instanceof Error ? mutation.error.message : 'No se pudo guardar.'}
              </p>
            )}

            <div className="flex justify-end gap-2 pt-2">
              <Dialog.Close asChild>
                <button type="button" className="rounded-md px-3 py-2 text-sm text-slate-600">
                  Cancelar
                </button>
              </Dialog.Close>
              <button
                type="submit"
                disabled={mutation.isPending}
                className="rounded-md bg-navy px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
              >
                {mutation.isPending ? 'Guardando…' : esEdicion ? 'Guardar' : 'Crear'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
