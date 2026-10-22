"""Rate limit simples de janela deslizante em memória.

Para múltiplas réplicas, troque `_store` por Redis/Cloudflare (a borda já deve ter
regras WAF de rate limit para /auth/*; esta camada é defesa em profundidade).
"""

import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

_store: dict[str, deque[float]] = defaultdict(deque)
_lock = threading.Lock()


def client_ip(request: Request) -> str:
    # Atrás do Cloudflare o IP real vem em CF-Connecting-IP
    return request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")


def hit(key: str, limit: int, window_seconds: int = 60) -> None:
    now = time.monotonic()
    with _lock:
        q = _store[key]
        while q and now - q[0] > window_seconds:
            q.popleft()
        if len(q) >= limit:
            raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Muitas tentativas. Aguarde um minuto.")
        q.append(now)


def auth_rate_limit(request: Request) -> None:
    hit(f"{client_ip(request)}:{request.url.path}", get_settings().rate_limit_auth_per_minute)


def reset() -> None:
    with _lock:
        _store.clear()
