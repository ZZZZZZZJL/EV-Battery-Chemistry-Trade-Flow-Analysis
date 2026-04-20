from __future__ import annotations

import json
import sys

import numpy as np
from scipy.optimize import linprog


def main() -> int:
    payload = json.load(sys.stdin)
    c = np.asarray(payload["c"], dtype=float)
    a_eq = np.asarray(payload["A_eq"], dtype=float) if payload.get("A_eq") else None
    b_eq = np.asarray(payload["b_eq"], dtype=float) if payload.get("b_eq") else None
    a_ub = np.asarray(payload["A_ub"], dtype=float) if payload.get("A_ub") else None
    b_ub = np.asarray(payload["b_ub"], dtype=float) if payload.get("b_ub") else None
    bounds = [
        (
            None if lower is None else float(lower),
            None if upper is None else float(upper),
        )
        for lower, upper in payload["bounds"]
    ]
    result = linprog(
        c=c,
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
    )
    json.dump(
        {
            "success": bool(result.success),
            "status": int(result.status),
            "message": str(result.message),
            "x": [] if result.x is None else [float(value) for value in result.x.tolist()],
        },
        sys.stdout,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
