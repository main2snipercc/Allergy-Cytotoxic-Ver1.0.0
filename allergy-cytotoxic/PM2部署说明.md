# 细胞毒实验排班系统 - PM2部署说明

## 🚀 一键部署

### 方法1：完整部署（推荐）
```bash
# 给脚本添加执行权限
chmod +x *.sh

# 一键部署（包含环境检查、安装、配置、启动）
./deploy.sh
```

### 方法2：分步部署
```bash
# 1. 环境配置和PM2启动
./start.sh

# 2. 或者只启动应用（需要先配置好环境）
./pm2_start.sh
```

## 📋 部署前准备

### 系统要求
- Ubuntu 18.04+ 或其他Linux发行版
- Python 3.11+
- 至少1GB可用内存
- 网络连接（用于安装依赖）

### 权限要求
- sudo权限（用于安装Node.js和PM2）
- 项目目录的读写权限

## 🔧 部署流程

### 1. 环境检查
- ✅ 检查Python版本
- ✅ 检查uv包管理器
- ✅ 检查Node.js
- ✅ 检查PM2

### 2. 自动安装
- 🔧 安装uv（如果未安装）
- 🔧 安装Node.js（如果未安装）
- 🔧 安装PM2（如果未安装）

### 3. 环境配置
- 📁 创建必要的目录
- 🐍 配置uv虚拟环境
- 📦 安装Python依赖
- ⚙️ 检查配置文件

### 4. PM2启动
- 🚀 启动应用
- 💾 保存PM2配置
- 🔄 设置开机自启
- 📊 显示运行状态

## 📁 文件说明

### 配置文件
- `start.json` - PM2配置文件
- `pm2_start.sh` - PM2启动脚本
- `start.sh` - 完整部署脚本
- `deploy.sh` - 一键部署脚本

### 目录结构
```
allergy-cytotoxic/
├── start.json              # PM2配置
├── pm2_start.sh            # PM2启动脚本
├── start.sh                # 完整部署脚本
├── deploy.sh               # 一键部署脚本
├── logs/                   # 日志目录（自动创建）
├── .venv/                  # Python虚拟环境
└── config/
    ├── user_settings.json  # 用户配置
    └── user_settings.json.example  # 配置模板
```

## 🎯 使用方法

### 启动应用
```bash
./deploy.sh
```

### PM2管理命令
```bash
# 查看状态
pm2 status

# 查看日志
pm2 logs allergy-cytotoxic

# 重启应用
pm2 restart allergy-cytotoxic

# 停止应用
pm2 stop allergy-cytotoxic

# 删除应用
pm2 delete allergy-cytotoxic

# 查看详细信息
pm2 show allergy-cytotoxic
```

### 访问应用
- **本地访问**: http://localhost:8501
- **局域网访问**: http://[服务器IP]:8501

## ⚠️ 注意事项

### 1. 配置文件
- 首次部署会自动创建 `config/user_settings.json`
- 请编辑配置文件设置webhook等信息
- 配置文件包含敏感信息，不要提交到版本控制

### 2. 端口配置
- 默认端口：8501
- 如需修改端口，请编辑 `start.json` 和 `pm2_start.sh`

### 3. 防火墙设置
```bash
# Ubuntu UFW
sudo ufw allow 8501

# 或者使用iptables
sudo iptables -A INPUT -p tcp --dport 8501 -j ACCEPT
```

### 4. 日志管理
- 日志文件保存在 `logs/` 目录
- 支持日志轮转和自动清理
- 可通过PM2命令查看实时日志

## 🔍 故障排除

### 常见问题

#### 1. 权限不足
```bash
# 给脚本添加执行权限
chmod +x *.sh

# 检查目录权限
ls -la
```

#### 2. 端口被占用
```bash
# 检查端口占用
sudo netstat -tlnp | grep 8501

# 杀死占用进程
sudo kill -9 [PID]
```

#### 3. 依赖安装失败
```bash
# 清理并重新安装
rm -rf .venv
./start.sh
```

#### 4. PM2启动失败
```bash
# 查看详细日志
pm2 logs allergy-cytotoxic

# 检查配置文件
cat start.json

# 手动启动测试
./pm2_start.sh
```

### 日志查看
```bash
# PM2日志
pm2 logs allergy-cytotoxic

# 系统日志
sudo journalctl -u pm2-root

# 应用日志
tail -f logs/combined.log
```

## 🚀 生产环境建议

### 1. 反向代理
建议使用Nginx作为反向代理：
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://localhost:8501;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

### 2. SSL证书
使用Let's Encrypt配置HTTPS：
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
```

### 3. 监控告警
配置PM2监控：
```bash
# 安装PM2监控
pm2 install pm2-server-monit

# 配置告警
pm2 set pm2-server-monit:email your-email@example.com
```

## 📞 技术支持

如遇问题，请：
1. 查看PM2日志：`pm2 logs allergy-cytotoxic`
2. 检查系统日志：`sudo journalctl -u pm2-root`
3. 查看应用日志：`tail -f logs/combined.log`
4. 提交Issue或联系技术支持

---

**祝您部署顺利！** 🎉
