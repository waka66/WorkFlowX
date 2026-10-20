# ============ 基础镜像 ============
FROM python:3.12-slim

RUN sed -i \
    -e 's|deb.debian.org/debian|mirrors.tencentyun.com/debian|g' \
    -e 's|deb.debian.org/debian-security|mirrors.tencentyun.com/debian-security|g' \
    /etc/apt/sources.list.d/debian.sources

# 设置时区、防止 Python 输出缓冲
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8\
    UV_DEFAULT_INDEX=http://mirrors.tencentyun.com/pypi/simple

# 设置工作目录
WORKDIR /app

# ============ 安装系统依赖 ============
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ============ 安装 Python 依赖 ============
# 先复制依赖清单，利用 Docker 缓存
COPY pyproject.toml ./
COPY uv.lock* ./

# 安装 uv（如果你的 pyproject 用 uv 管理）
RUN pip install --no-cache-dir -i https://mirrors.cloud.tencent.com/pypi/simple uv

# 用 uv 安装依赖（生成虚拟环境在 /app/.venv）
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# ============ 复制项目代码 ============
COPY . .

# ============ 启动脚本 ============
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# ============ 声明端口 ============
EXPOSE 8000

# ============ 健康检查 ============
# 用存活探针而非就绪探针：DB 抖动不应导致容器被反复重启
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
  CMD curl -f http://localhost:8000/healthz || exit 1

# ============ 入口 ============
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]