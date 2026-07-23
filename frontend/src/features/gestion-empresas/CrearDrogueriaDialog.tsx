import { useState } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { crearDrogueria, type DrogueriaCreatePayload } from '@/lib/api/droguerias'

const CAMPOS_VACIOS: DrogueriaCreatePayload = {
  nombre: '',
  razon_social: '',
  cuit: '',
  ciudad: '',
  provincia: '',
  contacto_email: '',
  contacto_telefono: '',
}

/** Formatea a medida que se escribe: NN-NNNNNNNN-N (formato CUIT/CUIL). */
function formatearCuit(valor: string): string {
  const digitos = valor.replace(/\D/g, '').slice(0, 11)
  const prefijo = digitos.slice(0, 2)
  const numero = digitos.slice(2, 10)
  const verificador = digitos.slice(10, 11)

  let resultado = prefijo
  if (numero) resultado += `-${numero}`
  if (verificador) resultado += `-${verificador}`
  return resultado
}

export function CrearDrogueriaDialog() {
  const [open, setOpen] = useState(false)
  const [campos, setCampos] = useState(CAMPOS_VACIOS)
  const queryClient = useQueryClient()

  const mutation = useMutation({
    mutationFn: () => crearDrogueria(campos),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['droguerias'] })
      setOpen(false)
      setCampos(CAMPOS_VACIOS)
    },
  })

  function campo(key: keyof DrogueriaCreatePayload, label: string, required = true) {
    return (
      <label className="block text-sm">
        <span className="mb-1 block text-slate-600">{label}</span>
        <input
          required={required}
          value={campos[key] ?? ''}
          onChange={(event) => setCampos((c) => ({ ...c, [key]: event.target.value }))}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </label>
    )
  }

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button
          type="button"
          className="rounded-md bg-navy px-4 py-2 text-sm font-semibold text-white"
        >
          + Nueva empresa
        </button>
      </Dialog.Trigger>

      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/40" />
        <Dialog.Content className="fixed top-1/2 left-1/2 w-full max-w-sm -translate-x-1/2 -translate-y-1/2 rounded-lg bg-white p-6 shadow-xl">
          <Dialog.Title className="text-base font-semibold text-slate-900">
            Nueva empresa
          </Dialog.Title>

          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault()
              mutation.mutate()
            }}
          >
            {campo('nombre', 'Nombre')}
            {campo('razon_social', 'Razón social')}

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">CUIT</span>
              <input
                required
                inputMode="numeric"
                placeholder="20-12345678-9"
                pattern="\d{2}-\d{8}-\d"
                title="Formato NN-NNNNNNNN-N"
                maxLength={13}
                value={campos.cuit}
                onChange={(event) =>
                  setCampos((c) => ({ ...c, cuit: formatearCuit(event.target.value) }))
                }
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>

            {campo('ciudad', 'Ciudad')}
            {campo('provincia', 'Provincia')}
            {campo('contacto_email', 'Email de contacto')}
            {campo('contacto_telefono', 'Teléfono de contacto')}

            {mutation.isError && (
              <p className="text-sm text-red-600">
                {mutation.error instanceof Error ? mutation.error.message : 'No se pudo crear.'}
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
                {mutation.isPending ? 'Creando…' : 'Crear'}
              </button>
            </div>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
