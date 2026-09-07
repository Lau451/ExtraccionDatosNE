# PCP Renglones Specification

## Purpose

Manage the per-line detail of a PCP: the renglón anchored on stable process identity, its product and
supplier context, supplier selection for negotiation, and the origin discriminator that lets manual
selection, legacy import, and future automatic rules coexist without rework.

## Requirements

### Requirement: Renglón Identity Anchored on item_proceso_id

The system MUST identify every PCP renglón by `item_proceso_id` and MUST NOT reference
`presupuesto_items.id`, because `presupuesto_items` rows are deleted and reinserted on every
presupuesto regeneration.

#### Scenario: Renglón survives a presupuesto regeneration

- GIVEN a PCP renglón anchored on `item_proceso_id` I
- WHEN the originating presupuesto is regenerated, replacing its `presupuesto_items` rows
- THEN the PCP renglón still resolves to the same product and process context via I
- AND no PCP data is lost or orphaned

#### Scenario: Reject a renglón referencing presupuesto_items.id

- GIVEN a request to create a PCP renglón
- WHEN the request identifies the line only by `presupuesto_items.id`
- THEN the system rejects the request

### Requirement: Product and Supplier Context Display

The system MUST display, for each renglón, the associated product's identifying data and the list of
suppliers currently associated with that product.

#### Scenario: Open a renglón and see product context

- GIVEN a PCP renglón for a known product
- WHEN Compras opens that renglón's detail
- THEN the system shows the product's identifying data
- AND shows the suppliers currently catalogued for that product

### Requirement: Supplier Selection for Negotiation

The system MUST allow selecting one supplier, several suppliers, or all available suppliers for a
renglón as the negotiation targets.

#### Scenario: Select a single supplier

- GIVEN a renglón with three available suppliers
- WHEN Compras selects one supplier for negotiation
- THEN the system records that single supplier as the negotiation target for the renglón

#### Scenario: Select all available suppliers

- GIVEN a renglón with several available suppliers
- WHEN Compras selects "all available suppliers"
- THEN the system records every currently catalogued supplier as a negotiation target

### Requirement: Origen Discriminator on Renglón Selection

The system MUST tag every renglón selection with an `origen` value of `manual`, `regla`, or
`import_legado`, and MUST NOT allow a renglón without one of these values.

#### Scenario: Manual selection is tagged

- GIVEN Compras manually adds a renglón to a PCP
- WHEN the renglón is created
- THEN its `origen` is `manual`

#### Scenario: Legacy-imported selection is tagged

- GIVEN a renglón originates from the legacy PCP import
- WHEN the renglón is created
- THEN its `origen` is `import_legado`

#### Scenario: Future rule-based origin is representable without schema change

- GIVEN the `origen` column already accepts `regla` as a valid value
- WHEN an automatic rules engine is introduced later
- THEN it can tag its generated renglones as `origen = 'regla'` without any schema migration
