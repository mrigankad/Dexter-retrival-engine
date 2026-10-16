"""Document ingestion: parse → chunk → embed (dense + sparse) → index → record."""

from .parsers import parse_file, ParserError
from .chunker import HierarchicalChunker
from .pipeline import IngestionPipeline, get_ingestion_pipeline
from .worker import enqueue_ingestion, IngestionWorker

__all__ = [
    "parse_file", "ParserError", "HierarchicalChunker",
    "IngestionPipeline", "get_ingestion_pipeline", "enqueue_ingestion", "IngestionWorker",
]
