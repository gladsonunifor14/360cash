"""Armazenamento de arquivos (repositório de documentos).

Implementação local endereçada por conteúdo (sha256). Em produção, montar um volume
cifrado ou trocar por Cloudflare R2 (API S3) mantendo a mesma interface.
"""

import hashlib
from pathlib import Path

from app.core.config import get_settings


def _root() -> Path:
    root = Path(get_settings().storage_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def put(office_id: str, data: bytes) -> tuple[str, str]:
    """Grava o conteúdo e retorna (storage_key, sha256)."""
    sha = hashlib.sha256(data).hexdigest()
    key = f"{office_id}/{sha[:2]}/{sha}"
    path = _root() / key
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(data)
    return key, sha


def get(storage_key: str) -> bytes:
    root = _root()
    path = (root / storage_key).resolve()
    if root not in path.parents:  # proteção contra path traversal
        raise FileNotFoundError(storage_key)
    return path.read_bytes()
