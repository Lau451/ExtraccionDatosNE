import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ConfirmDialog } from '@/components/ConfirmDialog'
import {
  crearDireccion,
  crearUsoDireccion,
  eliminarDireccion,
  eliminarUsoDireccion,
  listarDirecciones,
  listarUsosDireccion,
  type TerceroDireccion,
  type TerceroDireccionCreatePayload,
  type UsoDireccion,
} from '@/lib/api/terceros'

const USOS_DISPONIBLES: UsoDireccion[] = ['facturacion', 'entrega', 'documentacion', 'otra']

const CAMPOS_VACIOS: TerceroDireccionCreatePayload = {
  etiqueta: '',
  calle: '',
  numero: '',
  piso_depto: '',
  ciudad: '',
  provincia: '',
  codigo_postal: '',
  pais: 'AR',
  observaciones: '',
}

export function DireccionesSection({
  terceroId,
  puedeEscribir,
}: {
  terceroId: string
  puedeEscribir: boolean
}) {
  const queryClient = useQueryClient()
  const [campos, setCampos] = useState<TerceroDireccionCreatePayload>(CAMPOS_VACIOS)
  const [aEliminar, setAEliminar] = useState<TerceroDireccion | null>(null)

  const { data: direcciones, isPending } = useQuery({
    queryKey: ['terceros', terceroId, 'direcciones'],
    queryFn: () => listarDirecciones(terceroId),
  })

  const crearMutation = useMutation({
    mutationFn: () =>
      crearDireccion(terceroId, {
        ...campos,
        etiqueta: campos.etiqueta || undefined,
        numero: campos.numero || undefined,
        piso_depto: campos.piso_depto || undefined,
        ciudad: campos.ciudad || undefined,
        provincia: campos.provincia || undefined,
        codigo_postal: campos.codigo_postal || undefined,
        observaciones: campos.observaciones || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['terceros', terceroId, 'direcciones'] })
      setCampos(CAMPOS_VACIOS)
    },
  })

  const eliminarMutation = useMutation({
    mutationFn: (direccionId: string) => eliminarDireccion(terceroId, direccionId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['terceros', terceroId, 'direcciones'] })
      setAEliminar(null)
    },
  })

  function campo(key: 'etiqueta' | 'numero' | 'piso_depto' | 'ciudad' | 'provincia' | 'codigo_postal' | 'pais', label: string) {
    return (
      <label className="text-sm">
        <span className="mb-1 block text-slate-600">{label}</span>
        <input
          value={(campos[key] as string) ?? ''}
          onChange={(event) => setCampos((c) => ({ ...c, [key]: event.target.value }))}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
      </label>
    )
  }

  return (
    <section>
      <h2 className="mb-3 text-sm font-semibold text-slate-700">Direcciones</h2>

      {isPending ? (
        <p className="text-sm text-slate-500">Cargando…</p>
      ) : (
        <div className="space-y-4">
          {(direcciones ?? []).map((direccion) => (
            <FilaDireccion
              key={direccion.id}
              terceroId={terceroId}
              direccion={direccion}
              puedeEscribir={puedeEscribir}
              onEliminar={() => setAEliminar(direccion)}
            />
          ))}
          {(direcciones ?? []).length === 0 && (
            <p className="text-sm text-slate-500">No hay direcciones cargadas.</p>
          )}
        </div>
      )}

      {puedeEscribir && (
        <form
          className="mt-6 grid grid-cols-2 gap-3 border-t border-slate-200 pt-4 md:grid-cols-3"
          onSubmit={(event) => {
            event.preventDefault()
            crearMutation.mutate()
          }}
        >
          <label className="text-sm">
            <span className="mb-1 block text-slate-600">Calle</span>
            <input
              required
              value={campos.calle}
              onChange={(event) => setCampos((c) => ({ ...c, calle: event.target.value }))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
            />
          </label>
          {campo('numero', 'Número')}
          {campo('piso_depto', 'Piso/Depto')}
          {campo('etiqueta', 'Etiqueta')}
          {campo('ciudad', 'Ciudad')}
          {campo('provincia', 'Provincia')}
          {campo('codigo_postal', 'Código postal')}
          {campo('pais', 'País')}

          <label className="col-span-full text-sm">
            <span className="mb-1 block text-slate-600">Observaciones</span>
            <textarea
              value={campos.observaciones ?? ''}
              onChange={(event) => setCampos((c) => ({ ...c, observaciones: event.target.value }))}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm"
              rows={2}
            />
          </label>

          <div className="col-span-full">
            <button
              type="submit"
              disabled={crearMutation.isPending}
              className="rounded-md bg-navy px-3 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {crearMutation.isPending ? 'Agregando…' : 'Agregar dirección'}
            </button>
          </div>
        </form>
      )}

      {crearMutation.isError && (
        <p className="mt-2 text-sm text-red-600">No se pudo agregar la dirección.</p>
      )}

      <ConfirmDialog
        open={aEliminar !== null}
        onOpenChange={(open) => !open && setAEliminar(null)}
        title="Eliminar dirección"
        description={`¿Eliminar la dirección "${aEliminar?.calle ?? ''}"? Esta acción no se puede deshacer.`}
        isPending={eliminarMutation.isPending}
        onConfirm={() => aEliminar && eliminarMutation.mutate(aEliminar.id)}
      />
    </section>
  )
}

function FilaDireccion({
  terceroId,
  direccion,
  puedeEscribir,
  onEliminar,
}: {
  terceroId: string
  direccion: TerceroDireccion
  puedeEscribir: boolean
  onEliminar: () => void
}) {
  const queryClient = useQueryClient()
  const [usoNuevo, setUsoNuevo] = useState<UsoDireccion>('facturacion')
  const [esPrincipalNuevo, setEsPrincipalNuevo] = useState(false)

  const { data: usos, isPending: isPendingUsos } = useQuery({
    queryKey: ['terceros', terceroId, 'direcciones', direccion.id, 'usos'],
    queryFn: () => listarUsosDireccion(terceroId, direccion.id),
  })

  const invalidarUsos = () =>
    queryClient.invalidateQueries({
      queryKey: ['terceros', terceroId, 'direcciones', direccion.id, 'usos'],
    })

  const crearUsoMutation = useMutation({
    mutationFn: () =>
      crearUsoDireccion(terceroId, direccion.id, { uso: usoNuevo, es_principal: esPrincipalNuevo }),
    onSuccess: () => {
      invalidarUsos()
      setEsPrincipalNuevo(false)
    },
  })

  const eliminarUsoMutation = useMutation({
    mutationFn: (uso: UsoDireccion) => eliminarUsoDireccion(terceroId, direccion.id, uso),
    onSuccess: invalidarUsos,
  })

  const usosAsignados = new Set((usos ?? []).map((u) => u.uso))
  const usosDisponiblesParaAgregar = USOS_DISPONIBLES.filter((uso) => !usosAsignados.has(uso))

  return (
    <div className="rounded-md border border-slate-200 p-4">
      <div className="flex items-start justify-between">
        <div>
          <p className="text-sm font-medium text-slate-800">
            {direccion.calle} {direccion.numero ?? ''}
            {direccion.etiqueta ? ` — ${direccion.etiqueta}` : ''}
          </p>
          <p className="text-sm text-slate-500">
            {[direccion.ciudad, direccion.provincia, direccion.pais].filter(Boolean).join(', ')}
          </p>
        </div>
        {puedeEscribir && (
          <button
            type="button"
            onClick={onEliminar}
            className="text-sm font-medium text-red-600 hover:underline"
          >
            Eliminar
          </button>
        )}
      </div>

      <div className="mt-3">
        {isPendingUsos ? (
          <p className="text-sm text-slate-500">Cargando usos…</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {(usos ?? []).map((uso) => (
              <span
                key={uso.uso}
                className="flex items-center gap-1 rounded-full bg-slate-100 px-2 py-1 text-xs text-slate-700"
              >
                {uso.uso}
                {uso.es_principal && <span className="font-semibold text-navy">★ principal</span>}
                {puedeEscribir && (
                  <button
                    type="button"
                    onClick={() => eliminarUsoMutation.mutate(uso.uso)}
                    className="ml-1 text-slate-400 hover:text-red-600"
                    aria-label={`Quitar uso ${uso.uso}`}
                  >
                    ×
                  </button>
                )}
              </span>
            ))}
            {(usos ?? []).length === 0 && <span className="text-xs text-slate-400">Sin usos asignados</span>}
          </div>
        )}

        {puedeEscribir && usosDisponiblesParaAgregar.length > 0 && (
          <form
            className="mt-3 flex flex-wrap items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault()
              crearUsoMutation.mutate()
            }}
          >
            <label className="text-sm">
              <span className="mb-1 block text-slate-600">Agregar uso</span>
              <select
                value={usoNuevo}
                onChange={(event) => setUsoNuevo(event.target.value as UsoDireccion)}
                className="rounded-md border border-slate-300 px-2 py-1 text-sm"
              >
                {usosDisponiblesParaAgregar.map((uso) => (
                  <option key={uso} value={uso}>
                    {uso}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex items-center gap-1 text-sm text-slate-600">
              <input
                type="checkbox"
                checked={esPrincipalNuevo}
                onChange={(event) => setEsPrincipalNuevo(event.target.checked)}
              />
              Principal
            </label>
            <button
              type="submit"
              disabled={crearUsoMutation.isPending}
              className="rounded-md border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 disabled:opacity-50"
            >
              {crearUsoMutation.isPending ? 'Agregando…' : 'Agregar'}
            </button>
          </form>
        )}

        {(crearUsoMutation.isError || eliminarUsoMutation.isError) && (
          <p className="mt-2 text-sm text-red-600">
            {crearUsoMutation.error instanceof Error
              ? crearUsoMutation.error.message
              : 'No se pudo aplicar el cambio de uso.'}
          </p>
        )}
      </div>
    </div>
  )
}
