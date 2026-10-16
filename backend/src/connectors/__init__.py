"""
Connectors: pull documents (and their permissions) from external systems into Bodham.

    local_folder   files on disk (dev, NFS mounts)
    web            a list of URLs / a sitemap
    s3             S3-compatible object storage (AWS S3, MinIO)
    sharepoint     SharePoint / OneDrive drives via Microsoft Graph (ACL sync)
    google_drive   Google Drive folders (ACL sync)
    confluence     Confluence Cloud spaces (page restrictions → ACL)

A ``Connector`` lists ``SourceItem``s and fetches their bytes; ``ConnectorSyncService``
diffs them against the previous run, creates/updates/removes documents and enqueues
ingestion with the right ACL principals.
"""

from .base import (
    Connector, ConnectorConfig, ConnectorError, SourceItem, get_connector_class, register_connector,
    list_connector_types, resolve_secret,
)
from .sync import ConnectorSyncService, SyncReport

__all__ = [
    "Connector", "ConnectorConfig", "ConnectorError", "SourceItem", "get_connector_class", "register_connector",
    "list_connector_types", "resolve_secret", "ConnectorSyncService", "SyncReport",
]

# register built-in connectors
from . import local_folder, web, s3, microsoft_graph, google_drive, confluence  # noqa: E402,F401
