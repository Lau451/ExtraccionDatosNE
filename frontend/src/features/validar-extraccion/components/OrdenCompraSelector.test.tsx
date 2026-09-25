import { useState } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { OrdenCompraSelector } from './OrdenCompraSelector'

vi.mock('@/lib/api/extracciones', () => ({
  obtenerClienteCandidato: vi.fn(),
}))

vi.mock('./ClienteBuscador', () => ({
  ClienteBuscador: ({ onSeleccionar }: { onSeleccionar: (tercero: unknown) => void }) => (
    <div>
      <p>Buscador manual</p>
      <button
        type="button"
        onClick={() =>
          onSeleccionar({ id: 'cli-manual', razon_social: 'Cliente Manual', cuit: null })
        }
      >
        Elegir cliente manual
      </button>
    </div>
  ),
}))

import { obtenerClienteCandidato } from '@/lib/api/extracciones'

function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
}

/** Arnés mínimo que reproduce el invariante real (design.md D3): el botón que
 * de verdad confirma la OC (Phase 8, ValidarExtraccionDetalle) sigue
 * deshabilitado hasta que `OrdenCompraSelector` reporte un `cliente_id` vía
 * el click explícito de "Confirmar cliente" -- nunca por mostrar la
 * sugerencia sola. */
function ArnesConBotonConfirmarOC({ extractionId }: { extractionId: string }) {
  const [clienteId, setClienteId] = useState<string | null>(null)
  return (
    <div>
      <OrdenCompraSelector
        extractionId={extractionId}
        onClienteConfirmado={(id) => setClienteId(id)}
        onClienteDesconfirmado={() => setClienteId(null)}
      />
      <button type="button" disabled={!clienteId}>
        Confirmar OC
      </button>
    </div>
  )
}

const CANDIDATO_ALIAS = {
  cliente_id: 'cli-1',
  razon_social: 'Hospital Central',
  cuit: '30-11111111-1',
  codigo_interno: 'T001',
  tipo: 'hospital',
  activo: true,
  cuit_no_exclusivo: false,
}

const CANDIDATO_COMPARTIDO_A = {
  cliente_id: 'cli-2',
  razon_social: 'Hospital San Roque - Sede Norte',
  cuit: '30-55555555-5',
  codigo_interno: 'T002',
  tipo: 'hospital',
  activo: true,
  cuit_no_exclusivo: true,
}

const CANDIDATO_COMPARTIDO_B = {
  cliente_id: 'cli-3',
  razon_social: 'Hospital San Roque - Sede Sur',
  cuit: '30-55555555-5',
  codigo_interno: 'T003',
  tipo: 'hospital',
  activo: true,
  cuit_no_exclusivo: true,
}

beforeEach(() => {
  vi.mocked(obtenerClienteCandidato).mockReset()
})

describe('OrdenCompraSelector (D3/D3.2)', () => {
  it('la sugerencia se muestra preseleccionada pero "Confirmar OC" sigue deshabilitado hasta el click explícito de "Confirmar cliente"', async () => {
    vi.mocked(obtenerClienteCandidato).mockResolvedValue({
      origen: 'alias',
      candidatos: [CANDIDATO_ALIAS],
      cuit_extraido: '30111111111',
      razon_social_extraida: 'HOSPITAL CENTRAL',
      advertencias: [],
    })

    renderConQueryClient(<ArnesConBotonConfirmarOC extractionId="ext-1" />)

    await waitFor(() => expect(screen.getByText(/hospital central/i)).toBeInTheDocument())
    expect(screen.getByRole('button', { name: /confirmar oc/i })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: /^confirmar cliente$/i }))

    await waitFor(() =>
      expect(screen.getByRole('button', { name: /confirmar oc/i })).not.toBeDisabled(),
    )
  })

  it('"No es este" abre el buscador manual (ClienteBuscador)', async () => {
    vi.mocked(obtenerClienteCandidato).mockResolvedValue({
      origen: 'alias',
      candidatos: [CANDIDATO_ALIAS],
      cuit_extraido: '30111111111',
      razon_social_extraida: 'HOSPITAL CENTRAL',
      advertencias: [],
    })

    renderConQueryClient(<ArnesConBotonConfirmarOC extractionId="ext-1" />)

    await waitFor(() => expect(screen.getByText(/hospital central/i)).toBeInTheDocument())
    expect(screen.queryByText(/buscador manual/i)).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /no es este/i }))

    expect(screen.getByText(/buscador manual/i)).toBeInTheDocument()
  })

  it('con N candidatos de CUIT compartido muestra N radio buttons, ninguno preseleccionado', async () => {
    vi.mocked(obtenerClienteCandidato).mockResolvedValue({
      origen: 'cuit_compartido',
      candidatos: [CANDIDATO_COMPARTIDO_A, CANDIDATO_COMPARTIDO_B],
      cuit_extraido: '30555555555',
      razon_social_extraida: 'HOSPITAL SAN ROQUE',
      advertencias: [],
    })

    renderConQueryClient(<ArnesConBotonConfirmarOC extractionId="ext-1" />)

    await waitFor(() => expect(screen.getAllByRole('radio')).toHaveLength(2))
    for (const radio of screen.getAllByRole('radio')) {
      expect(radio).not.toBeChecked()
    }
    expect(screen.getByRole('button', { name: /confirmar oc/i })).toBeDisabled()
  })

  it('al confirmar la sugerencia muestra el cliente confirmado y oculta "Confirmar cliente"', async () => {
    vi.mocked(obtenerClienteCandidato).mockResolvedValue({
      origen: 'alias',
      candidatos: [CANDIDATO_ALIAS],
      cuit_extraido: '30111111111',
      razon_social_extraida: 'HOSPITAL CENTRAL',
      advertencias: [],
    })

    renderConQueryClient(<ArnesConBotonConfirmarOC extractionId="ext-1" />)

    await waitFor(() => expect(screen.getByText(/hospital central/i)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /^confirmar cliente$/i }))

    expect(screen.getByText(/cliente confirmado/i)).toBeInTheDocument()
    expect(screen.getByText(/hospital central/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /^confirmar cliente$/i })).not.toBeInTheDocument()
  })

  it('"Cambiar" vuelve a la sugerencia y deshabilita otra vez "Confirmar OC"', async () => {
    vi.mocked(obtenerClienteCandidato).mockResolvedValue({
      origen: 'alias',
      candidatos: [CANDIDATO_ALIAS],
      cuit_extraido: '30111111111',
      razon_social_extraida: 'HOSPITAL CENTRAL',
      advertencias: [],
    })

    renderConQueryClient(<ArnesConBotonConfirmarOC extractionId="ext-1" />)

    await waitFor(() => expect(screen.getByText(/hospital central/i)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /^confirmar cliente$/i }))
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /confirmar oc/i })).not.toBeDisabled(),
    )

    fireEvent.click(screen.getByRole('button', { name: /cambiar/i }))

    expect(screen.queryByText(/cliente confirmado/i)).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /^confirmar cliente$/i })).toBeInTheDocument()
    await waitFor(() =>
      expect(screen.getByRole('button', { name: /confirmar oc/i })).toBeDisabled(),
    )
  })

  it('el cliente elegido en el buscador manual también se muestra como confirmado', async () => {
    vi.mocked(obtenerClienteCandidato).mockResolvedValue({
      origen: 'ninguno',
      candidatos: [],
      cuit_extraido: null,
      razon_social_extraida: null,
      advertencias: [],
    })

    renderConQueryClient(<ArnesConBotonConfirmarOC extractionId="ext-1" />)

    await waitFor(() => expect(screen.getByText(/buscador manual/i)).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: /elegir cliente manual/i }))

    expect(screen.getByText(/cliente confirmado/i)).toBeInTheDocument()
    expect(screen.getByText(/cliente manual/i)).toBeInTheDocument()
  })

  it('sin sugerencia (origen "ninguno") cae directo al buscador, sin pedir "No es este"', async () => {
    vi.mocked(obtenerClienteCandidato).mockResolvedValue({
      origen: 'ninguno',
      candidatos: [],
      cuit_extraido: null,
      razon_social_extraida: null,
      advertencias: [],
    })

    renderConQueryClient(<ArnesConBotonConfirmarOC extractionId="ext-1" />)

    await waitFor(() => expect(screen.getByText(/buscador manual/i)).toBeInTheDocument())
    expect(screen.queryByRole('button', { name: /no es este/i })).not.toBeInTheDocument()
  })
})
