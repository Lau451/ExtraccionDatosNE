import { useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from '@tanstack/react-router'
import clsx from 'clsx'
import { ApiError } from '@/lib/api/client'
import {
  listarClientes,
  procesarDocumento,
  type ProcesarResultado,
  type TipoDocumento,
} from '@/lib/api/extraccion'

const RECIENTES_KEY = ['documentos-recientes']

const TIPO_OPTIONS: { value: TipoDocumento; label: string }[] = [
  { value: 'licitaciones', label: 'Licitación / Directa' },
  { value: 'comparativas', label: 'Comparativa' },
  { value: 'ordenes', label: 'Orden de compra' },
]

const ACCEPT_POR_TIPO: Record<TipoDocumento, string> = {
  licitaciones: '.pdf,.jpg,.jpeg,.png,.xls,.xlsx',
  ordenes: '.pdf,.jpg,.jpeg,.png,.xls,.xlsx',
  comparativas: '.pdf,.jpg,.jpeg,.png,.xls,.xlsx,.ods,.html,.htm',
}

interface ResultadoPorArchivo {
  archivo: string
  ok: boolean
  error?: string
  /** 409 de duplicado: id de la extracción ya existente (misma droguería)
   * para ofrecer ir directo a ella en vez de solo mostrar el error. */
  extractionIdExistente?: string
}

function extractionIdDuplicado(error: unknown): string | undefined {
  if (!(error instanceof ApiError) || error.status !== 409) return undefined
  const body = error.body as { extraction_id?: unknown } | null
  return typeof body?.extraction_id === 'string' ? body.extraction_id : undefined
}

// D13 § Agrupar al subir -- con N>1 archivos de tipo 'ordenes' se genera un
// único grupo_id (UUID v4) y se manda en cada uno de los N POST /procesar,
// disparados EN SECUENCIA: /procesar tiene su propio semáforo de Gemini y su
// deduplicación por SHA256 (design.md D13 § "Por qué (a) no es un request con
// N archivos", C8), así que no se paraleliza acá tampoco. Un error en un
// archivo (p.ej. 409 de duplicado) no aborta el resto -- se reporta por
// archivo.
async function procesarMultiple(
  archivos: File[],
  tipo: TipoDocumento,
  clienteId: string | undefined,
): Promise<ResultadoPorArchivo[]> {
  const grupoId = tipo === 'ordenes' && archivos.length > 1 ? crypto.randomUUID() : undefined
  const resultados: ResultadoPorArchivo[] = []
  for (const archivo of archivos) {
    try {
      const resultado: ProcesarResultado = await procesarDocumento({
        archivo,
        tipo,
        clienteId,
        grupoId,
      })
      resultados.push({
        archivo: archivo.name,
        ok: resultado.error === undefined,
        error: resultado.error,
      })
    } catch (error) {
      resultados.push({
        archivo: archivo.name,
        ok: false,
        error: error instanceof Error ? error.message : 'Error desconocido',
        extractionIdExistente: extractionIdDuplicado(error),
      })
    }
  }
  return resultados
}

export function FormCard() {
  const [tipo, setTipo] = useState<TipoDocumento>('licitaciones')
  const [archivos, setArchivos] = useState<File[]>([])
  const [clienteId, setClienteId] = useState('')
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const queryClient = useQueryClient()
  const navigate = useNavigate()

  const clientesQuery = useQuery({ queryKey: ['clientes'], queryFn: listarClientes })

  const mutation = useMutation({
    mutationFn: async () => {
      if (archivos.length === 0) throw new Error('Falta seleccionar un archivo')
      const resultados = await procesarMultiple(archivos, tipo, clienteId || undefined)
      return { resultados }
    },
    // carga-asincrona T2 -- /procesar responde 202 apenas termina el upload
    // (el robot corre en background, ver services/extraccion/main.py). Ya no
    // hay nada que esperar acá ni a qué navegar: el usuario ve el progreso
    // real en "Cargas recientes" (RecentCard pollea mientras haya algo
    // 'processing'). Solo invalidamos esa query para que la fila nueva
    // aparezca sin esperar al próximo refetch automático.
    onSuccess: ({ resultados }) => {
      setArchivos([])
      if (fileInputRef.current) fileInputRef.current.value = ''

      const procesados = resultados.filter((resultado) => resultado.ok).length
      if (procesados > 0) {
        queryClient.invalidateQueries({ queryKey: RECIENTES_KEY })
      }
    },
  })

  function handleFiles(fileList: FileList | null) {
    // 'ordenes' es el único tipo con carga múltiple (D13) -- para los otros
    // dos, aunque el usuario seleccione varios, solo se toma el primero.
    const lista = fileList ? Array.from(fileList) : []
    setArchivos(tipo === 'ordenes' ? lista : lista.slice(0, 1))
    mutation.reset()
  }

  function cambiarTipo(nuevoTipo: TipoDocumento) {
    setTipo(nuevoTipo)
    setArchivos([])
    mutation.reset()
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm">
      <div className="mb-5 flex gap-2">
        {TIPO_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => cambiarTipo(option.value)}
            className={clsx(
              'flex cursor-pointer items-center gap-1.5 rounded-full px-3 py-1.5 text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1',
              tipo === option.value
                ? 'bg-navy text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200',
            )}
          >
            {option.label}
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
            handleFiles(event.dataTransfer.files)
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
            multiple={tipo === 'ordenes'}
            accept={ACCEPT_POR_TIPO[tipo]}
            onChange={(event) => handleFiles(event.target.files)}
          />
          {archivos.length > 0 ? (
            <p className="text-sm font-medium text-slate-900">
              {archivos.length === 1
                ? archivos[0].name
                : `${archivos.length} archivos seleccionados`}
            </p>
          ) : (
            <>
              <p className="text-sm font-medium text-slate-900">
                Seleccionar archivo{tipo === 'ordenes' ? '(s)' : ''}
              </p>
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
          <ul className="space-y-1 text-sm">
            {mutation.data?.resultados.map((resultado) => (
              <li key={resultado.archivo} className={resultado.ok ? 'text-emerald-600' : 'text-red-600'}>
                {resultado.archivo}: {resultado.ok ? 'Recibido — procesando en segundo plano' : resultado.error}
                {resultado.extractionIdExistente && (
                  <button
                    type="button"
                    onClick={() =>
                      navigate({
                        to: '/validar-extraccion/$extractionId',
                        params: { extractionId: resultado.extractionIdExistente as string },
                        search: { rowCount: 0 },
                      })
                    }
                    className="ml-2 cursor-pointer font-medium text-accent underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1"
                  >
                    Ver extracción existente
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}

        <button
          type="submit"
          disabled={archivos.length === 0 || mutation.isPending}
          className="w-full cursor-pointer rounded-md bg-navy py-2.5 text-sm font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent focus-visible:ring-offset-1 disabled:cursor-not-allowed disabled:opacity-40"
        >
          {mutation.isPending ? 'Enviando…' : 'Procesar archivo(s)'}
        </button>
      </form>
    </div>
  )
}
