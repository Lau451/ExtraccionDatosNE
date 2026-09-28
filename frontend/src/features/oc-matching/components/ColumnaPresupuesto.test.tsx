import { fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { RenglonOrdenCompra, RenglonPresupuesto } from '@/lib/api/ocMatching'
import { ColumnaPresupuesto } from './ColumnaPresupuesto'

function presupuesto(overrides: Partial<RenglonPresupuesto> = {}): RenglonPresupuesto {
  return {
    presupuesto_item_id: 'pi-1',
    item_proceso_id: 'ip-1',
    numero_renglon: 1,
    descripcion: 'Ibuprofeno 400mg x 20',
    cantidad_ofertada: 10,
    precio_unitario: 1250,
    producto_id: null,
    renglones_oc_vinculados: 0,
    renglones_oc_vinculados_otras_oc: 0,
    cantidad_vinculada: 0,
    ...overrides,
  }
}

function ordenCompra(overrides: Partial<RenglonOrdenCompra> = {}): RenglonOrdenCompra {
  return {
    oc_item_id: 'item-1',
    numero_renglon: 1,
    descripcion: 'Ibuprofeno 400mg x 20',
    cantidad: 10,
    precio_unitario: 1250,
    producto_id: null,
    estado: 'pendiente',
    presupuesto_item_id: null,
    vinculo_origen: null,
    candidatos: [],
    ...overrides,
  }
}

function renderColumna(props: Partial<Parameters<typeof ColumnaPresupuesto>[0]> = {}) {
  const onVincularManual = vi.fn()
  render(
    <ColumnaPresupuesto
      renglones={[]}
      renglonOcSeleccionado={null}
      isPending={false}
      onVincularManual={onVincularManual}
      {...props}
    />,
  )
  return { onVincularManual }
}

describe('ColumnaPresupuesto — número de renglón', () => {
  it('muestra el número de renglón del presupuesto en cada fila', () => {
    renderColumna({
      renglones: [
        presupuesto({ presupuesto_item_id: 'pi-1', numero_renglon: 38, descripcion: 'Lacosamida 100 mg' }),
        presupuesto({ presupuesto_item_id: 'pi-2', numero_renglon: 7, descripcion: 'Cefalexina 500 mg' }),
      ],
    })

    const filas = screen.getAllByRole('listitem')
    expect(filas[0]).toHaveTextContent('Renglón 38')
    expect(filas[1]).toHaveTextContent('Renglón 7')
  })
})

describe('ColumnaPresupuesto — búsqueda y filtro (spec oc-presupuesto-vinculacion, T2)', () => {
  it('filtra por texto de la descripción, ignorando acentos y mayúsculas', () => {
    renderColumna({
      renglones: [
        presupuesto({ presupuesto_item_id: 'pi-1', descripcion: 'Ibuprofeno 400mg x 20' }),
        presupuesto({ presupuesto_item_id: 'pi-2', descripcion: 'Paracetamol 500mg x 10' }),
      ],
    })

    fireEvent.change(screen.getByLabelText(/buscar en el presupuesto/i), {
      target: { value: 'IBUPROFENO' },
    })

    expect(screen.getByText('Ibuprofeno 400mg x 20')).toBeInTheDocument()
    expect(screen.queryByText('Paracetamol 500mg x 10')).not.toBeInTheDocument()
  })

  it('filtra por número de renglón exacto', () => {
    renderColumna({
      renglones: [
        presupuesto({ presupuesto_item_id: 'pi-1', numero_renglon: 3, descripcion: 'Ibuprofeno' }),
        presupuesto({ presupuesto_item_id: 'pi-2', numero_renglon: 12, descripcion: 'Paracetamol' }),
      ],
    })

    fireEvent.change(screen.getByLabelText(/buscar en el presupuesto/i), { target: { value: '12' } })

    expect(screen.getByText('Paracetamol')).toBeInTheDocument()
    expect(screen.queryByText('Ibuprofeno')).not.toBeInTheDocument()
  })

  it('"Solo candidatos" está deshabilitado sin selección de renglón de OC', () => {
    renderColumna({
      renglones: [presupuesto({ presupuesto_item_id: 'pi-1', descripcion: 'Ibuprofeno' })],
      renglonOcSeleccionado: null,
    })

    expect(screen.getByRole('checkbox', { name: /solo candidatos/i })).toBeDisabled()
  })

  it('con un renglón de OC seleccionado, "Solo candidatos" filtra a los que son candidatos de ese renglón', () => {
    const seleccionado = ordenCompra({
      candidatos: [{ presupuesto_item_id: 'pi-1', similitud: null }],
    })

    renderColumna({
      renglones: [
        presupuesto({ presupuesto_item_id: 'pi-1', descripcion: 'Ibuprofeno' }),
        presupuesto({ presupuesto_item_id: 'pi-2', descripcion: 'Paracetamol' }),
      ],
      renglonOcSeleccionado: seleccionado,
    })

    const toggle = screen.getByRole('checkbox', { name: /solo candidatos/i })
    expect(toggle).not.toBeDisabled()

    fireEvent.click(toggle)

    expect(screen.getByText('Ibuprofeno')).toBeInTheDocument()
    expect(screen.queryByText('Paracetamol')).not.toBeInTheDocument()
  })
})

describe('ColumnaPresupuesto — scroll al candidato (spec oc-presupuesto-vinculacion, T3)', () => {
  // La lista del presupuesto tiene su propio scroll: llevar el candidato a la
  // vista mueve SOLO esa lista (scrollTo sobre el contenedor), nunca la página
  // (scrollIntoView desplaza todos los ancestros y saca de la vista la OC).
  // jsdom no implementa ninguno de los dos ni calcula layout: se mockean
  // scrollTo/scrollIntoView y offsetTop, y se restauran después de cada test.
  const scrollToOriginal = Element.prototype.scrollTo
  const scrollIntoViewOriginal = Element.prototype.scrollIntoView
  const offsetTopOriginal = Object.getOwnPropertyDescriptor(HTMLElement.prototype, 'offsetTop')
  let scrollToMock: ReturnType<typeof vi.fn>
  let scrollIntoViewMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    scrollToMock = vi.fn()
    scrollIntoViewMock = vi.fn()
    Element.prototype.scrollTo = scrollToMock as unknown as typeof Element.prototype.scrollTo
    Element.prototype.scrollIntoView = scrollIntoViewMock
    Object.defineProperty(HTMLElement.prototype, 'offsetTop', {
      configurable: true,
      get(this: HTMLElement) {
        return this.textContent?.includes('Paracetamol') && this.getAttribute('role') === 'listitem'
          ? 240
          : 0
      },
    })
  })

  afterEach(() => {
    Element.prototype.scrollTo = scrollToOriginal
    Element.prototype.scrollIntoView = scrollIntoViewOriginal
    if (offsetTopOriginal) Object.defineProperty(HTMLElement.prototype, 'offsetTop', offsetTopOriginal)
  })

  const renglones = [
    presupuesto({ presupuesto_item_id: 'pi-1', descripcion: 'Ibuprofeno' }),
    presupuesto({ presupuesto_item_id: 'pi-2', descripcion: 'Paracetamol' }),
  ]

  it('al seleccionar un renglón de OC, desplaza solo la lista del presupuesto hasta su primer candidato', () => {
    const { rerender } = render(
      <ColumnaPresupuesto
        renglones={renglones}
        renglonOcSeleccionado={null}
        isPending={false}
        onVincularManual={vi.fn()}
      />,
    )
    expect(scrollToMock).not.toHaveBeenCalled()

    rerender(
      <ColumnaPresupuesto
        renglones={renglones}
        renglonOcSeleccionado={ordenCompra({
          candidatos: [{ presupuesto_item_id: 'pi-2', similitud: null }],
        })}
        isPending={false}
        onVincularManual={vi.fn()}
      />,
    )

    expect(scrollToMock).toHaveBeenCalledTimes(1)
    expect(scrollToMock.mock.contexts[0]).toBe(screen.getByRole('list'))
    expect(scrollToMock).toHaveBeenCalledWith(expect.objectContaining({ top: 240 }))
    expect(scrollIntoViewMock).not.toHaveBeenCalled()
  })

  it('no vuelve a hacer scroll si llega un objeto nuevo del mismo renglón de OC (p. ej. tras confirmar otro renglón)', () => {
    const seleccionado = () =>
      ordenCompra({ candidatos: [{ presupuesto_item_id: 'pi-2', similitud: null }] })

    const { rerender } = render(
      <ColumnaPresupuesto
        renglones={renglones}
        renglonOcSeleccionado={seleccionado()}
        isPending={false}
        onVincularManual={vi.fn()}
      />,
    )
    expect(scrollToMock).toHaveBeenCalledTimes(1)

    rerender(
      <ColumnaPresupuesto
        renglones={[...renglones]}
        renglonOcSeleccionado={seleccionado()}
        isPending={false}
        onVincularManual={vi.fn()}
      />,
    )

    expect(scrollToMock).toHaveBeenCalledTimes(1)
  })

  it('sin candidatos para el renglón seleccionado, no intenta hacer scroll', () => {
    const { rerender } = render(
      <ColumnaPresupuesto
        renglones={renglones}
        renglonOcSeleccionado={null}
        isPending={false}
        onVincularManual={vi.fn()}
      />,
    )

    rerender(
      <ColumnaPresupuesto
        renglones={renglones}
        renglonOcSeleccionado={ordenCompra({ candidatos: [] })}
        isPending={false}
        onVincularManual={vi.fn()}
      />,
    )

    expect(scrollToMock).not.toHaveBeenCalled()
    expect(scrollIntoViewMock).not.toHaveBeenCalled()
  })
})

describe('ColumnaPresupuesto — vínculo manual (spec oc-presupuesto-vinculacion, T4)', () => {
  it('con un renglón de OC pendiente seleccionado, ofrece vincular manualmente cada renglón del presupuesto', () => {
    const seleccionado = ordenCompra({
      oc_item_id: 'item-9',
      numero_renglon: 4,
      estado: 'pendiente',
      candidatos: [],
    })

    const { onVincularManual } = renderColumna({
      renglones: [presupuesto({ presupuesto_item_id: 'pi-1', descripcion: 'Ibuprofeno' })],
      renglonOcSeleccionado: seleccionado,
    })

    const boton = screen.getByRole('button', { name: /vincular al renglón 4 de la oc/i })
    fireEvent.click(boton)

    expect(onVincularManual).toHaveBeenCalledWith('item-9', 'pi-1')
  })

  it('sin un renglón de OC pendiente seleccionado, no ofrece el botón de vínculo manual', () => {
    renderColumna({
      renglones: [presupuesto({ presupuesto_item_id: 'pi-1', descripcion: 'Ibuprofeno' })],
      renglonOcSeleccionado: null,
    })

    expect(screen.queryByRole('button', { name: /vincular al renglón/i })).not.toBeInTheDocument()
  })

  it('con un renglón de OC ya confirmado seleccionado, no ofrece el botón de vínculo manual', () => {
    renderColumna({
      renglones: [presupuesto({ presupuesto_item_id: 'pi-1', descripcion: 'Ibuprofeno' })],
      renglonOcSeleccionado: ordenCompra({ estado: 'confirmado', candidatos: [] }),
    })

    expect(screen.queryByRole('button', { name: /vincular al renglón/i })).not.toBeInTheDocument()
  })
})
