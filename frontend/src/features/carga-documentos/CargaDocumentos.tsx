import { FormCard } from './components/FormCard'
import { RecentCard } from './components/RecentCard'

export function CargaDocumentos() {
  return (
    <div className="mx-auto max-w-2xl space-y-6 px-6 py-10">
      <header>
        <h1 className="text-xl font-semibold text-slate-900">Carga de documentos</h1>
        <p className="text-sm text-slate-500">Subí el documento a procesar</p>
      </header>

      <FormCard />
      <RecentCard />
    </div>
  )
}
