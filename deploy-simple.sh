#!/bin/bash

# Docker Compose remote deploy script.
# Usage:
#   ./build-and-push.sh
#   ./deploy-simple.sh [remote_host]

set -euo pipefail

REMOTE_HOST="${1:-your-server.example.com}"
REMOTE_USER="${REMOTE_USER:-root}"
REMOTE_PATH="${REMOTE_PATH:-/opt/specrag}"
REMOTE_DATA_DIR="${REMOTE_DATA_DIR:-${REMOTE_PATH}}"
REMOTE_PORT="${REMOTE_PORT:-5002}"
COMPOSE_FILE="docker-compose.prod.yml"
KB_STORAGE_MODE="${KB_STORAGE_MODE:-enterprise}"
KB_TENANT_ID="${KB_TENANT_ID:-default}"
KB_QDRANT_COLLECTION="${KB_QDRANT_COLLECTION:-specrag_units}"

if [ "${KB_STORAGE_MODE}" = "enterprise" ]; then
    if [ -z "${KB_POSTGRES_DSN:-}" ]; then
        echo "❌ KB_STORAGE_MODE=enterprise 需要设置 KB_POSTGRES_DSN"
        exit 1
    fi
    if [ -z "${KB_QDRANT_URL:-}" ]; then
        echo "❌ KB_STORAGE_MODE=enterprise 需要设置 KB_QDRANT_URL"
        exit 1
    fi
fi

if [ ! -f ".docker-version" ]; then
    echo "❌ 请先运行 ./build-and-push.sh"
    exit 1
fi

if [ ! -f "${COMPOSE_FILE}" ]; then
    echo "❌ 缺少 ${COMPOSE_FILE}"
    exit 1
fi

IMAGE_NAME=$(cat .docker-version)

echo "========================================================================"
echo "  SpecRAG Docker Compose 部署"
echo "========================================================================"
echo "  目标服务器: ${REMOTE_HOST}"
echo "  远端目录:   ${REMOTE_PATH}"
echo "  数据目录:   ${REMOTE_DATA_DIR}"
echo "  镜像:       ${IMAGE_NAME}"
echo "  端口:       ${REMOTE_PORT}"
echo "  KB存储:     ${KB_STORAGE_MODE}"
echo "========================================================================"

echo "📤 上传 compose 文件..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" "mkdir -p '${REMOTE_PATH}' '${REMOTE_DATA_DIR}/data' '${REMOTE_DATA_DIR}/uploads' '${REMOTE_DATA_DIR}/outputs' '${REMOTE_DATA_DIR}/logs' '${REMOTE_DATA_DIR}/config'"
scp "${COMPOSE_FILE}" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/${COMPOSE_FILE}"

if [ -f "config/OAI_CONFIG_LIST" ]; then
    echo "📤 上传模型配置..."
    scp "config/OAI_CONFIG_LIST" "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_DATA_DIR}/config/OAI_CONFIG_LIST"
else
    echo "⚠️  本地 config/OAI_CONFIG_LIST 不存在，请确认远端已有 ${REMOTE_DATA_DIR}/config/OAI_CONFIG_LIST"
fi

echo "📤 写入远端 .env..."
cat > /tmp/specrag-deploy.env << EOF
SPECRAG_IMAGE=${IMAGE_NAME}
SPECRAG_DATA_DIR=${REMOTE_DATA_DIR}
SPECRAG_PORT=${REMOTE_PORT}
LOG_LEVEL=INFO
KB_STORAGE_MODE=${KB_STORAGE_MODE}
KB_TENANT_ID=${KB_TENANT_ID}
KB_POSTGRES_DSN=${KB_POSTGRES_DSN:-}
KB_QDRANT_URL=${KB_QDRANT_URL:-}
KB_QDRANT_COLLECTION=${KB_QDRANT_COLLECTION}
EOF
scp /tmp/specrag-deploy.env "${REMOTE_USER}@${REMOTE_HOST}:${REMOTE_PATH}/.env"
rm -f /tmp/specrag-deploy.env

echo "🚀 远端拉取并启动容器..."
ssh "${REMOTE_USER}@${REMOTE_HOST}" << EOF
set -e
cd "${REMOTE_PATH}"

if docker compose version >/dev/null 2>&1; then
  COMPOSE="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE="docker-compose"
else
  echo "❌ 远端未安装 docker compose 或 docker-compose"
  exit 1
fi

echo "🧹 清理旧版部署残留..."
if [ -f docker-compose.simple.yml ]; then
  \$COMPOSE -f docker-compose.simple.yml down || true
fi
docker rm -f specrag >/dev/null 2>&1 || true

echo "📦 拉取镜像: ${IMAGE_NAME}"
\$COMPOSE -f ${COMPOSE_FILE} pull

echo "🛑 停止旧容器..."
\$COMPOSE -f ${COMPOSE_FILE} down || true

echo "🚀 启动新容器..."
\$COMPOSE -f ${COMPOSE_FILE} up -d --no-build --force-recreate

echo "⏳ 等待服务启动..."
sleep 10

echo "📊 部署状态"
\$COMPOSE -f ${COMPOSE_FILE} ps

echo "📝 最新日志"
\$COMPOSE -f ${COMPOSE_FILE} logs --tail 30
EOF

echo ""
echo "========================================================================"
echo "✅ 部署完成"
echo "========================================================================"
echo "🌐 访问地址: http://${REMOTE_HOST}:${REMOTE_PORT}"
echo "📝 查看日志: ssh ${REMOTE_USER}@${REMOTE_HOST} 'cd ${REMOTE_PATH} && docker compose -f ${COMPOSE_FILE} logs -f'"
echo "========================================================================"
