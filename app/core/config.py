from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

# 计算项目根目录的绝对路径
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    app_name: str = "WorkflowX"
    debug: bool = False

    database_url: str

    upload_dir: Path = str(BASE_DIR / "uploads")

    secret_key: str
    algorithm: str

    # 日志配置
    log_file: str = str(BASE_DIR / "logs" / "app.log")  # 默认日志文件路径，留空字符串可禁用文件日志
    log_level: str = "INFO"  # 日志级别，可选 DEBUG, INFO, WARNING, ERROR, CRITICAL


    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",  # 使用绝对路径
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()