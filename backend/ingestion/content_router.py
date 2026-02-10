"""
Content Router - Routes parsed document content to appropriate processors.

Dispatches Docling output to:
- Text → Hierarchical Chunker
- Tables → Table Canonicalizer → Chunker
- Charts/Figures → Chart Analyzer → Chunker
- Images → Object Storage + VLM Analysis

Ensures each content type gets specialized processing before embedding.
"""

from typing import Any, Dict, List, Optional, Tuple
import hashlib
import os

from core.config import settings
from core.logger import get_logger
from services.object_storage_service import ObjectStorageService
from .table_canonicalizer import TableCanonicalizer, CanonicalTable
from .chart_analyzer import ChartAnalyzer, ChartAnalysis

logger = get_logger(__name__)


class ContentRouter:
    """
    Routes parsed content to type-specific processing pipelines.
    
    Pipeline:
    1. Receive Docling/parser output
    2. Classify content elements by type
    3. Route to appropriate processor
    4. Collect processed outputs
    5. Merge into unified chunk list
    """

    def __init__(self, llm_service=None):
        self.table_canonicalizer = TableCanonicalizer()
        self.chart_analyzer = ChartAnalyzer(llm_service=llm_service)
        self.object_storage = ObjectStorageService()
        self._llm = llm_service

    async def route_and_process(
        self,
        parsed_document: Dict[str, Any],
        document_id: str,
        filename: str,
        metadata: Optional[Dict] = None,
    ) -> Dict[str, Any]:
        """
        Route parsed document content through specialized processors.
        
        Args:
            parsed_document: Output from Docling/parser
            document_id: Unique document ID
            filename: Source filename
            metadata: Additional metadata
            
        Returns:
            Dict with categorized processed content:
            {
                "text_sections": [...],
                "canonical_tables": [...],
                "chart_analyses": [...],
                "images": [...],
                "processing_stats": {...}
            }
        """
        metadata = metadata or {}
        result = {
            "text_sections": [],
            "canonical_tables": [],
            "chart_analyses": [],
            "images": [],
            "processing_stats": {
                "total_pages": 0,
                "text_sections": 0,
                "tables_processed": 0,
                "charts_processed": 0,
                "images_stored": 0,
            },
        }

        pages = parsed_document.get("pages", [])
        result["processing_stats"]["total_pages"] = len(pages)

        table_counter = 0
        chart_counter = 0
        image_counter = 0

        for page in pages:
            page_num = page.get("page_number", 1)

            # 1. Process Text Content
            text_content = page.get("text", "")
            sections = page.get("sections", [])
            
            if sections:
                for section in sections:
                    result["text_sections"].append({
                        "content": section.get("content", ""),
                        "title": section.get("title", ""),
                        "page": page_num,
                        "section_level": section.get("level", 0),
                        "bbox": section.get("bbox"),
                    })
            elif text_content:
                result["text_sections"].append({
                    "content": text_content,
                    "title": "",
                    "page": page_num,
                    "section_level": 0,
                    "bbox": None,
                })

            # 2. Process Tables
            for table_data in page.get("tables", []):
                table_counter += 1
                table_id = f"{document_id}_table_{table_counter}"
                
                try:
                    canonical_table = self._process_table(
                        table_data, table_id, page_num, text_content
                    )
                    result["canonical_tables"].append(canonical_table)
                    
                    # Store structured data in object storage
                    self._store_asset(document_id, table_id, "table", canonical_table.to_dict())
                    
                except Exception as e:
                    logger.warning(
                        "Table processing failed",
                        table_id=table_id, page=page_num, error=str(e)
                    )

            # 3. Process Charts/Graphics
            for graphic_data in page.get("graphics", []):
                chart_counter += 1
                chart_id = f"{document_id}_chart_{chart_counter}"
                
                try:
                    chart_analysis = self._process_chart(
                        graphic_data, chart_id, page_num, text_content
                    )
                    result["chart_analyses"].append(chart_analysis)
                    
                    # Store analysis in object storage
                    self._store_asset(document_id, chart_id, "chart", chart_analysis.to_dict())
                    
                except Exception as e:
                    logger.warning(
                        "Chart processing failed",
                        chart_id=chart_id, page=page_num, error=str(e)
                    )

            # 4. Process Images (store for reference)
            for image_data in page.get("images", []):
                image_counter += 1
                image_id = f"{document_id}_img_{image_counter}"
                
                try:
                    image_info = self._process_image(
                        image_data, image_id, page_num, document_id
                    )
                    if image_info:
                        result["images"].append(image_info)
                except Exception as e:
                    logger.warning(
                        "Image processing failed",
                        image_id=image_id, error=str(e)
                    )

        # Update stats
        result["processing_stats"]["text_sections"] = len(result["text_sections"])
        result["processing_stats"]["tables_processed"] = len(result["canonical_tables"])
        result["processing_stats"]["charts_processed"] = len(result["chart_analyses"])
        result["processing_stats"]["images_stored"] = len(result["images"])

        logger.info(
            "Content routing complete",
            document_id=document_id,
            stats=result["processing_stats"],
        )

        return result

    def _process_table(
        self,
        table_data: Dict,
        table_id: str,
        page_num: int,
        context_text: str,
    ) -> CanonicalTable:
        """Process a raw table through the canonicalizer."""
        headers = table_data.get("headers", [])
        rows = table_data.get("rows", [])
        caption = table_data.get("caption") or table_data.get("summary")

        # Handle different table formats
        if isinstance(rows, list) and rows:
            if isinstance(rows[0], dict):
                # Convert dict rows to list of lists
                if not headers:
                    headers = list(rows[0].keys())
                rows = [[str(row.get(h, "")) for h in headers] for row in rows]
            elif isinstance(rows[0], str):
                # Single column table
                rows = [[r] for r in rows]

        # Also try structured_data field
        if not rows and "structured_data" in table_data:
            sd = table_data["structured_data"]
            if isinstance(sd, str):
                # Try to parse as markdown table
                lines = [l.strip() for l in sd.strip().split("\n") if l.strip()]
                if lines:
                    parsed_rows = []
                    for line in lines:
                        if line.startswith("|"):
                            cells = [c.strip() for c in line.split("|")[1:-1]]
                            if not all(c.replace("-", "").strip() == "" for c in cells):
                                parsed_rows.append(cells)
                    if parsed_rows:
                        if not headers:
                            headers = parsed_rows[0]
                            rows = parsed_rows[1:]
                        else:
                            rows = parsed_rows

        return self.table_canonicalizer.canonicalize(
            table_id=table_id,
            page=page_num,
            headers=headers,
            rows=rows,
            caption=caption,
            context_before=context_text[:500],
        )

    def _process_chart(
        self,
        graphic_data: Dict,
        chart_id: str,
        page_num: int,
        context_text: str,
    ) -> ChartAnalysis:
        """Process a chart/figure through the analyzer."""
        return self.chart_analyzer.analyze_chart(
            chart_id=chart_id,
            page=page_num,
            chart_type=graphic_data.get("type", "unknown"),
            title=graphic_data.get("title"),
            caption=graphic_data.get("caption") or graphic_data.get("analysis"),
            image_path=graphic_data.get("image_path"),
            raw_data=graphic_data.get("data"),
            bounding_box=graphic_data.get("bbox"),
            context_text=context_text[:500],
        )

    def _process_image(
        self,
        image_data: Dict,
        image_id: str,
        page_num: int,
        document_id: str,
    ) -> Optional[Dict]:
        """Store an image in object storage and return metadata."""
        image_path = image_data.get("path") or image_data.get("image_path")
        if not image_path or not os.path.exists(image_path):
            return None

        try:
            object_name = f"{document_id}/images/{image_id}{os.path.splitext(image_path)[1]}"
            self.object_storage.upload_file(
                file_path=image_path,
                bucket_name=settings.minio_bucket_assets,
                object_name=object_name,
            )
            return {
                "id": image_id,
                "page": page_num,
                "storage_path": object_name,
                "caption": image_data.get("caption", ""),
                "bbox": image_data.get("bbox"),
            }
        except Exception as e:
            logger.warning("Image storage failed", error=str(e))
            return None

    def _store_asset(
        self,
        document_id: str,
        asset_id: str,
        asset_type: str,
        data: Dict,
    ):
        """Store a processed asset (table/chart) in object storage."""
        try:
            import json
            object_name = f"{document_id}/{asset_type}s/{asset_id}.json"
            self.object_storage.put_json(
                bucket_name=settings.minio_bucket_assets,
                object_name=object_name,
                data=data,
            )
        except Exception as e:
            logger.warning(
                "Asset storage failed",
                asset_id=asset_id, type=asset_type, error=str(e)
            )
