#!/bin/bash

# Docker镜像构建和推送脚本
# 自动生成UUID版本号，推送到指定镜像仓库

set -e  # 遇到错误立即退出

# 配置
REGISTRY="${REGISTRY:-your-registry.example.com/your-namespace}"
IMAGE_NAME="specrag"
DOCKERFILE="${DOCKERFILE:-Dockerfile.prod}"
PLATFORM="${PLATFORM:-linux/amd64}"

# 生成UUID作为版本号
if command -v uuidgen >/dev/null 2>&1; then
    # macOS/Linux系统有uuidgen命令
    VERSION=$(uuidgen | tr '[:upper:]' '[:lower:]')
else
    # 使用Python生成UUID（兼容性更好）
    VERSION=$(python3 -c "import uuid; print(str(uuid.uuid4()))")
fi

# 完整镜像名
FULL_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}:${VERSION}"
LATEST_IMAGE_NAME="${REGISTRY}/${IMAGE_NAME}:latest"

echo "🚀 开始构建Docker镜像..."
echo "📦 镜像名称: ${FULL_IMAGE_NAME}"
echo "🔖 版本号: ${VERSION}"
echo "📄 Dockerfile: ${DOCKERFILE}"
echo "🧱 平台: ${PLATFORM}"
echo ""

# 构建镜像
echo "🔨 构建镜像中..."
docker build --platform ${PLATFORM} -f ${DOCKERFILE} -t ${FULL_IMAGE_NAME} -t ${LATEST_IMAGE_NAME} .

if [ $? -eq 0 ]; then
    echo "✅ 镜像构建成功"
else
    echo "❌ 镜像构建失败"
    exit 1
fi

echo ""
echo "📤 推送镜像到镜像仓库..."

# 推送带版本号的镜像
echo "推送版本镜像: ${FULL_IMAGE_NAME}"
docker push ${FULL_IMAGE_NAME}

if [ $? -eq 0 ]; then
    echo "✅ 版本镜像推送成功"
else
    echo "❌ 版本镜像推送失败"
    exit 1
fi

# 推送latest镜像
echo "推送latest镜像: ${LATEST_IMAGE_NAME}"
docker push ${LATEST_IMAGE_NAME}

if [ $? -eq 0 ]; then
    echo "✅ latest镜像推送成功"
else
    echo "❌ latest镜像推送失败"
    exit 1
fi

echo ""
echo "🎉 构建和推送完成！"
echo "📋 镜像信息:"
echo "   版本镜像: ${FULL_IMAGE_NAME}"
echo "   最新镜像: ${LATEST_IMAGE_NAME}"
echo ""
echo "📝 部署命令:"
echo "   docker pull ${FULL_IMAGE_NAME}"
echo "   docker pull ${LATEST_IMAGE_NAME}"
echo ""
echo "💾 保存版本信息..."
echo "${FULL_IMAGE_NAME}" > .docker-version

echo "✅ 构建完成！镜像: ${FULL_IMAGE_NAME}"
