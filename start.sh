#!/bin/bash

# 细胞毒实验排班系统 - PM2一键启动脚本
# 使用方法: ./start.sh

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 获取脚本所在目录
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

log_info "开始部署细胞毒实验排班系统..."

# 1. 检查系统环境
log_info "检查系统环境..."

# 检查是否为Ubuntu系统
if ! grep -q "Ubuntu" /etc/os-release 2>/dev/null; then
    log_warning "检测到非Ubuntu系统，某些命令可能需要调整"
fi

# 检查Python版本
if ! command -v python3 &> /dev/null; then
    log_error "Python3未安装，请先安装Python3.11+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
log_info "Python版本: $PYTHON_VERSION"

# 检查uv是否安装
if ! command -v uv &> /dev/null; then
    log_info "uv未安装，正在安装uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    
    # 更新PATH环境变量
    export PATH="$HOME/.local/bin:$PATH"
    
    # 重新加载环境变量
    if [ -f "$HOME/.bashrc" ]; then
        source "$HOME/.bashrc"
    fi
    
    # 再次检查uv是否可用
    if ! command -v uv &> /dev/null; then
        log_error "uv安装后仍无法识别，尝试手动添加到PATH..."
        export PATH="$HOME/.local/bin:$PATH"
        
        # 如果还是不行，尝试直接使用完整路径
        if [ -f "$HOME/.local/bin/uv" ]; then
            log_warning "使用完整路径访问uv: $HOME/.local/bin/uv"
            UV_CMD="$HOME/.local/bin/uv"
        else
            log_error "uv安装失败，请手动安装"
            exit 1
        fi
    else
        UV_CMD="uv"
        log_success "uv已安装: $(uv --version)"
    fi
else
    UV_CMD="uv"
    log_success "uv已安装: $(uv --version)"
fi

# 检查Node.js和PM2
if ! command -v node &> /dev/null; then
    log_error "Node.js未安装，正在安装Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_lts.x | sudo -E bash -
    sudo apt-get install -y nodejs
fi

if ! command -v pm2 &> /dev/null; then
    log_error "PM2未安装，正在安装PM2..."
    sudo npm install -g pm2
fi

log_success "PM2已安装: $(pm2 --version)"

# 2. 创建必要的目录
log_info "创建必要的目录..."
mkdir -p logs
mkdir -p data/archive

# 3. 配置uv环境
log_info "配置uv环境..."
if [ ! -d ".venv" ]; then
    log_info "创建虚拟环境..."
    if [ "$UV_CMD" = "uv" ]; then
        uv venv
    else
        $UV_CMD venv
    fi
fi

# 激活虚拟环境
source .venv/bin/activate

# 4. 安装依赖
log_info "安装Python依赖..."
if [ "$UV_CMD" = "uv" ]; then
    uv sync
else
    $UV_CMD sync
fi

# 5. 检查配置文件
log_info "检查配置文件..."

# 检查user_settings.json是否存在，如果不存在则创建
if [ ! -f "config/user_settings.json" ]; then
    log_warning "配置文件不存在，创建默认配置..."
    cp config/user_settings.json.example config/user_settings.json
    log_info "请编辑 config/user_settings.json 配置webhook等信息"
fi

# 6. 更新start.json中的路径
log_info "更新PM2配置..."
sed -i "s|/path/to/your/project|$SCRIPT_DIR|g" start.json

# 7. 停止已存在的进程
log_info "停止已存在的进程..."
pm2 stop allergy-cytotoxic 2>/dev/null || true
pm2 delete allergy-cytotoxic 2>/dev/null || true

# 8. 启动应用
log_info "启动应用..."
pm2 start start.json

# 9. 保存PM2配置
log_info "保存PM2配置..."
pm2 save

# 10. 设置开机自启
log_info "设置开机自启..."
pm2 startup

# 11. 显示状态
log_info "显示应用状态..."
pm2 status
pm2 logs allergy-cytotoxic --lines 10

# 12. 显示访问信息
log_info "应用启动完成！"
log_success "访问地址: http://localhost:8501"
log_success "PM2管理命令:"
echo "  - 查看状态: pm2 status"
echo "  - 查看日志: pm2 logs allergy-cytotoxic"
echo "  - 重启应用: pm2 restart allergy-cytotoxic"
echo "  - 停止应用: pm2 stop allergy-cytotoxic"
echo "  - 删除应用: pm2 delete allergy-cytotoxic"

# 13. 检查应用是否正常运行
sleep 3
if pm2 list | grep -q "allergy-cytotoxic.*online"; then
    log_success "应用启动成功！"
else
    log_error "应用启动失败，请检查日志: pm2 logs allergy-cytotoxic"
    exit 1
fi
