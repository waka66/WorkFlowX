from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path

# 计算项目根目录的绝对路径
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    app_name: str = "WorkFlowX"
    app_env: str = "dev"          # dev / test / prod，由环境变量注入，用于日志区分
    app_version: str = "0.1.0"    # 发布排查用
    debug: bool = False

    database_url: str

    upload_dir: Path = str(BASE_DIR / "uploads")

    secret_key: str
    algorithm: str

    # 日志配置
    log_file: str = str(BASE_DIR / "logs" / "app.log")  # 默认日志文件路径，留空字符串可禁用文件日志
    log_level: str = "INFO"  # 日志级别，可选 DEBUG, INFO, WARNING, ERROR, CRITICAL

    # CORS 白名单：必须显式列出来源
    # "['*']" 与 allow_credentials=True 同时使用会被浏览器拒绝
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    # 数据库连接池：外置便于按机器规格调整（4 核时 4 workers × 10 连接 = 40 < PG max_connections）
    db_pool_size: int = 5           # 常驻连接数
    db_max_overflow: int = 5        # 允许的额外连接数
    db_pool_recycle: int = 1800     # 连接回收秒数，避免复用到已被 DB 断开的连接
    db_pool_pre_ping: bool = True   # 取连接前先探活，规避空闲连接被掐导致的偶发 500


    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",  # 使用绝对路径
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()