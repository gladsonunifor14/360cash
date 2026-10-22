import io
import zipfile

from fastapi import HTTPException, UploadFile

from app.core.config import get_settings

MAX_ZIP_ENTRIES = 2000
MAX_ZIP_TOTAL = 200 * 1024 * 1024


async def read_limited(file: UploadFile) -> bytes:
    limit = get_settings().upload_max_bytes
    data = await file.read(limit + 1)
    if len(data) > limit:
        raise HTTPException(413, f"Arquivo {file.filename} excede o limite de {limit // (1024 * 1024)} MB")
    return data


def expand_zip(filename: str, data: bytes, suffixes: tuple[str, ...]) -> list[tuple[str, bytes]]:
    """Expande ZIP com proteção contra zip bomb e path traversal; retorna [(nome, conteúdo)]."""
    if not filename.lower().endswith(".zip"):
        return [(filename, data)]
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise HTTPException(422, f"ZIP inválido: {filename}") from exc
    infos = [i for i in zf.infolist() if not i.is_dir() and i.filename.lower().endswith(suffixes)]
    if len(infos) > MAX_ZIP_ENTRIES or sum(i.file_size for i in infos) > MAX_ZIP_TOTAL:
        raise HTTPException(413, "ZIP excede os limites de quantidade/tamanho")
    return [(i.filename.rsplit("/", 1)[-1], zf.read(i)) for i in infos]
