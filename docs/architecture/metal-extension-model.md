# Metal Extension Model

## Principle

Use one shared product core plus per-metal adapters.

## Shared Core

- web app
- runtime bundle loading
- payload assembly conventions
- publishing and bundle validation
- baseline and optimization pipeline facades

## Metal-Specific Extension Points

Each metal can define:

- `spec.py`: metadata and support level
- `stages.py`: stage ordering
- `transforms.py`: metal-specific normalization
- `validators.py`: metal-specific validation
- `payloads.py`: metal-specific payload contract notes

## Current Support Status

- Full support: Lithium, Nickel, Cobalt
- Partial skeleton: Manganese, Graphite, Phosphorus

## Why This Matters

- avoids six parallel systems
- keeps future metals additive instead of invasive
- makes incomplete support explicit instead of implicit
