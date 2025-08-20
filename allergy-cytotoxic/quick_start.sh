#!/bin/bash

# 细胞毒实验排班系统 - 快速启动脚本
# 使用方法: ./quick_start.sh

echo "🚀 快速启动细胞毒实验排班系统..."

# 给所有脚本添加执行权限
chmod +x *.sh

# 一键部署
./deploy.sh

echo "✅ 启动完成！访问 http://localhost:8501"
