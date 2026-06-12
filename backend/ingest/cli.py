"""Ingestion entrypoint: (optionally) download acts, ingest PDFs, crawl, keep scheduler alive.

Run:  python -m backend.ingest.cli                # ingest + crawl
      python -m backend.ingest.cli --download     # fetch missing bare acts first
"""
from __future__ import annotations

import sys
import time

from backend.core.logging import get_logger
from backend.ingest.pdf import ingest_all_pdfs
from backend.ingest.web import crawl_dynamic_sources, start_scheduler

logger = get_logger("ingest.cli")


def main() -> None:
    logger.info("=== AdhikarAI Ingestion ===")

    if "--download" in sys.argv:
        from backend.ingest.download import main as download_acts

        logger.info("[0/2] Downloading missing bare acts from India Code ...")
        download_acts()

    logger.info("[1/2] Ingesting static PDFs ...")
    ingest_all_pdfs("./pdfs")

    logger.info("[2/2] Crawling dynamic web sources ...")
    crawl_dynamic_sources()

    scheduler = start_scheduler()
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        scheduler.shutdown()
        logger.info("[Scheduler] stopped")


if __name__ == "__main__":
    main()
