"""
side_menu.py
PySide6 (Maya 2027 対応) 左側メニュー(アイコン上・ラベル下の縦ナビゲーション) + ページ切り替え

収録:
    1. SideMenu          : 左メニュー本体(主役)。1ウィジェットで全項目を描画
                           - アイコン(QIcon か ベクター描画関数)+ ラベル、項目ごとのアイコン色
                           - 選択ハイライトが縦にスライド / 項目ごとのホバーアニメーション
                           - マウス + キーボード(↑/↓/Home/End、Tabでフォーカス)
                           - 項目単位の有効/無効、ツールチップ
                           - シグナル: currentChanged(int) / currentTextChanged(str)
    2. SideMenuContainer : SideMenu + 右側のページ(QStackedWidget)を組み合わせたもの
                           addPage(title, widget=None, ...) で、widget を省略すると見出しラベルだけのページを作る
    3. PlaceholderPage   : 見出し(タイトル + 説明)だけのページ

【使い方】
    win = SideMenuContainer()
    win.addPage("インポート", my_import_widget, icon=icon_import, color="#6cc4bb")
    win.addPage("エクスポート")              # widget 省略 → ラベルだけのページ
    win.currentChanged.connect(...)

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python side_menu.py
    - Maya:  import side_menu; side_menu.show_demo()
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


# ===========================================================================
# 1. SideMenu
# ===========================================================================
class SideMenu(QtWidgets.QWidget):
    """縦並びのナビゲーションメニュー。排他選択(常にどれか1つが選択状態)。"""

    currentChanged = QtCore.Signal(int)
    currentTextChanged = QtCore.Signal(str)

    # 参考画像から実測した配色
    COLOR_BG = "#333333"
    COLOR_LINE = "#383838"          # 右端の区切り線
    COLOR_SELECTED_BG = "#4f4f4f"
    COLOR_HOVER_BG = "#3d3d3d"
    COLOR_SELECTED_ACCENT = "#7fb4e3"   # 選択中のアイコン色
    COLOR_TEXT = "#d8d8d8"
    COLOR_DEFAULT_ICON = "#b0b0b0"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []         # dict(text, icon, icon_fn, color, enabled, tooltip)
        self._hover_t = []
        self._hover_anims = []
        self._current = -1
        self._sel_pos = 0.0      # 選択ハイライトの位置(項目インデックス単位。アニメで補間)
        self._hover_index = -1
        self._pressed_index = -1

        self._slide = QtCore.QVariantAnimation(self)
        self._slide.setDuration(150)
        self._slide.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._slide.valueChanged.connect(self._on_slide)

        self.setFocusPolicy(Qt.TabFocus)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        # 幅はコンテンツで決まり、高さは親に合わせて伸びる
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Expanding)

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------
    def addItem(self, text, icon=None, color=None, tooltip=""):
        """
        項目を追加してそのインデックスを返す。
            icon:  QIcon / 描画関数 fn(painter, QRectF, QColor) / None
            color: 非選択時のアイコン色(描画関数のアイコンに効く)
        """
        item = dict(text=text, icon=None, icon_fn=None,
                    color=QtGui.QColor(color or self.COLOR_DEFAULT_ICON),
                    enabled=True, tooltip=tooltip)
        if callable(icon):
            item["icon_fn"] = icon
        elif icon is not None:
            item["icon"] = icon
        self._items.append(item)

        self._hover_t.append(0.0)
        i = len(self._items) - 1
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
        return len(self._items)

    def itemText(self, index):
        return self._items[index]["text"]

    def setItemText(self, index, text):
        self._items[index]["text"] = text
        self.updateGeometry()
        self.update()

    def setItemColor(self, index, color):
        self._items[index]["color"] = QtGui.QColor(color)
        self.update()

    def setItemToolTip(self, index, text):
        self._items[index]["tooltip"] = text

    def setItemEnabled(self, index, enabled):
        """項目単位の有効/無効。無効な項目は選択できず、キー移動でもスキップされる。"""
        self._items[index]["enabled"] = bool(enabled)
        self.update()

    def currentIndex(self):
        return self._current

    def currentText(self):
        return self._items[self._current]["text"] if self._current >= 0 else ""

    def setCurrentIndex(self, index, animate=True):
        if not (0 <= index < len(self._items)) or index == self._current:
            return
        if not self._items[index]["enabled"]:
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
        self.currentTextChanged.emit(self._items[index]["text"])

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
    # 寸法(すべてフォント基準)
    # ------------------------------------------------------------------
    def _item_h(self):
        return _em(self, 4.2)

    def _gap(self):
        return _em(self, 0.15)

    def _top(self):
        return _em(self, 0.8)

    def _icon_size(self):
        return _em(self, 1.5)

    def _bold_font(self):
        f = QtGui.QFont(self.font())
        f.setBold(True)
        return f

    def sizeHint(self):
        # 選択時は太字になるので、太字で測った最大幅に合わせる(選択で幅が変わらない)
        fm = QtGui.QFontMetrics(self._bold_font())
        widest = max((fm.horizontalAdvance(it["text"]) for it in self._items), default=0)
        w = max(widest + _em(self, 1.2), _em(self, 5.5))
        n = len(self._items)
        h = self._top() * 2 + n * self._item_h() + max(0, n - 1) * self._gap()
        return QtCore.QSize(w, h)

    def minimumSizeHint(self):
        return self.sizeHint()

    def _item_rect(self, pos):
        """pos は小数インデックス(スライド中の位置にも使う)。"""
        y = self._top() + pos * (self._item_h() + self._gap())
        return QtCore.QRectF(0, y, self.width() - 1, self._item_h())

    def _index_at(self, p):
        for i in range(len(self._items)):
            if self._item_rect(i).contains(p):
                return i
        return -1

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        bg = QtGui.QColor(self.COLOR_BG)
        p.fillRect(self.rect(), bg)
        # 右端の区切り線
        p.fillRect(QtCore.QRect(self.width() - 1, 0, 1, self.height()), QtGui.QColor(self.COLOR_LINE))

        if not self._items:
            return

        c_hover = QtGui.QColor(self.COLOR_HOVER_BG)
        c_sel_bg = QtGui.QColor(self.COLOR_SELECTED_BG)
        c_accent = QtGui.QColor(self.COLOR_SELECTED_ACCENT)
        c_text = QtGui.QColor(self.COLOR_TEXT)
        radius = 0  # 画像は角丸なし。角丸にしたい場合はここを _em(self, 0.3) などに

        # 1) ホバー/押下の背景(非選択のみ)
        p.setPen(Qt.NoPen)
        for i, it in enumerate(self._items):
            if not it["enabled"]:
                continue
            t = self._hover_t[i]
            col = _lerp_color(bg, c_hover, t)
            if i == self._pressed_index and i != self._current:
                col = col.lighter(115)
            if t > 0 or i == self._pressed_index:
                p.setBrush(col)
                p.drawRoundedRect(self._item_rect(i), radius, radius)

        # 2) 選択ハイライト(スライド中は2項目にまたがる)
        p.setBrush(c_sel_bg)
        p.drawRoundedRect(self._item_rect(self._sel_pos), radius, radius)

        # 3) アイコン + ラベル
        nearest = int(round(self._sel_pos))
        isz = self._icon_size()
        gap = _em(self, 0.4)
        normal_font, bold_font = self.font(), self._bold_font()
        for i, it in enumerate(self._items):
            r = self._item_rect(i)
            closeness = max(0.0, 1.0 - abs(i - self._sel_pos))
            enabled = it["enabled"] and self.isEnabled()

            font = bold_font if i == nearest else normal_font
            fm = QtGui.QFontMetrics(font)
            block = isz + gap + fm.height()
            y0 = r.top() + (r.height() - block) / 2

            icon_rect = QtCore.QRectF(r.center().x() - isz / 2, y0, isz, isz)
            if enabled:
                icon_col = _lerp_color(it["color"], c_accent, closeness)
                text_col = _lerp_color(c_text, QtGui.QColor("#ffffff"), closeness)
            else:
                icon_col = QtGui.QColor("#6a6a6a")
                text_col = QtGui.QColor("#777777")

            if it["icon_fn"] is not None:
                p.save()
                it["icon_fn"](p, icon_rect, icon_col)
                p.restore()
            elif it["icon"] is not None:
                mode = QtGui.QIcon.Normal if enabled else QtGui.QIcon.Disabled
                it["icon"].paint(p, icon_rect.toRect(), Qt.AlignCenter, mode)

            p.setFont(font)
            p.setPen(text_col)
            text_w = int(r.width() - _em(self, 0.4))
            text = fm.elidedText(it["text"], Qt.ElideRight, text_w)
            text_rect = QtCore.QRectF(r.left(), y0 + isz + gap, r.width(), fm.height())
            p.drawText(text_rect, int(Qt.AlignHCenter | Qt.AlignVCenter), text)

        # 4) フォーカス枠(Tabで来た時のみ)
        if self.hasFocus() and self._current >= 0:
            p.setBrush(Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 150), 1.5))
            p.drawRect(self._item_rect(self._current).adjusted(2, 2, -2, -2))

    # ------------------------------------------------------------------
    # マウス
    # ------------------------------------------------------------------
    def mouseMoveEvent(self, e):
        i = self._index_at(e.position())
        self._set_hover(i if (i >= 0 and self._items[i]["enabled"]) else -1)
        super().mouseMoveEvent(e)

    def leaveEvent(self, e):
        self._set_hover(-1)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            i = self._index_at(e.position())
            self._pressed_index = i if (i >= 0 and self._items[i]["enabled"]) else -1
            self.update()
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        # 押した項目の上で離した時だけ確定
        if e.button() == Qt.LeftButton:
            i = self._index_at(e.position())
            pressed, self._pressed_index = self._pressed_index, -1
            if i >= 0 and i == pressed:
                self.setCurrentIndex(i)
            self.update()
        super().mouseReleaseEvent(e)

    def event(self, e):
        if e.type() == QtCore.QEvent.ToolTip:
            i = self._index_at(e.pos().toPointF())
            tip = self._items[i]["tooltip"] if i >= 0 else ""
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
        while 0 <= i < len(self._items):
            if self._items[i]["enabled"]:
                self.setCurrentIndex(i)
                return
            i += direction

    def _to_edge(self, from_start):
        rng = range(len(self._items)) if from_start else range(len(self._items) - 1, -1, -1)
        for i in rng:
            if self._items[i]["enabled"]:
                self.setCurrentIndex(i)
                return

    def keyPressEvent(self, e):
        k = e.key()
        if k in (Qt.Key_Up, Qt.Key_Left):
            self._step(-1)
        elif k in (Qt.Key_Down, Qt.Key_Right):
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
        self._sel_pos = float(max(0, self._current))  # 非表示中の変更をずれなく反映
        super().showEvent(e)


# ===========================================================================
# 2. PlaceholderPage / SideMenuContainer
# ===========================================================================
class PlaceholderPage(QtWidgets.QWidget):
    """見出し(タイトル + 説明)だけのページ。中身は後から差し替える前提の仮ページ。"""

    def __init__(self, title, description="", accent="#7fb4e3", parent=None):
        super().__init__(parent)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)

        head = QtWidgets.QHBoxLayout()
        self.title_label = QtWidgets.QLabel(title)
        f = self.title_label.font()
        f.setBold(True)
        f.setPointSizeF(f.pointSizeF() * 1.3)
        self.title_label.setFont(f)
        pal = self.title_label.palette()
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(accent))
        self.title_label.setPalette(pal)
        head.addWidget(self.title_label)

        self.desc_label = QtWidgets.QLabel(description)
        pal = self.desc_label.palette()
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#a0a0a0"))
        self.desc_label.setPalette(pal)
        head.addWidget(self.desc_label, 1)
        lay.addLayout(head)
        lay.addStretch()


class SideMenuContainer(QtWidgets.QWidget):
    """左に SideMenu、右にページ(QStackedWidget)。メニュー選択でページが切り替わる。"""

    currentChanged = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self._menu = SideMenu()
        self._stack = QtWidgets.QStackedWidget()
        lay.addWidget(self._menu)
        lay.addWidget(self._stack, 1)
        self._menu.currentChanged.connect(self._stack.setCurrentIndex)
        self._menu.currentChanged.connect(self.currentChanged)

    def menu(self):
        return self._menu

    def stack(self):
        return self._stack

    def addPage(self, title, page=None, icon=None, color=None, description="", tooltip=""):
        """
        ページを追加してインデックスを返す。
        page を省略すると、title と description の見出しだけのページを作る。
        """
        if page is None:
            page = PlaceholderPage(title, description)
        self._stack.addWidget(page)             # 先にページを入れる(メニューの初回選択で切り替わるため)
        return self._menu.addItem(title, icon, color, tooltip)

    def page(self, index):
        return self._stack.widget(index)

    def currentIndex(self):
        return self._menu.currentIndex()

    def setCurrentIndex(self, index):
        self._menu.setCurrentIndex(index)


# ===========================================================================
# デモ用アイコン(描画関数 fn(painter, QRectF, QColor))
# ===========================================================================
def _pen(p, r, c, width=0.085):
    p.setPen(QtGui.QPen(c, max(1.3, r.width() * width), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)


def _pt(r, x, y):
    """矩形 r の中の相対座標(0..1)を QPointF に。"""
    return QtCore.QPointF(r.left() + r.width() * x, r.top() + r.height() * y)


def _tray(p, r):
    p.drawPolyline(QtGui.QPolygonF([_pt(r, 0.0, 0.62), _pt(r, 0.0, 1.0), _pt(r, 1.0, 1.0), _pt(r, 1.0, 0.62)]))


def icon_import(p, r, c):
    _pen(p, r, c)
    _tray(p, r)
    p.drawLine(_pt(r, 0.5, 0.0), _pt(r, 0.5, 0.72))
    p.drawPolyline(QtGui.QPolygonF([_pt(r, 0.24, 0.46), _pt(r, 0.5, 0.74), _pt(r, 0.76, 0.46)]))


def icon_export(p, r, c):
    _pen(p, r, c)
    _tray(p, r)
    p.drawLine(_pt(r, 0.5, 0.74), _pt(r, 0.5, 0.02))
    p.drawPolyline(QtGui.QPolygonF([_pt(r, 0.24, 0.28), _pt(r, 0.5, 0.0), _pt(r, 0.76, 0.28)]))


def icon_brush(p, r, c):
    _pen(p, r, c)
    p.translate(r.center())
    p.rotate(40)
    p.translate(-r.center())
    p.drawRoundedRect(QtCore.QRectF(r.left() + r.width() * 0.3, r.top() - r.height() * 0.05,
                                    r.width() * 0.4, r.height() * 0.5), 2, 2)
    p.drawLine(_pt(r, 0.5, 0.45), _pt(r, 0.5, 1.05))


def icon_joint(p, r, c):
    _pen(p, r, c)
    rad = r.width() * 0.15
    a, b = _pt(r, 0.18, 0.82), _pt(r, 0.82, 0.18)
    d = QtCore.QPointF(b.x() - a.x(), b.y() - a.y())
    n = (d.x() ** 2 + d.y() ** 2) ** 0.5
    u = QtCore.QPointF(d.x() / n * rad, d.y() / n * rad)
    p.drawEllipse(a, rad, rad)
    p.drawEllipse(b, rad, rad)
    p.drawLine(a + u, b - u)


def icon_bindpose(p, r, c):
    _pen(p, r, c)
    p.drawEllipse(_pt(r, 0.5, 0.15), r.width() * 0.13, r.width() * 0.13)
    p.drawPolyline(QtGui.QPolygonF([_pt(r, 0.1, 0.42), _pt(r, 0.5, 0.5), _pt(r, 0.9, 0.42)]))
    p.drawLine(_pt(r, 0.5, 0.3), _pt(r, 0.5, 0.68))
    p.drawPolyline(QtGui.QPolygonF([_pt(r, 0.25, 1.0), _pt(r, 0.5, 0.68), _pt(r, 0.75, 1.0)]))


def icon_mesh(p, r, c):
    _pen(p, r, c)
    p.drawPolygon(QtGui.QPolygonF([_pt(r, 0.5, 0.0), _pt(r, 1.0, 1.0), _pt(r, 0.0, 1.0)]))
    p.drawLine(_pt(r, 0.5, 0.0), _pt(r, 0.5, 1.0))
    p.drawLine(_pt(r, 0.25, 0.5), _pt(r, 0.75, 0.5))


# ===========================================================================
# デモ
# ===========================================================================
DEMO_OBJECT_NAME = "sideMenuDemo"

DEMO_PAGES = [
    ("インポート", icon_import, "#6cc4bb", "ウエイトファイルを読み込みメッシュに適用"),
    ("エクスポート", icon_export, "#6cc4bb", "スキンウエイトをファイルに書き出し"),
    ("ウエイト", icon_brush, "#e88a9c", "ウエイトの編集・コピー・正規化"),
    ("ジョイント", icon_joint, "#e3a35c", "ジョイントの選択・リマップ"),
    ("バインドポーズ", icon_bindpose, "#b398e0", "バインドポーズの確認と復元"),
    ("メッシュ", icon_mesh, "#7cbf76", "スキンメッシュの整理"),
]


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
        self.setWindowTitle("Side Menu Demo")
        self.setWindowFlags(Qt.Window)
        self.resize(720, 460)

        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#444444"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(220, 220, 220))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        self.container = SideMenuContainer()
        for title, icon, color, desc in DEMO_PAGES:
            self.container.addPage(title, icon=icon, color=color, description=desc, tooltip=desc)
        lay.addWidget(self.container, 1)

        self.status = QtWidgets.QLabel()
        self.status.setContentsMargins(8, 4, 8, 4)
        lay.addWidget(self.status)
        self.container.currentChanged.connect(
            lambda i: self.status.setText(f"currentChanged: {i}  ({self.container.menu().currentText()})"))


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