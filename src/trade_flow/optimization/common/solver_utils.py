"""Solver utility helpers for optimization wrappers."""


def solver_backend_name(explicit_backend: str | None = None) -> str:
    return explicit_backend or "scipy"
