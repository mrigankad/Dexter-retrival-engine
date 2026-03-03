"""
DynamicExpertAgent - Dynamic Persona Loading Agent

Responsible for loading arbitrary agent definitions from markdown files
with YAML frontmatter and acting on their persona to answer domain queries.
"""

from typing import Dict, Any, Optional
import time
import logging
import os
import yaml
from datetime import datetime

from src.agents.base.base_agent import Agent

logger = logging.getLogger(__name__)


class DynamicExpertAgent(Agent):
    """
    Dynamically loads an agent persona from a markdown file (with YAML frontmatter)
    and uses the prompt to provide domain expertise.
    """

    def __init__(self, persona_filepath: str):
        """
        Initialize the dynamic agent.

        Args:
            persona_filepath: Relative or absolute path to the persona markdown file
                              relative to the 'backend/src/agents/prompts/personas' directory.
        """
        self.raw_filepath = persona_filepath
        full_path = self._resolve_filepath(persona_filepath)
        
        self.persona_data = self._load_persona_file(full_path)
        
        # Load identity from frontmatter
        name = self.persona_data.get("frontmatter", {}).get("name", "DynamicAgent")
        role = self.persona_data.get("frontmatter", {}).get("description", "Domain Expert")
        
        # Format the name properly: e.g. "engineering-ai-engineer" -> "Engineering Ai Engineer"
        formatted_name = " ".join([word.capitalize() for word in name.replace("-", " ").split()])

        super().__init__(
            name=formatted_name,
            role=role
        )

        self.domain = "dynamic"
        self.expertise_areas = ["dynamic domain expertise"]
        self.tools = {
            "provide_expertise": None,
        }

    def _resolve_filepath(self, filepath: str) -> str:
        """Resolve the filepath relative to the personas directory."""
        if os.path.isabs(filepath):
            return filepath
        
        # Find the path relative to this file
        current_dir = os.path.dirname(os.path.abspath(__file__))
        # Walk up to 'agents', then down to 'prompts/personas'
        base_dir = os.path.join(os.path.dirname(current_dir), "prompts", "personas")
        return os.path.join(base_dir, filepath)

    def _load_persona_file(self, exact_path: str) -> Dict[str, Any]:
        """Load and parse the markdown file with YAML frontmatter."""
        if not os.path.exists(exact_path):
            raise FileNotFoundError(f"Persona file not found at: {exact_path}")
            
        with open(exact_path, "r", encoding="utf-8") as file:
            content = file.read()

        # Parse YAML frontmatter
        frontmatter = {}
        body = content
        
        if content.startswith("---"):
            end_idx = content.find("---", 3)
            if end_idx != -1:
                yaml_content = content[3:end_idx].strip()
                try:
                    frontmatter = yaml.safe_load(yaml_content) or {}
                except yaml.YAMLError as e:
                    logger.warning(f"Failed to parse YAML frontmatter in {exact_path}: {e}")
                body = content[end_idx + 3:].strip()
                
        return {
            "frontmatter": frontmatter,
            "system_prompt": body
        }

    async def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute domain expertise task using the loaded persona.

        Args:
            task: {
                "task": "provide_expertise",
                "domain_question": "...",
                "context": {...}
            }
        """
        if task.get("task") != "provide_expertise":
            raise ValueError(f"{self.name} only handles 'provide_expertise' task")

        domain_question = task.get("domain_question", "")
        if not domain_question:
            raise ValueError("No domain question provided")

        context = task.get("context", "")

        logger.info(f"{self.name}: Analyzing question: {domain_question[:100]}...")

        start_time = time.time()

        try:
            from src.services.llm.nvidia_llm_service import NvidiaLLMService
            llm_service = NvidiaLLMService()

            prompt = self._create_expertise_prompt(domain_question, context)

            expertise_response = await llm_service.generate(
                prompt=prompt,
                max_tokens=1000,
                temperature=0.7 
            )

            duration = time.time() - start_time

            await self.observe({
                "type": "dynamic_expertise_execution",
                "domain": self.domain,
                "agent_name": self.name,
                "duration": duration,
                "importance": 0.8,
            })

            self.record_execution(
                task_name="provide_expertise",
                status="success",
                duration=duration,
                metadata={"agent_name": self.name, "domain": self.domain}
            )

            self.update_performance(
                success=True,
                quality_score=0.85, 
                response_time=duration
            )

            return {
                "status": "success",
                "agent": self.name,
                "expertise": expertise_response,
                "execution_time": round(duration, 3),
                "metadata": {
                    "domain": self.domain,
                    "timestamp": datetime.now().isoformat(),
                    "persona_used": self.raw_filepath
                }
            }

        except Exception as exc:
            logger.error(f"{self.name} failed: {exc}")
            duration = time.time() - start_time
            self.record_execution(
                task_name="provide_expertise",
                status="error",
                duration=duration,
                metadata={"error": str(exc)}
            )
            self.update_performance(success=False, quality_score=0.0, response_time=duration)
            raise

    async def think(self, domain_question: str, expertise_type: str = "") -> Dict[str, Any]:
        """Determine analysis strategy."""
        return {
            "reasoning_strategy": "Applying persona-specific knowledge base.",
            "persona": self.name,
            "depth_level": "comprehensive",
        }

    def _create_expertise_prompt(self, domain_question: str, context: Any) -> str:
        """Create the final prompt combining the persona and the actual question."""
        context_text = f"\nAdditional Context:\n{context}" if context else ""
        system_instructions = self.persona_data.get("system_prompt", "You are an expert.")

        return f"""{system_instructions}

Based on your expert persona defined above, please answer the following question.

Question: {domain_question}{context_text}

Please provide a detailed and highly actionable response that heavily leans on your specific domain expertise and follows any formatting rules or workflows defined in your persona instructions.
"""
