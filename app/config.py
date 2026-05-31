from pydantic_settings import BaseSettings
from typing import List


class Settings(BaseSettings):
    BOT_TOKEN: str
    DATABASE_URL: str
    ADMIN_IDS: str = ""
    TZ: str = "Asia/Tashkent"

    @property
    def admin_ids(self) -> List[int]:
        if not self.ADMIN_IDS:
            return []
        return [int(x.strip()) for x in self.ADMIN_IDS.split(",") if x.strip()]

    class Config:
        env_file = ".env"


settings = Settings()
