"""悬浮字幕窗：屏幕底部居中、置顶、鼠标穿透、不抢焦点。三行：上一句原文（暗）/ 译文（黄）/ 当前句（实时）"""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QPainter
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .platform import float_above_everything


class Overlay(QWidget):
    def __init__(self, display):
        super().__init__(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_MacAlwaysShowToolWindow)
        self.d = display
        self.opacity = int(255 * display.opacity)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 8, 16, 10)
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
            lay.addWidget(lab)
            self.labels[name] = lab
        self.set_translation_visible(False)

    def set_translation_visible(self, on):
        self.labels["mid"].setVisible(on)
        self.place()

    def set_text(self, name, text):
        """一行放不下时截掉开头、保留最新的字"""
        lab = self.labels[name]
        w = max(50, self.width() - 40)
        lab.setText(QFontMetrics(lab.font()).elidedText(text or "", Qt.ElideLeft, w))

    def clear(self):
        for lab in self.labels.values():
            lab.setText("")

    def place(self):
        scr = QGuiApplication.primaryScreen().availableGeometry()
        w = int(min(self.d.width, scr.width() * 0.8))
        lines = 3 if self.labels["mid"].isVisible() else 2
        h = int(self.d.font * (1.35 * lines + 0.9))
        self.setFixedSize(w, h)
        self.move(scr.x() + (scr.width() - w) // 2, scr.y() + scr.height() - h - self.d.bottom_margin)

    def showEvent(self, e):
        super().showEvent(e)
        float_above_everything(self)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, self.opacity))
        p.drawRoundedRect(self.rect(), 14, 14)
