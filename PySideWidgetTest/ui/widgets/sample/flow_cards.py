"""
flow_cards.py
PySide6 (Maya 2027 対応) フローレイアウト + カード型ボタン

収録:
    1. FlowLayout : 幅に応じて折り返して並べるレイアウト
                    - 最大/最小列数、アイテムの最小幅/最大幅、行の揃え、余白を設定可能
                    - 均等幅モード(カードを揃えて並べる)と、通常のフローモード(各アイテムの sizeHint 幅)
                    - height-for-width 対応 / 非表示のウィジェットは自動で詰める(絞り込み表示向け)
    2. CardButton : [アイコン] タイトル(最大2行) / サブタイトル + お気に入り★ + 右下メニュー▲
    3. HfwWindow  : FlowLayout を直接ウィンドウに置くとき用の基底(下記の注意参照)

【注意】Qt はトップレベルウィンドウの最小の高さを height-for-width から計算しません。
    FlowLayout は QScrollArea(setWidgetResizable(True))の中に置くか、ウィンドウに直接置く場合は
    HfwWindow を継承してください(そうしないと、幅を狭めたときにカードが押し潰されます)。

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python flow_cards.py
    - Maya:  import flow_cards; flow_cards.show_demo()
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
# 1. FlowLayout
# ===========================================================================
class FlowLayout(QtWidgets.QLayout):
    """
    フローレイアウト。

    均等幅モード(setUniformItems(True), 既定):
        列数 = 「アイテム最小幅」で入る数(最小/最大列数で制限)。
        アイテム幅は残りの幅を等分して決まる(最大幅を設定すると、それ以上は広がらない)。
        最後の行が余っても、アイテムの幅は他の行と同じ(左寄せ等は setRowAlignment)。
        行の高さは、その行で一番高いアイテムに揃う。

    通常フローモード(setUniformItems(False)):
        各アイテムが自分の sizeHint の幅で並び、入らなくなったら次の行へ。
        最大列数は「1行に並べる最大数」として効く。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self._hs = 8
        self._vs = 8
        self._max_cols = 0       # 0 = 無制限
        self._min_cols = 1
        self._item_min_w = 0     # 0 = 全アイテムの sizeHint 幅の最大値を使う
        self._item_max_w = 0     # 0 = 無制限
        self._uniform = True
        self._row_align = Qt.AlignLeft

    # --- QLayout 必須実装 ---------------------------------------------------
    def addItem(self, item):
        self._items.append(item)
        self.invalidate()

    def insertWidget(self, index, widget):
        """指定位置にウィジェットを挿入する(並べ替え・お気に入り先頭表示などに)。"""
        self.addChildWidget(widget)
        self._items.insert(index, QtWidgets.QWidgetItem(widget))
        self.invalidate()

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            item = self._items.pop(index)
            self.invalidate()
            return item
        return None

    # --- 設定API -----------------------------------------------------------
    def setMaxColumns(self, n):
        """1行に並べる最大数。0 で無制限。"""
        self._max_cols = max(0, int(n))
        self.invalidate()

    def maxColumns(self):
        return self._max_cols

    def setMinColumns(self, n):
        """幅が足りなくても最低これだけは1行に並べる(アイテムは最小幅より細くなる)。"""
        self._min_cols = max(1, int(n))
        self.invalidate()

    def setItemMinWidth(self, px):
        """列数を決めるための「アイテムの最小幅」。0 なら全アイテムの sizeHint 幅の最大値。"""
        self._item_min_w = max(0, int(px))
        self.invalidate()

    def setItemMaxWidth(self, px):
        """アイテムが広がる上限。0 で無制限(残り幅を等分して使い切る)。"""
        self._item_max_w = max(0, int(px))
        self.invalidate()

    def setUniformItems(self, on):
        self._uniform = bool(on)
        self.invalidate()

    def setRowAlignment(self, align):
        """行全体の水平方向の寄せ(Qt.AlignLeft / AlignHCenter / AlignRight)。
        アイテムが最大幅で頭打ちになって余白ができたときに効く。"""
        self._row_align = align
        self.invalidate()

    def setHorizontalSpacing(self, px):
        self._hs = max(0, int(px))
        self.invalidate()

    def setVerticalSpacing(self, px):
        self._vs = max(0, int(px))
        self.invalidate()

    def setSpacing(self, px):
        self._hs = self._vs = max(0, int(px))
        self.invalidate()

    def spacing(self):
        return self._hs

    def horizontalSpacing(self):
        return self._hs

    def verticalSpacing(self):
        return self._vs

    # --- 計算 ---------------------------------------------------------------
    def _visible_items(self):
        # 非表示ウィジェットの QWidgetItem は isEmpty() が True になる
        return [it for it in self._items if not it.isEmpty()]

    def _inner_width(self, width):
        m = self.contentsMargins()
        return max(0, width - m.left() - m.right())

    def _uniform_metrics(self, items, avail):
        """均等幅モードの (列数, アイテム幅) を返す。"""
        sp = self._hs
        pref = self._item_min_w or max((it.sizeHint().width() for it in items), default=1)
        pref = max(1, pref)
        cols = (avail + sp) // (pref + sp)
        cols = max(self._min_cols, cols)
        if self._max_cols:
            cols = min(cols, self._max_cols)
        cols = max(1, cols)
        w = (avail - sp * (cols - 1)) // cols
        if self._item_max_w:
            w = min(w, self._item_max_w)
        return cols, max(1, w)

    def columnsForWidth(self, width):
        """レイアウト幅 width のときの1行の列数(均等幅モードのみ。通常モードは先頭行の数)。"""
        items = self._visible_items()
        if not items:
            return 0
        avail = self._inner_width(width)
        if self._uniform:
            return self._uniform_metrics(items, avail)[0]
        return len(self._classic_rows(items, avail)[0][0]) if items else 0

    @staticmethod
    def _item_h(item, w):
        return item.heightForWidth(w) if item.hasHeightForWidth() else item.sizeHint().height()

    def _align_offset(self, free):
        if free <= 0:
            return 0
        if self._row_align & Qt.AlignRight:
            return free
        if self._row_align & Qt.AlignHCenter:
            return free // 2
        return 0

    def _classic_rows(self, items, avail):
        rows, cur, cur_w = [], [], 0
        for it in items:
            iw = min(it.sizeHint().width(), avail) if avail > 0 else it.sizeHint().width()
            if self._item_max_w:
                iw = min(iw, self._item_max_w)
            need = iw + (self._hs if cur else 0)
            if cur and (cur_w + need > avail or (self._max_cols and len(cur) >= self._max_cols)):
                rows.append((cur, cur_w))
                cur, cur_w, need = [], 0, iw
            cur.append((it, iw))
            cur_w += need
        if cur:
            rows.append((cur, cur_w))
        return rows

    def _do_layout(self, rect, test_only):
        """配置を計算し(test_only=False ならアイテムも動かし)、必要な高さを返す。"""
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        avail = eff.width()
        items = self._visible_items()
        if not items:
            return m.top() + m.bottom()

        y = eff.y()
        if self._uniform:
            cols, w = self._uniform_metrics(items, avail)
            block_w = cols * w + (cols - 1) * self._hs
            x0 = eff.x() + self._align_offset(avail - block_w)
            for start in range(0, len(items), cols):
                row = items[start:start + cols]
                h = max(self._item_h(it, w) for it in row)
                if not test_only:
                    for i, it in enumerate(row):
                        it.setGeometry(QtCore.QRect(x0 + i * (w + self._hs), y, w, h))
                y += h + self._vs
        else:
            for row, row_w in self._classic_rows(items, avail):
                h = max(self._item_h(it, iw) for it, iw in row)
                x = eff.x() + self._align_offset(avail - row_w)
                for it, iw in row:
                    if not test_only:
                        it.setGeometry(QtCore.QRect(x, y, iw, self._item_h(it, iw)))
                    x += iw + self._hs
                y += h + self._vs

        return (y - self._vs) - rect.y() + m.bottom()

    # --- サイズ(height-for-width) -------------------------------------------
    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def expandingDirections(self):
        return Qt.Orientation(0)

    def sizeHint(self):
        items = self._visible_items()
        m = self.contentsMargins()
        if not items:
            return QtCore.QSize(m.left() + m.right(), m.top() + m.bottom())
        pref = self._item_min_w or max(it.sizeHint().width() for it in items)
        cols = self._max_cols or min(len(items), 3)
        w = cols * pref + (cols - 1) * self._hs + m.left() + m.right()
        return QtCore.QSize(w, self.heightForWidth(w))

    def minimumSize(self):
        m = self.contentsMargins()
        size = QtCore.QSize(0, 0)
        for it in self._visible_items():
            size = size.expandedTo(it.minimumSize())
        return size + QtCore.QSize(m.left() + m.right(), m.top() + m.bottom())


class HfwWindow(QtWidgets.QWidget):
    """height-for-width なレイアウトを直接載せるウィンドウ用。幅に応じて最小の高さを更新する。"""

    def _fit_min_height(self):
        lay = self.layout()
        if lay is None or not lay.hasHeightForWidth():
            return
        need = lay.minimumHeightForWidth(self.width())
        if need > 0 and need != self.minimumHeight():
            self.setMinimumHeight(need)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_min_height()

    def event(self, e):
        ok = super().event(e)
        if e.type() == QtCore.QEvent.LayoutRequest:
            self._fit_min_height()
        return ok


# ===========================================================================
# 2. CardButton
# ===========================================================================
def _wrap_lines(text, font, width, max_lines):
    """text を width で折り返し、max_lines を超えたら最終行を「…」で省略して、行ごとの文字列を返す。"""
    text = text.replace("\n", " ")
    layout = QtGui.QTextLayout(text, font)
    opt = QtGui.QTextOption()
    opt.setWrapMode(QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(opt)
    spans = []
    layout.beginLayout()
    while True:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(1, width))
        spans.append((line.textStart(), line.textLength()))
    layout.endLayout()

    lines = [text[s:s + n].rstrip() for s, n in spans]
    if len(lines) > max_lines:
        rest = text[spans[max_lines - 1][0]:]
        lines = lines[:max_lines - 1] + [QtGui.QFontMetrics(font).elidedText(rest, Qt.ElideRight, width)]
    return lines or [""]


class CardButton(QtWidgets.QAbstractButton):
    """
    カード型ボタン。
        ┌──────────────────────────────┐
        │ [アイコン]  タイトル(最大2行)   ★ │
        │            サブタイトル        ◢ │
        └──────────────────────────────┘
    - カード本体のクリック       → clicked
    - ★ のクリック             → favoriteToggled(bool)   (clicked は発行しない)
    - 右下 ◢ のクリック/右クリック → setMenu() のメニューを表示、無ければ menuRequested(QPoint)
    - アイコンは QIcon か、描画関数 fn(painter, QRectF, QColor) を渡せる
    """

    favoriteToggled = QtCore.Signal(bool)
    menuRequested = QtCore.Signal(QtCore.QPoint)   # グローバル座標

    COLOR_CARD = "#3a3a3a"
    COLOR_TILE = "#2b2b2b"
    COLOR_ACCENT = "#e88a9c"
    COLOR_STAR = "#f0c060"
    COLOR_TITLE = "#eeeeee"
    COLOR_SUB = "#a0a0a0"

    def __init__(self, title="", subtitle="", icon=None, favorite=False, parent=None):
        super().__init__(parent)
        self.setText(title)
        self._subtitle = subtitle
        self._icon_fn = None
        if callable(icon):
            self._icon_fn = icon
        elif icon is not None:
            self.setIcon(icon)
        self._favorite = bool(favorite)
        self._menu = None
        self._menu_indicator = True
        self._accent = QtGui.QColor(self.COLOR_ACCENT)

        self._hover_zone = None    # None / "card" / "star" / "corner"
        self._press_zone = None
        self._hover_t = 0.0
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(120)
        self._anim.valueChanged.connect(self._on_anim)

        self.setFocusPolicy(Qt.TabFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

    # --- 公開API ----------------------------------------------------------
    def subtitle(self):
        return self._subtitle

    def setSubtitle(self, text):
        self._subtitle = text
        self.update()

    def setIconPainter(self, fn):
        """fn(painter, QRectF, QColor) でアイコンを描く(ベクター。DPIに強い)。"""
        self._icon_fn = fn
        self.update()

    def isFavorite(self):
        return self._favorite

    def setFavorite(self, on):
        on = bool(on)
        if on != self._favorite:
            self._favorite = on
            self.update()
            self.favoriteToggled.emit(on)

    def setMenu(self, menu):
        self._menu = menu

    def setMenuIndicatorVisible(self, on):
        self._menu_indicator = bool(on)
        self.update()

    def setAccentColor(self, color):
        self._accent = QtGui.QColor(color)
        self.update()

    # --- 寸法(すべてフォント基準) --------------------------------------------
    def _pad(self):
        return _em(self, 0.6)

    def _text_block_h(self):
        # タイトル2行 + サブタイトル1行 ぶんを常に確保 → どのカードも同じ高さになる
        return self.fontMetrics().height() * 3

    def _card_h(self):
        return self._text_block_h() + self._pad() * 2

    def _tile(self):
        return self._card_h() - self._pad() * 2

    def sizeHint(self):
        return QtCore.QSize(_em(self, 16), self._card_h())

    def minimumSizeHint(self):
        return QtCore.QSize(_em(self, 10), self._card_h())

    def _star_rect(self):
        s = _em(self, 1.5)
        return QtCore.QRectF(self.width() - s - self._pad() * 0.4, self._pad() * 0.4, s, s)

    def _corner_rect(self):
        s = _em(self, 1.6)
        g = _em(self, 0.25)
        return QtCore.QRectF(self.width() - s - g, self.height() - s - g, s, s)

    def _zone_at(self, pos):
        if self._star_rect().contains(pos):
            return "star"
        if self._menu_indicator and self._corner_rect().contains(pos):
            return "corner"
        return "card"

    # --- アニメーション/状態 --------------------------------------------------
    def _on_anim(self, v):
        self._hover_t = float(v)
        self.update()

    def _animate_to(self, target):
        a = self._anim
        a.stop()
        a.setStartValue(self._hover_t)
        a.setEndValue(float(target))
        a.start()

    def enterEvent(self, e):
        if self.isEnabled():
            self._animate_to(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover_zone = None
        self._animate_to(0.0)
        self.update()
        super().leaveEvent(e)

    def changeEvent(self, e):
        if e.type() == QtCore.QEvent.EnabledChange and not self.isEnabled():
            self._anim.stop()
            self._hover_t = 0.0
            self._hover_zone = None
        if e.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.EnabledChange,
                        QtCore.QEvent.PaletteChange):
            self.updateGeometry()
            self.update()
        super().changeEvent(e)

    # --- マウス/キー -------------------------------------------------------------
    def mouseMoveEvent(self, e):
        z = self._zone_at(e.position())
        if z != self._hover_zone:
            self._hover_zone = z
            self.update()
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            z = self._zone_at(e.position())
            if z in ("star", "corner"):
                # ★/◢ は自前で処理(カード本体の clicked は発行しない)
                self._press_zone = z
                e.accept()
                return
        self._press_zone = None
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._press_zone is not None:
            z, self._press_zone = self._press_zone, None
            if e.button() == Qt.LeftButton and self._zone_at(e.position()) == z:
                if z == "star":
                    self.setFavorite(not self._favorite)
                else:
                    self._open_menu()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def _open_menu(self):
        anchor = self.mapToGlobal(self._corner_rect().bottomLeft().toPoint())
        if self._menu is not None:
            self._menu.exec(anchor)
        else:
            self.menuRequested.emit(anchor)

    def contextMenuEvent(self, e):
        if self._menu is not None:
            self._menu.exec(e.globalPos())
        else:
            self.menuRequested.emit(e.globalPos())

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.click()
        elif e.key() == Qt.Key_Menu:
            self._open_menu()
        else:
            super().keyPressEvent(e)

    # --- 描画 ------------------------------------------------------------------
    @staticmethod
    def _star_path(cx, cy, outer):
        import math
        path = QtGui.QPainterPath()
        inner = outer * 0.45
        for i in range(10):
            r = outer if i % 2 == 0 else inner
            a = -math.pi / 2 + i * math.pi / 5
            pt = QtCore.QPointF(cx + r * math.cos(a), cy + r * math.sin(a))
            if i == 0:
                path.moveTo(pt)
            else:
                path.lineTo(pt)
        path.closeSubpath()
        return path

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.5)

        w, h = self.width(), self.height()
        pad = self._pad()
        r = QtCore.QRectF(0, 0, w, h)
        radius = _em(self, 0.35)

        # --- 背景 ---
        base = QtGui.QColor(self.COLOR_CARD)
        bg = _lerp_color(base, base.lighter(112), self._hover_t)
        if self.isDown():
            bg = base.darker(112)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, radius, radius)

        # --- アクセント枠(ホバー/フォーカス) ---
        ring = 1.0 if self.hasFocus() else self._hover_t
        if ring > 0 and self.isEnabled():
            c = QtGui.QColor(self._accent)
            c.setAlpha(round(255 * ring))
            p.setBrush(Qt.NoBrush)
            p.setPen(QtGui.QPen(c, 2))
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), radius - 1, radius - 1)

        # --- アイコン枠 + アイコン ---
        tile = self._tile()
        tile_rect = QtCore.QRectF(pad, pad, tile, tile)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(self.COLOR_TILE))
        p.drawRoundedRect(tile_rect, radius * 0.9, radius * 0.9)

        glyph = tile_rect.adjusted(tile * 0.22, tile * 0.22, -tile * 0.22, -tile * 0.22)
        if self._icon_fn is not None:
            p.save()
            self._icon_fn(p, glyph, self._accent)
            p.restore()
        elif not self.icon().isNull():
            mode = QtGui.QIcon.Normal if self.isEnabled() else QtGui.QIcon.Disabled
            self.icon().paint(p, glyph.toRect(), Qt.AlignCenter, mode)

        # --- テキスト(タイトル最大2行 + サブタイトル1行を縦中央に) ---
        x0 = pad + tile + pad * 1.1
        title_w = int(w - pad - x0 - self._star_rect().width() * 0.9)
        sub_w = int(w - pad - x0 - (self._corner_rect().width() * 0.85 if self._menu_indicator else 0))

        bold = QtGui.QFont(self.font())
        bold.setBold(True)
        fm = QtGui.QFontMetrics(bold)
        lh = fm.height()
        title_lines = _wrap_lines(self.text(), bold, title_w, 2)
        n = len(title_lines) + (1 if self._subtitle else 0)
        y = (h - lh * n) / 2

        p.setFont(bold)
        p.setPen(QtGui.QColor(self.COLOR_TITLE))
        for line in title_lines:
            p.drawText(QtCore.QPointF(x0, y + fm.ascent()), line)
            y += lh
        if self._subtitle:
            p.setFont(self.font())
            p.setPen(QtGui.QColor(self.COLOR_SUB))
            sub = self.fontMetrics().elidedText(self._subtitle, Qt.ElideRight, sub_w)
            p.drawText(QtCore.QPointF(x0, y + self.fontMetrics().ascent()), sub)

        # --- ★ お気に入り ---
        sr = self._star_rect()
        star = self._star_path(sr.center().x(), sr.center().y(), sr.width() * 0.4)
        star_hover = self._hover_zone == "star"
        if self._favorite:
            col = QtGui.QColor(self.COLOR_STAR)
            p.setPen(Qt.NoPen)
            p.setBrush(col.lighter(115) if star_hover else col)
        else:
            col = QtGui.QColor("#d8d8d8" if star_hover else self.COLOR_SUB)
            p.setPen(QtGui.QPen(col, 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.setBrush(Qt.NoBrush)
        p.drawPath(star)

        # --- ◢ 右下メニュー ---
        if self._menu_indicator:
            cr = self._corner_rect()
            corner_hover = self._hover_zone == "corner"
            if corner_hover:
                p.setPen(Qt.NoPen)
                p.setBrush(QtGui.QColor("#555555"))
                p.drawRoundedRect(cr, radius * 0.7, radius * 0.7)
            s = cr.width() * 0.33
            cx, cy = cr.center().x(), cr.center().y()
            tri = QtGui.QPolygonF([QtCore.QPointF(cx + s, cy - s), QtCore.QPointF(cx + s, cy + s),
                                   QtCore.QPointF(cx - s, cy + s)])
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor("#e0e0e0" if corner_hover else "#8a8a8a"))
            p.drawPolygon(tri)


# ===========================================================================
# デモ用アイコン(描画関数 fn(painter, QRectF, QColor))
# ===========================================================================
def _pen(p, r, c, width=0.1):
    p.setPen(QtGui.QPen(c, max(1.2, r.width() * width), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)


def icon_normalize(p, r, c):
    _pen(p, r, c)
    cx = r.center().x()
    p.drawLine(QtCore.QPointF(r.left(), r.top()), QtCore.QPointF(r.right(), r.top()))
    p.drawLine(QtCore.QPointF(r.left(), r.bottom()), QtCore.QPointF(r.right(), r.bottom()))
    p.drawLine(QtCore.QPointF(cx, r.top() + 2), QtCore.QPointF(cx, r.bottom() - 2))


def icon_number(text):
    def draw(p, r, c):
        f = QtGui.QFont(p.font())
        f.setPixelSize(max(8, int(r.height() * 1.15)))
        p.setFont(f)
        p.setPen(c)
        p.drawText(r, int(Qt.AlignCenter), text)
    return draw


def icon_move(p, r, c):
    _pen(p, r, c)
    y = r.center().y()
    p.drawLine(QtCore.QPointF(r.left(), r.top()), QtCore.QPointF(r.left(), r.bottom()))
    p.drawLine(QtCore.QPointF(r.left() + r.width() * 0.3, y), QtCore.QPointF(r.right(), y))
    d = r.width() * 0.25
    p.drawLine(QtCore.QPointF(r.right() - d, y - d), QtCore.QPointF(r.right(), y))
    p.drawLine(QtCore.QPointF(r.right() - d, y + d), QtCore.QPointF(r.right(), y))


def icon_copy(p, r, c):
    _pen(p, r, c)
    s = r.width() * 0.65
    p.drawRoundedRect(QtCore.QRectF(r.left() + r.width() * 0.35, r.top(), s, s), 2, 2)
    p.drawRoundedRect(QtCore.QRectF(r.left(), r.top() + r.height() * 0.35, s, s), 2, 2)


def icon_link(p, r, c):
    _pen(p, r, c)
    rad = r.width() * 0.2
    y = r.center().y()
    p.drawEllipse(QtCore.QPointF(r.left() + rad, y), rad, rad)
    p.drawEllipse(QtCore.QPointF(r.right() - rad, y), rad, rad)
    p.drawLine(QtCore.QPointF(r.left() + rad * 2, y), QtCore.QPointF(r.right() - rad * 2, y))


def icon_brush(p, r, c):
    p.translate(r.center())
    p.rotate(40)
    s = r.width()
    p.translate(-r.center())
    _pen(p, r, c)
    cx = r.center().x()
    p.drawRoundedRect(QtCore.QRectF(cx - s * 0.28, r.top() - 2, s * 0.56, s * 0.5), 2, 2)
    p.drawLine(QtCore.QPointF(cx, r.top() + s * 0.5), QtCore.QPointF(cx, r.bottom() + 2))


def icon_cursor(p, r, c):
    _pen(p, r, c)
    pts = [QtCore.QPointF(r.left(), r.top()), QtCore.QPointF(r.left() + r.width() * 0.9, r.top() + r.height() * 0.45),
           QtCore.QPointF(r.left() + r.width() * 0.45, r.top() + r.height() * 0.55),
           QtCore.QPointF(r.left() + r.width() * 0.35, r.bottom())]
    p.drawPolygon(QtGui.QPolygonF(pts))


# ===========================================================================
# デモ
# ===========================================================================
DEMO_OBJECT_NAME = "flowCardsDemo"

DEMO_CARDS = [
    ("正規化", "クリックで実行", icon_normalize, True),
    ("インフルエンス数の制限", "最大 4・ロック除外", icon_number("4"), True),
    ("ウエイトの移動", "選択順 1 → 2", icon_move, False),
    ("ウエイトのコピー", "頂点番号・正規化", icon_copy, False),
    ("最近接ウエイトのコピー", "距離 0.010・選択メッシュのみ", icon_link, True),
    ("スキンメッシュのクリーンアップ", "≦ 0.001 削除・未使用ジョイント除去", icon_brush, False),
    ("ジョイントのウエイト選択", "> 0.000・置換", icon_cursor, False),
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


class _Container(QtWidgets.QWidget):
    resized = QtCore.Signal()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.resized.emit()


class DemoWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(DEMO_OBJECT_NAME)
        self.setWindowTitle("Flow Cards Demo  (ウィンドウ幅を変えて確認)")
        self.setWindowFlags(Qt.Window)
        self.resize(800, 520)

        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#444444"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(220, 220, 220))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#2b2b2b"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor(220, 220, 220))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#5d5d5d"))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor(220, 220, 220))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        root = QtWidgets.QVBoxLayout(self)

        # --- 設定コントロール ---
        ctl = QtWidgets.QHBoxLayout()
        self.search = QtWidgets.QLineEdit()
        self.search.setPlaceholderText("絞り込み(非表示のカードは自動で詰める)")
        ctl.addWidget(self.search, 1)

        def spin(label, lo, hi, val, step=1):
            ctl.addWidget(QtWidgets.QLabel(label))
            s = QtWidgets.QSpinBox()
            s.setRange(lo, hi)
            s.setValue(val)
            s.setSingleStep(step)
            ctl.addWidget(s)
            return s

        self.sp_max = spin("最大列数(0=無制限)", 0, 8, 0)
        self.sp_minw = spin("最小幅", 0, 600, 0, 10)
        self.sp_maxw = spin("最大幅(0=無制限)", 0, 800, 0, 10)
        self.chk_uniform = QtWidgets.QCheckBox("均等幅")
        self.chk_uniform.setChecked(True)
        ctl.addWidget(self.chk_uniform)
        self.cmb_align = QtWidgets.QComboBox()
        self.cmb_align.addItems(["左寄せ", "中央", "右寄せ"])
        ctl.addWidget(self.cmb_align)
        root.addLayout(ctl)

        # --- スクロールエリア内のフロー ---
        self.container = _Container()
        self.flow = FlowLayout(self.container)
        self.flow.setContentsMargins(8, 8, 8, 8)
        self.flow.setSpacing(10)
        self.cards = []
        for title, sub, icon, fav in DEMO_CARDS:
            c = CardButton(title, sub, icon, fav)
            c.setToolTip(title)
            c.clicked.connect(lambda _=False, t=title: self._say(f"clicked: {t}"))
            c.favoriteToggled.connect(lambda on, t=title: self._say(f"★ {t} = {on}"))
            c.menuRequested.connect(lambda pt, t=title: self._say(f"menu: {t}"))
            self.flow.addWidget(c)
            self.cards.append(c)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setWidget(self.container)
        root.addWidget(scroll, 1)

        self.status = QtWidgets.QLabel()
        root.addWidget(self.status)

        # --- 接続 ---
        self.search.textChanged.connect(self._filter)
        self.sp_max.valueChanged.connect(self.flow.setMaxColumns)
        self.sp_minw.valueChanged.connect(self.flow.setItemMinWidth)
        self.sp_maxw.valueChanged.connect(self.flow.setItemMaxWidth)
        self.chk_uniform.toggled.connect(self.flow.setUniformItems)
        self.cmb_align.currentIndexChanged.connect(
            lambda i: self.flow.setRowAlignment((Qt.AlignLeft, Qt.AlignHCenter, Qt.AlignRight)[i]))
        self.container.resized.connect(self._update_status)
        self._msg = ""
        self._update_status()

    def _filter(self, text):
        text = text.strip().lower()
        for c in self.cards:
            c.setVisible(not text or text in c.text().lower() or text in c.subtitle().lower())

    def _say(self, msg):
        self._msg = msg
        self._update_status()

    def _update_status(self):
        cols = self.flow.columnsForWidth(self.container.width())
        self.status.setText(f"列数: {cols}    {self._msg}")


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




    