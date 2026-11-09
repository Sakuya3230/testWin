"""
value_slider.py
PySide6 (Maya 2027 対応) 値ラベル付きスライダー(描画ベース)

    ●━━━━━━○───────────────   1.0 秒
    青い塗り + 丸いハンドル + 右に値(単位付き)

特徴:
    - 浮動小数(setRange / setSingleStep / setDecimals / setSuffix)
    - ドラッグ / 溝のクリックでジャンプ / ホイール / キーボード(←→ ↑↓ PageUp/Down Home/End)
    - ステップに吸着。ホバーでハンドルがわずかに大きくなる。Tab フォーカス時だけフォーカスリング
    - シグナル: valueChanged(float) / sliderPressed / sliderReleased

【使い方】
    s = ValueSlider()
    s.setRange(0.0, 5.0); s.setSingleStep(0.1); s.setDecimals(1); s.setSuffix(" 秒")
    s.setValue(1.0)
    s.valueChanged.connect(lambda v: print(v))
    s.setValueVisible(False)           # 右の値表示を消す

単体で動くよう、他モジュールへの依存はありません。
    - 単体:  python value_slider.py
    - Maya:  import value_slider; value_slider.show_demo()
"""
from PySide6 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt

C_GROOVE = QtGui.QColor("#f0f0f0")
C_GROOVE_EDGE = QtGui.QColor("#b4b4b4")
C_FILL = QtGui.QColor("#1479ff")
C_HANDLE = QtGui.QColor("#1a7cff")
C_HANDLE_EDGE = QtGui.QColor("#6aa9ff")
C_TEXT = QtGui.QColor("#f2f2f2")
C_FOCUS = QtGui.QColor("#8ec0ff")


def _em(widget, ratio):
    """フォント高さ基準の長さ(px)。UIスケール/DPIが変わっても比率が崩れない。"""
    return max(1, round(widget.fontMetrics().height() * ratio))


class ValueSlider(QtWidgets.QWidget):
    valueChanged = QtCore.Signal(float)
    sliderPressed = QtCore.Signal()
    sliderReleased = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._min = 0.0
        self._max = 100.0
        self._step = 1.0
        self._value = 0.0
        self._decimals = 0
        self._suffix = ""
        self._show_value = True
        self._hover = False
        self._drag = False
        self._grab_dx = 0.0
        self._kb_focus = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    # ---- 公開API ----
    def value(self):
        return self._value

    def minimum(self):
        return self._min

    def maximum(self):
        return self._max

    def setRange(self, lo, hi):
        self._min, self._max = float(min(lo, hi)), float(max(lo, hi))
        self._set_value(self._value, emit=False)
        self.updateGeometry()
        self.update()

    def setSingleStep(self, step):
        self._step = max(1e-9, float(step))

    def setDecimals(self, n):
        self._decimals = max(0, int(n))
        self.updateGeometry()
        self.update()

    def setSuffix(self, text):
        self._suffix = text
        self.updateGeometry()
        self.update()

    def setValueVisible(self, on):
        self._show_value = bool(on)
        self.updateGeometry()
        self.update()

    def setValue(self, v):
        self._set_value(v, emit=True)

    def text(self):
        return f"{self._value:.{self._decimals}f}{self._suffix}"

    # ---- 値 ----
    def _snap(self, v):
        v = max(self._min, min(self._max, v))
        n = round((v - self._min) / self._step)
        v = self._min + n * self._step
        v = max(self._min, min(self._max, v))
        return round(v, self._decimals + 6)

    def _set_value(self, v, emit):
        v = self._snap(v)
        if v == self._value:
            return
        self._value = v
        self.update()
        if emit:
            self.valueChanged.emit(v)

    # ---- 寸法 ----
    def _handle_d(self):
        return _em(self, 1.35 + (0.1 if self._hover or self._drag else 0.0))

    def _label_width(self):
        if not self._show_value:
            return 0
        fm = self.fontMetrics()
        samples = (f"{self._min:.{self._decimals}f}{self._suffix}",
                   f"{self._max:.{self._decimals}f}{self._suffix}")
        return max(fm.horizontalAdvance(s) for s in samples) + _em(self, 0.5)

    def sizeHint(self):
        return QtCore.QSize(_em(self, 14) + self._label_width(), _em(self, 2.2))

    def minimumSizeHint(self):
        return QtCore.QSize(_em(self, 5) + self._label_width(), _em(self, 2.2))

    def _track(self):
        """(x0, x1): ハンドル中心の移動範囲。"""
        r = _em(self, 1.35) / 2.0
        lw = self._label_width()
        gap = _em(self, 1.0) if lw else 0
        return r + 1, self.width() - lw - gap - r - 1

    def _pos_of(self, v):
        x0, x1 = self._track()
        span = self._max - self._min
        t = 0.0 if span <= 0 else (v - self._min) / span
        return x0 + (x1 - x0) * t

    def _value_at(self, x):
        x0, x1 = self._track()
        if x1 <= x0:
            return self._min
        t = (x - x0) / (x1 - x0)
        return self._min + (self._max - self._min) * max(0.0, min(1.0, t))

    # ---- マウス ----
    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton or not self.isEnabled():
            return
        self._kb_focus = False
        x = e.position().x()
        hx = self._pos_of(self._value)
        r = self._handle_d() / 2.0
        # ハンドルの上なら掴んだ位置を保つ。溝なら即ジャンプしてそのままドラッグ
        self._grab_dx = hx - x if abs(x - hx) <= r + 2 else 0.0
        self._drag = True
        self.sliderPressed.emit()
        self._set_value(self._value_at(x + self._grab_dx), emit=True)
        self.update()

    def mouseMoveEvent(self, e):
        if self._drag:
            self._set_value(self._value_at(e.position().x() + self._grab_dx), emit=True)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._drag:
            self._drag = False
            self.update()
            self.sliderReleased.emit()

    def wheelEvent(self, e):
        if not self.isEnabled():
            e.ignore()
            return
        d = e.angleDelta().y()
        if d:
            self.setValue(self._value + (self._step if d > 0 else -self._step))
        e.accept()

    # ---- キーボード ----
    def focusInEvent(self, e):
        self._kb_focus = e.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason,
                                        Qt.ShortcutFocusReason)
        self.update()

    def focusOutEvent(self, e):
        self._kb_focus = False
        self.update()

    def keyPressEvent(self, e):
        k = e.key()
        page = max(self._step, (self._max - self._min) / 10.0)
        if k in (Qt.Key_Right, Qt.Key_Up):
            self.setValue(self._value + self._step)
        elif k in (Qt.Key_Left, Qt.Key_Down):
            self.setValue(self._value - self._step)
        elif k == Qt.Key_PageUp:
            self.setValue(self._value + page)
        elif k == Qt.Key_PageDown:
            self.setValue(self._value - page)
        elif k == Qt.Key_Home:
            self.setValue(self._min)
        elif k == Qt.Key_End:
            self.setValue(self._max)
        else:
            e.ignore()
            return
        self._kb_focus = True
        self.update()

    # ---- 描画 ----
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        h = self.height()
        cy = h / 2.0
        x0, x1 = self._track()
        gh = _em(self, 0.65)
        enabled = self.isEnabled()
        if not enabled:
            p.setOpacity(0.5)

        # 溝
        groove = QtCore.QRectF(x0 - gh / 2, cy - gh / 2, (x1 - x0) + gh, gh)
        p.setPen(QtGui.QPen(C_GROOVE_EDGE, 1))
        p.setBrush(C_GROOVE)
        p.drawRoundedRect(groove.adjusted(.5, .5, -.5, -.5), gh / 2, gh / 2)
        # 塗り(左端から現在値まで)
        hx = self._pos_of(self._value)
        fill = QtCore.QRectF(groove.left() + .5, groove.top() + .5,
                             hx - groove.left() - .5, groove.height() - 1)
        if fill.width() > 0:
            p.setPen(Qt.NoPen)
            p.setBrush(C_FILL)
            p.drawRoundedRect(fill, (gh - 1) / 2, (gh - 1) / 2)

        # ハンドル
        d = self._handle_d()
        hr = QtCore.QRectF(hx - d / 2, cy - d / 2, d, d)
        p.setPen(QtGui.QPen(C_HANDLE_EDGE, 1))
        p.setBrush(C_HANDLE)
        p.drawEllipse(hr.adjusted(.5, .5, -.5, -.5))
        if self._kb_focus and self.hasFocus():
            p.setPen(QtGui.QPen(C_FOCUS, 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(hr.adjusted(-2.5, -2.5, 2.5, 2.5))

        # 値ラベル(右揃え)
        if self._show_value:
            p.setOpacity(1.0 if enabled else 0.5)
            p.setPen(C_TEXT)
            lw = self._label_width()
            p.drawText(QtCore.QRectF(self.width() - lw, 0, lw, h), Qt.AlignVCenter | Qt.AlignRight,
                       self.text())


# ===========================================================================
# デモ
# ===========================================================================
DEMO_OBJECT_NAME = "valueSliderDemoWindow"


def _maya_main_window():
    """Mayaが無い環境では None を返す(単体実行できるように)。"""
    try:
        from maya import OpenMayaUI as omui
        from shiboken6 import wrapInstance
    except ImportError:
        return None
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


class DemoWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setObjectName(DEMO_OBJECT_NAME)
        self.setWindowTitle("value_slider demo")
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#444444"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#dddddd"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        self.setFocusPolicy(Qt.ClickFocus)

        self.time = ValueSlider()
        self.time.setRange(0.0, 5.0)
        self.time.setSingleStep(0.1)
        self.time.setDecimals(1)
        self.time.setSuffix(" 秒")
        self.time.setValue(1.0)

        self.pct = ValueSlider()
        self.pct.setRange(0, 100)
        self.pct.setSingleStep(5)
        self.pct.setSuffix(" %")
        self.pct.setValue(60)

        self.off = ValueSlider()
        self.off.setRange(0, 1)
        self.off.setSingleStep(0.01)
        self.off.setDecimals(2)
        self.off.setValue(0.3)
        self.off.setEnabled(False)

        self.status = QtWidgets.QLabel("")
        self.time.valueChanged.connect(lambda v: self.status.setText(f"time = {v}"))
        self.pct.valueChanged.connect(lambda v: self.status.setText(f"percent = {v}"))

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(6)
        for w in (self.time, self.pct, self.off, self.status):
            lay.addWidget(w)
        lay.addStretch(1)
        self.resize(480, 200)

    def showEvent(self, e):
        super().showEvent(e)
        self.setFocus()


def show_demo():
    """Maya内でもスタンドアロンでも使えるデモ表示。多重生成を防ぐ。"""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    for w in app.allWidgets():
        if w.objectName() == DEMO_OBJECT_NAME:
            w.close()
            w.deleteLater()
    win = DemoWindow(_maya_main_window())
    win.show()
    return win


if __name__ == "__main__":
    import sys
    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    _win = show_demo()
    sys.exit(_app.exec())