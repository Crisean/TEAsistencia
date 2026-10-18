"""Configuración central. Todo se controla por variables de entorno (ver .env.example)."""
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent.parent


def _env(name: str, default: str) -> str:
    return os.getenv(name, default)


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, str(default)))


def _float(name: str, default: float) -> float:
    return float(os.getenv(name, str(default)))


def _bool(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in ("1", "true", "si", "sí", "yes")


@dataclass
class Settings:
    # --- identidad ---
    app_name: str = field(default_factory=lambda: _env("APP_NAME", "Asistente TE"))
    # --- datos ---
    corpus_path: Path = field(default_factory=lambda: Path(_env("CORPUS_PATH", str(BASE / "data" / "corpus.txt"))))
    synonyms_path: Path = field(default_factory=lambda: Path(_env("SYNONYMS_PATH", str(BASE / "data" / "sinonimos.txt"))))
    index_path: Path = field(default_factory=lambda: Path(_env("INDEX_PATH", str(BASE / "data" / "index.json"))))
    # --- LLM ("anthropic" | "openai" (compatible) | "none" = solo respuestas directas, 0 tokens) ---
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "anthropic"))
    model_name: str = field(default_factory=lambda: _env("MODEL_NAME", "claude-haiku-5-5"))
    llm_api_key: str = field(default_factory=lambda: _env("LLM_API_KEY", ""))
    llm_base_url: str = field(default_factory=lambda: _env("LLM_BASE_URL", ""))
    llm_timeout_s: float = field(default_factory=lambda: _float("LLM_TIMEOUT_S", 20))
    # --- control de tokens (por consulta) ---
    max_query_chars: int = field(default_factory=lambda: _int("MAX_QUERY_CHARS", 300))
    top_k: int = field(default_factory=lambda: _int("TOP_K", 3))
    max_context_chars: int = field(default_factory=lambda: _int("MAX_CONTEXT_CHARS", 1800))
    max_output_tokens: int = field(default_factory=lambda: _int("MAX_OUTPUT_TOKENS", 250))
    # --- control de tokens (por usuario / global) ---
    user_tokens_day: int = field(default_factory=lambda: _int("USER_TOKENS_DAY", 10000))
    user_queries_day: int = field(default_factory=lambda: _int("USER_QUERIES_DAY", 15))
    ip_multiplier: int = field(default_factory=lambda: _int("IP_MULTIPLIER", 5))
    req_per_min: int = field(default_factory=lambda: _int("REQ_PER_MIN", 8))
    global_tokens_day: int = field(default_factory=lambda: _int("GLOBAL_TOKENS_DAY", 300000))
    # --- recuperación ---
    min_score: float = field(default_factory=lambda: _float("MIN_SCORE", 1.2))
    min_coverage: float = field(default_factory=lambda: _float("MIN_COVERAGE", 0.34))
    direct_enabled: bool = field(default_factory=lambda: _bool("DIRECT_ENABLED", True))
    direct_coverage: float = field(default_factory=lambda: _float("DIRECT_COVERAGE", 0.99))
    direct_ratio: float = field(default_factory=lambda: _float("DIRECT_RATIO", 1.4))
    stale_days: int = field(default_factory=lambda: _int("STALE_DAYS", 365))
    # --- caché ---
    cache_size: int = field(default_factory=lambda: _int("CACHE_SIZE", 500))
    cache_ttl_s: int = field(default_factory=lambda: _int("CACHE_TTL_S", 86400))
    # --- administrador: importación con IA y publicación en GitHub (panel /admin) ---
    import_max_chunks: int = field(default_factory=lambda: _int("IMPORT_MAX_CHUNKS", 6))
    import_chunk_chars: int = field(default_factory=lambda: _int("IMPORT_CHUNK_CHARS", 6000))
    github_token: str = field(default_factory=lambda: _env("GITHUB_TOKEN", ""))
    github_repo: str = field(default_factory=lambda: _env("GITHUB_REPO", ""))  # "usuario/repositorio"
    github_branch: str = field(default_factory=lambda: _env("GITHUB_BRANCH", "main"))
    github_corpus_path: str = field(default_factory=lambda: _env("GITHUB_CORPUS_PATH", "data/corpus.txt"))
    # --- operación / seguridad ---
    admin_token: str = field(default_factory=lambda: _env("ADMIN_TOKEN", ""))
    timezone: str = field(default_factory=lambda: _env("TIMEZONE", "America/Hermosillo"))
    show_admin_link: bool = field(default_factory=lambda: _bool("SHOW_ADMIN_LINK", True))
    reports_per_day: int = field(default_factory=lambda: _int("REPORTS_PER_DAY", 5))
    report_webhook_url: str = field(default_factory=lambda: _env("REPORT_WEBHOOK_URL", ""))
    id_salt: str = field(default_factory=lambda: _env("ID_SALT", "cambia-esto"))
    emergency_text: str = field(default_factory=lambda: _env(
        "EMERGENCY_TEXT",
        "Si es una emergencia, avisa de inmediato a tu supervisor y a la Brigada de Emergencia o Seguridad Patrimonial "
        "de la planta, activa la alarma más cercana y, si es necesario, llama al 911. Esta herramienta no atiende emergencias."))


settings = Settings()


def hoy() -> date:
    """Fecha local de la planta (el servidor de Render corre en UTC)."""
    return datetime.now(ZoneInfo(settings.timezone)).date()
