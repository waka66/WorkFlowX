#!/bin/bash
set -e

echo "⏳ 等待数据库就绪..."
until python -c "import socket; socket.create_connection(('${DB_HOST:-db}', ${DB_PORT:-5432}), timeout=1)" 2>/dev/null; do
    echo "数据库未就绪，2 秒后重试..."
    sleep 2
done

echo "✅ 数据库已就绪"

echo "🔄 执行数据库迁移..."
uv run alembic upgrade head

echo "🚀 启动应用..."
exec "$@"