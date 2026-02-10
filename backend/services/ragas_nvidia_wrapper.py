"""
NVIDIA Judge Wrapper for Ragas - LangChain Compatible.
"""

from typing import Any, List, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langchain_core.outputs import ChatResult, ChatGeneration
import requests
import os

from core.config import settings
from core.logger import get_logger

logger = get_logger(__name__)

class NvidiaJudgeLLM(BaseChatModel):
    """LangChain wrapper for NVIDIA NIM to be used by Ragas."""
    
    model_name: str = settings.nvidia_llm_model
    
    def _generate(
        self,
        messages: List[BaseMessage],
        stop: Optional[List[str]] = None,
        run_manager: Optional[Any] = None,
        **kwargs: Any,
    ) -> ChatResult:
        # Convert LangChain messages to NVIDIA/OpenAI format
        prompt = ""
        for m in messages:
            if isinstance(m, HumanMessage):
                prompt += f"\nUser: {m.content}"
            elif isinstance(m, AIMessage):
                prompt += f"\nAssistant: {m.content}"
            else:
                prompt += f"\n{m.content}"

        headers = {
            "Authorization": f"Bearer {settings.nvidia_api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 1024
        }

        try:
            response = requests.post(
                f"{settings.nvidia_base_url}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            content = result["choices"][0]["message"]["content"]
            
            generation = ChatGeneration(message=AIMessage(content=content))
            return ChatResult(generations=[generation])
        except Exception as e:
            logger.error("NVIDIA Judge LLM call failed", error=str(e))
            raise

    @property
    def _llm_type(self) -> str:
        return "nvidia_judge"
