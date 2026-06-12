"""Backward-compatible entrypoint. The implementation now lives in backend/ingest/.

Run:  python ingestor.py   (or)   python -m backend.ingest.cli
"""
from backend.ingest.cli import main

if __name__ == "__main__":
    main()
