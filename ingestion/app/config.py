from __future__ import annotations

import os


class Settings:
    """Central runtime configuration, read once from the environment."""

    def __init__(self) -> None:
        self.api_key: str = os.environ.get("MCP_INSIGHT_API_KEY", "")
        self.classifier_url: str = os.environ.get(
            "CLASSIFIER_URL", "http://classifier:8100"
        ).rstrip("/")
        self.slack_webhook_url: str = os.environ.get("SLACK_WEBHOOK_URL", "")
        self.alert_score_threshold: float = float(
            os.environ.get("ALERT_SCORE_THRESHOLD", "60")
        )
        self.alert_cooldown_s: float = float(
            os.environ.get("ALERT_COOLDOWN_SECONDS", str(15 * 60))
        )
        self.anomaly_zscore_threshold: float = float(
            os.environ.get("ANOMALY_ZSCORE_THRESHOLD", "3.0")
        )
        self.anomaly_history_buckets: int = int(
            os.environ.get("ANOMALY_HISTORY_BUCKETS", "8")
        )
        self.anomaly_min_history_buckets: int = int(
            os.environ.get("ANOMALY_MIN_HISTORY_BUCKETS", "3")
        )
        origins = os.environ.get("DASHBOARD_ORIGINS", "http://localhost:5173,http://localhost:4173")
        self.dashboard_origins: list[str] = [o.strip() for o in origins.split(",") if o.strip()]

        self.rate_limit_ingest_per_minute: int = int(
            os.environ.get("RATE_LIMIT_INGEST_PER_MINUTE", "120")
        )
        self.rate_limit_read_per_minute: int = int(
            os.environ.get("RATE_LIMIT_READ_PER_MINUTE", "300")
        )

    @property
    def auth_enabled(self) -> bool:
        return bool(self.api_key)


settings = Settings()
