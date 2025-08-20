#!/bin/bash

# 细胞毒实验排班系统 - 快速部署脚本
# 使用方法: ./deploy.sh

set -e

# 颜色定义
GREEN='\033[0;32m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}🚀 开始部署细胞毒实验排班系统...${NC}"

# 1. 给脚本添加执行权限
chmod +x start.sh
chmod +x pm2_start.sh
chmod +x deploy.sh

# 2. 运行完整部署脚本
./start.sh

echo -e "${GREEN}✅ 部署完成！${NC}"
echo -e "${BLUE}📱 访问地址: http://localhost:8501${NC}"
echo -e "${BLUE}🔧 PM2管理: pm2 status${NC}"
