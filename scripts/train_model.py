"""CLI: train an ML model from the catalog."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Annotated

import typer
from rich.console import Console

from blackorca.data.catalog import Catalog
from blackorca.data.contracts import BarAggregation
from blackorca.ml.pipelines import PITPipeline
from blackorca.ml.train import train_model
from blackorca.strategies.examples.ml_signal import default_feature_stack

app = typer.Typer(no_args_is_help=True, add_completion=False)
console = Console()


@app.command()
def main(
    symbol: Annotated[str, typer.Option()] = "NVDA",
    years: Annotated[int, typer.Option()] = 5,
    name: Annotated[str, typer.Option()] = "default",
    framework: Annotated[str, typer.Option(help="lightgbm or ridge")] = "lightgbm",
    target_horizon: Annotated[int, typer.Option()] = 1,
    n_splits: Annotated[int, typer.Option()] = 5,
) -> None:
    cat = Catalog()
    end = datetime.now()
    start = end - timedelta(days=years * 365)
    bars = cat.read_bars([symbol], start, end, BarAggregation.DAY)
    if bars.is_empty():
        raise typer.BadParameter(f"no bars for {symbol}; ingest first")
    pipeline = PITPipeline(default_feature_stack())
    result = train_model(
        bars,
        pipeline,
        name=name,
        framework=framework,
        target_horizon=target_horizon,
        n_splits=n_splits,
    )
    console.print(
        {
            "name": result.model_name,
            "version": result.version,
            "n_train_rows": result.n_train_rows,
            "cv_metrics": result.cv_metrics,
            "feature_columns": result.feature_columns,
        }
    )


if __name__ == "__main__":
    app()


_ = date  # quiet unused import
