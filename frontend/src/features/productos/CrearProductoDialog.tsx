import { useEffect, useState, type ReactNode } from 'react'
import * as Dialog from '@radix-ui/react-dialog'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import {
  actualizarProducto,
  crearProducto,
  type Categoria,
  type Clasificacion,
  type Producto,
  type ProductoCreatePayload,
} from '@/lib/api/productos'

const CLASIFICACIONES: Clasificacion[] = [
  'medicamento',
  'descartable',
  'insumo',
  'equipamiento',
  'perfumeria',
  'otro',
]

const CAMPOS_VACIOS: ProductoCreatePayload = {
  codigo_interno: '',
  nombre: '',
  categoria_id: '',
  clasificacion: undefined,
  droga: '',
  presentacion: '',
  forma_farmaceutica: '',
  laboratorio: '',
  codigo_anmat: '',
}

function camposDesdeProducto(producto: Producto): ProductoCreatePayload {
  return {
    codigo_interno: producto.codigo_interno,
    nombre: producto.nombre,
    categoria_id: producto.categoria_id ?? '',
    clasificacion: producto.clasificacion ?? undefined,
    droga: producto.droga ?? '',
    presentacion: producto.presentacion ?? '',
    forma_farmaceutica: producto.forma_farmaceutica ?? '',
    laboratorio: producto.laboratorio ?? '',
    codigo_anmat: producto.codigo_anmat ?? '',
  }
}

/** Alta o edición de un producto — mismo formulario para ambos casos (igual
 * criterio que gestion-empresas para no duplicar el formulario). En modo
 * edición se pasa `producto`; el trigger se recibe como children para poder
 * usarse tanto como botón de header ("+ Nuevo producto") como acción de fila
 * ("Editar"). */
export function CrearProductoDialog({
  producto,
  categorias,
  trigger,
}: {
  producto?: Producto
  categorias: Categoria[]
  trigger: ReactNode
}) {
  const [open, setOpen] = useState(false)
  const [campos, setCampos] = useState<ProductoCreatePayload>(
    producto ? camposDesdeProducto(producto) : CAMPOS_VACIOS,
  )
  const queryClient = useQueryClient()
  const esEdicion = !!producto

  useEffect(() => {
    if (open) {
      setCampos(producto ? camposDesdeProducto(producto) : CAMPOS_VACIOS)
    }
  }, [open, producto])

  function limpiarPayload(): ProductoCreatePayload {
    return {
      ...campos,
      categoria_id: campos.categoria_id || undefined,
      clasificacion: campos.clasificacion || undefined,
      droga: campos.droga || undefined,
      presentacion: campos.presentacion || undefined,
      forma_farmaceutica: campos.forma_farmaceutica || undefined,
      laboratorio: campos.laboratorio || undefined,
      codigo_anmat: campos.codigo_anmat || undefined,
    }
  }

  const mutation = useMutation({
    mutationFn: () =>
      esEdicion ? actualizarProducto(producto.id, limpiarPayload()) : crearProducto(limpiarPayload()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['productos'] })
      setOpen(false)
    },
  })

  function campo(key: keyof ProductoCreatePayload, label: string, required = false) {
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
            {esEdicion ? 'Editar producto' : 'Nuevo producto'}
          </Dialog.Title>

          <form
            className="mt-4 space-y-3"
            onSubmit={(event) => {
              event.preventDefault()
              mutation.mutate()
            }}
          >
            {campo('codigo_interno', 'Código interno', true)}
            {campo('nombre', 'Nombre', true)}

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Categoría</span>
              <select
                value={campos.categoria_id ?? ''}
                onChange={(event) => setCampos((c) => ({ ...c, categoria_id: event.target.value }))}
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">Sin categoría</option>
                {categorias.map((categoria) => (
                  <option key={categoria.id} value={categoria.id}>
                    {categoria.nombre}
                  </option>
                ))}
              </select>
            </label>

            <label className="block text-sm">
              <span className="mb-1 block text-slate-600">Clasificación</span>
              <select
                value={campos.clasificacion ?? ''}
                onChange={(event) =>
                  setCampos((c) => ({
                    ...c,
                    clasificacion: (event.target.value || undefined) as Clasificacion | undefined,
                  }))
                }
                className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              >
                <option value="">Sin clasificación</option>
                {CLASIFICACIONES.map((clasificacion) => (
                  <option key={clasificacion} value={clasificacion}>
                    {clasificacion}
                  </option>
                ))}
              </select>
            </label>

            {campo('droga', 'Droga')}
            {campo('presentacion', 'Presentación')}
            {campo('forma_farmaceutica', 'Forma farmacéutica')}
            {campo('laboratorio', 'Laboratorio')}
            {campo('codigo_anmat', 'Código ANMAT')}

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
