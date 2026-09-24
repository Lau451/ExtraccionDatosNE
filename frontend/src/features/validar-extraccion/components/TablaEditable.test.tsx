import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { CampoConfig, FilaEditable } from '../useFilasEditables'
import { TablaEditable } from './TablaEditable'

const CAMPOS_ORDEN_COMPRA: CampoConfig[] = [
  { campo: 'numero_renglon', tipo: 'texto-opcional', editable: false },
  { campo: 'descripcion', tipo: 'texto' },
  { campo: 'precio_unitario', tipo: 'decimal-positivo' },
  { campo: '_archivo', tipo: 'texto-opcional', editable: false },
]

function filaOrdenCompra(overrides: Partial<FilaEditable> = {}): FilaEditable {
  return {
    _id: 'original-0',
    _nueva: false,
    _borrada: false,
    numero_renglon: '1',
    descripcion: 'Ibuprofeno',
    precio_unitario: '1250,00',
    _archivo: 'oc-hospital.pdf',
    ...overrides,
  }
}

function props(filas: FilaEditable[]) {
  return {
    campos: CAMPOS_ORDEN_COMPRA,
    filas,
    erroresPorCelda: {},
    onActualizarCelda: vi.fn(),
    onRevertirCelda: vi.fn(),
    onBorrarFila: vi.fn(),
    onAgregarFila: vi.fn(),
  }
}

const CAMPOS_ORDEN_COMPRA_CON_IMPORTE: CampoConfig[] = [
  { campo: 'descripcion', tipo: 'texto' },
  { campo: 'cantidad', tipo: 'decimal' },
  { campo: 'precio_unitario', tipo: 'decimal-positivo' },
  { campo: 'importe_total', tipo: 'texto-opcional', editable: false },
]

function filaOrdenCompraConImporte(overrides: Partial<FilaEditable> = {}): FilaEditable {
  return {
    _id: 'original-0',
    _nueva: false,
    _borrada: false,
    descripcion: 'Ibuprofeno',
    cantidad: '100',
    precio_unitario: '1250,00',
    importe_total: '125000,00',
    ...overrides,
  }
}

describe('TablaEditable — importe_total (T2, control no bloqueante cantidad × precio_unitario)', () => {
  it('se muestra como columna de solo lectura, sin abrir CeldaEditable', () => {
    render(<TablaEditable {...props([filaOrdenCompraConImporte()])} campos={CAMPOS_ORDEN_COMPRA_CON_IMPORTE} />)

    expect(screen.getByTestId('original-0:importe_total')).toHaveTextContent('125000,00')
    expect(screen.queryByRole('textbox', { name: /importe total fila 1/i })).not.toBeInTheDocument()
  })

  it('sin advertencia cuando importe_total coincide con cantidad × precio_unitario', () => {
    render(<TablaEditable {...props([filaOrdenCompraConImporte()])} campos={CAMPOS_ORDEN_COMPRA_CON_IMPORTE} />)

    expect(screen.queryByText(/no coincide/i)).not.toBeInTheDocument()
  })

  it('advertencia (no bloqueante) cuando importe_total no coincide con cantidad × precio_unitario', () => {
    render(
      <TablaEditable
        {...props([filaOrdenCompraConImporte({ importe_total: '999,00' })])}
        campos={CAMPOS_ORDEN_COMPRA_CON_IMPORTE}
      />,
    )

    const aviso = screen.getByText(/no coincide/i)
    expect(aviso).toBeInTheDocument()
    expect(aviso).toHaveClass('text-amber-600')
  })

  it('sin advertencia cuando importe_total viene vacío', () => {
    render(
      <TablaEditable
        {...props([filaOrdenCompraConImporte({ importe_total: '' })])}
        campos={CAMPOS_ORDEN_COMPRA_CON_IMPORTE}
      />,
    )

    expect(screen.queryByText(/no coincide/i)).not.toBeInTheDocument()
  })
})

describe('TablaEditable — columnas de referencia no editables (D13.1, Phase 8)', () => {
  it('numero_renglon/_archivo se muestran pero no abren un CeldaEditable (sin <input>)', () => {
    render(<TablaEditable {...props([filaOrdenCompra()])} />)

    // Las columnas editables sí exponen un textbox real.
    expect(screen.getByRole('textbox', { name: /descripción fila 1/i })).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /precio unitario fila 1/i })).toBeInTheDocument()

    // Las columnas de referencia NO exponen ningún input -- un click no debe
    // poder editarlas.
    expect(screen.queryByRole('textbox', { name: /n° renglón.*fila 1/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('textbox', { name: /archivo fila 1/i })).not.toBeInTheDocument()

    // El valor sigue visible como texto plano.
    expect(screen.getByTestId('original-0:numero_renglon')).toHaveTextContent('1')
    expect(screen.getByTestId('original-0:_archivo')).toHaveTextContent('oc-hospital.pdf')
  })

  it('un click sobre la celda de referencia no dispara onActualizarCelda', () => {
    const propiedades = props([filaOrdenCompra()])
    render(<TablaEditable {...propiedades} />)

    fireEvent.click(screen.getByTestId('original-0:numero_renglon'))

    expect(propiedades.onActualizarCelda).not.toHaveBeenCalled()
  })

  it('numero_renglon se renderiza vacío cuando el documento no lo declaró (C10)', () => {
    render(<TablaEditable {...props([filaOrdenCompra({ numero_renglon: '' })])} />)

    expect(screen.getByTestId('original-0:numero_renglon')).toHaveTextContent('')
  })
})
