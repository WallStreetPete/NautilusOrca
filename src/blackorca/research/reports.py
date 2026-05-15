"""HTML report rendering for research artifacts.

Self-contained — no external CSS/JS frameworks. Output goes to
``data/reports/{name}.html`` by default.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl


def _df_to_html_table(df: pl.DataFrame, title: str = "") -> str:
    if df.is_empty():
        return f"<h3>{title}</h3><p><em>empty</em></p>"
    cols = "".join(f"<th>{c}</th>" for c in df.columns)
    rows = []
    for row in df.iter_rows():
        cells = "".join(f"<td>{c}</td>" for c in row)
        rows.append(f"<tr>{cells}</tr>")
    return f"<h3>{title}</h3><table><thead><tr>{cols}</tr></thead><tbody>{''.join(rows)}</tbody></table>"


def render_report(
    title: str,
    sections: dict[str, pl.DataFrame | str],
    out_path: str | Path,
) -> Path:
    parts = []
    for name, content in sections.items():
        if isinstance(content, pl.DataFrame):
            parts.append(_df_to_html_table(content, title=name))
        else:
            parts.append(f"<h3>{name}</h3>{content}")

    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 1080px; margin: 2rem auto; }}
h1 {{ font-weight: 600; }}
table {{ border-collapse: collapse; margin: 1rem 0; }}
th, td {{ border: 1px solid #ddd; padding: 0.3rem 0.6rem; font-size: 13px; }}
th {{ background: #f0f4f8; }}
</style></head><body>
<h1>{title}</h1>
{''.join(parts)}
</body></html>
"""
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p


__all__ = ["render_report"]
