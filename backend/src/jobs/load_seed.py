"""Load the bundled catalog seed (seed/catalog-*.sql.gz) into the products table.

Used where `psql` and the Docker init script can't reach the DB, i.e. the private RDS: the seed is
baked into the Lambda image and a separate long-timeout function runs this once
(`scripts/deploy.sh seed`). Safe to re-run: rows are upserted, and products missing from the seed
(e.g. no person-free photo any more) are removed.

    python -m src.jobs.load_seed            # local: DATABASE_URL / .env
"""
from __future__ import annotations

import gzip
import logging
import re
import time
from pathlib import Path

from src.backend.config import load_app_env
from src.backend.db import connect_db, initialize_database

logger = logging.getLogger(__name__)
SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
HEADER = re.compile(r"^COPY public\.products \(([^)]*)\) FROM stdin;$")
KEY = ("platform", "goods_no")


def seed_parts(seed_dir: Path = SEED_DIR) -> list[Path]:
    parts = sorted(seed_dir.glob("catalog-*.sql.gz"))
    if not parts:
        raise FileNotFoundError(f"no catalog-*.sql.gz in {seed_dir}")
    return parts


def read_part(path: Path) -> tuple[list[str], list[str]]:
    """(column names, raw COPY text rows) of one dump_seed.sh part."""
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        header = HEADER.match(handle.readline().rstrip("\n"))
        if not header:
            raise ValueError(f"{path.name}: not a products COPY dump")
        rows = []
        for line in handle:
            if line.rstrip("\n") == "\\.":
                break
            rows.append(line)
    return [column.strip() for column in header.group(1).split(",")], rows


def load(seed_dir: Path = SEED_DIR) -> dict[str, int]:
    started = time.perf_counter()
    initialize_database()  # schema + vector(128) column, idempotent
    with connect_db() as connection:
        connection.execute("CREATE TEMP TABLE seed_products (LIKE products INCLUDING DEFAULTS) ON COMMIT DROP")
        columns: list[str] | None = None
        loaded = 0
        with connection.cursor() as cursor:
            for part in seed_parts(seed_dir):
                part_columns, rows = read_part(part)
                if columns not in (None, part_columns):
                    raise ValueError(f"{part.name}: columns differ from the first part")
                columns = part_columns
                with cursor.copy(f"COPY seed_products ({', '.join(columns)}) FROM STDIN") as copy:
                    for row in rows:
                        copy.write(row)
                loaded += len(rows)
                logger.info("staged %s (%d rows)", part.name, len(rows))
        assert columns is not None
        updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in columns if column not in KEY)
        upserted = connection.execute(
            f"INSERT INTO products ({', '.join(columns)}) SELECT {', '.join(columns)} FROM seed_products "
            f"ON CONFLICT (platform, goods_no) DO UPDATE SET {updates}, updated_at = now()"
        ).rowcount
        removed = connection.execute(
            "DELETE FROM products p WHERE NOT EXISTS "
            "(SELECT 1 FROM seed_products s WHERE s.platform = p.platform AND s.goods_no = p.goods_no)"
        ).rowcount
        total = connection.execute("SELECT count(*) AS n FROM products").fetchone()["n"]
    result = {"seed_rows": loaded, "upserted": upserted, "removed": removed, "products": total,
              "seconds": round(time.perf_counter() - started, 1)}
    logger.info("seed loaded: %s", result)
    return result


def handler(event, context):  # Lambda entry point (SeedFunction in infra/aws/backend.yaml)
    logging.getLogger().setLevel(logging.INFO)
    load_app_env()
    return load()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(load())
