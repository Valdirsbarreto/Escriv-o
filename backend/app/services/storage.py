"""
Escrivão AI — Serviço de Armazenamento (S3/MinIO + Supabase Storage)
Upload e download de arquivos usando boto3. Signed URLs via Supabase REST quando disponível.
"""

import io
import logging
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)


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

    def generate_download_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        """
        Gera URL de download temporária.
        Usa a API REST do Supabase quando SUPABASE_URL estiver configurado (produção),
        caso contrário usa presigned URL do boto3 (MinIO/dev).
        """
        # Supabase Storage REST API (produção)
        if settings.SUPABASE_URL and settings.SUPABASE_SERVICE_KEY:
            try:
                import httpx
                # Usa o bucket de onde o arquivo foi fisicamente salvo (escalado pelo boto3 fallback)
                supabase_bucket = self.bucket
                
                # Remove o prefixo do bucket da key se ele tiver sido salvo no banco com path completo
                actual_key = key
                if actual_key.startswith(f"{supabase_bucket}/"):
                    actual_key = actual_key[len(supabase_bucket)+1:]

                url = f"{settings.SUPABASE_URL}/storage/v1/object/sign/{supabase_bucket}/{actual_key}"
                resp = httpx.post(
                    url,
                    headers={
                        "Authorization": f"Bearer {settings.SUPABASE_SERVICE_KEY}",
                        "apikey": settings.SUPABASE_SERVICE_KEY,
                        "Content-Type": "application/json",
                    },
                    json={"expiresIn": expires_in},
                    timeout=10,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    signed_path = data.get("signedURL") or data.get("signedUrl") or ""
                    if signed_path:
                        # signedURL já é o path relativo; montar URL completa com /storage/v1
                        if signed_path.startswith("http"):
                            return signed_path
                        # Garante que /storage/v1 seja inserido antes de /object/...
                        base_url = settings.SUPABASE_URL.rstrip('/')
                        if not signed_path.startswith('/'):
                            signed_path = '/' + signed_path
                        return f"{base_url}/storage/v1{signed_path}"
                logger.warning(f"[STORAGE] Supabase signed URL falhou: {resp.status_code} {resp.text[:200]}")
            except Exception as e:
                logger.warning(f"[STORAGE] Erro ao gerar Supabase signed URL: {e}")

        # Fallback: boto3 presigned URL (MinIO / dev)
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires_in,
            )
        except Exception as e:
            logger.warning(f"[STORAGE] Erro ao gerar presigned URL boto3: {e}")
            return None
