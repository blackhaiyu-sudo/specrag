#!/bin/bash

# SpecRAG 应用停止脚本
# 用于优雅关闭正在运行的应用程序

echo "正在停止 SpecRAG..."

# 查找并停止 Python 应用进程
echo "📋 查找正在运行的应用进程..."

# 查找 app.py 进程
APP_PIDS=$(ps aux | grep -E "python.*app\.py" | grep -v grep | awk '{print $2}')

if [ -z "$APP_PIDS" ]; then
    echo "ℹ️  未找到正在运行的 app.py 进程"
else
    echo "🔍 找到以下 app.py 进程:"
    ps aux | grep -E "python.*app\.py" | grep -v grep | awk '{print "   PID: " $2 " - " $11 " " $12}'
    
    echo "⏹️  正在停止应用进程..."
    for pid in $APP_PIDS; do
        echo "   停止进程 PID: $pid"
        kill -TERM $pid 2>/dev/null
    done
    
    # 等待进程优雅退出
    echo "⏳ 等待进程优雅退出..."
    sleep 3
    
    # 检查是否还有进程在运行
    REMAINING_PIDS=$(ps aux | grep -E "python.*app\.py" | grep -v grep | awk '{print $2}')
    if [ ! -z "$REMAINING_PIDS" ]; then
        echo "⚠️  部分进程未能优雅退出，强制终止..."
        for pid in $REMAINING_PIDS; do
            echo "   强制终止进程 PID: $pid"
            kill -9 $pid 2>/dev/null
        done
    fi
fi

# 查找并停止 start.sh 进程
START_PIDS=$(ps aux | grep "start\.sh" | grep -v grep | awk '{print $2}')

if [ ! -z "$START_PIDS" ]; then
    echo "🔍 找到 start.sh 进程，正在停止..."
    for pid in $START_PIDS; do
        echo "   停止 start.sh 进程 PID: $pid"
        kill -TERM $pid 2>/dev/null
    done
fi

# 检查端口占用情况
echo "🔌 检查端口占用情况..."
PORT_5002=$(lsof -ti:5002 2>/dev/null)


if [ ! -z "$PORT_5002" ]; then
    echo "⚠️  端口 5002 仍被占用，进程 PID: $PORT_5002"
    echo "   正在释放端口 5002..."
    kill -9 $PORT_5002 2>/dev/null
fi

# 最终检查
echo "🔍 最终检查..."
FINAL_CHECK=$(ps aux | grep -E "(python.*app\.py|start\.sh)" | grep -v grep)

if [ -z "$FINAL_CHECK" ]; then
    echo "SpecRAG 已成功停止"
    echo "所有相关进程已清理完毕"
else
    echo "⚠️  仍有以下进程在运行:"
    echo "$FINAL_CHECK"
    echo "💡 如需强制清理，请手动执行: pkill -f 'python.*app'"
fi

echo "🏁 停止脚本执行完成"
