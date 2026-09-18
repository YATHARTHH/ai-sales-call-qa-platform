# Dependency Direction Rules

This project enforces strict hexagonal / modular monolith boundaries. Circular dependencies and domain pollution are strictly prohibited.

## Dependency Hierarchy

```text
       ┌──────────────┐
       │    Domain    │ (Zero dependencies)
       └──────▲───────┘
              │
       ┌──────┴───────┐
       │  Evaluation  │ (Depends ONLY on Domain)
       └──────▲───────┘
              │
       ┌──────┴───────┐
       │ Application  │ (Depends on Domain, Contracts, Evaluation)
       └──────▲───────┘
              │
       ┌──────┴───────┐
       │Infrastructure│ (Implements Domain & Application Ports)
       └──────▲───────┘
              │
       ┌──────┴───────┐
       │ Apps (API/W) │ (Orchestrates Application & Infrastructure)
       └──────────────┘
```

## Enforced Invariants
1. `packages/domain` MUST NOT import `packages/infrastructure`, `apps`, `fastapi`, `sqlalchemy`, `redis`, `boto3`, or `openai`.
2. `packages/evaluation` MUST NOT import `packages/infrastructure` or `apps`.
3. `packages/application` MUST NOT import `packages/infrastructure` directly.
4. Violations are automatically caught by `pytest tests/arch/`.
