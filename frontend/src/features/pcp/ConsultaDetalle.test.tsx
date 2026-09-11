import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { AgruparConsultaDialog } from './AgruparConsultaDialog'
import { ConsultaDetalle } from './ConsultaDetalle'

const { perfilMock } = vi.hoisted(() => ({ perfilMock: { rol: 'admin' as string } }))

vi.mock('@/features/auth/AuthContext', () => ({ useAuth: () => ({ perfil: perfilMock }) }))
vi.mock('@/lib/api/pcp', () => ({
  obtenerConsulta: vi.fn(),
  descargarPdfConsulta: vi.fn(),
  enviarConsulta: vi.fn(),
  agruparConsultas: vi.fn(),
}))

import { agruparConsultas, descargarPdfConsulta, enviarConsulta, obtenerConsulta } from '@/lib/api/pcp'

const CONSULTA = {
  id: 'consulta-1',
  drogueria_id: 'drog-1',
  proveedor_id: 'prov-1',
  contacto_id: null,
  estado: 'borrador',
  canal: null,
  fecha_envio: null,
  fecha_respuesta_esperada: null,
  documento_path: null,
}

const SELECCIONES = [
  { pcp_renglon_id: 'reng-1', proveedor_id: 'prov-1' },
  { pcp_renglon_id: 'reng-2', proveedor_id: 'prov-1' },
  { pcp_renglon_id: 'reng-3', proveedor_id: 'prov-2' },
]

function renderConsultaDetalle(consultaId = 'consulta-1') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return { client, ...render(<QueryClientProvider client={client}><ConsultaDetalle consultaId={consultaId} /></QueryClientProvider>) }
}

function renderAgruparConsultaDialog(props: { selecciones?: typeof SELECCIONES, puedeEscribir?: boolean } = {}) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return {
    client,
    ...render(
      <QueryClientProvider client={client}>
        <AgruparConsultaDialog
          pcpId="pcp-1"
          selecciones={props.selecciones ?? SELECCIONES}
          puedeEscribir={props.puedeEscribir ?? true}
        />
      </QueryClientProvider>,
    ),
  }
}

beforeEach(() => {
  perfilMock.rol = 'admin'
  vi.mocked(obtenerConsulta).mockReset().mockResolvedValue(CONSULTA as never)
  vi.mocked(descargarPdfConsulta).mockReset().mockResolvedValue(new Blob(['%PDF-1.4'], { type: 'application/pdf' }))
  vi.mocked(enviarConsulta).mockReset().mockResolvedValue({ ...CONSULTA, estado: 'enviada' } as never)
  vi.mocked(agruparConsultas).mockReset().mockResolvedValue([{ ...CONSULTA, id: 'consulta-nueva' }] as never)
})

describe('AgruparConsultaDialog', () => {
  it('agrupa los renglones seleccionados de uno o más proveedores en una única confirmación', async () => {
    renderAgruparConsultaDialog()

    fireEvent.click(screen.getByRole('button', { name: /agrupar consulta/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirmar/i }))

    await waitFor(() => expect(agruparConsultas).toHaveBeenCalledWith({ selecciones: SELECCIONES }))
  })

  it('no renderiza ningún disparador de agrupación para un rol de solo lectura', () => {
    renderAgruparConsultaDialog({ puedeEscribir: false })

    expect(screen.queryByRole('button', { name: /agrupar consulta/i })).not.toBeInTheDocument()
  })

  it('cuando varios proveedores distintos producen varias consultas creadas, muestra un enlace por cada una', async () => {
    vi.mocked(agruparConsultas).mockResolvedValue([
      { ...CONSULTA, id: 'consulta-prov-1', proveedor_id: 'prov-1' },
      { ...CONSULTA, id: 'consulta-prov-2', proveedor_id: 'prov-2' },
    ] as never)
    renderAgruparConsultaDialog()

    fireEvent.click(screen.getByRole('button', { name: /agrupar consulta/i }))
    fireEvent.click(screen.getByRole('button', { name: /confirmar/i }))

    expect(await screen.findByRole('link', { name: /ver consulta de prov-1/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /ver consulta de prov-2/i })).toBeInTheDocument()
  })
})

describe('ConsultaDetalle', () => {
  it('muestra el detalle de una consulta ya agrupada con su proveedor y estado', async () => {
    renderConsultaDetalle()

    expect(await screen.findByText(/prov-1/)).toBeInTheDocument()
    expect(obtenerConsulta).toHaveBeenCalledWith('consulta-1')
  })

  it('descarga el PDF de la consulta sin exponer el contenido binario crudo en pantalla', async () => {
    renderConsultaDetalle()
    await screen.findByText(/prov-1/)

    fireEvent.click(screen.getByRole('button', { name: /descargar pdf/i }))

    await waitFor(() => expect(descargarPdfConsulta).toHaveBeenCalledWith('consulta-1'))
    expect(screen.queryByText('%PDF-1.4')).not.toBeInTheDocument()
  })

  it('muestra un error visible cuando falla la descarga del PDF y mantiene la acción disponible', async () => {
    vi.mocked(descargarPdfConsulta).mockRejectedValueOnce(new Error('Error 500 al descargar el PDF de la consulta'))
    renderConsultaDetalle()
    await screen.findByText(/prov-1/)

    fireEvent.click(screen.getByRole('button', { name: /descargar pdf/i }))

    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo descargar el PDF.')
    expect(screen.getByRole('button', { name: /descargar pdf/i })).not.toBeDisabled()
  })

  it('muestra la acción Enviar consulta para un rol de escritura', async () => {
    renderConsultaDetalle()

    expect(await screen.findByRole('button', { name: 'Enviar consulta' })).toBeInTheDocument()
  })

  it('oculta por completo la acción Enviar consulta para un rol de solo lectura', async () => {
    perfilMock.rol = 'superadmin'
    renderConsultaDetalle()

    await screen.findByText(/prov-1/)
    expect(screen.queryByRole('button', { name: 'Enviar consulta' })).not.toBeInTheDocument()
  })

  it('muestra una confirmación visible al enviar la consulta con éxito, sin detalle del adaptador de mensajería', async () => {
    renderConsultaDetalle()
    await screen.findByRole('button', { name: 'Enviar consulta' })

    fireEvent.click(screen.getByRole('button', { name: 'Enviar consulta' }))

    await waitFor(() => expect(enviarConsulta).toHaveBeenCalledWith('consulta-1'))
    expect(await screen.findByText(/consulta enviada/i)).toBeInTheDocument()
    expect(screen.queryByText(/whatsapp/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/email/i)).not.toBeInTheDocument()
  })

  it('muestra un error al fallar el envío y mantiene la acción disponible para reintentar', async () => {
    vi.mocked(enviarConsulta).mockRejectedValueOnce(new Error('No se pudo enviar la consulta'))
    renderConsultaDetalle()
    await screen.findByRole('button', { name: 'Enviar consulta' })

    fireEvent.click(screen.getByRole('button', { name: 'Enviar consulta' }))

    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo enviar la consulta')
    expect(screen.getByRole('button', { name: 'Enviar consulta' })).not.toBeDisabled()
  })

  it('al reintentar el envío después de un fallo, limpia el error y muestra la confirmación de éxito', async () => {
    vi.mocked(enviarConsulta)
      .mockRejectedValueOnce(new Error('No se pudo enviar la consulta'))
      .mockResolvedValueOnce({ ...CONSULTA, estado: 'enviada' } as never)
    renderConsultaDetalle()
    await screen.findByRole('button', { name: 'Enviar consulta' })

    fireEvent.click(screen.getByRole('button', { name: 'Enviar consulta' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('No se pudo enviar la consulta')

    fireEvent.click(screen.getByRole('button', { name: 'Enviar consulta' }))

    expect(await screen.findByText(/consulta enviada/i)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(enviarConsulta).toHaveBeenCalledTimes(2)
  })

  it('nunca muestra el detalle específico del adaptador de mensajería cuando el envío falla', async () => {
    vi.mocked(enviarConsulta).mockRejectedValueOnce(
      new Error(
        "No se pudo entregar la consulta 'consulta-1' por ningún canal configurado: "
        + "[WhatsApp: número de destino inválido, Email: tiempo de espera SMTP agotado]",
      ),
    )
    renderConsultaDetalle()
    await screen.findByRole('button', { name: 'Enviar consulta' })

    fireEvent.click(screen.getByRole('button', { name: 'Enviar consulta' }))

    const alerta = await screen.findByRole('alert')
    expect(alerta).toHaveTextContent('No se pudo enviar la consulta.')
    expect(alerta).not.toHaveTextContent(/whatsapp/i)
    expect(alerta).not.toHaveTextContent(/smtp/i)
    expect(alerta).not.toHaveTextContent(/canal configurado/i)
  })
})
