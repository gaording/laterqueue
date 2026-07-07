#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
晚点队列 (LaterQueue) — 桌面宠物版

一只沙漏小精灵蹲在你桌面角落（始终置顶、可拖动、不打断你）。
点它，冒出任务气泡：被打断时答应别人"晚点处理"的事都在里面，
按优先级从上往下排；有空时自己去"领"，做完打勾。右键小精灵管添加和退出。

框架：PySide6（Qt）。数据：~/Library/Application Support/LaterQueue/queue.json
"""

import os
import sys
import json
import uuid
import traceback
import subprocess
from datetime import datetime

from PySide6.QtCore import Qt, QPoint, QSize, QTimer
from PySide6.QtGui import QPixmap, QAction, QFont, QColor
from PySide6.QtWidgets import (
    QApplication, QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
    QMenu, QInputDialog, QScrollArea, QGraphicsDropShadowEffect, QSizePolicy,
)


# =========================== 数据层 ===========================

APP_NAME = "LaterQueue"
DATA_DIR = os.path.expanduser(f"~/Library/Application Support/{APP_NAME}")
DATA_FILE = os.path.join(DATA_DIR, "queue.json")
STATE_FILE = os.path.join(DATA_DIR, "state.json")
LAUNCH_AGENT_LABEL = "com.laterqueue.app"
LAUNCH_AGENT_PATH = os.path.expanduser(
    f"~/Library/LaunchAgents/{LAUNCH_AGENT_LABEL}.plist")
ASSET_PET = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "assets", "pet.png")
PET_WIDTH = 130   # 桌面上小精灵显示宽度（px）


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def load_items():
    _ensure_dir()
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_items(items):
    _ensure_dir()
    tmp = DATA_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    os.replace(tmp, DATA_FILE)


def new_item(text):
    return {
        "id": uuid.uuid4().hex,
        "text": text.strip(),
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "status": "pending",
    }


def load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    _ensure_dir()
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
    except Exception:
        pass


# =========================== 开机自启 ===========================

def _app_launch_args():
    real = os.path.realpath(sys.argv[0])
    if ".app/Contents/MacOS/" in real:
        return ["/usr/bin/open", real.split(".app/Contents/MacOS/")[0] + ".app"]
    return None


def launch_at_login_enabled():
    return os.path.exists(LAUNCH_AGENT_PATH)


def set_launch_at_login(enable):
    if enable:
        args = _app_launch_args()
        if not args:
            return False
        plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{LAUNCH_AGENT_LABEL}</string>
  <key>ProgramArguments</key>
  <array>{''.join(f'<string>{a}</string>' for a in args)}</array>
  <key>RunAtLoad</key><true/>
</dict></plist>"""
        os.makedirs(os.path.dirname(LAUNCH_AGENT_PATH), exist_ok=True)
        with open(LAUNCH_AGENT_PATH, "w") as f:
            f.write(plist)
        subprocess.run(["launchctl", "load", LAUNCH_AGENT_PATH], check=False)
    else:
        if os.path.exists(LAUNCH_AGENT_PATH):
            subprocess.run(["launchctl", "unload", LAUNCH_AGENT_PATH], check=False)
            os.remove(LAUNCH_AGENT_PATH)
    return True


# =========================== 任务气泡 ===========================

class QueueBubble(QWidget):
    """挂在小精灵旁边的圆角小面板，展示并操作队列。"""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        try:
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        except Exception:
            pass

        # 圆角卡片容器
        self.card = QWidget(self)
        self.card.setObjectName("card")
        self.card.setStyleSheet("""
            #card { background: rgba(252,247,238,0.98); border-radius: 16px; }
            QLabel#title { color:#8a6a3a; font-weight:600; }
            QLabel#count { color:#b0a48f; }
            QLabel.task { color:#33302b; }
            QPushButton { border:none; background:transparent; font-size:15px;
                          color:#9a8f7d; padding:0; }
            QPushButton:hover { color:#5a5347; }
            QPushButton#add { background:#e8a33c; color:white; border-radius:12px;
                              font-size:13px; font-weight:600; padding:5px 12px; }
            QPushButton#add:hover { background:#d9922f; }
        """)
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(28)
        shadow.setColor(QColor(0, 0, 0, 70))
        shadow.setOffset(0, 6)
        self.card.setGraphicsEffect(shadow)

        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(18, 18, 18, 18)   # 给阴影留边
        self.outer.addWidget(self.card)

        self.vbox = QVBoxLayout(self.card)
        self.vbox.setContentsMargins(16, 14, 16, 16)
        self.vbox.setSpacing(8)

        self.refresh()

    def refresh(self):
        # 清空
        while self.vbox.count():
            item = self.vbox.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        pending = self.app.pending()

        # 头部
        head = QHBoxLayout()
        title = QLabel("晚点队列")
        title.setObjectName("title")
        title.setFont(QFont("", 14))
        head.addWidget(title)
        head.addStretch(1)
        cnt = QLabel(f"欠着 {len(pending)} 件" if pending else "清空啦～")
        cnt.setObjectName("count")
        head.addWidget(cnt)
        hw = QWidget()
        hw.setLayout(head)
        self.vbox.addWidget(hw)

        # 任务行
        if not pending:
            empty = QLabel("有空的时候，从这里领任务 🎐")
            empty.setStyleSheet("color:#b0a48f;")
            self.vbox.addWidget(empty)
        else:
            for it in pending:
                self.vbox.addWidget(self._row(it))

        # 添加按钮
        add = QPushButton("＋ 添加一条")
        add.setObjectName("add")
        add.clicked.connect(self.app.add_via_dialog)
        addw = QHBoxLayout()
        addw.addStretch(1)
        addw.addWidget(add)
        addw.addStretch(1)
        aw = QWidget()
        aw.setLayout(addw)
        self.vbox.addWidget(aw)

        self.card.adjustSize()
        self.adjustSize()

    def _row(self, it):
        row = QHBoxLayout()
        row.setSpacing(6)
        done = QPushButton("✓")
        done.setFixedSize(22, 22)
        done.setToolTip("完成")
        done.clicked.connect(lambda: self.app.mark_done(it["id"]))
        row.addWidget(done)

        lbl = QLabel(it["text"])
        lbl.setProperty("class", "task")
        lbl.setMinimumWidth(180)
        lbl.setMaximumWidth(240)
        lbl.setWordWrap(False)
        row.addWidget(lbl, 1)

        up = QPushButton("↑")
        up.setFixedSize(22, 22)
        up.setToolTip("置顶")
        up.clicked.connect(lambda: self.app.bump_top(it["id"]))
        row.addWidget(up)

        dele = QPushButton("✕")
        dele.setFixedSize(22, 22)
        dele.setToolTip("删除")
        dele.clicked.connect(lambda: self.app.delete(it["id"]))
        row.addWidget(dele)

        w = QWidget()
        w.setLayout(row)
        return w


# =========================== 小精灵主窗口 ===========================

class Pet(QWidget):
    def __init__(self):
        super().__init__()
        self.items = load_items()

        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        try:
            self.setAttribute(Qt.WA_MacAlwaysShowToolWindow, True)
        except Exception:
            pass

        # 小精灵图片
        self.label = QLabel(self)
        pix = QPixmap(ASSET_PET)
        if not pix.isNull():
            pix = pix.scaledToWidth(PET_WIDTH, Qt.SmoothTransformation)
        self.label.setPixmap(pix)
        self.label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.resize(pix.size() if not pix.isNull() else QSize(PET_WIDTH, 150))

        # 待办计数小气泡（叠在右上角）
        self.badge = QLabel(self)
        self.badge.setAlignment(Qt.AlignCenter)
        self.badge.setStyleSheet("""
            background:#e8574c; color:white; border-radius:11px;
            font-size:12px; font-weight:700;""")
        self.badge.setFixedSize(22, 22)
        self.badge.setAttribute(Qt.WA_TransparentForMouseEvents, True)  # 不挡拖动
        self.badge.hide()

        self.bubble = QueueBubble(self)
        self.bubble.hide()

        self._menu = self._build_menu()
        self._press_pos = None
        self._moved = False

        self._restore_position()
        self.update_badge()

    # ---------- 菜单 ----------
    def _build_menu(self):
        m = QMenu(self)
        a_add = QAction("＋ 添加一条", self)
        a_add.triggered.connect(self.add_via_dialog)
        m.addAction(a_add)
        a_toggle = QAction("显示 / 隐藏 队列", self)
        a_toggle.triggered.connect(self.toggle_bubble)
        m.addAction(a_toggle)
        a_center = QAction("把小精灵拉回屏幕中央", self)
        a_center.triggered.connect(self.center_pet)
        m.addAction(a_center)
        m.addSeparator()
        a_clear = QAction("清除已完成记录", self)
        a_clear.triggered.connect(self.clear_done)
        m.addAction(a_clear)
        self.a_launch = QAction("开机自动启动", self, checkable=True)
        self.a_launch.setChecked(launch_at_login_enabled())
        self.a_launch.triggered.connect(self.toggle_launch)
        m.addAction(self.a_launch)
        m.addSeparator()
        a_quit = QAction("退出", self)
        a_quit.triggered.connect(QApplication.quit)
        m.addAction(a_quit)
        return m

    # ---------- 数据操作 ----------
    def pending(self):
        return [it for it in self.items if it["status"] == "pending"]

    def add_via_dialog(self):
        text, ok = QInputDialog.getText(
            self, "晚点队列", "要晚点处理的事（回车加入队列顶部）：")
        if ok and text.strip():
            self.items.insert(0, new_item(text.strip()))
            save_items(self.items)
            self.refresh_ui()
            if not self.bubble.isVisible():
                self.toggle_bubble()

    def mark_done(self, item_id):
        for it in self.items:
            if it["id"] == item_id:
                it["status"] = "done"
                it["done_at"] = datetime.now().isoformat(timespec="seconds")
                break
        save_items(self.items)
        self.refresh_ui()

    def bump_top(self, item_id):
        idx = next((k for k, it in enumerate(self.items)
                    if it["id"] == item_id), None)
        if idx is not None:
            self.items.insert(0, self.items.pop(idx))
            save_items(self.items)
            self.refresh_ui()

    def delete(self, item_id):
        self.items = [it for it in self.items if it["id"] != item_id]
        save_items(self.items)
        self.refresh_ui()

    def clear_done(self):
        self.items = [it for it in self.items if it["status"] != "done"]
        save_items(self.items)
        self.refresh_ui()

    # ---------- 刷新 ----------
    def refresh_ui(self):
        # 推迟到本次点击事件处理完再重建，避免销毁"正被点击的按钮"导致崩溃
        QTimer.singleShot(0, self._do_refresh)

    def _do_refresh(self):
        # 只更新内容，不重新摆放气泡（否则每次点按钮气泡都会跳位置）
        self.bubble.refresh()
        self.update_badge()

    def update_badge(self):
        n = len(self.pending())
        if n > 0:
            self.badge.setText(str(n) if n < 100 else "99+")
            self.badge.move(self.width() - 26, 4)
            self.badge.show()
            self.badge.raise_()
        else:
            self.badge.hide()

    # ---------- 气泡显隐与定位 ----------
    def toggle_bubble(self):
        if self.bubble.isVisible():
            self.bubble.hide()
        else:
            self.bubble.refresh()
            self._place_bubble()
            self.bubble.show()
            self.bubble.raise_()

    def _place_bubble(self):
        # 放在小精灵上方；若上方空间不够则放下方
        self.bubble.adjustSize()
        bw, bh = self.bubble.width(), self.bubble.height()
        g = self.frameGeometry()
        x = g.center().x() - bw // 2
        y = g.top() - bh + 10
        screen = QApplication.primaryScreen().availableGeometry()
        if y < screen.top():
            y = g.bottom() - 10
        x = max(screen.left() + 4, min(x, screen.right() - bw - 4))
        self.bubble.move(x, y)

    def center_pet(self):
        scr = QApplication.primaryScreen().availableGeometry()
        self.move(scr.center().x() - self.width() // 2,
                  scr.center().y() - self.height() // 2)

    # ---------- 位置记忆 ----------
    def _restore_position(self):
        st = load_state()
        screen = QApplication.primaryScreen().availableGeometry()
        if "x" in st and "y" in st:
            self.move(int(st["x"]), int(st["y"]))
        else:
            self.move(screen.right() - self.width() - 40,
                      screen.bottom() - self.height() - 40)
        self._ready = True   # 之后的移动才开始记忆

    # ---------- 鼠标：系统级拖动 / 点击 / 右键 ----------
    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            self._menu.exec(e.globalPosition().toPoint())
            return
        if e.button() == Qt.LeftButton:
            self._press_global = e.globalPosition().toPoint()
            self._click_candidate = True

    def mouseMoveEvent(self, e):
        if not getattr(self, "_click_candidate", False):
            return
        moved = (e.globalPosition().toPoint()
                 - self._press_global).manhattanLength()
        if moved > 6:
            # 交给系统来拖，macOS 上无边框窗口这样才拖得动
            self._click_candidate = False
            wh = self.windowHandle()
            if wh is not None:
                wh.startSystemMove()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and getattr(self, "_click_candidate", False):
            self._click_candidate = False
            self.toggle_bubble()   # 没拖动 = 单击，展开/收起队列

    def moveEvent(self, e):
        super().moveEvent(e)
        if getattr(self, "_ready", False):
            save_state({"x": self.x(), "y": self.y()})
            if self.bubble.isVisible():
                self._place_bubble()


    # ---------- 菜单动作 ----------
    def toggle_launch(self, checked):
        ok = set_launch_at_login(checked)
        if not ok:
            self.a_launch.setChecked(False)


def main():
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)   # 隐藏气泡不退出

    # 全局错误捕获：任何异常都写进 error.log 并弹窗，方便定位
    error_log = os.path.join(DATA_DIR, "error.log")

    def excepthook(exc_type, exc, tb):
        # Ctrl+C 退出 / 正常退出：交给默认处理，不当成错误弹窗
        if issubclass(exc_type, (KeyboardInterrupt, SystemExit)):
            sys.__excepthook__(exc_type, exc, tb)
            return
        msg = "".join(traceback.format_exception(exc_type, exc, tb))
        _ensure_dir()
        try:
            with open(error_log, "a", encoding="utf-8") as f:
                f.write(datetime.now().isoformat() + "\n" + msg + "\n")
        except Exception:
            pass
        sys.stderr.write(msg)
        try:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(None, "晚点队列出错了（已记录到 error.log）",
                                 msg[-1600:])
        except Exception:
            pass

    sys.excepthook = excepthook

    pet = Pet()
    pet.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
