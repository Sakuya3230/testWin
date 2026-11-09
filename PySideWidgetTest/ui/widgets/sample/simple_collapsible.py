"""
simple_collapsible.py
PySide6 (Maya 2027 対応) アニメーションなしの最小構成おりたたみフレーム

    ⌄ 選択  1 機能          ← ヘッダー(矢印 + 太字タイトル + 淡色のサブタイトル + 下線)
    ───────────────────
    (中身)                  ← ヘッダーのクリックで表示/非表示するだけ

【使い方】
    f = SimpleCollapsible("選択", subtitle="1 機能")
    f.addWidget(QtWidgets.QLabel("中身"))        # f.contentLayout() で自由にレイアウト
    f.toggled.connect(lambda opened: ...)
    f.setExpanded(False)
    f.setSubtitle("2 機能")

縦に並べれば、閉じた分だけ下のフレームが詰まります(通常の QVBoxLayout の挙動)。
単体で動くよう、他モジュールへの依存はありません。
    - 単体:  python simple_collapsible.py
    - Maya:  import simple_collapsible; simple_collapsible.show_demo()
"""
from PySide6 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt

C_TITLE = QtGui.QColor("#ffffff")
C_SUB = QtGui.QColor("#a8a8a8")
C_ICON = QtGui.QColor("#b8b8b8")
C_LINE = QtGui.QColor("#5a5a5a")
C_ACCENT = QtGui.QColor("#5285a6")


def _em(widget, ratio):
    """フォント高さ基準の長さ(px)。UIスケール/DPIが変わっても比率が崩れない。"""
    return max(1, round(widget.fontMetrics().height() * ratio))


class _Header(QtWidgets.QWidget):
    clicked = QtCore.Signal()

    def __init__(self, owner):
        super().__init__(owner)
        self._o = owner
        self._hover = False
        self._kb_focus = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def _title_font(self):
        f = QtGui.QFont(self.font())
        f.setBold(True)
        return f

    def sizeHint(self):
        return QtCore.QSize(_em(self, 10), _em(self, 2.6))

    def minimumSizeHint(self):
        return QtCore.QSize(_em(self, 4), _em(self, 2.6))

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        self._kb_focus = False
        e.accept()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicked.emit()

    def focusInEvent(self, e):
        self._kb_focus = e.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason,
                                        Qt.ShortcutFocusReason)
        self.update()

    def focusOutEvent(self, e):
        self._kb_focus = False
        self.update()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self._kb_focus = True
            self.clicked.emit()
        else:
            e.ignore()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        w, h = self.width(), self.height()
        em = self.fontMetrics().height()
        cy = (h - 1) / 2.0

        # 矢印(開: ⌄ / 閉: ›)
        s = em * 0.28
        cx = em * 1.1
        pen = QtGui.QPen(C_TITLE if self._hover else C_ICON, max(1.5, em * 0.12))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        if self._o.isExpanded():
            p.drawPolyline([QtCore.QPointF(cx - s, cy - s * .5), QtCore.QPointF(cx, cy + s * .5),
                            QtCore.QPointF(cx + s, cy - s * .5)])
        else:
            p.drawPolyline([QtCore.QPointF(cx - s * .5, cy - s), QtCore.QPointF(cx + s * .5, cy),
                            QtCore.QPointF(cx - s * .5, cy + s)])

        # タイトル + サブタイトル
        x = em * 2.2
        tf = self._title_font()
        tfm = QtGui.QFontMetrics(tf)
        title = tfm.elidedText(self._o._title, Qt.ElideRight, max(1, int(w - x - em * 0.5)))
        p.setFont(tf)
        p.setPen(C_TITLE)
        p.drawText(QtCore.QRectF(x, 0, w - x, h - 1), Qt.AlignVCenter | Qt.AlignLeft, title)
        x += tfm.horizontalAdvance(title) + em * 0.6
        sub = self._o._subtitle
        if sub and x < w:
            p.setFont(self.font())
            p.setPen(C_SUB)
            p.drawText(QtCore.QRectF(x, 0, w - x, h - 1), Qt.AlignVCenter | Qt.AlignLeft,
                       self.fontMetrics().elidedText(sub, Qt.ElideRight, int(w - x)))

        # 下線
        p.fillRect(QtCore.QRectF(0, h - 1, w, 1), C_LINE)

        if self._kb_focus and self.hasFocus():
            p.setFont(self.font())
            p.setBrush(Qt.NoBrush)
            p.setPen(QtGui.QPen(C_ACCENT, 1))
            p.drawRoundedRect(QtCore.QRectF(1.5, 1.5, w - 3, h - 4), 3, 3)


class SimpleCollapsible(QtWidgets.QWidget):
    """ヘッダー + 中身。クリックで中身を show/hide するだけのフレーム。"""
    toggled = QtCore.Signal(bool)            # 開いたら True

    def __init__(self, title="", subtitle="", expanded=True, parent=None):
        super().__init__(parent)
        self._title = title
        self._subtitle = subtitle
        self._expanded = bool(expanded)
        self._header = _Header(self)
        self._body = QtWidgets.QWidget(self)
        self._body_lay = QtWidgets.QVBoxLayout(self._body)
        em = self.fontMetrics().height()
        self._body_lay.setContentsMargins(round(em * 2.2), round(em * 0.6), round(em * 0.6), round(em * 0.6))
        self._body_lay.setSpacing(4)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._header)
        lay.addWidget(self._body)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self._body.setVisible(self._expanded)
        self._header.clicked.connect(self.toggle)

    def title(self):
        return self._title

    def setTitle(self, text):
        self._title = text
        self._header.update()

    def subtitle(self):
        return self._subtitle

    def setSubtitle(self, text):
        self._subtitle = text
        self._header.update()

    def contentLayout(self):
        return self._body_lay

    def addWidget(self, w, *args, **kw):
        self._body_lay.addWidget(w, *args, **kw)

    def addLayout(self, lay, *args, **kw):
        self._body_lay.addLayout(lay, *args, **kw)

    def isExpanded(self):
        return self._expanded

    def toggle(self):
        self.setExpanded(not self._expanded)

    def setExpanded(self, expanded):
        expanded = bool(expanded)
        if expanded == self._expanded:
            return
        self._expanded = expanded
        self._body.setVisible(expanded)
        self._header.update()
        self.toggled.emit(expanded)


# ===========================================================================
# デモ
# ===========================================================================
DEMO_OBJECT_NAME = "simpleCollapsibleDemoWindow"


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
        self.setWindowTitle("simple_collapsible demo")
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#484848"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#dddddd"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)
        self.setFocusPolicy(Qt.ClickFocus)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 8, 12, 8)
        lay.setSpacing(4)
        self.frames = []
        for title, sub, items in (("選択", "1 機能", ["頂点", "エッジ", "フェース"]),
                                  ("表示", "2 機能", ["ワイヤフレーム", "ライト"]),
                                  ("その他", "", ["未設定"])):
            f = SimpleCollapsible(title, sub, expanded=(title != "その他"))
            for n in items:
                f.addWidget(QtWidgets.QCheckBox(n))
            lay.addWidget(f)
            self.frames.append(f)
        lay.addStretch(1)
        self.resize(420, 360)

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