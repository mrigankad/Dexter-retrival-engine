from __future__ import annotations

import os
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, Type

from pydantic import BaseModel, Field

from src.core.config import settings


class ConnectorError(RuntimeError):
    pass


def resolve_secret(value: Optional[str]) -> Optional[str]:
    """Config values of the form ``env:VAR`` are read from the environment at use time."""
    if value and isinstance(value, str) and value.startswith("env:"):
        return os.environ.get(value[4:], "")
    return value


class SourceItem(BaseModel):
    """A document discovered in a source system."""
    external_id: str
    title: str
    file_type: str                                  # extension without dot (pdf, docx, html, ...)
    url: Optional[str] = None
    modified: Optional[datetime] = None
    size: Optional[int] = None
    etag: Optional[str] = None
    principals: List[str] = Field(default_factory=list)   # source-side ACL mapped to Bodham principals
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def version_key(self) -> str:
        return self.etag or (self.modified.isoformat() if self.modified else "") + f":{self.size or ''}"

    def supported(self) -> bool:
        return self.file_type.lower() in settings.allowed_extensions_list


class ConnectorConfig(BaseModel):
    """Persisted connector definition (secrets referenced as ``env:VAR``)."""
    id: Optional[str] = None
    tenant_id: Optional[str] = None
    type: str
    name: str
    settings: Dict[str, Any] = Field(default_factory=dict)
    visibility: str = "tenant"                      # private | tenant | public | source
    shared_groups: List[str] = Field(default_factory=list)
    inherit_source_acl: bool = True                 # add source principals to the document ACL
    delete_missing: bool = True                     # remove documents that disappeared at the source
    enabled: bool = True
    schedule_minutes: Optional[int] = None
    delta_cursor: Optional[str] = None              # connector-specific incremental cursor

    def secret(self, key: str, default: str = "") -> str:
        return resolve_secret(self.settings.get(key)) or default


class Connector(ABC):
    type: str = "base"
    description: str = ""
    required_settings: List[str] = []

    def __init__(self, config: ConnectorConfig):
        self.config = config
        missing = [k for k in self.required_settings if not config.settings.get(k)]
        if missing:
            raise ConnectorError(f"{self.type} connector requires settings: {', '.join(missing)}")

    @abstractmethod
    async def test_connection(self) -> Dict[str, Any]: ...

    @abstractmethod
    def list_items(self) -> AsyncIterator[SourceItem]: ...

    @abstractmethod
    async def fetch(self, item: SourceItem) -> bytes: ...

    def new_cursor(self) -> Optional[str]:
        """Incremental cursor to persist after a successful sync (delta links etc.)."""
        return None

    async def aclose(self) -> None:
        return None


_registry: Dict[str, Type[Connector]] = {}


def register_connector(cls: Type[Connector]) -> Type[Connector]:
    _registry[cls.type] = cls
    return cls


def get_connector_class(type_name: str) -> Type[Connector]:
    if type_name not in _registry:
        raise ConnectorError(f"Unknown connector type '{type_name}'. Available: {sorted(_registry)}")
    return _registry[type_name]


def list_connector_types() -> List[Dict[str, Any]]:
    return [{"type": t, "description": c.description, "required_settings": c.required_settings} for t, c in sorted(_registry.items())]


def ext_of(name: str, content_type: Optional[str] = None) -> str:
    if "." in name:
        ext = name.rsplit(".", 1)[-1].lower()
        if ext in settings.allowed_extensions_list:
            return ext
    ct = (content_type or "").split(";")[0].strip().lower()
    return {
        "application/pdf": "pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
        "text/html": "html", "application/xhtml+xml": "html",
        "text/markdown": "md", "text/plain": "txt", "text/csv": "csv",
    }.get(ct, name.rsplit(".", 1)[-1].lower() if "." in name else "")
