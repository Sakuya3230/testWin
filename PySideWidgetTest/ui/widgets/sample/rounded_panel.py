"""
rounded_panel.py
PySide6 (Maya 2027 対応) 角丸の領域(パネル)

    ╭──────────────────────────────────────────╮
    │ 参照パス   [ [プロジェクト]/skin_weights ] [📁] │   ← 左にラベル列(全行で幅が揃う)
    │ 一時保存   [セーブ] [ロード]  メモリに保持…     │
    ╰──────────────────────────────────────────╯

収録:
    1. RoundedPanel : 角丸の塗り(+ 任意の枠線)を描くコンテナ。addRow(ラベル, 部品...) でラベル列が揃う
                      addWidget / addLayout でフリーレイアウトも可
    2. RoundButton  : 角丸ボタン(文字 or アイコン)。アイコンは fn(painter, QRectF, QColor)
    3. icon_folder  : フォルダのベクターアイコン
    4. make_line_edit : 角丸の入力欄(QLineEdit + スタイルシート)

【使い方】
    panel = RoundedPanel()
    edit = make_line_edit("[プロジェクト]/skin_weights")
    browse = RoundButton(icon=icon_folder)
    panel.addRow("参照パス", edit, browse)                       # 伸びる部品(入力欄など)が余白を取る
    save, load = RoundButton("セーブ"), RoundButton("ロード")
    panel.addRow("一時保存", save, load, QtWidgets.QLabel("メモリに保持"))
    panel.setRadius(10); panel.setBorder("#505050")             # 見た目の調整

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python rounded_panel.py
    - Maya:  import rounded_panel; rounded_panel.show_demo()
"""
from PySide6 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt

C_PANEL = QtGui.QColor("#414141")
C_BTN = QtGui.QColor("#5a5a5a")
C_BTN_HOVER = QtGui.QColor("#686868")
C_BTN_DOWN = QtGui.QColor("#4c4c4c")
C_BTN_TEXT = QtGui.QColor("#e6e6e6")
C_ICON = QtGui.QColor("#e6e6e6")
C_ACCENT = QtGui.QColor("#5285a6")
C_FIELD = "#2b2b2b"


def _em(widget, ratio):
    """フォント高さ基準の長さ(px)。UIスケール/DPIが変わっても比率が崩れない。"""
    return max(1, round(widget.fontMetrics().height() * ratio))


# ---------------------------------------------------------------------------
# アイコン  fn(painter, QRectF, QColor)
# ---------------------------------------------------------------------------
def icon_folder(p, r, c):
    s = r.width()
    x, y = r.left(), r.top()
    pen = QtGui.QPen(c, max(1.4, s * 0.09))
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)
    path = QtGui.QPainterPath()
    path.moveTo(x + s * .08, y + s * .22)
    path.lineTo(x + s * .38, y + s * .22)
    path.lineTo(x + s * .48, y + s * .34)
    path.lineTo(x + s * .92, y + s * .34)
    path.lineTo(x + s * .92, y + s * .80)
    path.lineTo(x + s * .08, y + s * .80)
    path.closeSubpath()
    p.drawPath(path)


# ===========================================================================
# 角丸ボタン
# ===========================================================================
class RoundButton(QtWidgets.QAbstractButton):
    """角丸のフラットボタン。文字 or アイコン(fn か QIcon)。アイコンのみの場合は正方形。"""

    def __init__(self, text="", icon=None, parent=None):
        super().__init__(parent)
        self.setText(text)
        self._icon_fn = icon
        self._hover = False
        self._kb_focus = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def setIconFn(self, fn):
        self._icon_fn = fn
        self.update()

    def sizeHint(self):
        h = _em(self, 2.5)
        if not self.text():
            return QtCore.QSize(h, h)
        return QtCore.QSize(self.fontMetrics().horizontalAdvance(self.text()) + _em(self, 2.4), h)

    def minimumSizeHint(self):
        return self.sizeHint()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def focusInEvent(self, e):
        self._kb_focus = e.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason,
                                        Qt.ShortcutFocusReason)
        super().focusInEvent(e)
        self.update()

    def focusOutEvent(self, e):
        self._kb_focus = False
        super().focusOutEvent(e)
        self.update()

    def mousePressEvent(self, e):
        self._kb_focus = False
        super().mousePressEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self._kb_focus = True
        super().keyPressEvent(e)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect())
        rad = _em(self, 0.4)
        if not self.isEnabled():
            bg = C_BTN.darker(130)
        elif self.isDown():
            bg = C_BTN_DOWN
        elif self._hover:
            bg = C_BTN_HOVER
        else:
            bg = C_BTN
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, rad, rad)
        col = C_BTN_TEXT if self.isEnabled() else QtGui.QColor("#888888")
        if self.text():
            p.setPen(col)
            p.drawText(r, Qt.AlignCenter, self.text())
        elif callable(self._icon_fn):
            s = r.height() * 0.58
            self._icon_fn(p, QtCore.QRectF(r.center().x() - s / 2, r.center().y() - s / 2, s, s), col)
        if self._kb_focus and self.hasFocus():
            p.setPen(QtGui.QPen(C_ACCENT, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(.5, .5, -.5, -.5), rad, rad)


# ===========================================================================
# 角丸の入力欄
# ===========================================================================
def make_line_edit(text="", placeholder="", parent=None):
    e = QtWidgets.QLineEdit(text, parent)
    e.setPlaceholderText(placeholder)
    e.setMinimumHeight(_em(e, 2.5))
    rad = _em(e, 0.4)
    pad = _em(e, 0.6)
    e.setStyleSheet(
        f"QLineEdit {{ background: {C_FIELD}; color: #e6e6e6; border: 1px solid transparent;"
        f" border-radius: {rad}px; padding: 0 {pad}px; selection-background-color: #5285a6; }}"
        f"QLineEdit:focus {{ border: 1px solid #5285a6; }}"
        f"QLineEdit:disabled {{ color: #777777; }}")
    return e


# ===========================================================================
# 角丸パネル
# ===========================================================================
class RoundedPanel(QtWidgets.QWidget):
    """角丸の塗りを描くコンテナ。行は addRow で追加(ラベル列が全行で揃う)。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._radius = None            # None: フォント比で自動
        self._fill = QtGui.QColor(C_PANEL)
        self._border = None
        self._rows = 0
        self._grid = QtWidgets.QGridLayout(self)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)
        self._apply_metrics()

    # ---- 見た目 ----
    def setRadius(self, px):
        self._radius = px
        self.update()

    def setFillColor(self, color):
        self._fill = QtGui.QColor(color)
        self.update()

    def setBorder(self, color=None):
        """枠線色を指定(None で枠なし)。"""
        self._border = QtGui.QColor(color) if color is not None else None
        self.update()

    def radius(self):
        return self._radius if self._radius is not None else _em(self, 0.8)

    def _apply_metrics(self):
        self._grid.setContentsMargins(_em(self, 1.3), _em(self, 1.0), _em(self, 1.3), _em(self, 1.0))
        self._grid.setHorizontalSpacing(_em(self, 1.4))
        self._grid.setVerticalSpacing(_em(self, 0.7))
        self._grid.setColumnStretch(1, 1)

    # ---- 中身 ----
    def contentLayout(self):
        return self._grid

    def addRow(self, label, *widgets):
        """左にラベル、右に部品を横並びで追加。横に伸びる部品が無ければ末尾に余白を足す。"""
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(_em(self, 0.6))
        stretches = False
        for w in widgets:
            if isinstance(w, QtWidgets.QWidget):
                row.addWidget(w)
                if w.sizePolicy().horizontalPolicy() in (QtWidgets.QSizePolicy.Expanding,
                                                         QtWidgets.QSizePolicy.MinimumExpanding):
                    stretches = True
            else:
                row.addLayout(w)
        if not stretches:
            row.addStretch(1)
        lb = QtWidgets.QLabel(label) if isinstance(label, str) else label
        self._grid.addWidget(lb, self._rows, 0, Qt.AlignVCenter)
        self._grid.addLayout(row, self._rows, 1)
        self._rows += 1
        return row

    def addWidget(self, w):
        """行を使わず全幅で追加。"""
        self._grid.addWidget(w, self._rows, 0, 1, 2)
        self._rows += 1

    def addLayout(self, lay):
        self._grid.addLayout(lay, self._rows, 0, 1, 2)
        self._rows += 1

    # ---- 描画 ----
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect())
        rad = self.radius()
        if self._border is not None:
            r = r.adjusted(.5, .5, -.5, -.5)
            p.setPen(QtGui.QPen(self._border, 1))
        else:
            p.setPen(Qt.NoPen)
        p.setBrush(self._fill)
        p.drawRoundedRect(r, rad, rad)


# ===========================================================================
# デモ
# ===========================================================================
DEMO_OBJECT_NAME = "roundedPanelDemoWindow"


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
        self.setWindowTitle("rounded_panel demo")
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#333333"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#cfcfcf"))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#2b2b2b"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#e6e6e6"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        # 参照画像と同じ構成
        panel = RoundedPanel()
        self.edit = make_line_edit("[プロジェクト]/skin_weights")
        self.btn_browse = RoundButton(icon=icon_folder)
        self.btn_save = RoundButton("セーブ")
        self.btn_load = RoundButton("ロード")
        self.note = QtWidgets.QLabel("ファイルを介さずメモリに保持・保持中: body_GEO(54)")
        self.note.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Preferred)
        panel.addRow("参照パス", self.edit, self.btn_browse)
        panel.addRow("一時保存", self.btn_save, self.btn_load, self.note)

        # バリエーション: 枠線付き・半径違い
        panel2 = RoundedPanel()
        panel2.setBorder("#5a5a5a")
        panel2.setFillColor("#383838")
        panel2.setRadius(14)
        panel2.addRow("名前", make_line_edit("", "名前を入力"))
        panel2.addRow("操作", RoundButton("適用"), RoundButton("リセット"))

        self.status = QtWidgets.QLabel("")
        self.btn_browse.clicked.connect(lambda: self.status.setText("フォルダ選択"))
        self.btn_save.clicked.connect(lambda: self.status.setText("セーブ"))
        self.btn_load.clicked.connect(lambda: self.status.setText("ロード"))

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        lay.setSpacing(12)
        lay.addWidget(panel)
        lay.addWidget(panel2)
        lay.addWidget(self.status)
        lay.addStretch(1)
        self.setFocusPolicy(Qt.ClickFocus)
        self.resize(620, 280)

    def showEvent(self, e):
        super().showEvent(e)
        self.setFocus()       # 起動直後に入力欄へフォーカスが付かないように


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