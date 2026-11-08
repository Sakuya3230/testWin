"""
custom_checkbox.py
PySide6 (Maya 2027 対応) 描画ベースのカスタムチェックボックス

    [✓] 正規化する        ← チェック時は青塗り + 白いチェックが「描かれる」アニメーション
    [ ] 既存スキンを置き換え  ← 未チェックは白いボックス + グレーの縁

特長:
    - QAbstractButton 継承なので toggled / clicked / setChecked / setEnabled / Spaceキー操作はそのまま使える
    - 3状態(未チェック / 一部チェック / チェック)に対応: setCheckState(Qt.PartiallyChecked)
      (「すべて選択」のチェックボックスなどに。クリックするとチェック状態になる)
    - チェックマークを描くアニメーション、ホバー、押下、フォーカス枠、無効状態
    - ボックスの大きさ・余白・角丸はフォント高さ基準なので、MayaのUIスケール変更に追従
    - 文字部分もクリック可能(標準のチェックボックスと同じ)。幅が足りなければ省略表示

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python custom_checkbox.py
    - Maya:  import custom_checkbox; custom_checkbox.show_demo()
"""
from PySide6 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt


def _em(widget, ratio):
    """フォント高さ基準の長さ(px)。UIスケール/DPIが変わっても比率が崩れない。"""
    return max(1, round(widget.fontMetrics().height() * ratio))


def _lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return QtGui.QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


class CheckBox(QtWidgets.QAbstractButton):
    """カスタムチェックボックス。"""

    # 参考画像から実測した配色
    COLOR_CHECKED = "#0075ff"
    COLOR_CHECKED_HOVER = "#2086ff"
    COLOR_BOX = "#ffffff"
    COLOR_BORDER = "#767676"
    COLOR_BORDER_HOVER = "#b4b4b4"
    COLOR_MARK = "#ffffff"

    stateChanged = QtCore.Signal(Qt.CheckState)   # 未チェック / 一部 / チェックの変化

    def __init__(self, text="", checked=False, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self._partial = False
        self._c_checked = QtGui.QColor(self.COLOR_CHECKED)

        self._t = 1.0 if checked else 0.0      # チェックの進行度 0..1(アニメーション)
        self._hover_t = 0.0
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(130)
        self._anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._hover_anim = QtCore.QVariantAnimation(self)
        self._hover_anim.setDuration(110)
        self._hover_anim.valueChanged.connect(self._on_hover)

        super().setChecked(checked)            # 初期状態はアニメーションなしで反映(接続前)
        self.toggled.connect(self._on_toggled)

        self.setFocusPolicy(Qt.TabFocus)       # Tabで来た時だけフォーカス枠(クリックでは出さない)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------
    def setCheckedColor(self, color):
        self._c_checked = QtGui.QColor(color)
        self.update()

    def checkState(self):
        if self._partial:
            return Qt.PartiallyChecked
        return Qt.Checked if self.isChecked() else Qt.Unchecked

    def setCheckState(self, state):
        """Qt.Unchecked / Qt.PartiallyChecked / Qt.Checked を設定する。"""
        before = self.checkState()
        if state == Qt.PartiallyChecked:
            self._partial = True
            self._go(1.0)                       # 見た目は「青塗り + ー」
            if self.isChecked():
                super().setChecked(False)       # toggled を発行(チェック → 一部)
        else:
            self._partial = False
            if self.isChecked() == (state == Qt.Checked):
                self._go(1.0 if state == Qt.Checked else 0.0)   # 一部 → 同じ状態の見た目に戻す
            super().setChecked(state == Qt.Checked)
        if self.checkState() != before:
            self.stateChanged.emit(self.checkState())

    def setChecked(self, checked):
        self.setCheckState(Qt.Checked if checked else Qt.Unchecked)

    def isPartiallyChecked(self):
        return self._partial

    def nextCheckState(self):
        # クリック時: 一部チェック → チェック。それ以外は通常のトグル。
        if self._partial:
            self.setCheckState(Qt.Checked)
        else:
            self.setCheckState(Qt.Unchecked if self.isChecked() else Qt.Checked)

    # ------------------------------------------------------------------
    # アニメーション
    # ------------------------------------------------------------------
    def _go(self, target):
        a = self._anim
        a.stop()
        if not self.isVisible():                # 非表示中はアニメーションせず即反映
            self._t = float(target)
            self.update()
            return
        a.setStartValue(self._t)
        a.setEndValue(float(target))
        a.start()

    def _on_toggled(self, checked):
        # setCheckState 経由なら _go 済み。直接 toggle() された場合に備えて追従
        if not self._partial:
            self._go(1.0 if checked else 0.0)

    def _on_anim(self, v):
        self._t = float(v)
        self.update()

    def _on_hover(self, v):
        self._hover_t = float(v)
        self.update()

    def _animate_hover(self, target):
        a = self._hover_anim
        a.stop()
        a.setStartValue(self._hover_t)
        a.setEndValue(float(target))
        a.start()

    def enterEvent(self, e):
        if self.isEnabled():
            self._animate_hover(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate_hover(0.0)
        super().leaveEvent(e)

    # ------------------------------------------------------------------
    # 寸法(フォント基準)
    # ------------------------------------------------------------------
    def _box(self):
        return _em(self, 1.4)

    def _gap(self):
        return _em(self, 0.6)

    def _margin(self):
        # ボックスの周りに確保する余白。フォーカス枠(ボックスの外側に描く)が切れないために必要
        return max(3, _em(self, 0.2))

    def sizeHint(self):
        fm = self.fontMetrics()
        m = self._margin()
        w = m * 2 + self._box()
        if self.text():
            w += self._gap() - m + fm.horizontalAdvance(self.text()) + 1
        return QtCore.QSize(w, max(self._box(), fm.height()) + m * 2)

    def minimumSizeHint(self):
        m = self._margin()
        w = m * 2 + self._box()
        if self.text():
            w += self._gap() - m + self.fontMetrics().horizontalAdvance("...")
        return QtCore.QSize(w, self.sizeHint().height())

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.5)

        box = self._box()
        r = QtCore.QRectF(self._margin(), (self.height() - box) / 2, box, box)
        radius = _em(self, 0.22)
        border_w = max(1.5, box * 0.08)

        t = self._t                              # 0 = 未チェック, 1 = チェック(または一部)
        hover = self._hover_t if self.isEnabled() else 0.0

        # --- ボックス ---
        # 塗り: 白 → 青 / 縁: グレー → 青(ホバーで少し明るく)
        checked_col = _lerp_color(self._c_checked, QtGui.QColor(self.COLOR_CHECKED_HOVER), hover)
        if self.isDown():
            checked_col = checked_col.darker(112)
        fill = _lerp_color(QtGui.QColor(self.COLOR_BOX), checked_col, t)
        if self.isDown() and t < 0.5:
            fill = fill.darker(108)
        border_unchecked = _lerp_color(QtGui.QColor(self.COLOR_BORDER),
                                       QtGui.QColor(self.COLOR_BORDER_HOVER), hover)
        border = _lerp_color(border_unchecked, checked_col, t)

        p.setBrush(fill)
        p.setPen(QtGui.QPen(border, border_w))
        half = border_w / 2
        p.drawRoundedRect(r.adjusted(half, half, -half, -half), radius, radius)

        # --- チェックマーク(線が伸びるように描く) ---
        mark = QtGui.QColor(self.COLOR_MARK)
        pen = QtGui.QPen(mark, max(1.6, box * 0.13), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        p.setBrush(Qt.NoBrush)
        p.setPen(pen)
        if self._partial:
            y = r.center().y()
            p.drawLine(QtCore.QPointF(r.left() + box * 0.26, y), QtCore.QPointF(r.right() - box * 0.26, y))
        elif t > 0.0:
            pts = [QtCore.QPointF(r.left() + box * 0.24, r.top() + box * 0.53),
                   QtCore.QPointF(r.left() + box * 0.43, r.top() + box * 0.72),
                   QtCore.QPointF(r.left() + box * 0.77, r.top() + box * 0.30)]
            l1 = QtCore.QLineF(pts[0], pts[1]).length()
            l2 = QtCore.QLineF(pts[1], pts[2]).length()
            drawn = t * (l1 + l2)
            path = QtGui.QPainterPath(pts[0])
            if drawn <= l1:
                path.lineTo(QtCore.QLineF(pts[0], pts[1]).pointAt(drawn / l1))
            else:
                path.lineTo(pts[1])
                path.lineTo(QtCore.QLineF(pts[1], pts[2]).pointAt(min(1.0, (drawn - l1) / l2)))
            p.drawPath(path)

        # --- フォーカス枠(Tabで来た時のみ) ---
        if self.hasFocus():
            # ダーク背景でも沈まないよう、チェック色を明るくした色で描く
            ring = QtGui.QColor(self._c_checked).lighter(165)
            p.setBrush(Qt.NoBrush)
            p.setPen(QtGui.QPen(ring, 1.5))
            p.drawRoundedRect(r.adjusted(-2.5, -2.5, 2.5, 2.5), radius + 2, radius + 2)

        # --- ラベル ---
        if self.text():
            x = r.right() + self._gap()
            fm = self.fontMetrics()
            text = fm.elidedText(self.text(), Qt.ElideRight, max(0, int(self.width() - x)))
            p.setPen(self.palette().color(QtGui.QPalette.WindowText))
            p.drawText(QtCore.QRectF(x, 0, self.width() - x, self.height()),
                       int(Qt.AlignLeft | Qt.AlignVCenter), text)

    def changeEvent(self, e):
        if e.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.EnabledChange,
                        QtCore.QEvent.PaletteChange):
            if e.type() == QtCore.QEvent.EnabledChange and not self.isEnabled():
                self._hover_anim.stop()
                self._hover_t = 0.0
            self.updateGeometry()
            self.update()
        super().changeEvent(e)

    def showEvent(self, e):
        # 非表示中の状態変更をずれなく反映
        self._anim.stop()
        self._t = 1.0 if (self.isChecked() or self._partial) else 0.0
        super().showEvent(e)


# ---------------------------------------------------------------------------
# デモ
# ---------------------------------------------------------------------------
DEMO_OBJECT_NAME = "customCheckboxDemo"


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
        super().__init__(parent)
        self.setObjectName(DEMO_OBJECT_NAME)
        self.setWindowTitle("Custom CheckBox Demo")
        self.setWindowFlags(Qt.Window)
        self.resize(560, 340)

        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#3a3a3a"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#dddddd"))
        pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor("#888888"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(10)

        def header(text):
            lb = QtWidgets.QLabel(text)
            f = lb.font()
            f.setBold(True)
            lb.setFont(f)
            lay.addWidget(lb)

        # 参考画像と同じ2列グリッド
        header("オプション")
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        self.opts = [CheckBox("正規化する", True), CheckBox("名前一致でインフルエンス対応", True),
                     CheckBox("未バインドならスキンバインド", True), CheckBox("既存スキンを置き換え", False)]
        for i, cb in enumerate(self.opts):
            grid.addWidget(cb, i // 2, i % 2)   # 行方向に並べる(参考画像と同じ順)
        grid.setColumnStretch(2, 1)
        lay.addLayout(grid)

        # 3状態: 「すべて選択」
        header("3状態(すべて選択)")
        self.all_cb = CheckBox("すべて選択")
        lay.addWidget(self.all_cb)
        self.children = [CheckBox(t) for t in ("body_GEO", "head_GEO", "hand_L_GEO")]
        child_row = QtWidgets.QVBoxLayout()
        child_row.setContentsMargins(24, 0, 0, 0)
        for c in self.children:
            child_row.addWidget(c)
        lay.addLayout(child_row)
        self._syncing = False
        self.all_cb.clicked.connect(self._all_clicked)
        for c in self.children:
            c.toggled.connect(self._child_toggled)

        header("無効状態")
        row = QtWidgets.QHBoxLayout()
        d1, d2 = CheckBox("無効(チェック)", True), CheckBox("無効(未チェック)")
        d1.setEnabled(False)
        d2.setEnabled(False)
        row.addWidget(d1)
        row.addWidget(d2)
        row.addStretch()
        lay.addLayout(row)

        lay.addStretch()
        self.log = QtWidgets.QLabel("(操作するとここに表示)")
        lay.addWidget(self.log)
        for cb in self.opts:
            cb.toggled.connect(lambda on, t=cb.text(): self.log.setText(f"{t} = {on}"))

    def _all_clicked(self):
        if self._syncing:
            return
        self._syncing = True
        on = self.all_cb.isChecked()
        for c in self.children:
            c.setChecked(on)
        self._syncing = False

    def _child_toggled(self, _):
        if self._syncing:
            return
        self._syncing = True
        n = sum(c.isChecked() for c in self.children)
        state = Qt.Unchecked if n == 0 else (Qt.Checked if n == len(self.children) else Qt.PartiallyChecked)
        self.all_cb.setCheckState(state)
        self._syncing = False


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