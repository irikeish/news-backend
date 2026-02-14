"""CLI for data ingestion and event generation."""

import asyncio
import logging
from pathlib import Path

import typer

from app.services.event_generator import generate_events
from app.services.ingest import load_news

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

app = typer.Typer()


@app.command()
def load(
    path: Path,
    summarize: bool = typer.Option(
        False, "--summarize", "-s", help="Summarize articles via LLM"
    ),
    n_summarize: int = typer.Option(
        10, "--n-summarize", "-n", help="Number of articles to summarize (1-n)"
    ),
):
    """Load news from JSON file into MongoDB.

    Example: python -m app.cli load news_data.json
    Example with summarization: python -m app.cli load news_data.json --summarize -n 20
    """
    if not path.exists():
        typer.echo(f"File not found: {path}", err=True)
        raise typer.Exit(1)
    if n_summarize < 1:
        typer.echo("n-summarize must be at least 1", err=True)
        raise typer.Exit(1)
    if summarize:
        typer.echo(
            f"Summarizing up to {n_summarize} articles (batches of 5, ~5–15s each)..."
        )
    n = asyncio.run(load_news(path, summarize=summarize, n_summarize=n_summarize))
    typer.echo(f"Loaded {n} articles")


@app.command("generate-events")
def generate_events_cmd(
    count: int = typer.Option(10000, "--count", "-n", help="Number of events"),
    users: int = typer.Option(500, "--users", "-u", help="Max user id range"),
    lat: float | None = typer.Option(
        None, "--lat", help="Center latitude for event locations"
    ),
    lon: float | None = typer.Option(
        None, "--lon", help="Center longitude for event locations"
    ),
):
    """Generate simulated user events for trending testing.

    Use --lat and --lon to cluster events around a location for trending tests.
    Example: uv run python -m app.cli generate-events --lat 18.02 --lon 72.70 -n 1000
    """
    if (lat is None) != (lon is None):
        typer.echo("Provide both --lat and --lon together", err=True)
        raise typer.Exit(1)
    n = asyncio.run(
        generate_events(count=count, users=users, center_lat=lat, center_lon=lon)
    )
    typer.echo(f"Generated {n} events")


def main():
    app()


if __name__ == "__main__":
    main()
