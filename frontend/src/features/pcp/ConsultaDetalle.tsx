import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useAuth } from '@/features/auth/AuthContext'
import { descargarPdfConsulta, enviarConsulta, obtenerConsulta } from '@/lib/api/pcp'
import { pcpQueryKeys } from './queryKeys'
import { PCP_WRITE_ROLES, puedeRol } from './roles'

/** Dispara la descarga del blob ya resuelto sin exponer su contenido binario
 * en pantalla. Se protege ante entornos sin `URL.createObjectURL` (jsdom no
 * lo implementa) para que el flujo de test no dependa de una API del DOM
 * que solo existe en navegadores reales. */
function iniciarDescarga(blob: Blob, nombreArchivo: string) {
  if (typeof URL === 'undefined' || typeof URL.createObjectURL !== 'function') return
  const url = URL.createObjectURL(blob)
  const enlace = document.createElement('a')
  enlace.href = url
  enlace.download = nombreArchivo
  document.body.appendChild(enlace)
  enlace.click()
  enlace.remove()
  URL.revokeObjectURL(url)
}

export function ConsultaDetalle({ consultaId }: { consultaId: string }) {
  const { perfil } = useAuth()
  const queryClient = useQueryClient()
  const puedeEscribir = puedeRol(perfil?.rol, PCP_WRITE_ROLES)

  const consultaQuery = useQuery({
    queryKey: pcpQueryKeys.consulta(consultaId),
    queryFn: () => obtenerConsulta(consultaId),
  })

  const descargaMutation = useMutation({
    mutationFn: () => descargarPdfConsulta(consultaId),
    onSuccess: (blob) => iniciarDescarga(blob, `consulta-${consultaId}.pdf`),
  })

  const envioMutation = useMutation({
    mutationFn: () => enviarConsulta(consultaId),
    onSuccess: (consultaActualizada) => {
      queryClient.setQueryData(pcpQueryKeys.consulta(consultaId), consultaActualizada)
    },
  })

  if (consultaQuery.isPending) return <p className="p-8 text-sm text-slate-500">Cargando consulta…</p>
  if (consultaQuery.isError || !consultaQuery.data) return <p role="alert" className="p-8 text-sm text-red-600">No se pudo cargar la consulta.</p>

  const consulta = consultaQuery.data

  return (
    <main className="p-8">
      <header>
        <p className="text-sm text-slate-500">Consulta {consulta.id}</p>
        <h1 className="text-balance text-xl font-semibold text-navy">Proveedor: {consulta.proveedor_id}</h1>
        <p className="mt-1 text-sm text-slate-500">Estado: {consulta.estado}</p>
      </header>
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          onClick={() => descargaMutation.mutate()}
          disabled={descargaMutation.isPending}
          className="min-h-10 rounded-md border border-slate-300 px-4 text-sm font-medium text-navy disabled:opacity-50"
        >
          Descargar PDF
        </button>
        {puedeEscribir ? (
          <button
            type="button"
            onClick={() => envioMutation.mutate()}
            disabled={envioMutation.isPending}
            className="min-h-10 rounded-md bg-navy px-4 text-sm font-semibold text-white disabled:opacity-50"
          >
            Enviar consulta
          </button>
        ) : null}
      </div>
      {descargaMutation.isError ? <p role="alert" className="mt-2 text-sm text-red-600">No se pudo descargar el PDF.</p> : null}
      {envioMutation.isSuccess ? <p className="mt-3 text-sm text-emerald-700">Consulta enviada.</p> : null}
      {envioMutation.isError ? (
        <p role="alert" className="mt-3 text-sm text-red-600">
          No se pudo enviar la consulta.
        </p>
      ) : null}
    </main>
  )
}
