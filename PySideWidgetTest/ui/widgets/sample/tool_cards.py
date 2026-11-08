"""
tool_cards.py
PySide6 (Maya 2027 対応) ツールカードの「表示モード切り替え」

    B1 最小(アイコンのみ)   : 小さなタイルが並ぶ。名前はホバーのツールチップ
    B3 バランス(+設定の要約): アイコン + 名前 + 設定の要約(2列)。説明はリッチツールチップ
    B4 詳細(説明つき一覧)   : 1列の一覧。アイコン + 名前 + 説明 + 右に設定のバッジ

    上部右の「アイコンだけの3つのスイッチボタン」で B1 / B3 / B4 を切り替える。

収録:
    ToolCard         : 1つのウィジェットが3つの表示モードを持つカード(flow_cards.CardButton の発展形)
    CardGroup        : グループ見出し(例「ウエイト」)+ カードを並べる領域(FlowLayout)
    ViewModeSwitch   : 上部右のアイコンだけの3ボタン(排他)
    ToolCardPanel    : スイッチ + グループ群(スクロール)。モードは全グループで共通
    RichToolTip      : 説明つきのリッチツールチップ(タイトル/説明/現在の設定)

前提: 以前作った flow_cards.py (FlowLayout) と同じフォルダに置いてください。

使い方:
    panel = ToolCardPanel("スキンウエイト")                  # 右上に B1/B3/B4 のスイッチが付く
    g = panel.addGroup("ウエイト")
    card = ToolCard("ウエイトの正規化", short_title="正規化", subtitle="クリックで実行",
                    description="ウエイトの合計を 1.0 に揃える", badge="", icon=icon_normalize)
    card.setHasSettings(False)                              # 設定が無いツールは ◢ を出さない
    card.clicked.connect(run_normalize)
    card.settingsRequested.connect(open_settings)           # ◢ のクリック / 右クリック
    g.addCard(card)
    panel.setViewMode(MODE_ICON)                            # プログラムから切り替え(保存した設定の復元に)
    panel.viewModeChanged.connect(save_mode)                # 切り替えを保存したい時
    panel.setMaxColumns(MODE_BALANCED, 3)                   # 1行に並べる最大数(0 = 幅なりに無制限)

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python tool_cards.py
    - Maya:  import tool_cards; tool_cards.show_demo()
"""
from PySide6 import QtCore, QtGui, QtWidgets

try:
    from .flow_cards import (FlowLayout, icon_normalize, icon_number, icon_move,
                            icon_copy, icon_link, icon_brush, icon_cursor)
except ImportError as _e:                     # pragma: no cover
    raise ImportError("tool_cards.py は flow_cards.py(FlowLayout)を必要とします。同じフォルダに置いてください。") from _e

Qt = QtCore.Qt

MODE_ICON = "icon"            # B1
MODE_BALANCED = "balanced"    # B3
MODE_DETAIL = "detail"        # B4
MODES = (MODE_ICON, MODE_BALANCED, MODE_DETAIL)
MODE_LABELS = {MODE_ICON: "アイコンのみ", MODE_BALANCED: "バランス(設定の要約)", MODE_DETAIL: "詳細(説明つき一覧)"}

# 参考画像から実測した配色
COLOR_PANEL = "#3a3a3a"
COLOR_AREA = "#444444"       # カードを並べる領域
COLOR_CARD = "#3a3a3a"
COLOR_TILE = "#2b2b2b"
COLOR_ACCENT = "#e88a9c"     # ホバー枠・アイコンの既定色
COLOR_TEXT = "#eeeeee"
COLOR_SUB = "#8a898a"
COLOR_BADGE_BG = "#5c3b43"
COLOR_BADGE_TEXT = "#efb0be"
COLOR_SELECTED = "#5285a6"


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


def _scaled_font(font, ratio, bold=None):
    f = QtGui.QFont(font)
    if f.pointSizeF() > 0:
        f.setPointSizeF(f.pointSizeF() * ratio)
    elif f.pixelSize() > 0:
        f.setPixelSize(max(6, round(f.pixelSize() * ratio)))
    if bold is not None:
        f.setBold(bold)
    return f


# ===========================================================================
# RichToolTip
# ===========================================================================
class RichToolTip(QtWidgets.QWidget):
    """
    タイトル / 説明 / 現在の設定 を並べるリッチツールチップ。

    ウィンドウごとに1つだけ、そのウィンドウの「子」として作る(ウィンドウと一緒に破棄される)。
    親なしのグローバルなシングルトンにすると、アプリ終了時の破棄順序で落ちることがあるため。
    """

    _NAME = "richToolTip"

    @classmethod
    def _for(cls, widget, create=True):
        win = widget.window()
        tip = win.findChild(cls, cls._NAME, Qt.FindDirectChildrenOnly)
        if tip is None and create:
            tip = cls(win)
        return tip

    @classmethod
    def showFor(cls, widget, title, description="", current=""):
        cls._for(widget)._show_for(widget, title, description, current)

    @classmethod
    def hideTip(cls, widget):
        try:
            tip = cls._for(widget, create=False)
        except RuntimeError:          # 終了処理で widget の C++ 側が先に破棄されている場合
            return
        if tip is not None:
            tip.hide()

    def __init__(self, parent):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint)
        self.setObjectName(self._NAME)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self._lines = []      # [(text, color, bold, scale)]

    def _show_for(self, widget, title, description, current):
        self._lines = [(title, QtGui.QColor("#ffffff"), True, 1.0)]
        if description:
            self._lines.append((description, QtGui.QColor("#d0d0d0"), False, 1.0))
        if current:
            self._lines.append((current, QtGui.QColor(COLOR_ACCENT), False, 0.95))
        self.setFont(widget.font())
        w, h = self._measure()
        self.resize(w, h)
        anchor = QtCore.QRect(widget.mapToGlobal(QtCore.QPoint(0, 0)), widget.size())
        screen = QtGui.QGuiApplication.screenAt(anchor.center()) or QtGui.QGuiApplication.primaryScreen()
        sg = screen.availableGeometry()
        x = max(sg.left(), min(anchor.left(), sg.right() - w))
        y = anchor.bottom() + 4
        if y + h > sg.bottom():
            y = max(sg.top(), anchor.top() - h - 4)
        self.move(x, y)
        self.show()
        self.update()

    def _pad(self):
        return _em(self, 0.8)

    def _measure(self):
        pad = self._pad()
        w = h = 0
        for text, _, bold, scale in self._lines:
            fm = QtGui.QFontMetrics(_scaled_font(self.font(), scale, bold))
            w = max(w, fm.horizontalAdvance(text))
            h += fm.height() + _em(self, 0.25)
        return min(w, _em(self, 30)) + pad * 2, h - _em(self, 0.25) + pad * 2

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setBrush(QtGui.QColor("#1e1e1e"))
        p.setPen(QtGui.QPen(QtGui.QColor("#4a4a4a"), 1))
        p.drawRoundedRect(r, _em(self, 0.3), _em(self, 0.3))
        pad = self._pad()
        y = pad
        for text, color, bold, scale in self._lines:
            font = _scaled_font(self.font(), scale, bold)
            fm = QtGui.QFontMetrics(font)
            p.setFont(font)
            p.setPen(color)
            p.drawText(QtCore.QPointF(pad, y + fm.ascent()),
                       fm.elidedText(text, Qt.ElideRight, self.width() - pad * 2))
            y += fm.height() + _em(self, 0.25)


# ===========================================================================
# ToolCard
# ===========================================================================
class ToolCard(QtWidgets.QAbstractButton):
    """
    1つのウィジェットで B1 / B3 / B4 の3つの見た目を持つカード。setViewMode() で切り替える。

        text()           : 名前(フル)。B4の見出し / B1のツールチップ
        shortTitle       : B3 の短い名前(省略時は text())
        subtitle         : B3 の2行目(設定の要約。例「最大 4」「クリックで実行」)
        description      : B4 の2行目(機能の説明) / B3 のリッチツールチップ
        badge            : B4 右端のピル(設定の要約。空なら出さない)
        currentSetting   : リッチツールチップ下段の「現在: …」
        hasSettings      : True で右下に ◢(設定あり)。クリック/右クリックで settingsRequested
    """

    settingsRequested = QtCore.Signal(QtCore.QPoint)    # グローバル座標

    def __init__(self, title="", short_title="", subtitle="", description="", badge="",
                 icon=None, parent=None):
        super().__init__(parent)
        self.setText(title)
        self._short = short_title
        self._subtitle = subtitle
        self._desc = description
        self._badge = badge
        self._current = ""
        self._has_settings = True
        self._icon_fn = icon if callable(icon) else None
        if icon is not None and not callable(icon):
            self.setIcon(icon)
        self._accent = QtGui.QColor(COLOR_ACCENT)
        self._menu = None
        self._mode = MODE_BALANCED
        self._kb_focus = False      # Tab キーでフォーカスされた時だけフォーカス枠を出す

        self._hover_zone = None     # None / "card" / "corner"
        self._press_zone = None
        self._hover_t = 0.0
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(120)
        self._anim.valueChanged.connect(self._on_anim)
        self._tip_timer = QtCore.QTimer(self)
        self._tip_timer.setSingleShot(True)
        self._tip_timer.setInterval(450)
        self._tip_timer.timeout.connect(self._show_tip)

        self.setFocusPolicy(Qt.TabFocus)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WA_Hover, True)
        self.setCursor(Qt.PointingHandCursor)
        self._apply_policy()

    # ------------------------------------------------------------------
    # 公開API
    # ------------------------------------------------------------------
    def viewMode(self):
        return self._mode

    def setViewMode(self, mode):
        if mode not in MODES or mode == self._mode:
            return
        self._mode = mode
        RichToolTip.hideTip(self)
        self._apply_policy()
        self.updateGeometry()
        self.update()

    def shortTitle(self):
        return self._short or self.text()

    def setShortTitle(self, t):
        self._short = t
        self.update()

    def subtitle(self):
        return self._subtitle

    def setSubtitle(self, t):
        self._subtitle = t
        self.update()

    def description(self):
        return self._desc

    def setDescription(self, t):
        self._desc = t
        self.update()

    def badge(self):
        return self._badge

    def setBadge(self, t):
        self._badge = t
        self.update()

    def currentSetting(self):
        return self._current

    def setCurrentSetting(self, t):
        self._current = t

    def setHasSettings(self, on):
        self._has_settings = bool(on)
        self.update()

    def setMenu(self, menu):
        self._menu = menu

    def setAccentColor(self, color):
        self._accent = QtGui.QColor(color)
        self.update()

    def setIconPainter(self, fn):
        """fn(painter, QRectF, QColor) でアイコンを描く(ベクター。DPIに強い)。"""
        self._icon_fn = fn
        self.update()

    def _apply_policy(self):
        if self._mode == MODE_ICON:
            self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        else:
            self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

    # ------------------------------------------------------------------
    # 寸法(すべてフォント基準)
    # ------------------------------------------------------------------
    def _lh(self):
        return self.fontMetrics().height()

    def _small_font(self):
        return _scaled_font(self.font(), 0.85)

    def _small_lh(self):
        return QtGui.QFontMetrics(self._small_font()).height()

    def _pad(self):
        return _em(self, {MODE_ICON: 0.3, MODE_BALANCED: 0.55, MODE_DETAIL: 0.5}[self._mode])

    def _card_h(self):
        if self._mode == MODE_ICON:
            return _em(self, 2.3)
        return self._lh() + self._small_lh() + self._pad() * 2 + _em(self, 0.1)

    def sizeHint(self):
        h = self._card_h()
        if self._mode == MODE_ICON:
            return QtCore.QSize(h, h)
        return QtCore.QSize(_em(self, 11 if self._mode == MODE_BALANCED else 24), h)

    def minimumSizeHint(self):
        h = self._card_h()
        if self._mode == MODE_ICON:
            return QtCore.QSize(h, h)
        return QtCore.QSize(_em(self, 7 if self._mode == MODE_BALANCED else 14), h)

    def _corner_rect(self):
        if not self._has_settings or self._mode == MODE_DETAIL:
            return QtCore.QRectF()
        s = _em(self, 1.0 if self._mode == MODE_ICON else 1.2)
        g = _em(self, 0.12)
        return QtCore.QRectF(self.width() - s - g, self.height() - s - g, s, s)

    def _zone_at(self, pos):
        cr = self._corner_rect()
        return "corner" if (not cr.isNull() and cr.contains(pos)) else "card"

    # ------------------------------------------------------------------
    # ホバー/ツールチップ
    # ------------------------------------------------------------------
    def _on_anim(self, v):
        self._hover_t = float(v)
        self.update()

    def _animate_to(self, target):
        a = self._anim
        a.stop()
        a.setStartValue(self._hover_t)
        a.setEndValue(float(target))
        a.start()

    def _show_tip(self):
        if not self.underMouse() or not self.isEnabled():
            return
        if self._mode == MODE_ICON:
            RichToolTip.showFor(self, self.text())
        elif self._mode == MODE_BALANCED:
            RichToolTip.showFor(self, self.text(), self._desc,
                                self._current or (f"現在: {self._badge}" if self._badge else ""))

    def enterEvent(self, e):
        if self.isEnabled():
            self._animate_to(1.0)
            if self._mode != MODE_DETAIL:
                self._tip_timer.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover_zone = None
        self._tip_timer.stop()
        RichToolTip.hideTip(self)
        self._animate_to(0.0)
        self.update()
        super().leaveEvent(e)

    def hideEvent(self, e):
        self._tip_timer.stop()
        RichToolTip.hideTip(self)
        super().hideEvent(e)

    def changeEvent(self, e):
        if e.type() == QtCore.QEvent.EnabledChange and not self.isEnabled():
            self._anim.stop()
            self._hover_t = 0.0
            self._hover_zone = None
        if e.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.EnabledChange, QtCore.QEvent.PaletteChange):
            self.updateGeometry()
            self.update()
        super().changeEvent(e)

    # ------------------------------------------------------------------
    # マウス/キー
    # ------------------------------------------------------------------
    def mouseMoveEvent(self, e):
        z = self._zone_at(e.position())
        if z != self._hover_zone:
            self._hover_zone = z
            self.update()
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        self._tip_timer.stop()
        RichToolTip.hideTip(self)
        if e.button() == Qt.LeftButton and self._zone_at(e.position()) == "corner":
            self._press_zone = "corner"       # ◢ は設定を開く(カード本体の clicked は出さない)
            e.accept()
            return
        self._press_zone = None
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._press_zone == "corner":
            self._press_zone = None
            if e.button() == Qt.LeftButton and self._zone_at(e.position()) == "corner":
                self._open_settings()
            e.accept()
            return
        super().mouseReleaseEvent(e)

    def _open_settings(self):
        cr = self._corner_rect()
        anchor = self.mapToGlobal((cr.bottomLeft() if not cr.isNull() else QtCore.QPointF(0, self.height())).toPoint())
        if self._menu is not None:
            self._menu.exec(anchor)
        else:
            self.settingsRequested.emit(anchor)

    def contextMenuEvent(self, e):
        if not self._has_settings:
            return
        if self._menu is not None:
            self._menu.exec(e.globalPos())
        else:
            self.settingsRequested.emit(e.globalPos())

    def focusInEvent(self, e):
        # ウィンドウを開いた直後の自動フォーカスでは枠を出さず、Tab 移動の時だけ出す
        self._kb_focus = e.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason)
        self.update()
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self._kb_focus = False
        self.update()
        super().focusOutEvent(e)

    def keyPressEvent(self, e):
        if not self._kb_focus:
            self._kb_focus = True       # キーボードで操作し始めたらフォーカス枠を出す
            self.update()
        if e.key() in (Qt.Key_Return, Qt.Key_Enter):
            self.click()
        elif e.key() == Qt.Key_Menu and self._has_settings:
            self._open_settings()
        else:
            super().keyPressEvent(e)

    # ------------------------------------------------------------------
    # 描画
    # ------------------------------------------------------------------
    def _paint_icon(self, p, rect):
        if self._icon_fn is not None:
            p.save()
            self._icon_fn(p, rect, self._accent)
            p.restore()
        elif not self.icon().isNull():
            mode = QtGui.QIcon.Normal if self.isEnabled() else QtGui.QIcon.Disabled
            self.icon().paint(p, rect.toRect(), Qt.AlignCenter, mode)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.5)
        w, h = self.width(), self.height()
        r = QtCore.QRectF(0, 0, w, h)
        radius = _em(self, 0.3)
        pad = self._pad()

        # --- 背景 ---
        base = QtGui.QColor(COLOR_CARD)
        bg = base.darker(112) if self.isDown() else _lerp_color(base, base.lighter(112), self._hover_t)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, radius, radius)

        # --- ホバー/フォーカスの枠 ---
        ring = 1.0 if self._kb_focus else self._hover_t
        if ring > 0 and self.isEnabled():
            c = QtGui.QColor(self._accent)
            c.setAlpha(round(255 * ring))
            p.setBrush(Qt.NoBrush)
            p.setPen(QtGui.QPen(c, 1.8))
            p.drawRoundedRect(r.adjusted(0.9, 0.9, -0.9, -0.9), radius, radius)

        if self._mode == MODE_ICON:
            s = _em(self, 1.25)
            self._paint_icon(p, QtCore.QRectF((w - s) / 2, (h - s) / 2, s, s))
        elif self._mode == MODE_BALANCED:
            self._paint_balanced(p, w, h, pad)
        else:
            self._paint_detail(p, w, h, pad, radius)

        # --- 右下 ◢(設定あり) ---
        cr = self._corner_rect()
        if not cr.isNull():
            hot = self._hover_zone == "corner"
            if hot:
                p.setPen(Qt.NoPen)
                p.setBrush(QtGui.QColor("#555555"))
                p.drawRoundedRect(cr, radius * 0.7, radius * 0.7)
            s = cr.width() * (0.28 if self._mode == MODE_ICON else 0.3)
            cx, cy = cr.center().x(), cr.center().y()
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor("#e0e0e0" if hot else "#8a8a8a"))
            p.drawPolygon(QtGui.QPolygonF([QtCore.QPointF(cx + s, cy - s), QtCore.QPointF(cx + s, cy + s),
                                           QtCore.QPointF(cx - s, cy + s)]))

    def _paint_balanced(self, p, w, h, pad):
        isz = _em(self, 1.2)
        self._paint_icon(p, QtCore.QRectF(pad, (h - isz) / 2, isz, isz))
        x0 = pad + isz + pad
        bold = _scaled_font(self.font(), 1.0, True)
        small = self._small_font()
        fm, sfm = QtGui.QFontMetrics(bold), QtGui.QFontMetrics(small)
        block = fm.height() + sfm.height()
        y = (h - block) / 2
        right = w - pad - (_em(self, 0.6) if not self._corner_rect().isNull() else 0)
        avail = max(0, int(right - x0))
        p.setFont(bold)
        p.setPen(QtGui.QColor(COLOR_TEXT))
        p.drawText(QtCore.QPointF(x0, y + fm.ascent()), fm.elidedText(self.shortTitle(), Qt.ElideRight, avail))
        y += fm.height()
        if self._subtitle:
            p.setFont(small)
            p.setPen(QtGui.QColor(COLOR_SUB))
            p.drawText(QtCore.QPointF(x0, y + sfm.ascent()), sfm.elidedText(self._subtitle, Qt.ElideRight, avail))

    def _paint_detail(self, p, w, h, pad, radius):
        # アイコン枠(暗い角丸の正方形)
        tile = h - pad * 2
        tr = QtCore.QRectF(pad, pad, tile, tile)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(COLOR_TILE))
        p.drawRoundedRect(tr, radius * 0.9, radius * 0.9)
        g = tile * 0.22
        self._paint_icon(p, tr.adjusted(g, g, -g, -g))

        right = w - pad
        small = self._small_font()
        sfm = QtGui.QFontMetrics(small)
        if self._badge:
            bf = _scaled_font(self.font(), 0.82)
            bfm = QtGui.QFontMetrics(bf)
            bw = bfm.horizontalAdvance(self._badge) + _em(self, 1.0)
            bh = bfm.height() + _em(self, 0.3)
            br = QtCore.QRectF(right - bw, (h - bh) / 2, bw, bh)
            p.setBrush(QtGui.QColor(COLOR_BADGE_BG))
            p.drawRoundedRect(br, bh / 2, bh / 2)
            p.setFont(bf)
            p.setPen(QtGui.QColor(COLOR_BADGE_TEXT))
            p.drawText(br, int(Qt.AlignCenter), self._badge)
            right = br.left() - pad

        x0 = pad + tile + pad * 1.1
        avail = max(0, int(right - x0))
        bold = _scaled_font(self.font(), 1.0, True)
        fm = QtGui.QFontMetrics(bold)
        y = (h - fm.height() - sfm.height()) / 2
        p.setFont(bold)
        p.setPen(QtGui.QColor(COLOR_TEXT))
        p.drawText(QtCore.QPointF(x0, y + fm.ascent()), fm.elidedText(self.text(), Qt.ElideRight, avail))
        y += fm.height()
        if self._desc:
            p.setFont(small)
            p.setPen(QtGui.QColor(COLOR_SUB))
            p.drawText(QtCore.QPointF(x0, y + sfm.ascent()), sfm.elidedText(self._desc, Qt.ElideRight, avail))


# ===========================================================================
# ViewModeSwitch(上部右のアイコンだけの3ボタン)
# ===========================================================================
def _stroke(p, r, c, width=0.09):
    p.setPen(QtGui.QPen(c, max(1.2, r.width() * width), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    p.setBrush(Qt.NoBrush)


def icon_view_icons(p, r, c):
    """B1: 小さなタイルが並ぶ(2行×3列)。"""
    _stroke(p, r, c)
    cw, gap = r.width() * 0.26, r.width() * 0.11
    for row in range(2):
        for col in range(3):
            x = r.left() + col * (cw + gap)
            y = r.top() + r.height() * 0.1 + row * (cw + gap)
            p.drawRoundedRect(QtCore.QRectF(x, y, cw, cw), 1.5, 1.5)


def icon_view_balanced(p, r, c):
    """B3: 2列のカード。"""
    _stroke(p, r, c)
    cw, gap = r.width() * 0.43, r.width() * 0.14
    ch = r.height() * 0.26
    for row in range(3):
        for col in range(2):
            p.drawRoundedRect(QtCore.QRectF(r.left() + col * (cw + gap), r.top() + row * (ch + r.height() * 0.11),
                                            cw, ch), 1.5, 1.5)


def icon_view_detail(p, r, c):
    """B4: 1列の一覧(行ごとに小さなタイル + 線)。"""
    _stroke(p, r, c)
    rh, gap = r.height() * 0.24, r.height() * 0.14
    for row in range(3):
        y = r.top() + row * (rh + gap)
        p.drawRoundedRect(QtCore.QRectF(r.left(), y, r.width(), rh), 1.5, 1.5)
        p.drawLine(QtCore.QPointF(r.left() + rh * 1.35, y + rh / 2), QtCore.QPointF(r.right() - rh * 0.5, y + rh / 2))


MODE_ICON_PAINTERS = {MODE_ICON: icon_view_icons, MODE_BALANCED: icon_view_balanced, MODE_DETAIL: icon_view_detail}


class ViewModeSwitch(QtWidgets.QWidget):
    """B1 / B3 / B4 を切り替える、アイコンだけの3つのトグルボタン(排他)。"""

    modeChanged = QtCore.Signal(str)

    def __init__(self, mode=MODE_BALANCED, parent=None):
        super().__init__(parent)
        self._mode = mode
        self._hover = -1
        self._pressed = -1
        self._kb_focus = False
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.TabFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def mode(self):
        return self._mode

    def setMode(self, mode):
        if mode in MODES and mode != self._mode:
            self._mode = mode
            self.update()
            self.modeChanged.emit(mode)

    def _btn(self):
        return _em(self, 1.9)

    def _gap(self):
        return _em(self, 0.15)

    def sizeHint(self):
        n = len(MODES)
        return QtCore.QSize(n * self._btn() + (n - 1) * self._gap() + 2, self._btn() + 2)

    def _rect(self, i):
        return QtCore.QRectF(1 + i * (self._btn() + self._gap()), 1, self._btn(), self._btn())

    def _index_at(self, pos):
        for i in range(len(MODES)):
            if self._rect(i).contains(pos):
                return i
        return -1

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.5)
        radius = _em(self, 0.3)
        for i, mode in enumerate(MODES):
            r = self._rect(i)
            sel = mode == self._mode
            if sel:
                bg = QtGui.QColor(COLOR_SELECTED)
                if i == self._pressed:
                    bg = bg.darker(112)
            elif i == self._pressed:
                bg = QtGui.QColor(255, 255, 255, 60)
            elif i == self._hover:
                bg = QtGui.QColor(255, 255, 255, 34)
            else:
                bg = None
            if bg is not None:
                p.setPen(Qt.NoPen)
                p.setBrush(bg)
                p.drawRoundedRect(r, radius, radius)
            s = r.width() * 0.52
            ir = QtCore.QRectF(0, 0, s, s)
            ir.moveCenter(r.center())
            p.save()
            MODE_ICON_PAINTERS[mode](p, ir, QtGui.QColor("#ffffff" if sel else "#b4b4b4"))
            p.restore()
        if self._kb_focus:
            i = MODES.index(self._mode)
            p.setBrush(Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 170), 1.2))
            p.drawRoundedRect(self._rect(i).adjusted(-1, -1, 1, 1), radius, radius)

    def focusInEvent(self, e):
        self._kb_focus = e.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason)
        self.update()
        super().focusInEvent(e)

    def focusOutEvent(self, e):
        self._kb_focus = False
        self.update()
        super().focusOutEvent(e)

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._pressed = self._index_at(e.position())
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            i, pressed = self._index_at(e.position()), self._pressed
            self._pressed = -1
            if i >= 0 and i == pressed:
                self.setMode(MODES[i])
            self.update()

    def keyPressEvent(self, e):
        if not self._kb_focus:
            self._kb_focus = True       # キーボードで操作し始めたらフォーカス枠を出す
            self.update()
        i = MODES.index(self._mode)
        if e.key() in (Qt.Key_Left, Qt.Key_Up):
            self.setMode(MODES[max(0, i - 1)])
        elif e.key() in (Qt.Key_Right, Qt.Key_Down):
            self.setMode(MODES[min(len(MODES) - 1, i + 1)])
        else:
            super().keyPressEvent(e)

    def event(self, e):
        if e.type() == QtCore.QEvent.ToolTip:
            i = self._index_at(e.pos().toPointF())
            if i >= 0:
                QtWidgets.QToolTip.showText(e.globalPos(), MODE_LABELS[MODES[i]], self)
            else:
                QtWidgets.QToolTip.hideText()
                e.ignore()
            return True
        return super().event(e)


# ===========================================================================
# CardGroup / ToolCardPanel
# ===========================================================================
class _AreaWidget(QtWidgets.QWidget):
    """カードを並べる領域(角丸の背景)。"""

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(COLOR_AREA))
        p.drawRoundedRect(QtCore.QRectF(self.rect()), _em(self, 0.4), _em(self, 0.4))


class CardGroup(QtWidgets.QWidget):
    """グループ見出し(例「ウエイト」)+ カードを並べる領域。表示モードに合わせて並べ方も切り替える。"""

    def __init__(self, title="", parent=None):
        super().__init__(parent)
        self._mode = MODE_BALANCED
        self._cards = []
        # モードごとの「1行に並べる最大数」(0 = 幅なりに無制限)
        self._max_cols = {MODE_ICON: 0, MODE_BALANCED: 0, MODE_DETAIL: 1}
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._label = QtWidgets.QLabel(title)
        pal = self._label.palette()
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#b4b4b4"))
        self._label.setPalette(pal)
        self._label.setContentsMargins(4, 0, 0, 0)
        lay.addWidget(self._label)
        self._area = _AreaWidget()
        self.flow = FlowLayout(self._area)
        self.flow.setContentsMargins(8, 8, 8, 8)
        lay.addWidget(self._area)

    def title(self):
        return self._label.text()

    def cards(self):
        return list(self._cards)

    def addCard(self, card):
        card.setViewMode(self._mode)
        self._cards.append(card)
        self.flow.addWidget(card)
        return card

    def viewMode(self):
        return self._mode

    def setViewMode(self, mode):
        if mode not in MODES:
            return
        self._mode = mode
        for c in self._cards:
            c.setViewMode(mode)
        self._apply_layout()

    def setMaxColumns(self, mode, n):
        """mode の表示で1行に並べる最大数。0 で幅なりに無制限。"""
        if mode in MODES:
            self._max_cols[mode] = max(0, int(n))
            if mode == self._mode:
                self._apply_layout()

    def _apply_layout(self):
        f, em = self.flow, lambda r: _em(self, r)
        f.setUniformItems(True)
        f.setRowAlignment(Qt.AlignLeft)
        if self._mode == MODE_ICON:
            tile = self._cards[0].sizeHint().width() if self._cards else em(2.3)
            f.setItemMinWidth(tile)
            f.setItemMaxWidth(tile)      # 引き伸ばさず、入るだけ左から並べる
            f.setMaxColumns(self._max_cols[MODE_ICON])
            f.setSpacing(em(0.4))
        elif self._mode == MODE_BALANCED:
            f.setItemMinWidth(em(9.5))   # 幅が許せば2列以上、狭ければ1列
            f.setItemMaxWidth(0)
            f.setMaxColumns(self._max_cols[MODE_BALANCED])
            f.setSpacing(em(0.4))
        else:
            f.setItemMinWidth(em(14))
            f.setItemMaxWidth(0)
            f.setMaxColumns(self._max_cols[MODE_DETAIL])    # 既定は 1 列の一覧
            f.setSpacing(em(0.3))
        f.invalidate()


class ToolCardPanel(QtWidgets.QWidget):
    """上部右にモード切り替えスイッチ、その下に複数のグループ(スクロール)。モードは全グループ共通。"""

    viewModeChanged = QtCore.Signal(str)

    def __init__(self, title="", mode=MODE_BALANCED, parent=None):
        super().__init__(parent)
        self._groups = []
        self._mode = mode
        self._max_cols = {}          # {モード: 最大列数}。後から追加したグループにも適用する

        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(COLOR_PANEL))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#dddddd"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(8)

        head = QtWidgets.QHBoxLayout()
        self._title = QtWidgets.QLabel(title)
        f = self._title.font()
        f.setBold(True)
        self._title.setFont(f)
        head.addWidget(self._title)
        head.addStretch()
        self.switch = ViewModeSwitch(mode)
        head.addWidget(self.switch)                # ← 上部右
        root.addLayout(head)

        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        # ホストの QSS(Maya など)に背景を塗られないよう透明にして、パネルの色を見せる
        self._scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                                   "QScrollArea > QWidget > QWidget { background: transparent; }")
        self._body = QtWidgets.QWidget()
        self._body_lay = QtWidgets.QVBoxLayout(self._body)
        self._body_lay.setContentsMargins(0, 0, 4, 0)
        self._body_lay.setSpacing(12)
        self._body_lay.addStretch()
        self._scroll.setWidget(self._body)
        root.addWidget(self._scroll, 1)

        self.switch.modeChanged.connect(self.setViewMode)

    def addGroup(self, title):
        g = CardGroup(title)
        for m, n in self._max_cols.items():
            g.setMaxColumns(m, n)
        g.setViewMode(self._mode)
        self._body_lay.insertWidget(self._body_lay.count() - 1, g)
        self._groups.append(g)
        return g

    def setTitle(self, text):
        self._title.setText(text)

    def setMaxColumns(self, mode, n):
        """mode の表示で1行に並べる最大数(全グループ共通)。0 で幅なりに無制限。"""
        self._max_cols[mode] = n
        for g in self._groups:
            g.setMaxColumns(mode, n)

    def groups(self):
        return list(self._groups)

    def cards(self):
        return [c for g in self._groups for c in g.cards()]

    def viewMode(self):
        return self._mode

    def setViewMode(self, mode):
        if mode not in MODES or mode == self._mode:
            return                             # 同じモードなら何もしない(シグナルの二重発行も防ぐ)
        self._mode = mode
        for g in self._groups:
            g.setViewMode(mode)
        if self.switch.mode() != mode:
            self.switch.setMode(mode)          # スイッチ側の表示も揃える(その modeChanged は上の早期 return で止まる)
        self.viewModeChanged.emit(mode)


# ===========================================================================
# デモ
# ===========================================================================
DEMO_OBJECT_NAME = "toolCardsDemo"

# (フル名, 短い名, B3の要約, B4の説明, B4バッジ, アイコン)
DEMO_WEIGHT_TOOLS = [
    ("ウエイトの正規化", "正規化", "クリックで実行", "ウエイトの合計を 1.0 に揃える", "", icon_normalize),
    ("インフルエンス数の制限", "インフル数制限", "最大 4", "頂点ごとの影響ジョイント数を上限まで減らす", "最大 4", icon_number("4")),
    ("ウエイトの移動", "ウエイト移動", "選択順 1→2", "あるジョイントのウエイトを別のジョイントへ移す", "選択順 1→2", icon_move),
    ("ウエイトのコピー", "ウエイトコピー", "頂点番号", "同じトポロジのメッシュへウエイトを写す", "頂点番号", icon_copy),
    ("最近接ウエイトのコピー", "最近接コピー", "距離 0.010", "位置が最も近い頂点からウエイトを写す", "距離 0.010", icon_link),
    ("スキンメッシュのクリーンアップ", "クリーンアップ", "≦0.001・未使用除去", "微小ウエイトと未使用インフルエンスを除去", "≦0.001・未使用除去", icon_brush),
    ("ジョイントのウエイト選択", "影響頂点を選択", "> 0.000", "選んだジョイントが影響する頂点を選択", "> 0.000", icon_cursor),
]


def build_cards(rows):
    cards = []
    for full, short, summary, desc, badge, icon in rows:
        c = ToolCard(full, short, summary, desc, badge, icon)
        c.setCurrentSetting(f"現在: {badge}" if badge else "")
        c.setHasSettings(bool(badge))          # 設定の要約が無い = 設定の無いツール(◢ を出さない)
        cards.append(c)
    return cards


def _maya_main_window():
    """Mayaが無い環境では None を返す(単体実行できるように)。"""
    try:
        from maya import OpenMayaUI as omui
        from shiboken6 import wrapInstance
    except ImportError:
        return None
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


class DemoWindow(ToolCardPanel):
    def __init__(self, parent=None):
        super().__init__("スキンウエイト", MODE_BALANCED, parent)
        self.setObjectName(DEMO_OBJECT_NAME)
        self.setWindowTitle("Tool Cards Demo")
        self.setWindowFlags(Qt.Window)
        self.resize(380, 520)
        # 単体確認用の細い暗色スクロールバー(Maya 内では Maya 側のスタイルが効くので不要)
        self.setStyleSheet(
            "QScrollBar:vertical { background: #3a3a3a; width: 10px; margin: 0; }"
            "QScrollBar::handle:vertical { background: #5a5a5a; border-radius: 4px; min-height: 24px; }"
            "QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }"
            "QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }")

        g = self.addGroup("ウエイト")
        for c in build_cards(DEMO_WEIGHT_TOOLS):
            c.clicked.connect(lambda _=False, t=c.text(): self.log.setText(f"clicked: {t}"))
            c.settingsRequested.connect(lambda pt, t=c.text(): self.log.setText(f"settings: {t}"))
            g.addCard(c)

        g2 = self.addGroup("ジョイント(サンプル)")
        for c in build_cards([
            ("ジョイントのミラー", "ミラー", "X 軸・L→R", "ジョイントを左右反転して複製する", "X 軸・L→R", icon_move),
            ("ジョイントの方向を揃える", "方向を揃える", "Y 上", "ジョイントの向きを揃える", "Y 上", icon_cursor),
            ("ジョイントの表示切り替え", "表示切り替え", "クリックで実行", "ジョイントの表示/非表示を切り替える", "", icon_link),
        ]):
            g2.addCard(c)

        self.log = QtWidgets.QLabel("(操作するとここに表示)")
        self.layout().addWidget(self.log)
        self.viewModeChanged.connect(lambda m: self.log.setText(f"viewMode: {m}"))


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