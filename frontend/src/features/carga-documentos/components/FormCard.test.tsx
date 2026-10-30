import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '@/lib/api/client'
import { FormCard } from './FormCard'

const { navigateMock } = vi.hoisted(() => ({ navigateMock: vi.fn() }))

vi.mock('@tanstack/react-router', () => ({
  useNavigate: () => navigateMock,
}))

vi.mock('@/lib/api/extraccion', () => ({
  listarClientes: vi.fn().mockResolvedValue([]),
  procesarDocumento: vi.fn(),
}))

import { listarClientes, procesarDocumento } from '@/lib/api/extraccion'

// Devuelve también el `queryClient` -- lo necesitan los tests de
// invalidación (carga-asincrona T2: éxito invalida 'documentos-recientes'
// en vez de esperar a que aparezca vía polling manual, D.).
function renderConQueryClient(ui: React.ReactElement) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const utils = render(<QueryClientProvider client={queryClient}>{ui}</QueryClientProvider>)
  return { ...utils, queryClient }
}

function archivo(nombre: string) {
  return new File(['contenido'], nombre, { type: 'application/pdf' })
}

beforeEach(() => {
  navigateMock.mockReset()
  vi.mocked(procesarDocumento).mockReset()
})

function elegirTipo(label: string) {
  fireEvent.click(screen.getByRole('button', { name: label }))
}

function abrirTabOrdenes() {
  fireEvent.click(screen.getByRole('button', { name: /orden de compra/i }))
}

describe('FormCard — carga múltiple de órdenes de compra (D13)', () => {
  it('con tipo="ordenes" el input de archivo acepta múltiples archivos', () => {
    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(input.multiple).toBe(true)
  })

  it('con tipo="licitaciones" el input NO es múltiple', () => {
    const { container } = renderConQueryClient(<FormCard />)
    elegirTipo('Licitación / Directa')

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(input.multiple).toBe(false)
  })

  it('con 3 archivos se disparan 3 procesarDocumento EN SECUENCIA con el mismo grupoId', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('11111111-1111-4111-8111-111111111111')
    const orden: string[] = []
    vi.mocked(procesarDocumento).mockImplementation(async ({ archivo: file }) => {
      orden.push(`start:${file.name}`)
      await Promise.resolve()
      orden.push(`end:${file.name}`)
      return { ok: true, tipo: 'orden_compra' }
    })

    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    const archivos = [archivo('a.pdf'), archivo('b.pdf'), archivo('c.pdf')]
    fireEvent.change(input, { target: { files: archivos } })

    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() => expect(procesarDocumento).toHaveBeenCalledTimes(3))

    expect(orden).toEqual([
      'start:a.pdf',
      'end:a.pdf',
      'start:b.pdf',
      'end:b.pdf',
      'start:c.pdf',
      'end:c.pdf',
    ])
    for (const llamada of vi.mocked(procesarDocumento).mock.calls) {
      expect(llamada[0].grupoId).toBe('11111111-1111-4111-8111-111111111111')
    }
  })

  it('un 409 de duplicado en el segundo archivo no aborta el tercero, y se reporta por archivo', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('22222222-2222-4222-8222-222222222222')
    vi.mocked(procesarDocumento).mockImplementation(async ({ archivo: file }) => {
      if (file.name === 'duplicado.pdf') {
        throw new Error('Ya existe un documento con este contenido (409)')
      }
      return { ok: true, tipo: 'orden_compra' }
    })

    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    const archivos = [archivo('a.pdf'), archivo('duplicado.pdf'), archivo('c.pdf')]
    fireEvent.change(input, { target: { files: archivos } })

    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() => expect(procesarDocumento).toHaveBeenCalledTimes(3))

    await waitFor(() =>
      expect(screen.getByText(/duplicado\.pdf/).closest('li')).toHaveTextContent(/409/),
    )
    expect(screen.getByText(/^a\.pdf/).closest('li')).toHaveTextContent(/procesando en segundo plano/i)
    expect(screen.getByText(/^c\.pdf/).closest('li')).toHaveTextContent(/procesando en segundo plano/i)
  })
})

describe('FormCard — documento duplicado (409)', () => {
  it('ofrece ir a la extracción existente que devuelve el 409', async () => {
    vi.mocked(procesarDocumento).mockRejectedValue(
      new ApiError('Este documento ya fue procesado', 409, { extraction_id: 'ext-existente' }),
    )

    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [archivo('repetido.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    const boton = await screen.findByRole('button', { name: /ver extracción existente/i })
    expect(screen.getByText(/repetido\.pdf/).closest('li')).toHaveTextContent(/ya fue procesado/i)

    fireEvent.click(boton)

    expect(navigateMock).toHaveBeenCalledWith({
      to: '/validar-extraccion/$extractionId',
      params: { extractionId: 'ext-existente' },
      search: { rowCount: 0 },
    })
  })

  it('un error sin extraction_id no ofrece el link', async () => {
    vi.mocked(procesarDocumento).mockRejectedValue(new ApiError('Error 500', 500, null))

    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [archivo('roto.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() =>
      expect(screen.getByText(/roto\.pdf/).closest('li')).toHaveTextContent(/error 500/i),
    )
    expect(screen.queryByRole('button', { name: /ver extracción existente/i })).not.toBeInTheDocument()
  })

  it('lote mixto (uno nuevo + un duplicado): reporta cada archivo, invalida "recientes" y no navega', async () => {
    vi.mocked(procesarDocumento).mockImplementation(async ({ archivo: file }) => {
      if (file.name === 'repetido.pdf') {
        throw new ApiError('Este documento ya fue procesado', 409, { extraction_id: 'ext-existente' })
      }
      return { ok: true, tipo: 'orden_compra', extraction_id: 'ext-nuevo' }
    })

    const { container, queryClient } = renderConQueryClient(<FormCard />)
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [archivo('nuevo.pdf'), archivo('repetido.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await screen.findByRole('button', { name: /ver extracción existente/i })
    expect(screen.getByText(/^nuevo\.pdf/).closest('li')).toHaveTextContent(/procesando en segundo plano/i)
    // Al menos un archivo del lote se aceptó -- vale la pena invalidar para
    // que "Cargas recientes" muestre la fila nueva de una.
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['documentos-recientes'] })
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('si ningún archivo se procesó (todos duplicados) no invalida "Cargas recientes"', async () => {
    vi.mocked(procesarDocumento).mockRejectedValue(
      new ApiError('Este documento ya fue procesado', 409, { extraction_id: 'ext-existente' }),
    )

    const { container, queryClient } = renderConQueryClient(<FormCard />)
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [archivo('repetido.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await screen.findByRole('button', { name: /ver extracción existente/i })
    expect(invalidateSpy).not.toHaveBeenCalled()
  })
})

// carga-asincrona T2 -- /procesar ahora responde 202 apenas termina el upload
// (el robot corre en background). Ya no tiene sentido esperar a que aparezca
// el documento nuevo ni auto-navegar a validación: el usuario se entera del
// resultado por el status en "Cargas recientes" (RecentCard).
describe('FormCard — confirmación asincrónica, sin auto-navegación (carga-asincrona T2)', () => {
  it('1 archivo tipo="ordenes" exitoso: no navega, muestra confirmación y resetea el formulario', async () => {
    vi.mocked(procesarDocumento).mockResolvedValue({
      ok: true,
      tipo: 'orden_compra',
      extraction_id: 'ext-nueva-1',
    })

    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [archivo('a.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() =>
      expect(screen.getByText(/^a\.pdf/).closest('li')).toHaveTextContent(/procesando en segundo plano/i),
    )
    expect(navigateMock).not.toHaveBeenCalled()
    // Formulario reseteado -- vuelve a mostrar el placeholder del dropzone.
    expect(screen.getByText(/seleccionar archivo/i)).toBeInTheDocument()
    // `input.value` no sirve como aserción acá: jsdom no refleja el
    // `fileInputRef.current.value = ''` del componente sobre `input` (la
    // misma referencia de nodo), así que la comparación nunca podía fallar.
    // El reset real se observa en el estado derivado: sin archivos
    // seleccionados, "Procesar archivo(s)" vuelve a estar deshabilitado.
    expect(screen.getByRole('button', { name: /procesar archivo/i })).toBeDisabled()
  })

  it('N archivos agrupados (mismo grupoId), TODOS exitosos: no navega y reporta cada uno', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('33333333-3333-4333-8333-333333333333')
    vi.mocked(procesarDocumento).mockResolvedValue({ ok: true, tipo: 'orden_compra' })

    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, {
      target: { files: [archivo('a.pdf'), archivo('b.pdf'), archivo('c.pdf')] },
    })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() => expect(procesarDocumento).toHaveBeenCalledTimes(3))
    await waitFor(() =>
      expect(screen.getByText(/^a\.pdf/).closest('li')).toHaveTextContent(/procesando en segundo plano/i),
    )
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('si UNO de los N falla, se queda en la pantalla de carga con el error por archivo (y no navega)', async () => {
    vi.spyOn(crypto, 'randomUUID').mockReturnValue('44444444-4444-4444-8444-444444444444')
    vi.mocked(procesarDocumento).mockImplementation(async ({ archivo: file }) => {
      if (file.name === 'duplicado.pdf') {
        throw new Error('Ya existe un documento con este contenido (409)')
      }
      return { ok: true, tipo: 'orden_compra' }
    })

    const { container } = renderConQueryClient(<FormCard />)
    abrirTabOrdenes()

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, {
      target: { files: [archivo('a.pdf'), archivo('duplicado.pdf'), archivo('c.pdf')] },
    })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() =>
      expect(screen.getByText(/duplicado\.pdf/).closest('li')).toHaveTextContent(/409/),
    )
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('tipo="licitaciones" exitoso: no navega (nunca lo hizo, ningún tipo auto-navega ahora)', async () => {
    vi.mocked(procesarDocumento).mockResolvedValue({ ok: true, tipo: 'licitacion' })

    const { container } = renderConQueryClient(<FormCard />)
    elegirTipo('Licitación / Directa')

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [archivo('a.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() => expect(procesarDocumento).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(screen.getByText(/^a\.pdf/).closest('li')).toHaveTextContent(/procesando en segundo plano/i),
    )
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('un lote exitoso invalida la query "documentos-recientes" para refrescar RecentCard', async () => {
    vi.mocked(procesarDocumento).mockResolvedValue({ ok: true, tipo: 'orden_compra' })

    const { container, queryClient } = renderConQueryClient(<FormCard />)
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
    elegirTipo('Licitación / Directa')

    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [archivo('a.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() => expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['documentos-recientes'] }))
  })
})

describe('FormCard — un solo tipo "Licitación / Directa" (presupuestador-v1 T2a)', () => {
  it('ofrece "Licitación / Directa", "Comparativa" y "Orden de compra", sin elegir la clase', () => {
    renderConQueryClient(<FormCard />)

    const tipos = screen.getAllByRole('button', { pressed: false }).map((boton) => boton.textContent)
    expect(tipos).toEqual(['Licitación / Directa', 'Comparativa', 'Orden de compra'])
    expect(screen.queryByRole('button', { name: '1 · Directa' })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: '2 · Licitación' })).not.toBeInTheDocument()
  })

  it('con "Licitación / Directa" no pide cliente y envía tipo="licitaciones" con un solo archivo', async () => {
    vi.mocked(procesarDocumento).mockResolvedValue({ ok: true, tipo: 'licitaciones' })

    const { container } = renderConQueryClient(<FormCard />)
    elegirTipo('Licitación / Directa')

    expect(screen.queryByRole('combobox')).not.toBeInTheDocument()
    expect(screen.queryByText(/cliente/i)).not.toBeInTheDocument()
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(input.multiple).toBe(false)
    expect(input.accept).toBe('.pdf,.jpg,.jpeg,.png,.xls,.xlsx')
    fireEvent.change(input, { target: { files: [archivo('a.pdf'), archivo('b.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() => expect(procesarDocumento).toHaveBeenCalledTimes(1))
    expect(vi.mocked(procesarDocumento).mock.calls[0][0]).toMatchObject({
      tipo: 'licitaciones',
      clienteId: undefined,
      grupoId: undefined,
    })
    expect(vi.mocked(procesarDocumento).mock.calls[0][0].archivo.name).toBe('a.pdf')
  })

  it('la comparativa sigue ofreciendo el cliente y lo envía', async () => {
    vi.mocked(listarClientes).mockResolvedValue([{ id: 'cli-1', nombre: 'Hospital Sayago' }])
    vi.mocked(procesarDocumento).mockResolvedValue({ ok: true, tipo: 'comparativas' })

    const { container } = renderConQueryClient(<FormCard />)
    elegirTipo('Comparativa')
    await screen.findByRole('option', { name: 'Hospital Sayago' })
    fireEvent.change(screen.getByRole('combobox'), { target: { value: 'cli-1' } })
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [archivo('c.pdf')] } })
    fireEvent.click(screen.getByRole('button', { name: /procesar/i }))

    await waitFor(() => expect(procesarDocumento).toHaveBeenCalledTimes(1))
    expect(vi.mocked(procesarDocumento).mock.calls[0][0]).toMatchObject({
      tipo: 'comparativas',
      clienteId: 'cli-1',
    })
  })
})

describe('FormCard — el tipo se elige siempre (presupuestador-v1 T1b)', () => {
  it('sin elegir tipo no hay ninguno marcado y no se puede cargar ni procesar', () => {
    const { container } = renderConQueryClient(<FormCard />)

    for (const label of ['Licitación / Directa', 'Comparativa', 'Orden de compra']) {
      expect(screen.getByRole('button', { name: label })).toHaveAttribute('aria-pressed', 'false')
    }
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(input).toBeDisabled()
    expect(screen.getByText('Elegí el tipo de documento para continuar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /procesar/i })).toBeDisabled()
  })

  it('arrastrar un archivo sin elegir tipo no lo carga', () => {
    renderConQueryClient(<FormCard />)
    const zona = screen.getByText('Elegí el tipo de documento para continuar').closest('label') as HTMLElement

    fireEvent.drop(zona, { dataTransfer: { files: [archivo('a.pdf')] } })

    expect(screen.queryByText('a.pdf')).not.toBeInTheDocument()
    expect(screen.getByText('Elegí el tipo de documento para continuar')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /procesar/i })).toBeDisabled()
    expect(procesarDocumento).not.toHaveBeenCalled()
  })

  it('arrastrar un archivo después de elegir tipo sí lo carga', () => {
    renderConQueryClient(<FormCard />)
    elegirTipo('Licitación / Directa')
    const zona = screen.getByText('Seleccionar archivo').closest('label') as HTMLElement

    fireEvent.drop(zona, { dataTransfer: { files: [archivo('a.pdf')] } })

    expect(screen.getByText('a.pdf')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /procesar/i })).toBeEnabled()
  })

  it('al elegir un tipo queda marcado y habilita la carga', () => {
    const { container } = renderConQueryClient(<FormCard />)
    elegirTipo('Licitación / Directa')

    expect(screen.getByRole('button', { name: 'Licitación / Directa' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: 'Comparativa' })).toHaveAttribute('aria-pressed', 'false')
    const input = container.querySelector('input[type="file"]') as HTMLInputElement
    expect(input).toBeEnabled()
    expect(screen.queryByText('Elegí el tipo de documento para continuar')).not.toBeInTheDocument()
  })
})
