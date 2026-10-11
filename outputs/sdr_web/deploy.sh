#!/bin/bash
# SDR Web应用 · 一键部署脚本
# 在腾讯云轻量服务器上执行：bash deploy.sh
set -e

echo "=== SDR Web应用部署脚本 ==="

# 1. 检查Python
if ! command -v python3 &> /dev/null; then
    echo "安装Python..."
    apt-get update && apt-get install -y python3 python3-pip python3-venv
fi

# 2. 创建工作目录
APP_DIR="/opt/sdr_web"
echo "部署到 $APP_DIR"
mkdir -p $APP_DIR

# 3. 复制文件（假设脚本和app代码在同一目录）
cp -r ./* $APP_DIR/ 2>/dev/null || true
cd $APP_DIR

# 4. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 5. 安装依赖
pip install -r requirements.txt

# 6. 初始化数据库
echo "初始化数据库..."
python3 init_db.py

# 7. 创建systemd服务（开机自启+崩溃重启）
cat > /etc/systemd/system/sdr-web.service << 'EOF'
[Unit]
Description=SDR Web Application
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/sdr_web
Environment=HOST=0.0.0.0
Environment=PORT=5000
ExecStart=/opt/sdr_web/venv/bin/python /opt/sdr_web/app.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable sdr-web
systemctl start sdr-web

echo ""
echo "=== 部署完成 ==="
echo "服务状态："
systemctl status sdr-web --no-pager | head -10
echo ""
echo "访问地址：http://$(curl -s ifconfig.me):5000/"
echo ""
echo "BD打开上面地址 → 右上角选名字 → 开始用"
