"""
underline_tabs.py
PySide6 (Maya 2027 対応) アンダーラインが動くタブウィジェット

    一般   表示   プロジェクト (上書き 1)
    ▔▔▔▔                          ← 選択中のタブの下線。タブを切り替えると、横にスライドして移動する

収録:
    1. UnderlineTabBar    : タブバー本体(主役)。1ウィジェットで全タブを描画
                            - 下線が伸び縮みしながらスライド(進行方向の端が先に動く)
                            - タブごとのバッジ(「上書き 1」のようなピル型の小ラベル)
                            - ホバー(うっすら下線)、キーボード(←/→/Home/End)、無効タブ、ツールチップ
                            - シグナル: currentChanged(int) / currentTextChanged(str)
    2. UnderlineTabWidget : UnderlineTabBar + ページ(QStackedWidget)の組み合わせ

【使い方】
    tabs = UnderlineTabWidget()
    tabs.addTab(page_general, "一般")
    tabs.addTab(page_project, "プロジェクト", badge="上書き 1")      # バッジ付き
    tabs.setTabBadge(2, "上書き 2")                                 # 後から変更/消去(空文字)
    tabs.currentChanged.connect(...)

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python underline_tabs.py
    - Maya:  import underline_tabs; underline_tabs.show_demo()
"""
from PySide6 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt


def _em(widget, ratio):
    """フォント高さ基準の長さ(px)。UIスケール/DPIが変わっても比率が崩れない。"""
    return max(1, round(widget.fontMetrics().height() * ratio))


def _lerp(a, b, t):
    return a + (b - a) * t


def _lerp_color(a, b, t):
    t = max(0.0, min(1.0, t))
    return QtGui.QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


# バッジ: kind -> (背景, 文字)
BADGE_COLORS = {
    "warn": ("#5c4428", "#f3d5b2"),
    "ok": ("#3d5c3a", "#c6efc2"),
    "error": ("#5c3b43", "#f6cbd3"),
    "info": ("#34495e", "#cfe5f7"),
}


# ===========================================================================
# 1. UnderlineTabBar
# ===========================================================================
class UnderlineTabBar(QtWidgets.QWidget):
    """下線が動くタブバー。排他選択(常にどれか1つが選択状態)。"""

    currentChanged = QtCore.Signal(int)
    currentTextChanged = QtCore.Signal(str)

    # 参考画像から実測した配色
    COLOR_BG = "#3a3a3a"
    COLOR_UNDERLINE = "#5285a6"
    COLOR_BASELINE = "#2b73c5"   # タブバー下端の全幅の細線
    COLOR_TEXT = "#c4c4c4"
    COLOR_TEXT_SELECTED = "#ffffff"
    COLOR_TEXT_DISABLED = "#707070"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs = []          # dict(text, badge, kind, enabled, tooltip)
        self._hover_t = []
        self._hover_anims = []
        self._current = -1
        self._hover_index = -1
        self._pressed_index = -1
        self._baseline_visible = True

        # 下線アニメーション: _t 0..1。_from は開始時点の下線 (left, right)
        self._from = None
        self._t = 1.0
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(260)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_anim)
        self._ease_lead = QtCore.QEasingCurve(QtCore.QEasingCurve.OutCubic)     # 進行方向の端
        self._ease_trail = QtCore.QEasingCurve(QtCore.QEasingCurve.InOutCubic)  # 後ろの端

        self.setFocusPolicy(Qt.TabFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------
    def addTab(self, text, badge="", badge_kind="warn", tooltip=""):
        """タブを追加してインデックスを返す。badge は「上書き 1」のような小ラベル(空なら無し)。"""
        self._tabs.append(dict(text=text, badge=badge, kind=badge_kind, enabled=True, tooltip=tooltip))
        self._hover_t.append(0.0)
        i = len(self._tabs) - 1
        a = QtCore.QVariantAnimation(self)
        a.setDuration(110)
        a.valueChanged.connect(lambda v, i=i: self._on_hover_value(i, v))
        self._hover_anims.append(a)
        self.updateGeometry()
        if self._current < 0:
            self.setCurrentIndex(0, animate=False)
        else:
            self.update()
        return i

    def count(self):
        return len(self._tabs)

    def tabText(self, index):
        return self._tabs[index]["text"]

    def setTabText(self, index, text):
        self._tabs[index]["text"] = text
        self._geometry_changed()

    def setTabBadge(self, index, text, kind=None):
        """バッジを設定する。text が空ならバッジを消す。"""
        t = self._tabs[index]
        t["badge"] = text
        if kind:
            t["kind"] = kind
        self._geometry_changed()

    def setTabEnabled(self, index, enabled):
        """無効なタブは選択できず、キー移動でもスキップされる。"""
        self._tabs[index]["enabled"] = bool(enabled)
        self.update()

    def setTabToolTip(self, index, text):
        self._tabs[index]["tooltip"] = text

    def setBaselineVisible(self, on):
        """タブバー下端の全幅の細線の表示/非表示。"""
        self._baseline_visible = bool(on)
        self.update()

    def currentIndex(self):
        return self._current

    def currentText(self):
        return self._tabs[self._current]["text"] if self._current >= 0 else ""

    def setCurrentIndex(self, index, animate=True):
        if not (0 <= index < len(self._tabs)) or index == self._current:
            return
        if not self._tabs[index]["enabled"]:
            return
        old_span = self._underline_span() if self._current >= 0 else None
        self._current = index
        self._anim.stop()
        if animate and old_span is not None and self.isVisible():
            self._from = old_span
            self._t = 0.0
            self._anim.start()
        else:
            self._from = None
            self._t = 1.0
            self.update()
        self.currentChanged.emit(index)
        self.currentTextChanged.emit(self._tabs[index]["text"])

    def setAnimationDuration(self, ms):
        self._anim.setDuration(int(ms))

    # ------------------------------------------------------------------
    # アニメーション
    # ------------------------------------------------------------------
    def _on_anim(self, v):
        self._t = float(v)
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

    def _geometry_changed(self):
        self.updateGeometry()
        self.update()

    # ------------------------------------------------------------------
    # 寸法(すべてフォント基準)
    # ------------------------------------------------------------------
    def _pad_x(self):
        return _em(self, 1.0)

    def _tab_gap(self):
        return _em(self, 0.3)

    def _margin_left(self):
        return _em(self, 0.6)

    def _underline_h(self):
        return max(2, _em(self, 0.15))

    def _bold_font(self):
        f = QtGui.QFont(self.font())
        f.setBold(True)
        return f

    def _badge_font(self):
        f = QtGui.QFont(self.font())
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() * 0.85)
        return f

    def _badge_size(self, text):
        fm = QtGui.QFontMetrics(self._badge_font())
        return QtCore.QSize(fm.horizontalAdvance(text) + _em(self, 1.1), fm.height() + _em(self, 0.3))

    def _tab_width(self, t):
        # 選択時は太字になるので、常に太字で測る(選択でタブ幅が変わらない)
        fm = QtGui.QFontMetrics(self._bold_font())
        w = self._pad_x() * 2 + fm.horizontalAdvance(t["text"])
        if t["badge"]:
            w += _em(self, 0.6) + self._badge_size(t["badge"]).width()
        return w

    def _tab_rect(self, i):
        x = self._margin_left()
        for k in range(i):
            x += self._tab_width(self._tabs[k]) + self._tab_gap()
        return QtCore.QRectF(x, 0, self._tab_width(self._tabs[i]), self.height())

    def _index_at(self, pos):
        for i in range(len(self._tabs)):
            if self._tab_rect(i).contains(pos):
                return i
        return -1

    def sizeHint(self):
        w = self._margin_left()
        for t in self._tabs:
            w += self._tab_width(t) + self._tab_gap()
        return QtCore.QSize(int(w), _em(self, 2.4))

    def minimumSizeHint(self):
        return self.sizeHint()

    # ------------------------------------------------------------------
    # 下線(伸び縮みしながらスライド)
    # ------------------------------------------------------------------
    def _underline_span(self):
        """現在の下線の (left, right)。アニメーション中は進行方向の端が先に動く。"""
        if self._current < 0:
            return 0.0, 0.0
        tr = self._tab_rect(self._current)
        to_l, to_r = tr.left(), tr.right()
        if self._from is None or self._t >= 1.0:
            return to_l, to_r
        fl, fr = self._from
        lead = self._ease_lead.valueForProgress(self._t)
        trail = self._ease_trail.valueForProgress(self._t)
        if to_l >= fl:   # 右へ移動: 右端が先行
            return _lerp(fl, to_l, trail), _lerp(fr, to_r, lead)
        return _lerp(fl, to_l, lead), _lerp(fr, to_r, trail)   # 左へ移動: 左端が先行

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QtGui.QColor(self.COLOR_BG))

        # 全幅の細線(タブバーの下端)
        base_h = 1 if self._baseline_visible else 0
        if self._baseline_visible:
            p.fillRect(QtCore.QRect(0, h - 1, w, 1), QtGui.QColor(self.COLOR_BASELINE))

        if not self._tabs:
            return

        accent = QtGui.QColor(self.COLOR_UNDERLINE)
        ul_h = self._underline_h()
        ul_y = h - base_h - ul_h

        # 1) ホバー中のタブにうっすら下線
        for i, t in enumerate(self._tabs):
            if i != self._current and t["enabled"] and self._hover_t[i] > 0:
                c = QtGui.QColor(accent)
                c.setAlpha(round(110 * self._hover_t[i]))
                r = self._tab_rect(i)
                p.fillRect(QtCore.QRectF(r.left(), ul_y, r.width(), ul_h), c)

        # 2) 選択の下線
        l, r = self._underline_span()
        p.setPen(Qt.NoPen)
        p.setBrush(accent)
        p.drawRoundedRect(QtCore.QRectF(l, ul_y, max(0.0, r - l), ul_h), ul_h / 2, ul_h / 2)

        # 3) ラベル + バッジ
        normal_font, bold_font = self.font(), self._bold_font()
        c_text = QtGui.QColor(self.COLOR_TEXT)
        c_sel = QtGui.QColor(self.COLOR_TEXT_SELECTED)
        content_h = h - base_h - ul_h
        for i, t in enumerate(self._tabs):
            tr = self._tab_rect(i)
            # 下線との重なり具合で文字色を補間(スライドに合わせて白くなる)
            overlap = max(0.0, min(r, tr.right()) - max(l, tr.left())) / tr.width()
            if t["enabled"] and self.isEnabled():
                col = _lerp_color(c_text, c_sel, max(overlap, self._hover_t[i] * 0.6))
            else:
                col = QtGui.QColor(self.COLOR_TEXT_DISABLED)

            font = bold_font if i == self._current else normal_font
            fm = QtGui.QFontMetrics(font)
            p.setFont(font)
            p.setPen(col)
            text_w = fm.horizontalAdvance(t["text"])
            # バッジ込みの内容幅を、タブの中で中央に置く
            badge_w = (_em(self, 0.6) + self._badge_size(t["badge"]).width()) if t["badge"] else 0
            x = tr.left() + (tr.width() - text_w - badge_w) / 2
            text_rect = QtCore.QRectF(x, 0, text_w + 1, content_h)
            p.drawText(text_rect, int(Qt.AlignLeft | Qt.AlignVCenter), t["text"])

            if t["badge"]:
                bg, fg = BADGE_COLORS.get(t["kind"], BADGE_COLORS["warn"])
                bs = self._badge_size(t["badge"])
                br = QtCore.QRectF(x + text_w + _em(self, 0.6), (content_h - bs.height()) / 2,
                                   bs.width(), bs.height())
                bgc, fgc = QtGui.QColor(bg), QtGui.QColor(fg)
                if not (t["enabled"] and self.isEnabled()):
                    bgc.setAlpha(110)
                    fgc.setAlpha(140)
                p.setPen(Qt.NoPen)
                p.setBrush(bgc)
                p.drawRoundedRect(br, br.height() / 2, br.height() / 2)
                p.setFont(self._badge_font())
                p.setPen(fgc)
                p.drawText(br, int(Qt.AlignCenter), t["badge"])

        # 4) フォーカス枠(Tabで来た時のみ)
        if self.hasFocus() and self._current >= 0:
            tr = self._tab_rect(self._current)
            p.setBrush(Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 140), 1.2))
            p.drawRoundedRect(QtCore.QRectF(tr.left() + 2, 3, tr.width() - 4, content_h - 4), 3, 3)

    # ------------------------------------------------------------------
    # マウス
    # ------------------------------------------------------------------
    def mouseMoveEvent(self, e):
        i = self._index_at(e.position())
        self._set_hover(i if (i >= 0 and self._tabs[i]["enabled"]) else -1)
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._set_hover(-1)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            i = self._index_at(e.position())
            self._pressed_index = i if (i >= 0 and self._tabs[i]["enabled"]) else -1
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        # 押したタブの上で離した時だけ確定
        if e.button() == Qt.LeftButton:
            i = self._index_at(e.position())
            pressed, self._pressed_index = self._pressed_index, -1
            if i >= 0 and i == pressed:
                self.setCurrentIndex(i)
        super().mouseReleaseEvent(e)

    def event(self, e):
        if e.type() == QtCore.QEvent.ToolTip:
            i = self._index_at(e.pos().toPointF())
            tip = self._tabs[i]["tooltip"] if i >= 0 else ""
            if tip:
                QtWidgets.QToolTip.showText(e.globalPos(), tip, self)
            else:
                QtWidgets.QToolTip.hideText()
                e.ignore()
            return True
        return super().event(e)

    # ------------------------------------------------------------------
    # キーボード
    # ------------------------------------------------------------------
    def _step(self, direction):
        i = self._current + direction
        while 0 <= i < len(self._tabs):
            if self._tabs[i]["enabled"]:
                self.setCurrentIndex(i)
                return
            i += direction

    def _to_edge(self, from_start):
        rng = range(len(self._tabs)) if from_start else range(len(self._tabs) - 1, -1, -1)
        for i in rng:
            if self._tabs[i]["enabled"]:
                self.setCurrentIndex(i)
                return

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Left, Qt.Key_Up):
            self._step(-1)
        elif k in (Qt.Key_Right, Qt.Key_Down):
            self._step(+1)
        elif k == Qt.Key_Home:
            self._to_edge(True)
        elif k == Qt.Key_End:
            self._to_edge(False)
        else:
            super().keyPressEvent(e)

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
        self._anim.stop()      # 非表示中の変更をずれなく反映
        self._from, self._t = None, 1.0
        super().showEvent(e)


# ===========================================================================
# 2. UnderlineTabWidget
# ===========================================================================
class UnderlineTabWidget(QtWidgets.QWidget):
    """UnderlineTabBar(上)+ ページ(下)。タブ選択でページが切り替わる。"""

    currentChanged = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._bar = UnderlineTabBar()
        self._stack = QtWidgets.QStackedWidget()
        lay.addWidget(self._bar)
        lay.addWidget(self._stack, 1)
        self._bar.currentChanged.connect(self._stack.setCurrentIndex)
        self._bar.currentChanged.connect(self.currentChanged)

    def tabBar(self):
        return self._bar

    def stack(self):
        return self._stack

    def addTab(self, page, text, badge="", badge_kind="warn", tooltip=""):
        """ページとタブを追加してインデックスを返す。"""
        self._stack.addWidget(page)     # 先にページを入れる(最初のタブ選択でページが切り替わるため)
        return self._bar.addTab(text, badge, badge_kind, tooltip)

    def page(self, index):
        return self._stack.widget(index)

    def count(self):
        return self._bar.count()

    def currentIndex(self):
        return self._bar.currentIndex()

    def setCurrentIndex(self, index):
        self._bar.setCurrentIndex(index)

    def setTabBadge(self, index, text, kind=None):
        self._bar.setTabBadge(index, text, kind)

    def setTabEnabled(self, index, enabled):
        self._bar.setTabEnabled(index, enabled)

    def setTabText(self, index, text):
        self._bar.setTabText(index, text)


# ===========================================================================
# デモ
# ===========================================================================
DEMO_OBJECT_NAME = "underlineTabsDemo"


def _maya_main_window():
    """Mayaが無い環境では None を返す(単体実行できるように)。"""
    try:
        from maya import OpenMayaUI as omui
        from shiboken6 import wrapInstance
    except ImportError:
        return None
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


def _label_page(text, hint=""):
    page = QtWidgets.QWidget()
    lay = QtWidgets.QVBoxLayout(page)
    lay.setContentsMargins(16, 14, 16, 14)
    lb = QtWidgets.QLabel(text)
    f = lb.font()
    f.setBold(True)
    f.setPointSizeF(f.pointSizeF() * 1.3)
    lb.setFont(f)
    lay.addWidget(lb)
    if hint:
        sub = QtWidgets.QLabel(hint)
        pal = sub.palette()
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#a0a0a0"))
        sub.setPalette(pal)
        lay.addWidget(sub)
    lay.addStretch()
    return page


class DemoWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(DEMO_OBJECT_NAME)
        self.setWindowTitle("Underline Tabs Demo")
        self.setWindowFlags(Qt.Window)
        self.resize(560, 360)

        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#454545"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#dddddd"))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#5d5d5d"))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#dddddd"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.tabs = UnderlineTabWidget()
        self.tabs.addTab(_label_page("一般", "言語・確認ダイアログなど"), "一般", tooltip="基本設定")
        self.tabs.addTab(_label_page("表示", "テーブルやカードの表示設定"), "表示")
        self.tabs.addTab(_label_page("プロジェクト", "プロジェクトごとの上書き設定"), "プロジェクト", badge="上書き 1")
        self.tabs.addTab(_label_page("詳細", "(無効なタブの例)"), "詳細")
        self.tabs.setTabEnabled(3, False)
        lay.addWidget(self.tabs, 1)

        # バッジの更新を試すボタン
        row = QtWidgets.QHBoxLayout()
        row.setContentsMargins(12, 6, 12, 8)
        row.setSpacing(8)
        self.btn = QtWidgets.QPushButton("バッジ +1")
        self.btn2 = QtWidgets.QPushButton("バッジを消す")
        row.addWidget(self.btn)
        row.addWidget(self.btn2)
        self.status = QtWidgets.QLabel()
        row.addWidget(self.status, 1)
        lay.addLayout(row)

        self._n = 1
        self.btn.clicked.connect(self._badge_plus)
        self.btn2.clicked.connect(lambda: self.tabs.setTabBadge(2, ""))
        self.tabs.currentChanged.connect(
            lambda i: self.status.setText(f"currentChanged: {i}  ({self.tabs.tabBar().currentText()})"))

    def _badge_plus(self):
        self._n += 1
        self.tabs.setTabBadge(2, f"上書き {self._n}")


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