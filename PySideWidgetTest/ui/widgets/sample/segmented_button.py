"""
segmented_button.py
PySide6 (Maya 2027 対応) セグメント(切り替え)ボタン

    [ 頂点番号 | 頂点座標 | UV座標 ]   ← どれか1つだけが選択状態になる排他ボタン

特長:
    - 1つのウィジェットが全セグメントを描画(QButtonGroup + 複数ボタンより軽く、見た目も一体)
    - 選択ハイライトが横にスライドするアニメーション / セグメントごとのホバーアニメーション
    - マウス操作 + キーボード操作(←/→/Home/End、Tabでフォーカス)
    - セグメント単位の有効/無効、全体の有効/無効
    - シグナル: currentChanged(int) / currentTextChanged(str)
    - 余白・角丸はフォント高さ基準なので Maya のUIスケール変更に追従

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python segmented_button.py
    - Maya:  import segmented_button; segmented_button.show_demo()
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


class SegmentedButton(QtWidgets.QWidget):
    """排他選択のセグメントボタン。"""

    currentChanged = QtCore.Signal(int)
    currentTextChanged = QtCore.Signal(str)

    # 参考画像から実測した配色
    COLOR_SELECTED = "#5285a6"
    COLOR_NORMAL = "#4a4a4a"
    COLOR_LINE = "#2b2b2b"   # 区切り線と外枠

    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self._items = []          # [text, ...]
        self._enabled = []        # [bool, ...] セグメント単位の有効状態
        self._hover_t = []        # セグメントごとのホバー進行度 0..1
        self._hover_anims = []
        self._current = -1
        self._sel_pos = 0.0       # 選択ハイライトの位置(インデックス単位。アニメーションで補間)
        self._hover_index = -1
        self._pressed_index = -1

        self._c_selected = QtGui.QColor(self.COLOR_SELECTED)
        self._c_normal = QtGui.QColor(self.COLOR_NORMAL)
        self._c_line = QtGui.QColor(self.COLOR_LINE)

        self._slide = QtCore.QVariantAnimation(self)
        self._slide.setDuration(150)
        self._slide.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._slide.valueChanged.connect(self._on_slide)

        # Tabキーで来た時だけフォーカス(クリックでフォーカス枠が出ない/Mayaのショートカットを奪いにくい)
        self.setFocusPolicy(Qt.TabFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

        if items:
            self.setItems(items)

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------
    def setItems(self, items, current=0):
        """項目を丸ごと入れ替える。current は最初に選択するインデックス。"""
        for a in self._hover_anims:
            a.stop()
            a.deleteLater()
        self._items = list(items)
        n = len(self._items)
        self._enabled = [True] * n
        self._hover_t = [0.0] * n
        self._hover_anims = []
        for i in range(n):
            a = QtCore.QVariantAnimation(self)
            a.setDuration(110)
            a.valueChanged.connect(lambda v, i=i: self._on_hover_value(i, v))
            self._hover_anims.append(a)

        self._current = -1
        self._hover_index = self._pressed_index = -1
        self.updateGeometry()
        if n:
            self.setCurrentIndex(current, animate=False)
        else:
            self.update()

    def addItem(self, text):
        cur = self._current
        self.setItems(self._items + [text], current=max(cur, 0))

    def count(self):
        return len(self._items)

    def itemText(self, index):
        return self._items[index]

    def currentIndex(self):
        return self._current

    def currentText(self):
        return self._items[self._current] if 0 <= self._current < len(self._items) else ""

    def setCurrentIndex(self, index, animate=True):
        if not (0 <= index < len(self._items)) or index == self._current:
            return
        if not self._enabled[index]:
            return
        self._current = index
        self._slide.stop()
        if animate and self.isVisible():
            self._slide.setStartValue(self._sel_pos)
            self._slide.setEndValue(float(index))
            self._slide.start()
        else:
            self._sel_pos = float(index)
            self.update()
        self.currentChanged.emit(index)
        self.currentTextChanged.emit(self._items[index])

    def setCurrentText(self, text):
        if text in self._items:
            self.setCurrentIndex(self._items.index(text))

    def setItemEnabled(self, index, enabled):
        """セグメント単位の有効/無効。無効な項目は選択できない。"""
        if 0 <= index < len(self._items):
            self._enabled[index] = bool(enabled)
            self.update()

    def setSelectedColor(self, color):
        self._c_selected = QtGui.QColor(color)
        self.update()

    # ------------------------------------------------------------------
    # アニメーション
    # ------------------------------------------------------------------
    def _on_slide(self, v):
        self._sel_pos = float(v)
        self.update()

    def _on_hover_value(self, i, v):
        if i < len(self._hover_t):
            self._hover_t[i] = float(v)
            self.update()

    def _set_hover(self, index):
        if index == self._hover_index:
            return
        old, self._hover_index = self._hover_index, index
        for i, target in ((old, 0.0), (index, 1.0)):
            if 0 <= i < len(self._hover_anims):
                a = self._hover_anims[i]
                a.stop()
                a.setStartValue(self._hover_t[i])
                a.setEndValue(target)
                a.start()

    # ------------------------------------------------------------------
    # サイズ
    # ------------------------------------------------------------------
    def _bold_font(self):
        f = QtGui.QFont(self.font())
        f.setBold(True)
        return f

    def _segment_width_hint(self):
        # 選択時は太字になるので、太字で測った最大幅に合わせる(選択で幅が変わらないように)
        fm = QtGui.QFontMetrics(self._bold_font())
        widest = max((fm.horizontalAdvance(t) for t in self._items), default=0)
        return widest + _em(self, 2.4)

    def sizeHint(self):
        n = max(1, len(self._items))
        return QtCore.QSize(self._segment_width_hint() * n, self.fontMetrics().height() + _em(self, 1.1))

    def minimumSizeHint(self):
        return self.sizeHint()

    # ------------------------------------------------------------------
    # 位置計算
    # ------------------------------------------------------------------
    def _seg_rect(self, i):
        n = max(1, len(self._items))
        w = self.width() / n
        return QtCore.QRectF(i * w, 0, w, self.height())

    def _index_at(self, pos):
        n = len(self._items)
        if n == 0 or not self.rect().contains(pos):
            return -1
        return min(n - 1, int(pos.x() / (self.width() / n)))

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------
    def paintEvent(self, e):
        n = len(self._items)
        if n == 0:
            return
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.45)

        outer = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = _em(self, 0.3)
        seg_w = self.width() / n

        # --- 全体を角丸でクリップして、各セグメントは単純な矩形で塗る --------
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(outer, radius, radius)
        p.save()
        p.setClipPath(clip)

        # 1) 非選択の地色(+ホバー/押下)
        p.setPen(Qt.NoPen)
        for i in range(n):
            base = self._c_normal
            if not self._enabled[i]:
                base = base.darker(115)
            else:
                base = _lerp_color(base, base.lighter(125), self._hover_t[i])
                if i == self._pressed_index and i != self._current:
                    base = base.darker(115)
            p.setBrush(base)
            p.drawRect(QtCore.QRectF(i * seg_w, 0, seg_w + 1, self.height()))

        # 2) 選択ハイライト(スライド中は2つのセグメントにまたがる)
        sel = QtCore.QRectF(self._sel_pos * seg_w, 0, seg_w, self.height())
        hi = self._c_selected
        if 0 <= self._current < n:
            hi = _lerp_color(hi, hi.lighter(112), self._hover_t[self._current])
        p.setBrush(hi)
        p.drawRect(sel)

        # 3) 区切り線(1px)
        p.setPen(QtGui.QPen(self._c_line, 1))
        for i in range(1, n):
            x = round(i * seg_w) - 0.5 + 0.5
            p.drawLine(QtCore.QPointF(x, 0), QtCore.QPointF(x, self.height()))
        p.restore()

        # 4) 外枠
        p.setBrush(Qt.NoBrush)
        p.setPen(QtGui.QPen(self._c_line, 1))
        p.drawRoundedRect(outer, radius, radius)

        # 5) テキスト: ハイライトに近いセグメントほど白く、最寄りのセグメントだけ太字
        nearest = int(round(self._sel_pos))
        normal_font, bold_font = self.font(), self._bold_font()
        pad = _em(self, 0.6)
        for i in range(n):
            closeness = max(0.0, 1.0 - abs(i - self._sel_pos))
            if self._enabled[i]:
                fg = _lerp_color(QtGui.QColor(215, 215, 215), QtGui.QColor(255, 255, 255), closeness)
            else:
                fg = QtGui.QColor(125, 125, 125)
            font = bold_font if i == nearest else normal_font
            p.setFont(font)
            p.setPen(fg)
            r = QtCore.QRectF(i * seg_w + pad, 0, seg_w - pad * 2, self.height())
            text = QtGui.QFontMetrics(font).elidedText(self._items[i], Qt.ElideRight, int(r.width()))
            p.drawText(r, int(Qt.AlignCenter), text)

        # 6) フォーカス枠(Tabで来た時のみ)
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 170), 1.5))
            p.drawRoundedRect(outer.adjusted(2, 2, -2, -2), radius, radius)

    # ------------------------------------------------------------------
    # マウス
    # ------------------------------------------------------------------
    def mouseMoveEvent(self, e):
        i = self._index_at(e.position().toPoint())
        self._set_hover(i if (i >= 0 and self._enabled[i]) else -1)
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._set_hover(-1)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            i = self._index_at(e.position().toPoint())
            self._pressed_index = i if (i >= 0 and self._enabled[i]) else -1
            self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        # 押したセグメント上で離した時だけ確定(ボタンの一般的な挙動)
        if e.button() == Qt.LeftButton:
            i = self._index_at(e.position().toPoint())
            pressed, self._pressed_index = self._pressed_index, -1
            if i >= 0 and i == pressed:
                self.setCurrentIndex(i)
            self.update()
        super().mouseReleaseEvent(e)

    # ------------------------------------------------------------------
    # キーボード
    # ------------------------------------------------------------------
    def _step(self, direction):
        """有効なセグメントだけを辿って選択を移動する。"""
        i = self._current + direction
        while 0 <= i < len(self._items):
            if self._enabled[i]:
                self.setCurrentIndex(i)
                return
            i += direction

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Left, Qt.Key_Up):
            self._step(-1)
        elif k in (Qt.Key_Right, Qt.Key_Down):
            self._step(+1)
        elif k == Qt.Key_Home:
            self._current_to_edge(+1)
        elif k == Qt.Key_End:
            self._current_to_edge(-1)
        else:
            super().keyPressEvent(e)

    def _current_to_edge(self, from_start):
        rng = range(len(self._items)) if from_start > 0 else range(len(self._items) - 1, -1, -1)
        for i in rng:
            if self._enabled[i]:
                self.setCurrentIndex(i)
                return

    # ------------------------------------------------------------------
    # その他
    # ------------------------------------------------------------------
    def changeEvent(self, e):
        if e.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.EnabledChange,
                        QtCore.QEvent.PaletteChange):
            if e.type() == QtCore.QEvent.EnabledChange and not self.isEnabled():
                self._set_hover(-1)
            self.updateGeometry()
            self.update()
        super().changeEvent(e)

    def showEvent(self, e):
        # 非表示中に変更された選択位置をずれなく反映
        self._sel_pos = float(max(0, self._current))
        super().showEvent(e)


# ---------------------------------------------------------------------------
# デモ
# ---------------------------------------------------------------------------
DEMO_OBJECT_NAME = "segmentedButtonDemo"


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
        self.setWindowTitle("Segmented Button Demo")
        self.setWindowFlags(Qt.Window)
        self.resize(480, 300)

        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(68, 68, 68))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(220, 220, 220))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(8)

        def header(text):
            lb = QtWidgets.QLabel(text)
            f = lb.font()
            f.setBold(True)
            lb.setFont(f)
            lb.setContentsMargins(0, 6, 0, 0)
            lay.addWidget(lb)

        header("表示モード(3項目)")
        self.seg = SegmentedButton(["頂点番号", "頂点座標", "UV座標"])
        lay.addWidget(self.seg)
        self.pages = QtWidgets.QStackedWidget()
        for text in ("頂点番号を表示します", "頂点のワールド座標を表示します", "UV座標を表示します"):
            self.pages.addWidget(QtWidgets.QLabel(text))
        lay.addWidget(self.pages)
        self.seg.currentChanged.connect(self.pages.setCurrentIndex)

        header("2項目 + 無効な項目あり")
        self.seg2 = SegmentedButton(["Local", "World", "Object"])
        self.seg2.setItemEnabled(2, False)
        lay.addWidget(self.seg2)

        header("全体が無効")
        seg3 = SegmentedButton(["A", "B", "C", "D"])
        seg3.setCurrentIndex(1, animate=False)
        seg3.setEnabled(False)
        lay.addWidget(seg3)

        header("幅を固定して使う場合(左寄せ)")
        row = QtWidgets.QHBoxLayout()
        self.seg4 = SegmentedButton(["ON", "OFF"])
        self.seg4.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        row.addWidget(self.seg4)
        row.addStretch()
        lay.addLayout(row)

        self.log = QtWidgets.QLabel("(操作するとここに表示)")
        lay.addStretch()
        lay.addWidget(self.log)
        for seg, name in ((self.seg, "mode"), (self.seg2, "space"), (self.seg4, "toggle")):
            seg.currentTextChanged.connect(lambda t, n=name: self.log.setText(f"{n} -> {t}"))


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