"""
Soccer IDSS — Data Pipeline CLI

Usage:
  uv run python main.py setup    First-time setup (.env, Postgres, schema)
  uv run python main.py scrape sofascore
  uv run python main.py pipeline
"""

import shutil
import sys

import click
import psycopg2
from loguru import logger

from config import BASE_DIR

MIGRATION = BASE_DIR / "migrations" / "001_initial_schema.sql"


logger.remove()
logger.add(sys.stderr, level="INFO", format="<level>{level}</level> | {message}")
logger.add(BASE_DIR / "pipeline.log", level="DEBUG", rotation="10 MB")


def _apply_schema(url: str) -> None:
    if not MIGRATION.exists():
        raise FileNotFoundError(f"Migration not found: {MIGRATION}")

    conn = psycopg2.connect(url)
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            for part in MIGRATION.read_text().split(";"):
                if any(
                    line.strip() and not line.strip().startswith("--")
                    for line in part.splitlines()
                ):
                    cur.execute(part)
    finally:
        conn.close()


@click.group()
def cli():
    """Soccer IDSS data pipeline."""


@cli.command("setup")
def setup():
    """First-time setup: .env + schema."""
    from config import DATABASE_URL

    env = BASE_DIR / ".env"
    example = BASE_DIR / ".env.example"
    if not env.exists():
        if not example.exists():
            raise click.ClickException(f"Missing {example}")
        shutil.copy(example, env)
        logger.info("Created .env from .env.example")

    logger.info(f"Applying schema to {DATABASE_URL}")
    try:
        _apply_schema(DATABASE_URL)
    except Exception as exc:
        raise click.ClickException(str(exc)) from exc
    logger.info("Setup complete — run `uv run python main.py pipeline` to ingest data")


@cli.group()
def scrape():
    """Scrape data sources."""


@scrape.command("sofascore")
def scrape_sofascore():
    """Scrape SofaScore stats for all configured leagues/seasons."""
    from pipeline.ingest import ingest_sofascore
    logger.info("Starting SofaScore scrape + ingest")
    ingest_sofascore()
    logger.info("Done")


@scrape.command("transfermarkt")
def scrape_transfermarkt():
    """Scrape Transfermarkt market values and player metadata."""
    from pipeline.ingest import ingest_transfermarkt
    logger.info("Starting Transfermarkt scrape + ingest")
    ingest_transfermarkt()
    logger.info("Done")


@cli.command("transform")
def transform():
    """Compute per-90 stats and populate player_features table."""
    from pipeline.transform import run_transform
    run_transform()


@cli.command("build-features")
def build_features():
    """MinMax-scale features, write parquet, update DB vectors."""
    from pipeline.build_features import run_build_features
    run_build_features()


@cli.command("pipeline")
@click.option("--skip-scrape", is_flag=True, help="Skip scraping, use cached data only")
def pipeline(skip_scrape: bool):
    """Run the full pipeline: [scrape →] transform → build-features."""
    if not skip_scrape:
        from pipeline.ingest import ingest_sofascore, ingest_transfermarkt
        logger.info("Step 1/4: Scraping SofaScore")
        ingest_sofascore()
        logger.info("Step 2/4: Scraping Transfermarkt")
        ingest_transfermarkt()
    else:
        logger.info("Skipping scrape steps (--skip-scrape)")

    from pipeline.transform import run_transform
    logger.info("Step 3/4: Transforming to per-90 features")
    run_transform()

    from pipeline.build_features import run_build_features
    logger.info("Step 4/4: Building feature parquet")
    run_build_features()

    logger.info("Pipeline complete. Parquet ready at data/processed/player_features.parquet")


if __name__ == "__main__":
    cli()
