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

  it('las columnas de referencia envuelven el valor completo en vez de truncarlo (T3)', () => {
    const archivoLargo = 'orden-de-compra-hospital-central-septiembre-2026-version-final.pdf'
    render(<TablaEditable {...props([filaOrdenCompra({ _archivo: archivoLargo })])} />)

    const celda = screen.getByTestId('original-0:_archivo')
    expect(celda).toHaveTextContent(archivoLargo)
    expect(celda.className).not.toMatch(/truncate/)
    expect(celda.className).toMatch(/whitespace-pre-wrap|break-words/)
  })
})

// T3 (carga-asincrona) — la pantalla de validación se veía apretada:
// descripción se truncaba dentro de un <input> de una sola línea, las
// columnas numéricas no tenían ancho propio, y Borrar/Deshacer quedaba
// detrás del scroll horizontal.
describe('TablaEditable — layout ancho por columna (T3)', () => {
  const CAMPOS_OC_COMPLETOS: CampoConfig[] = [
    { campo: 'numero_renglon', tipo: 'texto-opcional', editable: false },
    { campo: 'descripcion', tipo: 'texto' },
    { campo: 'cantidad', tipo: 'decimal' },
    { campo: 'precio_unitario', tipo: 'decimal-positivo' },
    { campo: 'importe_total', tipo: 'texto-opcional', editable: false },
  ]

  function filaCompleta(overrides: Partial<FilaEditable> = {}): FilaEditable {
    return {
      _id: 'original-0',
      _nueva: false,
      _borrada: false,
      numero_renglon: '1',
      descripcion:
        'Amoxicilina 500mg comprimidos recubiertos, caja x 21 unidades, laboratorio nacional homologado',
      cantidad: '100',
      precio_unitario: '1250,00',
      importe_total: '125000,00',
      ...overrides,
    }
  }

  it('descripción se edita en un textarea multilínea que muestra el texto completo, sin truncar', () => {
    render(
      <TablaEditable {...props([filaCompleta()])} campos={CAMPOS_OC_COMPLETOS} />,
    )

    const campo = screen.getByRole('textbox', { name: /descripción fila 1/i })
    expect(campo.tagName).toBe('TEXTAREA')
    expect((campo as HTMLTextAreaElement).value).toBe(filaCompleta().descripcion)
  })

  it('Enter en la descripción (textarea) sigue moviendo el foco a la fila siguiente, sin insertar salto de línea', () => {
    render(
      <TablaEditable
        {...props([filaCompleta({ _id: 'original-0' }), filaCompleta({ _id: 'original-1' })])}
        campos={CAMPOS_OC_COMPLETOS}
      />,
    )

    const filaUno = screen.getByRole('textbox', { name: /descripción fila 1/i })
    const filaDos = screen.getByRole('textbox', { name: /descripción fila 2/i })

    // T1c/T3b: en jsdom, Enter nunca inserta un salto de línea en un textarea
    // por sí solo (no hay input nativo que simular), así que comparar el
    // `.value` antes/después no puede fallar aunque se saque el
    // `event.preventDefault()` real -- lo que sí se puede observar es que el
    // evento efectivamente se canceló: `fireEvent` devuelve `false` cuando
    // algún handler llamó `preventDefault()` (semántica de
    // `dispatchEvent` estándar).
    const noFueCancelado = fireEvent.keyDown(filaUno, { key: 'Enter' })

    expect(filaDos).toHaveFocus()
    expect(noFueCancelado).toBe(false)
  })

  it('cantidad/precio_unitario/importe_total quedan alineados a la derecha con tabular-nums', () => {
    render(
      <TablaEditable {...props([filaCompleta()])} campos={CAMPOS_OC_COMPLETOS} />,
    )

    const cantidad = screen.getByRole('textbox', { name: /cantidad fila 1/i })
    expect(cantidad.className).toMatch(/text-right/)
    expect(cantidad.className).toMatch(/tabular-nums/)

    const importe = screen.getByTestId('original-0:importe_total')
    expect(importe.className).toMatch(/text-right/)
    expect(importe.className).toMatch(/tabular-nums/)
  })

  it('la columna de acciones (Borrar/Deshacer) queda sticky al borde derecho', () => {
    render(<TablaEditable {...props([filaCompleta()])} campos={CAMPOS_OC_COMPLETOS} />)

    const boton = screen.getByRole('button', { name: /^borrar fila 1$/i })
    const celda = boton.closest('td')
    expect(celda?.className).toMatch(/sticky/)
    expect(celda?.className).toMatch(/right-0/)
  })
})
