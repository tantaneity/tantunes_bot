from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    BOT_TOKEN: str
    REDIS_URL: str = "redis://redis:6379"
    UPLOAD_CHANNEL_ID: int | None = None
    DB_PATH: str = "/app/data/tantunes.db"
    ADMIN_IDS: str = ""
    SPOTIFY_CLIENT_ID: str = ""
    SPOTIFY_CLIENT_SECRET: str = ""
    DEEZER_ARL: str = ""

    @property
    def spotify_enabled(self) -> bool:
        return bool(self.SPOTIFY_CLIENT_ID and self.SPOTIFY_CLIENT_SECRET)

    @property
    def deezer_enabled(self) -> bool:
        return bool(self.DEEZER_ARL)

    @property
    def admin_ids(self) -> list[int]:
        return [int(x) for x in self.ADMIN_IDS.split(",") if x.strip().isdigit()]


settings = Settings()
