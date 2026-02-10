"""
Ingestion Worker - Background document processing.

Runs as a separate container for async document ingestion.
"""

import asyncio
import os
import signal
from typing import Optional

import redis.asyncio as redis

from core.config import settings
from core.logger import setup_logging, get_logger
from .embedding_pipeline import EmbeddingPipeline
from db.postgres_models import Document
from db.session_manager import async_session_factory
from sqlalchemy import update
from datetime import datetime
import uuid

# Initialize logging
setup_logging(log_level=settings.log_level, json_logs=True)
logger = get_logger(__name__)


class IngestionWorker:
    """Background worker for document ingestion."""
    
    def __init__(self):
        self.pipeline = EmbeddingPipeline()
        self.redis: Optional[redis.Redis] = None
        self.running = False
        self.queue_name = "ingestion_queue"
    
    async def connect(self):
        """Connect to Redis."""
        self.redis = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        logger.info("Connected to Redis")
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self.redis:
            await self.redis.close()
            logger.info("Disconnected from Redis")
    
    async def process_job(self, job_data: str) -> bool:
        """Process a single ingestion job."""
        try:
            import json
            job = json.loads(job_data)
            
            document_id = job["document_id"]
            file_path = job["file_path"]
            metadata = job.get("metadata", {})
            
            logger.info("Processing job", document_id=document_id)
            
            async with async_session_factory() as session:
                # Update status to processing
                await session.execute(
                    update(Document)
                    .where(Document.id == uuid.UUID(document_id))
                    .values(status="processing")
                )
                await session.commit()
            
                try:
                    result = await self.pipeline.process_document(
                        document_id=document_id,
                        file_path=file_path,
                        metadata=metadata,
                    )
                    
                    # Clean up file after processing
                    if os.path.exists(file_path):
                        os.remove(file_path)
                    
                    # Update status to completed
                    await session.execute(
                        update(Document)
                        .where(Document.id == uuid.UUID(document_id))
                        .values(
                            status="completed",
                            processed_at=datetime.utcnow(),
                            chunks_count=result.get("chunks_count", 0),
                            doc_metadata=result
                        )
                    )
                    await session.commit()
                    
                    logger.info("Job completed", document_id=document_id, status=result["status"])
                    return True
                    
                except Exception as e:
                    # Update status to failed
                    await session.execute(
                        update(Document)
                        .where(Document.id == uuid.UUID(document_id))
                        .values(
                            status="failed",
                            error_message=str(e)
                        )
                    )
                    await session.commit()
                    raise e
            
        except Exception as e:
            logger.exception("Job failed", error=str(e))
            return False
    
    async def run(self):
        """Run the worker loop."""
        await self.connect()
        self.running = True
        
        logger.info("Ingestion worker started")
        
        while self.running:
            try:
                # Wait for job from queue
                result = await self.redis.brpop(self.queue_name, timeout=5)
                
                if result:
                    _, job_data = result
                    await self.process_job(job_data)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception("Worker error", error=str(e))
                await asyncio.sleep(1)
        
        await self.disconnect()
        logger.info("Ingestion worker stopped")
    
    def stop(self):
        """Signal the worker to stop."""
        self.running = False


async def main():
    """Main entry point for the worker."""
    worker = IngestionWorker()
    
    # Handle shutdown signals
    loop = asyncio.get_event_loop()
    
    def shutdown_handler():
        logger.info("Shutdown signal received")
        worker.stop()
    
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, shutdown_handler)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass
    
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
