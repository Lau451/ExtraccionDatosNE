import { useState } from 'react'
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CabeceraOrdenCompra } from './CabeceraOrdenCompra'

/** Arnés mínimo (mismo patrón que OrdenCompraSelector.test.tsx): el botón
 * "Confirmar OC" real (Phase 8) se deshabilita según el `bloqueado` que
 * reporta este componente vía `onCambio` -- acá se reproduce sin necesitar
 * el wiring completo. */
function ArnesConBotonConfirmar({ filas }: { filas: Record<string, string>[] }) {
  const [bloqueado, setBloqueado] = useState(true)
  const [observacionesReportadas, setObservacionesReportadas] = useState('')
  const [cantidadEntregasReportada, setCantidadEntregasReportada] = useState('')
  return (
    <div>
      <CabeceraOrdenCompra
        filas={filas}
        onCambio={(cabecera, bloqueadoActual) => {
          setBloqueado(bloqueadoActual)
          setObservacionesReportadas(cabecera.observaciones)
          setCantidadEntregasReportada(cabecera.cantidad_entregas)
        }}
      />
      <button type="button" disabled={bloqueado}>
        Confirmar OC
      </button>
      <p data-testid="observaciones-reportadas">{observacionesReportadas}</p>
      <p data-testid="cantidad-entregas-reportada">{cantidadEntregasReportada}</p>
    </div>
  )
}

const MIEMBRO_A = {
  _extraction_id: 'ext-a',
  numero_oc: '1001',
  razon_social_cliente: 'Hospital Central',
  cuit_cliente: '30-11111111-1',
  fecha_emision: '2026-01-10',
  direccion_entrega: 'Calle Falsa 123',
  cantidad_entregas: '2',
}

const MIEMBRO_B_NUMERO_OC_DISTINTO = {
  ...MIEMBRO_A,
  _extraction_id: 'ext-b',
  numero_oc: '1002',
}

const MIEMBRO_B_OTROS_CAMPOS_DISTINTOS = {
  ...MIEMBRO_A,
  _extraction_id: 'ext-b',
  razon_social_cliente: 'Hospital Central S.A.',
  fecha_emision: '2026-01-15',
  direccion_entrega: 'Otra Dirección 456',
}

const MIEMBRO_A_CON_OBSERVACIONES = { ...MIEMBRO_A, observaciones: 'Entregar en depósito' }
const MIEMBRO_B_OBSERVACIONES_DISTINTAS = {
  ...MIEMBRO_A,
  _extraction_id: 'ext-b',
  observaciones: 'Coordinar con portería',
}

describe('CabeceraOrdenCompra (D13.1)', () => {
  it('numero_oc en desacuerdo entre miembros: campo en rojo y "Confirmar OC" deshabilitado', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A, MIEMBRO_B_NUMERO_OC_DISTINTO]} />)

    const input = screen.getByLabelText(/número de oc/i)
    expect(input).toHaveClass('border-red-500')
    expect(screen.getByRole('button', { name: /confirmar oc/i })).toBeDisabled()
  })

  it('editar numero_oc a un valor único habilita "Confirmar OC"', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A, MIEMBRO_B_NUMERO_OC_DISTINTO]} />)

    expect(screen.getByRole('button', { name: /confirmar oc/i })).toBeDisabled()

    // Distinto de los dos valores declarados ("1001"/"1002") Y del valor que
    // ya muestra el input por empate (D13.1 -- primer miembro gana), para no
    // pisar el "gotcha" de React con inputs controlados: si `fireEvent.change`
    // manda el mismo valor que ya tiene el nodo, React no dispara `onChange`.
    fireEvent.change(screen.getByLabelText(/número de oc/i), { target: { value: '9999' } })

    expect(screen.getByRole('button', { name: /confirmar oc/i })).not.toBeDisabled()
  })

  it('desacuerdo en razón social / fecha de emisión / dirección de entrega muestra aviso pero no bloquea', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A, MIEMBRO_B_OTROS_CAMPOS_DISTINTOS]} />)

    expect(screen.getByRole('button', { name: /confirmar oc/i })).not.toBeDisabled()
    const aviso = screen.getByText(/desacuerdo entre archivos del grupo/i)
    expect(aviso).toHaveTextContent(/razón social/i)
    expect(aviso).toHaveTextContent(/fecha de emisión/i)
    expect(aviso).toHaveTextContent(/dirección de entrega/i)
  })

  it('sin desacuerdo entre miembros: sin aviso y "Confirmar OC" habilitado de entrada', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A, { ...MIEMBRO_A, _extraction_id: 'ext-b' }]} />)

    expect(screen.getByRole('button', { name: /confirmar oc/i })).not.toBeDisabled()
    expect(screen.queryByText(/desacuerdo/i)).not.toBeInTheDocument()
  })
})

describe('CabeceraOrdenCompra — observaciones (T2)', () => {
  it('precarga el textarea "Observaciones" con el valor más frecuente entre miembros', () => {
    render(
      <ArnesConBotonConfirmar
        filas={[MIEMBRO_A_CON_OBSERVACIONES, { ...MIEMBRO_A_CON_OBSERVACIONES, _extraction_id: 'ext-b' }]}
      />,
    )

    expect(screen.getByLabelText(/observaciones/i)).toHaveValue('Entregar en depósito')
  })

  it('editar el textarea reporta el nuevo valor vía onCambio', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A_CON_OBSERVACIONES]} />)

    fireEvent.change(screen.getByLabelText(/observaciones/i), { target: { value: 'Coordinar horario' } })

    expect(screen.getByTestId('observaciones-reportadas')).toHaveTextContent('Coordinar horario')
  })

  it('desacuerdo en observaciones entre miembros aparece en el aviso, pero no bloquea', () => {
    render(
      <ArnesConBotonConfirmar filas={[MIEMBRO_A_CON_OBSERVACIONES, MIEMBRO_B_OBSERVACIONES_DISTINTAS]} />,
    )

    expect(screen.getByRole('button', { name: /confirmar oc/i })).not.toBeDisabled()
    expect(screen.getByText(/desacuerdo entre archivos del grupo/i)).toHaveTextContent(/observaciones/i)
  })

  it('sin observaciones en ningún miembro, el textarea arranca vacío', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A, { ...MIEMBRO_A, _extraction_id: 'ext-b' }]} />)

    expect(screen.getByLabelText(/observaciones/i)).toHaveValue('')
  })
})

// T2 (oc-entregas-planificacion) -- cantidad_entregas no tiene un campo
// editable propio (a diferencia de numero_oc/fecha/dirección/observaciones):
// se reporta vía onCambio con el mismo criterio "valor más frecuente entre
// miembros, empate -> primer miembro" que el resto de la cabecera (D13.1),
// para que ValidarExtraccionDetalle.tsx la mande en OrdenCompraOverride.
describe('CabeceraOrdenCompra — cantidad_entregas (T2 oc-entregas-planificacion)', () => {
  it('reporta vía onCambio el valor de cantidad_entregas declarado por el documento', () => {
    render(
      <ArnesConBotonConfirmar
        filas={[MIEMBRO_A, { ...MIEMBRO_A, _extraction_id: 'ext-b' }]}
      />,
    )

    expect(screen.getByTestId('cantidad-entregas-reportada')).toHaveTextContent('2')
  })

  it('desacuerdo entre miembros reporta el valor más frecuente y lo muestra en el aviso', () => {
    const miembroB = { ...MIEMBRO_A, _extraction_id: 'ext-b', cantidad_entregas: '3' }
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A, miembroB]} />)

    expect(screen.getByTestId('cantidad-entregas-reportada')).toHaveTextContent('2')
    expect(screen.getByText(/desacuerdo entre archivos del grupo/i)).toHaveTextContent(
      /cantidad de entregas/i,
    )
  })
})

// T3 (carga-asincrona) — direccion_entrega era un <input> de una sola línea:
// una dirección larga quedaba cortada. Pasa a ser un textarea auto-creciente
// que muestra la dirección completa.
describe('CabeceraOrdenCompra — dirección de entrega multilínea (T3)', () => {
  it('el campo "Dirección de entrega" es un textarea que muestra el valor completo', () => {
    const direccionLarga =
      'Avenida Presidente Roque Sáenz Peña 1234, Piso 8 Oficina B, Ciudad Autónoma de Buenos Aires'
    render(
      <ArnesConBotonConfirmar
        filas={[{ ...MIEMBRO_A, direccion_entrega: direccionLarga }]}
      />,
    )

    const campo = screen.getByLabelText(/dirección de entrega/i)
    expect(campo.tagName).toBe('TEXTAREA')
    expect(campo).toHaveValue(direccionLarga)
  })
})

// T3b (carga-asincrona) -- el textarea de T3 no manejaba Enter: un Enter real
// insertaba un salto de línea crudo en direccion_entrega. La dirección sigue
// siendo un único valor lógico (a diferencia de Observaciones, que sí es
// multilínea a propósito) hasta que T4 decida un formato real.
describe('CabeceraOrdenCompra — dirección de entrega es un valor único (T3b)', () => {
  it('Enter en el textarea de dirección no inserta un salto de línea', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A]} />)
    const campo = screen.getByLabelText(/dirección de entrega/i)

    const noFueCancelado = fireEvent.keyDown(campo, { key: 'Enter' })

    expect(noFueCancelado).toBe(false)
  })

  it('T1d: Enter mientras se compone con un IME no se bloquea (confirma la composición)', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A]} />)
    const campo = screen.getByLabelText(/dirección de entrega/i)

    const noFueCancelado = fireEvent.keyDown(campo, { key: 'Enter', isComposing: true })

    expect(noFueCancelado).toBe(true)
  })

  it('Enter que confirma una composición en Safari (isComposing=false, keyCode 229) tampoco se bloquea', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A]} />)
    const campo = screen.getByLabelText(/dirección de entrega/i)

    const noFueCancelado = fireEvent.keyDown(campo, { key: 'Enter', keyCode: 229 })

    expect(noFueCancelado).toBe(true)
  })

  it('un salto de línea que llega por otra vía (pegado, autocompletado) se normaliza a ", "', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A]} />)
    const campo = screen.getByLabelText(/dirección de entrega/i)

    fireEvent.change(campo, {
      target: { value: 'Calle Falsa 123\nPiso 4to\n\nDepto B' },
    })

    expect(campo).toHaveValue('Calle Falsa 123, Piso 4to, Depto B')
  })

  it('un valor sin saltos de línea no se altera', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A]} />)
    const campo = screen.getByLabelText(/dirección de entrega/i)

    fireEvent.change(campo, { target: { value: 'Calle Falsa 123' } })

    expect(campo).toHaveValue('Calle Falsa 123')
  })

  it('observaciones sigue permitiendo saltos de línea reales (a diferencia de dirección)', () => {
    render(<ArnesConBotonConfirmar filas={[MIEMBRO_A_CON_OBSERVACIONES]} />)
    const campo = screen.getByLabelText(/observaciones/i)

    fireEvent.change(campo, { target: { value: 'Línea 1\nLínea 2' } })

    expect(campo).toHaveValue('Línea 1\nLínea 2')
  })
})
