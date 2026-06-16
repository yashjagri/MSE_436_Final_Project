"""
Soccer IDSS — Data Pipeline CLI

Usage:
  python main.py db-init            Apply schema migration to Postgres
  python main.py scrape sofascore   Scrape SofaScore stats → cache + DB
  python main.py scrape transfermarkt  Scrape Transfermarkt → cache + DB
  python main.py transform          Compute per-90 stats → player_features
  python main.py build-features     MinMax-scale → write parquet + DB vectors
  python main.py pipeline           Run all four steps end-to-end
"""

import subprocess
import sys
from pathlib import Path

import click
from loguru import logger

from config import DATABASE_URL, BASE_DIR


# ──────────────────────────────────────────────────────────────────
# Logging setup
# ──────────────────────────────────────────────────────────────────

logger.remove()
logger.add(sys.stderr, level="INFO", format="<level>{level}</level> | {message}")
logger.add(BASE_DIR / "pipeline.log", level="DEBUG", rotation="10 MB")


# ──────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────

@click.group()
def cli():
    """Soccer IDSS data pipeline."""


@cli.command("db-init")
def db_init():
    """Apply migrations/001_initial_schema.sql to the configured Postgres DB."""
    migration = BASE_DIR / "migrations" / "001_initial_schema.sql"
    if not migration.exists():
        logger.error(f"Migration not found: {migration}")
        sys.exit(1)

    logger.info(f"Applying schema to {DATABASE_URL}")
    result = subprocess.run(
        ["psql", DATABASE_URL, "-f", str(migration)],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        logger.error(result.stderr)
        sys.exit(result.returncode)
    logger.info("Schema applied successfully")
    if result.stdout:
        print(result.stdout)


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
