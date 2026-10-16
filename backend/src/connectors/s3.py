"""S3-compatible object storage. Settings: bucket, prefix, endpoint_url (MinIO), region,
access_key_id / secret_access_key (env:... references). Requires boto3."""

from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator, Dict

from .base import Connector, ConnectorError, SourceItem, ext_of, register_connector


@register_connector
class S3Connector(Connector):
    type = "s3"
    description = "AWS S3 or S3-compatible bucket (MinIO)"
    required_settings = ["bucket"]

    def __init__(self, config, client: Any = None):
        super().__init__(config)
        self._client = client

    def _s3(self):
        if self._client is None:
            try:
                import boto3  # optional dependency
            except ImportError as exc:
                raise ConnectorError("boto3 is required for the s3 connector (pip install boto3)") from exc
            s = self.config.settings
            self._client = boto3.client(
                "s3", endpoint_url=s.get("endpoint_url") or None, region_name=s.get("region") or None,
                aws_access_key_id=self.config.secret("access_key_id") or None,
                aws_secret_access_key=self.config.secret("secret_access_key") or None,
            )
        return self._client

    async def test_connection(self) -> Dict[str, Any]:
        s3 = self._s3()
        resp = await asyncio.to_thread(s3.list_objects_v2, Bucket=self.config.settings["bucket"],
                                       Prefix=self.config.settings.get("prefix", ""), MaxKeys=1)
        return {"status": "ok", "bucket": self.config.settings["bucket"], "sample": [o["Key"] for o in resp.get("Contents", [])]}

    async def list_items(self) -> AsyncIterator[SourceItem]:
        s3 = self._s3()
        bucket, prefix = self.config.settings["bucket"], self.config.settings.get("prefix", "")
        token = None
        while True:
            kwargs = {"Bucket": bucket, "Prefix": prefix}
            if token:
                kwargs["ContinuationToken"] = token
            resp = await asyncio.to_thread(s3.list_objects_v2, **kwargs)
            for obj in resp.get("Contents", []):
                key = obj["Key"]
                if key.endswith("/"):
                    continue
                yield SourceItem(
                    external_id=key, title=key.rsplit("/", 1)[-1], file_type=ext_of(key), url=f"s3://{bucket}/{key}",
                    modified=obj.get("LastModified"), size=obj.get("Size"), etag=(obj.get("ETag") or "").strip('"'),
                )
            if not resp.get("IsTruncated"):
                break
            token = resp.get("NextContinuationToken")

    async def fetch(self, item: SourceItem) -> bytes:
        resp = await asyncio.to_thread(self._s3().get_object, Bucket=self.config.settings["bucket"], Key=item.external_id)
        return resp["Body"].read()
