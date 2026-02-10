"""
Entity Extractor - Named Entity and Relationship Extraction.

Extracts entities from document chunks for optional knowledge graph:
- Named entities (companies, people, products, locations)
- Financial metrics and KPIs
- Temporal references
- Entity relationships
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
import re

from core.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Entity:
    """An extracted entity."""
    text: str
    entity_type: str  # organization | person | product | location | metric | time_period
    normalized: str = ""  # Canonical form
    frequency: int = 1
    pages: List[int] = field(default_factory=list)
    context_snippets: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not self.normalized:
            self.normalized = self.text.strip().lower()

    def __hash__(self):
        return hash((self.normalized, self.entity_type))

    def __eq__(self, other):
        return (self.normalized, self.entity_type) == (other.normalized, other.entity_type)


@dataclass
class EntityRelation:
    """A relationship between two entities."""
    source: Entity
    target: Entity
    relation_type: str  # reports_to | owns | produces | located_in | measured_by
    context: str = ""
    confidence: float = 0.7
    page: int = 0


# Common financial entity patterns
METRIC_PATTERNS = re.compile(
    r"\b(revenue|net income|profit|ebitda|ebit|eps|dps|roe|roa|roce|"
    r"gross margin|operating margin|net margin|capex|opex|"
    r"free cash flow|operating cash flow|debt equity ratio|"
    r"current ratio|book value|market cap|dividend yield|"
    r"sales|turnover|growth rate|cagr)\b",
    re.IGNORECASE,
)

TIME_PATTERNS = re.compile(
    r"\b(FY\s*\d{2,4}(?:-\d{2,4})?|Q[1-4]\s*(?:FY)?\s*\d{2,4}|"
    r"H[12]\s*(?:FY)?\s*\d{2,4}|20[0-3]\d(?:-\d{2,4})?|"
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{4})\b",
    re.IGNORECASE,
)

# Simple NER patterns (for rule-based extraction)
ORG_INDICATORS = [
    "ltd", "limited", "inc", "corp", "corporation", "group", "holdings",
    "company", "co.", "plc", "pvt", "private", "public",
]

PRODUCT_PATTERNS = re.compile(
    r"\b(iron ore|steel|coal|coking coal|thermal coal|pellets|"
    r"hot rolled|cold rolled|wire rod|rebar|flat steel|long steel|"
    r"sinter|pig iron|sponge iron|dri|hbi)\b",
    re.IGNORECASE,
)


class EntityExtractor:
    """
    Extracts entities and relationships from document chunks.
    
    Extraction methods:
    1. Rule-based pattern matching (fast, high precision)
    2. LLM-based extraction (high recall, optional)
    """

    def __init__(self, llm_service=None):
        self.llm = llm_service
        self._entity_cache: Dict[str, Entity] = {}

    def extract_entities(
        self,
        text: str,
        page: int = 0,
        document_id: str = "",
    ) -> List[Entity]:
        """
        Extract entities from a text chunk.
        
        Args:
            text: Text to extract entities from
            page: Source page number
            document_id: Source document ID
            
        Returns:
            List of extracted entities
        """
        entities = []

        # 1. Extract financial metrics
        metrics = METRIC_PATTERNS.findall(text)
        for m in metrics:
            entity = Entity(
                text=m,
                entity_type="metric",
                normalized=m.lower().strip(),
                pages=[page],
                context_snippets=[self._get_context(text, m)],
            )
            entities.append(entity)

        # 2. Extract time periods
        times = TIME_PATTERNS.findall(text)
        for t in times:
            entity = Entity(
                text=t,
                entity_type="time_period",
                normalized=t.strip(),
                pages=[page],
            )
            entities.append(entity)

        # 3. Extract organizations (heuristic)
        orgs = self._extract_organizations(text)
        for org in orgs:
            entity = Entity(
                text=org,
                entity_type="organization",
                normalized=org.lower().strip(),
                pages=[page],
                context_snippets=[self._get_context(text, org)],
            )
            entities.append(entity)

        # 4. Extract products/commodities
        products = PRODUCT_PATTERNS.findall(text)
        for p in products:
            entity = Entity(
                text=p,
                entity_type="product",
                normalized=p.lower().strip(),
                pages=[page],
            )
            entities.append(entity)

        # Deduplicate
        return self._deduplicate_entities(entities)

    async def extract_entities_llm(
        self, text: str, page: int = 0
    ) -> List[Entity]:
        """Use LLM for advanced entity extraction."""
        if not self.llm:
            return self.extract_entities(text, page)

        try:
            prompt = f"""Extract all named entities from this text. Categorize each as:
- organization: Companies, institutions
- person: People mentioned
- product: Products, commodities
- location: Places, regions
- metric: Financial KPIs and metrics
- time_period: Dates, quarters, fiscal years

Text:
{text[:2000]}

Output as JSON list:
[{{"text": "entity text", "type": "category"}}]"""

            response = await self.llm.generate(
                prompt=prompt,
                max_tokens=500,
                temperature=0.1,
            )

            import json
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]
            else:
                json_str = response

            entities_data = json.loads(json_str)
            entities = []
            for ed in entities_data:
                entities.append(Entity(
                    text=ed["text"],
                    entity_type=ed.get("type", "unknown"),
                    pages=[page],
                ))
            return self._deduplicate_entities(entities)

        except Exception as e:
            logger.warning("LLM entity extraction failed", error=str(e))
            return self.extract_entities(text, page)

    def extract_relations(
        self, entities: List[Entity], text: str, page: int = 0
    ) -> List[EntityRelation]:
        """
        Extract relationships between entities.
        
        Uses co-occurrence and pattern-based relation detection.
        """
        relations = []

        # Co-occurrence based relations
        for i, e1 in enumerate(entities):
            for j, e2 in enumerate(entities):
                if i >= j:
                    continue
                if e1.entity_type == e2.entity_type:
                    continue

                # Check if entities co-occur within proximity
                if self._entities_cooccur(e1.text, e2.text, text, window=200):
                    relation_type = self._infer_relation(e1, e2)
                    if relation_type:
                        relations.append(EntityRelation(
                            source=e1,
                            target=e2,
                            relation_type=relation_type,
                            context=self._get_context(text, e1.text, 100),
                            page=page,
                        ))

        return relations

    def merge_entity_lists(
        self, *entity_lists: List[Entity]
    ) -> List[Entity]:
        """Merge multiple entity lists with frequency counting."""
        merged: Dict[Tuple[str, str], Entity] = {}

        for entities in entity_lists:
            for entity in entities:
                key = (entity.normalized, entity.entity_type)
                if key in merged:
                    existing = merged[key]
                    existing.frequency += 1
                    existing.pages.extend(entity.pages)
                    existing.pages = list(set(existing.pages))
                    existing.context_snippets.extend(entity.context_snippets[:2])
                else:
                    merged[key] = Entity(
                        text=entity.text,
                        entity_type=entity.entity_type,
                        normalized=entity.normalized,
                        frequency=entity.frequency,
                        pages=list(entity.pages),
                        context_snippets=list(entity.context_snippets[:2]),
                    )

        return sorted(merged.values(), key=lambda e: e.frequency, reverse=True)

    # ── Internal Methods ───────────────────────────────────────

    def _extract_organizations(self, text: str) -> List[str]:
        """Extract organization names using heuristics."""
        orgs = set()

        # Pattern: Capitalized words followed by org indicators
        for indicator in ORG_INDICATORS:
            pattern = rf"\b([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*\s+{re.escape(indicator)}\.?)\b"
            matches = re.findall(pattern, text)
            orgs.update(matches)

        # Pattern: Acronyms that look like company names (3+ caps)
        acronyms = re.findall(r"\b([A-Z]{3,})\b", text)
        # Filter out common non-company acronyms
        non_company = {"THE", "AND", "FOR", "NOT", "BUT", "PDF", "FIG", "TABLE"}
        orgs.update(a for a in acronyms if a not in non_company)

        return list(orgs)

    @staticmethod
    def _entities_cooccur(
        text1: str, text2: str, full_text: str, window: int = 200
    ) -> bool:
        """Check if two entity texts co-occur within a window."""
        pos1 = full_text.lower().find(text1.lower())
        pos2 = full_text.lower().find(text2.lower())

        if pos1 < 0 or pos2 < 0:
            return False

        return abs(pos1 - pos2) <= window

    @staticmethod
    def _infer_relation(e1: Entity, e2: Entity) -> Optional[str]:
        """Infer relation type from entity types."""
        type_pair = (e1.entity_type, e2.entity_type)
        
        relation_map = {
            ("organization", "metric"): "reports",
            ("metric", "organization"): "measures",
            ("organization", "product"): "produces",
            ("product", "organization"): "produced_by",
            ("organization", "location"): "located_in",
            ("metric", "time_period"): "measured_at",
            ("organization", "time_period"): "reported_at",
        }
        
        return relation_map.get(type_pair)

    @staticmethod
    def _get_context(text: str, entity_text: str, window: int = 80) -> str:
        """Get surrounding context for an entity."""
        pos = text.lower().find(entity_text.lower())
        if pos < 0:
            return ""
        start = max(0, pos - window)
        end = min(len(text), pos + len(entity_text) + window)
        return text[start:end].strip()

    @staticmethod
    def _deduplicate_entities(entities: List[Entity]) -> List[Entity]:
        """Remove duplicate entities."""
        seen: Dict[Tuple[str, str], Entity] = {}
        for entity in entities:
            key = (entity.normalized, entity.entity_type)
            if key not in seen:
                seen[key] = entity
            else:
                seen[key].frequency += 1
                seen[key].pages.extend(entity.pages)
        return list(seen.values())
