from __future__ import annotations

from .sankey_presenter import build_sankey_payload


def build_table_payload(
    *,
    metal: str,
    year: int,
    result_mode: str,
    table_view: str,
    cobalt_mode: str,
    access_mode: str,
) -> dict:
    payload = build_sankey_payload(
        metal=metal,
        year=year,
        result_mode=result_mode,
        table_view=table_view,
        theme="light",
        reference_qty=None,
        cobalt_mode=cobalt_mode,
        access_mode=access_mode,
    )
    return {
        "metadata": {
            "metal": metal,
            "year": year,
            "resultMode": result_mode,
            "tableView": table_view,
        },
        "tables": payload.get("tables", {}),
        "stageSummary": payload.get("stageSummary", []),
    }
