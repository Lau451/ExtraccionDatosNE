import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import clsx from 'clsx'
import {
  listarClientes,
  listarDocumentosRecientes,
  procesarDocumento,
  type TipoDocumento,
} from '@/lib/api/extraccion'

const RECIENTES_KEY = ['documentos-recientes']

function esperar(ms: number) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

// El backend responde 200 apenas termina de leer el CSV -- el guardado real en
// `extraction_results` corre después, en un BackgroundTask (ver
// services/extraccion/main.py: schedule_persist_output). Un solo invalidate
// apenas llega la respuesta casi siempre le gana la carrera a ese guardado y
// deja "Cargas recientes" desactualizado hasta el próximo refetch (foco de
// ventana, navegación). Reintentamos hasta ver crecer el conteo, con tope.
async function esperarNuevoDocumento(queryClient: ReturnType<typeof useQueryClient>, countAntes: number) {
  for (let intento = 0; intento < 6; intento++) {
    const data = await queryClient.fetchQuery({
      queryKey: RECIENTES_KEY,
      queryFn: () => listarDocumentosRecientes(),
    })
    if (data.documentos.length > countAntes) return
    await esperar(600)
  }
}

const TIPO_OPTIONS: { value: TipoDocumento; label: string; disabled?: boolean }[] = [
  { value: 'licitaciones', label: 'Licitación / Directa' },
  { value: 'comparativas', label: 'Comparativa' },
  { value: 'ordenes', label: 'Orden de compra', disabled: true },
]

const ACCEPT_POR_TIPO: Record<TipoDocumento, string> = {
  licitaciones: '.pdf,.jpg,.jpeg,.png,.xls,.xlsx',
  ordenes: '.pdf,.jpg,.jpeg,.png,.xls,.xlsx',
  comparativas: '.pdf,.jpg,.jpeg,.png,.xls,.xlsx,.ods,.html,.htm',
}

export function FormCard() {
  const [tipo, setTipo] = useState<TipoDocumento>('licitaciones')
  const [archivo, setArchivo] = useState<File | null>(null)
  const [clienteId, setClienteId] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()

  const clientesQuery = useQuery({ queryKey: ['clientes'], queryFn: listarClientes })

  const mutation = useMutation({
    mutationFn: async () => {
      if (!archivo) throw new Error('Falta seleccionar un archivo')
      const countAntes = queryClient.getQueryData<{ documentos: unknown[] }>(RECIENTES_KEY)
        ?.documentos.length ?? 0
      const resultado = await procesarDocumento({ archivo, tipo, clienteId: clienteId || undefined })
      await esperarNuevoDocumento(queryClient, countAntes)
      return resultado
    },
    onSuccess: () => {
      setArchivo(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
    },
  })

  function handleFile(file: File | null) {
    setArchivo(file)
    mutation.reset()
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-5 flex gap-2">
        {TIPO_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            disabled={option.disabled}
            title={option.disabled ? 'Próximamente' : undefined}
            onClick={() => setTipo(option.value)}
            className={clsx(
              'flex items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors',
              option.disabled
                ? 'cursor-not-allowed bg-slate-50 text-slate-300'
                : tipo === option.value
                  ? 'bg-navy text-white'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
            )}
          >
            {option.label}
            {option.disabled && (
              <span className="rounded-full bg-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
                Próximamente
              </span>
            )}
          </button>
        ))}
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault()
          mutation.mutate()
        }}
        className="space-y-4"
      >
        <label
          onDragOver={(event) => {
            event.preventDefault()
            setIsDragging(true)
          }}
          onDragLeave={() => setIsDragging(false)}
          onDrop={(event) => {
            event.preventDefault()
            setIsDragging(false)
            handleFile(event.dataTransfer.files[0] ?? null)
          }}
          className={clsx(
            'flex cursor-pointer flex-col items-center justify-center rounded-lg border-2 border-dashed px-4 py-8 text-center transition-colors',
            isDragging ? 'border-accent bg-accent/5' : 'border-slate-300',
          )}
        >
          <input
            ref={fileInputRef}
            type="file"
            hidden
            accept={ACCEPT_POR_TIPO[tipo]}
            onChange={(event) => handleFile(event.target.files?.[0] ?? null)}
          />
          {archivo ? (
            <p className="text-sm font-medium text-slate-900">{archivo.name}</p>
          ) : (
            <>
              <p className="text-sm font-medium text-slate-900">Seleccionar archivo</p>
              <p className="text-xs text-slate-500">o arrastrá y soltá acá</p>
            </>
          )}
        </label>

        <div>
          <span className="mb-1 block text-sm text-slate-600">
            Cliente <span className="text-slate-400">(opcional)</span>
          </span>
          <select
            value={clienteId}
            onChange={(event) => setClienteId(event.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
          >
            <option value="">Sin cliente</option>
            {clientesQuery.data?.map((cliente) => (
              <option key={cliente.id} value={cliente.id}>
                {cliente.nombre}
              </option>
            ))}
          </select>
        </div>

        {mutation.isError && (
          <p className="text-sm text-red-600">{(mutation.error as Error).message}</p>
        )}
        {mutation.isSuccess && (
          <p className="text-sm text-emerald-600">Documento procesado correctamente.</p>
        )}

        <button
          type="submit"
          disabled={!archivo || mutation.isPending}
          className="w-full rounded-md bg-navy py-2.5 text-sm font-semibold text-white disabled:opacity-40"
        >
          {mutation.isPending ? 'Procesando…' : 'Procesar archivo'}
        </button>
      </form>
    </div>
  )
}
