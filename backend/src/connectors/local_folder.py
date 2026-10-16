"""Files on the local filesystem (recursive). Settings: path, glob (optional, default **/*)."""

from __future__ import annotations

import glob
import hashlib
import os
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict

from .base import Connector, ConnectorError, SourceItem, ext_of, register_connector


@register_connector
class LocalFolderConnector(Connector):
    type = "local_folder"
    description = "Files in a directory on the server (recursive)"
    required_settings = ["path"]

    @property
    def root(self) -> str:
        return os.path.abspath(self.config.settings["path"])

    async def test_connection(self) -> Dict[str, Any]:
        if not os.path.isdir(self.root):
            raise ConnectorError(f"Directory not found: {self.root}")
        count = sum(1 for _ in self._paths())
        return {"status": "ok", "path": self.root, "files": count}

    def _paths(self):
        pattern = self.config.settings.get("glob", "**/*")
        for path in sorted(glob.glob(os.path.join(self.root, pattern), recursive=True)):
            if os.path.isfile(path):
                yield path

    async def list_items(self) -> AsyncIterator[SourceItem]:
        for path in self._paths():
            stat = os.stat(path)
            ext = ext_of(os.path.basename(path))
            rel = os.path.relpath(path, self.root)
            yield SourceItem(
                external_id=rel, title=os.path.basename(path), file_type=ext, url=f"file://{path}",
                modified=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc), size=stat.st_size,
                etag=hashlib.sha1(f"{stat.st_mtime_ns}:{stat.st_size}".encode()).hexdigest(),
                metadata={"relative_path": rel},
            )

    async def fetch(self, item: SourceItem) -> bytes:
        path = os.path.join(self.root, item.external_id)
        if not os.path.abspath(path).startswith(self.root):
            raise ConnectorError("Path traversal rejected")
        with open(path, "rb") as f:
            return f.read()
