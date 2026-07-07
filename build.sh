#!/usr/bin/env bash
# 一键把「晚点队列」打包成 macOS .app
# 用法：在项目目录下  bash build.sh   （或先 chmod +x build.sh 再 ./build.sh）
set -e
cd "$(dirname "$0")"

echo "▶ 准备虚拟环境…"
if [ ! -d venv ]; then
  python3 -m venv venv
fi
source venv/bin/activate

echo "▶ 安装依赖（PySide6 + py2app）…"
pip install --upgrade pip >/dev/null
pip install PySide6 py2app >/dev/null

echo "▶ 先确认能正常启动（3 秒后自动关）…"
( python laterqueue.py & PID=$!; sleep 3; kill $PID 2>/dev/null ) || true

echo "▶ 清理旧产物并打包…"
rm -rf build dist
python setup.py py2app

echo ""
echo "✅ 完成！应用在 dist/LaterQueue.app"
echo "   把它拖进「应用程序」即可。首次打开若提示身份不明，右键 → 打开。"
open dist/ 2>/dev/null || true
