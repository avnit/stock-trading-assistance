from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    anthropic_model: str = Field(default="claude-opus-4-7", alias="ANTHROPIC_MODEL")

    alpaca_api_key: str = Field(default="", alias="ALPACA_API_KEY")
    alpaca_secret_key: str = Field(default="", alias="ALPACA_SECRET_KEY")
    alpaca_paper: bool = Field(default=True, alias="ALPACA_PAPER")

    sec_user_agent: str = Field(default="", alias="SEC_USER_AGENT")

    max_notional_usd: float = Field(default=500.0, alias="ARGO_MAX_NOTIONAL_USD")
    data_dir: Path = Field(default=Path("~/.argo").expanduser(), alias="ARGO_DATA_DIR")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "argo.db"

    @property
    def research_dir(self) -> Path:
        return self.data_dir / "research"

    def ensure_dirs(self) -> None:
        self.data_dir.expanduser().mkdir(parents=True, exist_ok=True)
        self.research_dir.expanduser().mkdir(parents=True, exist_ok=True)


def get_settings() -> Settings:
    s = Settings()
    s.data_dir = Path(str(s.data_dir)).expanduser()
    s.ensure_dirs()
    return s
