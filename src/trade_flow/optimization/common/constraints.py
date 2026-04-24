"""Constraint helpers shared by optimization pipelines."""


def default_bounds() -> dict[str, tuple[float, float]]:
    return {"coefficient": (0.0, 5.0)}
