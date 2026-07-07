"""
py2app 打包脚本 —— 在 Mac 上把桌宠打成可双击运行的 .app

用法（在本目录下，用装好依赖的同一个环境）：
    python setup.py py2app
    open dist/            # 把 LaterQueue.app 拖进"应用程序"

清理：rm -rf build dist
"""

from setuptools import setup

APP = ["laterqueue.py"]
DATA_FILES = [("assets", ["assets/pet.png"])]   # 打包时带上小精灵图片

OPTIONS = {
    "argv_emulation": False,          # 新系统上开启常出问题，保持关闭
    "packages": ["PySide6", "shiboken6"],
    "plist": {
        "CFBundleName": "LaterQueue",
        "CFBundleDisplayName": "晚点队列",
        "CFBundleIdentifier": "com.laterqueue.app",
        "CFBundleVersion": "0.3.0",
        "CFBundleShortVersionString": "0.3.0",
        "LSUIElement": True,          # 桌宠应用，不在 Dock 显示
    },
}

setup(
    app=APP,
    name="LaterQueue",
    data_files=DATA_FILES,
    options={"py2app": OPTIONS},
    setup_requires=["py2app"],
)
