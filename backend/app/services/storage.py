"""
Escrivão AI — Serviço de Armazenamento (S3/MinIO)
Upload e download de arquivos usando boto3.
"""

import io
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


class StorageService:
    """Gerencia upload/download de arquivos no MinIO (S3-compatível)."""

    def __init__(self):
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name="us-east-1",
        )
        self.bucket = settings.S3_BUCKET_NAME
        self._ensure_bucket()

    def _ensure_bucket(self):
        """Cria o bucket se não existir."""
        try:
            self.client.head_bucket(Bucket=self.bucket)
        except ClientError:
            try:
                self.client.create_bucket(Bucket=self.bucket)
            except ClientError:
                pass  # Pode falhar se MinIO não estiver disponível em dev

    async def upload_file(
        self,
        content: bytes,
        key: str,
        content_type: Optional[str] = "application/octet-stream",
    ) -> str:
        """
        Envia arquivo para o storage.
        Retorna o path/key do objeto.
        """
        self.client.put_object(
            Bucket=self.bucket,
            Key=key,
            Body=io.BytesIO(content),
            ContentType=content_type or "application/octet-stream",
        )
        return key

    async def download_file(self, key: str) -> bytes:
        """Baixa arquivo do storage."""
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()

    async def delete_file(self, key: str) -> None:
        """Remove arquivo do storage."""
        self.client.delete_object(Bucket=self.bucket, Key=key)

    async def file_exists(self, key: str) -> bool:
        """Verifica se arquivo existe."""
        try:
            self.client.head_object(Bucket=self.bucket, Key=key)
            return True
        except ClientError:
            return False
