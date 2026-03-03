"""
MinIO Object Storage Service.

Provides S3-compatible object storage for:
- Original document storage
- Parsed assets (tables, images, charts)
- Document backups
"""

import io
from typing import Optional, BinaryIO, List, Dict, Any
from datetime import timedelta

from minio import Minio
from minio.error import S3Error

from src.core.config import settings
from src.core.logger import get_logger

logger = get_logger(__name__)


class ObjectStorageService:
    """
    MinIO S3-compatible object storage client.
    
    Handles document and asset storage with automatic bucket creation
    and lifecycle management.
    """
    
    def __init__(
        self,
        endpoint: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        secure: Optional[bool] = None
    ):
        """
        Initialize MinIO client.
        
        Args:
            endpoint: MinIO endpoint (default from settings)
            access_key: MinIO access key (default from settings)
            secret_key: MinIO secret key (default from settings)
            secure: Use HTTPS (default from settings)
        """
        self.endpoint = endpoint or settings.minio_endpoint
        self.access_key = access_key or settings.minio_access_key
        self.secret_key = secret_key or settings.minio_secret_key
        self.secure = secure if secure is not None else settings.minio_secure
        
        self.bucket_documents = settings.minio_bucket_documents
        self.bucket_assets = settings.minio_bucket_assets
        
        self.client = Minio(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure
        )
        
        logger.info(
            "MinIO client initialized",
            endpoint=self.endpoint,
            secure=self.secure
        )
    
    async def ensure_buckets_exist(self) -> None:
        """
        Ensure required buckets exist, create if not.
        Should be called during application startup.
        """
        buckets = [self.bucket_documents, self.bucket_assets]
        
        for bucket_name in buckets:
            try:
                if not self.client.bucket_exists(bucket_name):
                    self.client.make_bucket(bucket_name)
                    logger.info(f"Created bucket: {bucket_name}")
                else:
                    logger.debug(f"Bucket exists: {bucket_name}")
            except S3Error as e:
                logger.error(f"Failed to ensure bucket {bucket_name}: {e}")
                raise
    
    # ==========================================
    # Document Operations
    # ==========================================
    
    async def upload_document(
        self,
        document_id: str,
        file_data: BinaryIO,
        filename: str,
        content_type: str = "application/octet-stream",
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Upload original document to MinIO.
        
        Args:
            document_id: Unique document identifier
            file_data: File binary data
            filename: Original filename
            content_type: MIME type
            metadata: Optional metadata dict
            
        Returns:
            Object path in MinIO
        """
        object_name = f"originals/{document_id}/{filename}"
        
        try:
            # Get file size
            file_data.seek(0, 2)  # Seek to end
            file_size = file_data.tell()
            file_data.seek(0)  # Seek back to start
            
            self.client.put_object(
                bucket_name=self.bucket_documents,
                object_name=object_name,
                data=file_data,
                length=file_size,
                content_type=content_type,
                metadata=metadata or {}
            )
            
            logger.info(
                "Document uploaded",
                document_id=document_id,
                filename=filename,
                size=file_size
            )
            
            return object_name
            
        except S3Error as e:
            logger.error(f"Failed to upload document {document_id}: {e}")
            raise
    
    async def get_document(
        self,
        document_id: str,
        filename: str
    ) -> bytes:
        """
        Retrieve original document from MinIO.
        
        Args:
            document_id: Document identifier
            filename: Original filename
            
        Returns:
            Document bytes
        """
        object_name = f"originals/{document_id}/{filename}"
        
        try:
            response = self.client.get_object(
                bucket_name=self.bucket_documents,
                object_name=object_name
            )
            data = response.read()
            response.close()
            response.release_conn()
            
            logger.debug(f"Retrieved document: {object_name}")
            return data
            
        except S3Error as e:
            logger.error(f"Failed to get document {object_name}: {e}")
            raise
    
    async def delete_document(self, document_id: str) -> None:
        """
        Delete all files associated with a document.
        
        Args:
            document_id: Document identifier
        """
        prefix = f"originals/{document_id}/"
        
        try:
            # List and delete all objects with this prefix
            objects = self.client.list_objects(
                bucket_name=self.bucket_documents,
                prefix=prefix,
                recursive=True
            )
            
            for obj in objects:
                self.client.remove_object(
                    bucket_name=self.bucket_documents,
                    object_name=obj.object_name
                )
                logger.debug(f"Deleted: {obj.object_name}")
            
            logger.info(f"Deleted all files for document: {document_id}")
            
        except S3Error as e:
            logger.error(f"Failed to delete document {document_id}: {e}")
            raise
    
    # ==========================================
    # Parsed Asset Operations
    # ==========================================
    
    async def upload_parsed_asset(
        self,
        document_id: str,
        asset_type: str,
        asset_id: str,
        data: bytes,
        content_type: str = "application/json",
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """
        Upload parsed asset (table, chart, image) to MinIO.
        
        Args:
            document_id: Parent document ID
            asset_type: Type of asset (tables, graphics, text_blocks)
            asset_id: Unique asset identifier
            data: Asset data bytes
            content_type: MIME type
            metadata: Optional metadata
            
        Returns:
            Object path in MinIO
        """
        object_name = f"{document_id}/{asset_type}/{asset_id}"
        
        try:
            data_stream = io.BytesIO(data)
            
            self.client.put_object(
                bucket_name=self.bucket_assets,
                object_name=object_name,
                data=data_stream,
                length=len(data),
                content_type=content_type,
                metadata=metadata or {}
            )
            
            logger.info(
                "Parsed asset uploaded",
                document_id=document_id,
                asset_type=asset_type,
                asset_id=asset_id
            )
            
            return object_name
            
        except S3Error as e:
            logger.error(f"Failed to upload asset {object_name}: {e}")
            raise
    
    async def get_parsed_asset(
        self,
        document_id: str,
        asset_type: str,
        asset_id: str
    ) -> bytes:
        """
        Retrieve parsed asset from MinIO.
        
        Args:
            document_id: Parent document ID
            asset_type: Type of asset
            asset_id: Asset identifier
            
        Returns:
            Asset bytes
        """
        object_name = f"{document_id}/{asset_type}/{asset_id}"
        
        try:
            response = self.client.get_object(
                bucket_name=self.bucket_assets,
                object_name=object_name
            )
            data = response.read()
            response.close()
            response.release_conn()
            
            return data
            
        except S3Error as e:
            logger.error(f"Failed to get asset {object_name}: {e}")
            raise
    
    async def list_parsed_assets(
        self,
        document_id: str,
        asset_type: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        List all parsed assets for a document.
        
        Args:
            document_id: Document identifier
            asset_type: Optional filter by asset type
            
        Returns:
            List of asset metadata dicts
        """
        prefix = f"{document_id}/"
        if asset_type:
            prefix = f"{document_id}/{asset_type}/"
        
        try:
            objects = self.client.list_objects(
                bucket_name=self.bucket_assets,
                prefix=prefix,
                recursive=True
            )
            
            assets = []
            for obj in objects:
                assets.append({
                    "object_name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified,
                    "etag": obj.etag
                })
            
            return assets
            
        except S3Error as e:
            logger.error(f"Failed to list assets for {document_id}: {e}")
            raise
    
    async def delete_parsed_assets(self, document_id: str) -> None:
        """
        Delete all parsed assets for a document.
        
        Args:
            document_id: Document identifier
        """
        prefix = f"{document_id}/"
        
        try:
            objects = self.client.list_objects(
                bucket_name=self.bucket_assets,
                prefix=prefix,
                recursive=True
            )
            
            for obj in objects:
                self.client.remove_object(
                    bucket_name=self.bucket_assets,
                    object_name=obj.object_name
                )
            
            logger.info(f"Deleted all assets for document: {document_id}")
            
        except S3Error as e:
            logger.error(f"Failed to delete assets for {document_id}: {e}")
            raise
    
    # ==========================================
    # Presigned URLs
    # ==========================================
    
    def get_presigned_download_url(
        self,
        bucket_name: str,
        object_name: str,
        expires: timedelta = timedelta(hours=1)
    ) -> str:
        """
        Generate a presigned URL for downloading an object.
        
        Args:
            bucket_name: Bucket name
            object_name: Object path
            expires: URL expiration time
            
        Returns:
            Presigned download URL
        """
        try:
            url = self.client.presigned_get_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=expires
            )
            return url
        except S3Error as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise
    
    def get_presigned_upload_url(
        self,
        bucket_name: str,
        object_name: str,
        expires: timedelta = timedelta(hours=1)
    ) -> str:
        """
        Generate a presigned URL for uploading an object.
        
        Args:
            bucket_name: Bucket name
            object_name: Object path
            expires: URL expiration time
            
        Returns:
            Presigned upload URL
        """
        try:
            url = self.client.presigned_put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                expires=expires
            )
            return url
        except S3Error as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise
    
    # ==========================================
    # Convenience Methods (used by ingestion pipeline)
    # ==========================================

    def upload_file(
        self,
        file_path: str,
        bucket_name: str,
        object_name: str,
        metadata: Optional[Dict[str, str]] = None,
    ) -> str:
        """
        Upload a local file to MinIO by path.

        Args:
            file_path: Local file path
            bucket_name: Target bucket
            object_name: Object key in the bucket
            metadata: Optional metadata dict

        Returns:
            The object name stored
        """
        import os
        import mimetypes

        # Ensure bucket exists
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
        except S3Error:
            pass  # bucket may already exist

        content_type = mimetypes.guess_type(file_path)[0] or "application/octet-stream"
        file_size = os.path.getsize(file_path)

        with open(file_path, "rb") as f:
            self.client.put_object(
                bucket_name=bucket_name,
                object_name=object_name,
                data=f,
                length=file_size,
                content_type=content_type,
                metadata=metadata or {},
            )

        logger.info("File uploaded", bucket=bucket_name, object=object_name, size=file_size)
        return object_name

    def put_json(
        self,
        bucket_name: str,
        object_name: str,
        data: Dict[str, Any],
    ) -> str:
        """
        Serialize a dict to JSON and store in MinIO.

        Args:
            bucket_name: Target bucket
            object_name: Object key
            data: Dictionary to serialize

        Returns:
            The object name stored
        """
        import json

        # Ensure bucket exists
        try:
            if not self.client.bucket_exists(bucket_name):
                self.client.make_bucket(bucket_name)
        except S3Error:
            pass

        json_bytes = json.dumps(data, default=str).encode("utf-8")
        stream = io.BytesIO(json_bytes)

        self.client.put_object(
            bucket_name=bucket_name,
            object_name=object_name,
            data=stream,
            length=len(json_bytes),
            content_type="application/json",
        )

        logger.debug("JSON stored", bucket=bucket_name, object=object_name)
        return object_name

    def get_json(
        self,
        bucket_name: str,
        object_name: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieve and deserialize a JSON object from MinIO.

        Args:
            bucket_name: Source bucket
            object_name: Object key

        Returns:
            Deserialized dict, or None on failure
        """
        import json

        try:
            response = self.client.get_object(
                bucket_name=bucket_name,
                object_name=object_name,
            )
            raw = response.read()
            response.close()
            response.release_conn()
            return json.loads(raw)
        except S3Error as e:
            logger.warning(f"get_json failed for {object_name}: {e}")
            return None

    def delete_object(
        self,
        bucket_name: str,
        object_name_or_prefix: str,
    ) -> None:
        """
        Delete an object (or all objects under a prefix) from MinIO.

        If the name ends with '/' it is treated as a prefix and all
        matching objects are removed.

        Args:
            bucket_name: Bucket name
            object_name_or_prefix: Object key or prefix ending with '/'
        """
        try:
            if object_name_or_prefix.endswith("/"):
                # Delete all objects under the prefix
                objects = self.client.list_objects(
                    bucket_name=bucket_name,
                    prefix=object_name_or_prefix,
                    recursive=True,
                )
                for obj in objects:
                    self.client.remove_object(bucket_name, obj.object_name)
                logger.info("Prefix deleted", bucket=bucket_name, prefix=object_name_or_prefix)
            else:
                self.client.remove_object(bucket_name, object_name_or_prefix)
                logger.info("Object deleted", bucket=bucket_name, object=object_name_or_prefix)
        except S3Error as e:
            logger.warning(f"delete_object failed: {e}")

    # ==========================================
    # Health Check
    # ==========================================
    
    def is_healthy(self) -> bool:
        """
        Check if MinIO connection is healthy.
        
        Returns:
            True if healthy, False otherwise
        """
        try:
            self.client.list_buckets()
            return True
        except Exception as e:
            logger.warning(f"MinIO health check failed: {e}")
            return False
