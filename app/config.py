from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    BOT_TOKEN: str
    ANTHROPIC_API_KEY: str
    DATABASE_URL: str = "sqlite+aiosqlite:///./data/dorilar.db"
    ADMIN_IDS: str = ""
    TZ: str = "Asia/Tashkent"

    @property
    def admin_ids(self) -> list[int]:
        if not self.ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]


settings = Settings()
