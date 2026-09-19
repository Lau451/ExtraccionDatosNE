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
