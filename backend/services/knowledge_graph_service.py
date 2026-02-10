"""
Knowledge Graph Service - Manages Neo4j operations for GraphRAG.
"""

import os
from typing import List, Dict, Any, Optional
from langchain_neo4j import Neo4jGraph
from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)


class KnowledgeGraphService:
    """Service to interact with Neo4j graph database."""

    def __init__(self):
        self.uri = settings.neo4j_uri
        self.username = settings.neo4j_username
        self.password = settings.neo4j_password
        self.graph = None
        self._initialize_graph()

    def _initialize_graph(self):
        """Initialize the Neo4j graph connection."""
        try:
            self.graph = Neo4jGraph(
                url=self.uri,
                username=self.username,
                password=self.password,
                enhanced_schema=True
            )
            logger.info("Successfully connected to Neo4j Knowledge Graph")
        except Exception as e:
            logger.error("Failed to connect to Neo4j", error=str(e))
            self.graph = None

    def add_triplet(self, head: str, relation: str, tail: str, document_id: str, metadata: Optional[Dict[str, Any]] = None):
        """Add a (Subject, Predicate, Object) triplet to the graph linked to a document."""
        if not self.graph:
            return

        rel_type = relation.upper().replace(" ", "_").strip()
        full_metadata = (metadata or {}).copy()
        full_metadata["document_id"] = document_id

        query = f"""
        MERGE (h:Entity {{name: $head}})
        MERGE (t:Entity {{name: $tail}})
        MERGE (h)-[r:{rel_type}]->(t)
        SET r += $metadata
        RETURN h, r, t
        """
        
        try:
            self.graph.query(query, {
                "head": head,
                "tail": tail,
                "metadata": full_metadata
            })
        except Exception as e:
            logger.error("Error adding triplet to Neo4j", error=str(e))

    def query_graph(self, cypher: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """Run a raw Cypher query."""
        if not self.graph:
            return []
        try:
            return self.graph.query(cypher, params)
        except Exception as e:
            logger.error("Cypher query execution error", error=str(e))
            return []

    def get_related_entities(self, entity_name: str, document_ids: Optional[List[str]] = None, depth: int = 1) -> List[Dict[str, Any]]:
        """Get entities related to the given entity, isolated by document IDs."""
        if not self.graph:
            return []

        # If document_ids provided, filter the relationship by document_id
        filter_clause = ""
        if document_ids:
            filter_clause = "WHERE ALL(rel IN r WHERE rel.document_id IN $doc_ids)"

        query = f"""
        MATCH (e:Entity {{name: $name}})-[r*1..$depth]-(related:Entity)
        {filter_clause}
        RETURN e.name as source, type(r[0]) as relationship, related.name as target
        LIMIT 50
        """
        return self.query_graph(query, {"name": entity_name, "depth": depth, "doc_ids": document_ids})

    def search_entities(self, query: str, document_ids: Optional[List[str]] = None) -> List[str]:
        """Search for entities, isolated by document IDs."""
        if not self.graph:
            return []

        # Build filtered query depending on whether doc IDs are provided
        if document_ids:
            cypher = """
            MATCH (e:Entity)-[r]-()
            WHERE r.document_id IN $doc_ids
            AND e.name CONTAINS $token
            RETURN DISTINCT e.name as name
            LIMIT 10
            """
        else:
            cypher = """
            MATCH (e:Entity)
            WHERE e.name CONTAINS $token
            RETURN DISTINCT e.name as name
            LIMIT 10
            """
        
        tokens = [t for t in query.split() if len(t) > 3]
        results = []
        for token in tokens:
            res = self.query_graph(cypher, {"token": token, "doc_ids": document_ids})
            results.extend([r['name'] for r in res])
        return list(set(results))
