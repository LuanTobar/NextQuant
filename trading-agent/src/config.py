from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    nats_url: str = "nats://localhost:4222"
    database_url: str = "postgresql://nexquant:nexquant_dev@localhost:5433/nexquant"
    questdb_url: str = "http://localhost:9010"
    encryption_key: str = ""
    log_level: str = "INFO"
    config_reload_interval_s: int = 60
    position_sync_interval_s: int = 30
    health_port: int = 8090

    # Claude Decision Layer
    anthropic_api_key: str = ""
    claude_model: str = "claude-sonnet-4-20250514"
    claude_max_tokens: int = 600
    claude_timeout_s: float = 12.0
    claude_confidence_threshold: float = 0.65
    claude_min_expected_return: float = 0.0025  # 0.25% minimum post-fees
    claude_circuit_breaker_failures: int = 3
    claude_circuit_breaker_cooldown_s: float = 300.0  # 5 min cooldown
    claude_enabled: bool = True  # Kill switch

    # Alerting — Discord/Slack/custom webhook; empty = disabled
    alert_webhook_url: str = ""

    class Config:
        env_prefix = ""


settings = Settings()
