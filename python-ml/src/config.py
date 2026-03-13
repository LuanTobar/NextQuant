from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    nats_url: str = "nats://localhost:4222"
    questdb_url: str = "http://localhost:9000"
    log_level: str = "INFO"
    model_retrain_interval: int = 100
    causal_lookback: int = 20
    health_port: int = 8086
    model_save_path: str = "/app/models"

    class Config:
        env_prefix = ""


settings = Settings()
