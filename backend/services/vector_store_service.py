"""
Qdrant Vector Store Service.

Provides vector storage and retrieval operations using Qdrant.
"""

from typing import List, Optional, Dict, Any
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import UnexpectedResponse

from core.config import settings
from core.logger import get_logger, log_timing

logger = get_logger(__name__)


class VectorStoreService:
    """Qdrant vector store client."""
    
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        collection: Optional[str] = None,
    ):
        self.host = host or settings.qdrant_host
        self.port = port or settings.qdrant_port
        self.collection = collection or settings.qdrant_collection
        self.vector_size = settings.qdrant_vector_size
        
        self.client = QdrantClient(host=self.host, port=self.port)
        self._ensure_collection()
    
    def _ensure_collection(self):
        """Ensure the collection exists with proper configuration."""
        try:
            self.client.get_collection(self.collection)
            logger.info(f"Collection {self.collection} exists")
        except Exception:
            self.client.create_collection(
                collection_name=self.collection,
                vectors_config=models.VectorParams(
                    size=self.vector_size,
                    distance=models.Distance.COSINE,
                ),
            )
            logger.info(f"Created collection {self.collection}")
    
    @log_timing("vector_upsert")
    async def upsert(
        self,
        vectors: List[List[float]],
        payloads: List[Dict[str, Any]],
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Upsert vectors with payloads.
        
        Args:
            vectors: List of embedding vectors
            payloads: List of metadata payloads
            ids: Optional list of IDs (generated if not provided)
            
        Returns:
            List of point IDs
        """
        if ids is None:
            ids = [str(uuid4()) for _ in vectors]
        
        points = [
            models.PointStruct(id=id_, vector=vec, payload=payload)
            for id_, vec, payload in zip(ids, vectors, payloads)
        ]
        
        self.client.upsert(collection_name=self.collection, points=points)
        
        logger.info(f"Upserted {len(points)} vectors")
        return ids
    
    @log_timing("vector_search")
    async def search(
        self,
        query_vector: List[float],
        top_k: int = 5,
        filter_conditions: Optional[Dict] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search for similar vectors.
        
        Args:
            query_vector: Query embedding
            top_k: Number of results
            filter_conditions: Optional filter dict (e.g., {"page": 100})
            
        Returns:
            List of results with payload and score
        """
        query_filter = None
        if filter_conditions:
            # Build Qdrant filter from simple dict
            must_conditions = []
            for key, value in filter_conditions.items():
                if isinstance(value, list):
                    must_conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchAny(any=value)
                        )
                    )
                else:
                    must_conditions.append(
                        models.FieldCondition(
                            key=key,
                            match=models.MatchValue(value=value)
                        )
                    )
            query_filter = models.Filter(must=must_conditions)
        
        # Use query_points for newer qdrant-client versions
        results = self.client.query_points(
            collection_name=self.collection,
            query=query_vector,
            limit=top_k,
            query_filter=query_filter,
            with_payload=True,
        )
        
        return [
            {
                "id": str(hit.id),
                "score": hit.score,
                "payload": hit.payload,
            }
            for hit in results.points
        ]
    
    async def delete(self, ids: List[str]) -> bool:
        """Delete vectors by ID."""
        self.client.delete(
            collection_name=self.collection,
            points_selector=models.PointIdsList(points=ids),
        )
        logger.info(f"Deleted {len(ids)} vectors")
        return True
    
    async def delete_by_filter(self, filter_conditions: Dict) -> bool:
        """Delete vectors matching filter."""
        self.client.delete(
            collection_name=self.collection,
            points_selector=models.FilterSelector(
                filter=models.Filter(**filter_conditions)
            ),
        )
        return True
    
    async def delete_by_filter(
        self,
        filter_conditions: Dict[str, Any],
        collection: Optional[str] = None,
    ) -> bool:
        """
        Delete all points matching a filter.

        Args:
            filter_conditions: Qdrant filter dict (e.g. {"must": [...]})
            collection: Target collection (default: configured collection)

        Returns:
            True if deletion was successful
        """
        col = collection or self.collection
        try:
            self.client.delete(
                collection_name=col,
                points_selector=models.FilterSelector(
                    filter=models.Filter(**filter_conditions),
                ),
            )
            logger.info("Deleted points by filter", collection=col)
            return True
        except Exception as e:
            logger.error("Failed to delete by filter", error=str(e))
            raise

    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection statistics."""
        info = self.client.get_collection(self.collection)
        return {
            "name": self.collection,
            "vectors_count": info.vectors_count,
            "points_count": info.points_count,
            "status": info.status,
        }
