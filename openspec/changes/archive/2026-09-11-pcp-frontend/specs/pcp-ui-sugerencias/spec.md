# PCP UI Sugerencias Specification

## Purpose

Show the read-only quantity-grouping and recent-price suggestions as a separate panel inside the
renglón detail screen, backed by the `sugerencias` router.

## Requirements

### Requirement: Suggestions Panel Inside Renglón Detail

The system MUST render quantity-grouping and recent-price suggestions in a dedicated panel inside
the renglón detail view, separate from the product/supplier context, and MUST render this panel as
read-only with no action that modifies PCP data.

#### Scenario: Quantity-grouping suggestion is shown

- GIVEN the same article appears as an open renglón in two PCPs nearing their requested delivery
  date
- WHEN the user opens either renglón's detail
- THEN the suggestions panel shows a joint-quote suggestion with the aggregated quantity

#### Scenario: Recent-price suggestion is shown

- GIVEN a still-valid `precios_proveedor` row exists for the renglón's article
- WHEN the user opens that renglón's detail
- THEN the suggestions panel shows the supplier, date, `mantenimiento_hasta`, and quantity band as
  a reference

#### Scenario: Suggestions panel is visible to every read role

- GIVEN a user with any of `superadmin`, `admin`, `gerencia`, `compras`
- WHEN they open a renglón detail
- THEN the suggestions panel renders without requiring a write role

#### Scenario: No suggestion action mutates PCP data

- GIVEN the suggestions panel is showing a suggestion
- WHEN the user views it
- THEN no control in the panel calls a PCP write endpoint; acting on a suggestion requires the
  user to use the renglones/consultas screens manually
