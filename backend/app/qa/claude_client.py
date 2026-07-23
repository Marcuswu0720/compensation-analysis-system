import anthropic

from ..config import settings

_client: anthropic.Anthropic | None = None


def get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        if not settings.anthropic_api_key:
            raise RuntimeError("未配置 ANTHROPIC_API_KEY，问答功能不可用")
        _client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _client
