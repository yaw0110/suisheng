"""悬浮字幕窗：置顶、不抢焦点。三行：上一句原文（暗）/ 译文（黄）/ 当前句（实时）。
按住任意位置可拖动（位置会记住）；鼠标移上去右上角出现 ×，点它关闭字幕；双击恢复默认位置。"""
from PySide6.QtCore import QPoint, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter, QPen
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .platform import float_above_everything

CLOSE_SIZE = 22


class Overlay(QWidget):
    closed = Signal()                  # 点了 ×
    moved = Signal(int, int)           # 拖动结束（新位置，全局坐标）

    def __init__(self, display):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.setMouseTracking(True)
        self.d = display
        self.opacity = int(255 * display.opacity)
        self.saved_pos = None          # 用户拖过的位置
        self.hover = self.hover_close = False
        self.drag_from = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 8, 28, 10)
        lay.setSpacing(2)
        self.labels = {}
        for name, scale, color in (("top", 0.75, QColor(255, 255, 255, 160)),
                                   ("mid", 0.9, QColor(255, 220, 90)),
                                   ("bot", 1.0, QColor(255, 255, 255))):
            lab = QLabel("", self)
            f = QFont(); f.setPixelSize(int(display.font * scale)); f.setBold(True)
            lab.setFont(f)
            lab.setAlignment(Qt.AlignCenter)
            lab.setStyleSheet(f"color: rgba({color.red()},{color.green()},{color.blue()},{color.alpha()});")
            lab.setAttribute(Qt.WA_TransparentForMouseEvents)  # 鼠标事件交给窗口本身处理（拖动）
            lay.addWidget(lab)
            self.labels[name] = lab
        self.set_translation_visible(False)

    # ---------- 内容 ----------
    def set_translation_visible(self, on):
        self.labels["mid"].setVisible(on)
        self.place()

    def set_text(self, name, text):
        """一行放不下时截掉开头、保留最新的字"""
        lab = self.labels[name]
        w = max(50, self.width() - 60)
        lab.setText(QFontMetrics(lab.font()).elidedText(text or "", Qt.ElideLeft, w))

    def clear(self):
        for lab in self.labels.values():
            lab.setText("")

    # ---------- 位置 ----------
    def place(self):
        scr = QGuiApplication.primaryScreen().availableGeometry()
        w = int(min(self.d.width, scr.width() * 0.8))
        lines = 3 if self.labels["mid"].isVisible() else 2
        h = int(self.d.font * (1.35 * lines + 0.9))
        self.setFixedSize(w, h)
        if self.saved_pos and any(s.availableGeometry().intersects(QRect(QPoint(*self.saved_pos), self.size()))
                                  for s in QGuiApplication.screens()):
            self.move(*self.saved_pos)                           # 用户拖过的位置（还在某个屏幕内才用）
        else:
            self.move(scr.x() + (scr.width() - w) // 2, scr.y() + scr.height() - h - self.d.bottom_margin)

    def reset_position(self):
        self.saved_pos = None
        self.place()
        self.moved.emit(-1, -1)                                  # -1 表示恢复默认

    # ---------- 鼠标：拖动 / 关闭 ----------
    def _close_rect(self):
        return QRect(self.width() - CLOSE_SIZE - 8, 6, CLOSE_SIZE, CLOSE_SIZE)

    def enterEvent(self, e):
        self.hover = True; self.update()

    def leaveEvent(self, e):
        self.hover = self.hover_close = False; self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self._close_rect().contains(e.position().toPoint()):
            self.closed.emit(); return
        self.drag_from = e.globalPosition().toPoint() - self.frameGeometry().topLeft()

    def mouseMoveEvent(self, e):
        over = self._close_rect().contains(e.position().toPoint())
        if over != self.hover_close:
            self.hover_close = over; self.update()
        self.setCursor(Qt.PointingHandCursor if over else (Qt.ClosedHandCursor if self.drag_from else Qt.OpenHandCursor))
        if self.drag_from is not None and e.buttons() & Qt.LeftButton:
            self.move(e.globalPosition().toPoint() - self.drag_from)

    def mouseReleaseEvent(self, e):
        if self.drag_from is not None:
            self.drag_from = None
            self.saved_pos = (self.x(), self.y())
            self.moved.emit(self.x(), self.y())
            self.setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, e):
        if not self._close_rect().contains(e.position().toPoint()):
            self.reset_position()

    # ---------- 绘制 ----------
    def showEvent(self, e):
        super().showEvent(e)
        float_above_everything(self)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, min(255, self.opacity + (40 if self.hover else 0))))
        p.drawRoundedRect(self.rect(), 14, 14)
        if self.hover:                                           # 鼠标在上面时才显示 ×
            r = self._close_rect()
            p.setBrush(QColor(255, 255, 255, 70 if self.hover_close else 35))
            p.drawEllipse(r)
            pen = QPen(QColor(255, 255, 255, 230 if self.hover_close else 170)); pen.setWidthF(2)
            p.setPen(pen)
            m = 7
            p.drawLine(r.left() + m, r.top() + m, r.right() - m, r.bottom() - m)
            p.drawLine(r.right() - m, r.top() + m, r.left() + m, r.bottom() - m)
