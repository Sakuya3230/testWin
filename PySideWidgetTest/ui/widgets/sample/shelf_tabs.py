"""
shelf_tabs.py
PySide6 (Maya 2027 対応) シェルフ風タブウィジェット

    Modeling   Rigging   Anim   +          ← フラット背景・文字だけのタブ。選択中は下線。末尾の「+」でタブ追加
    ▔▔▔▔▔▔▔
    [icon] [icon] [icon] ...               ← アイコン + 下にラベル。フローレイアウトで折り返す
    label  label  label

収録:
    1. ShelfTabBar     : タブバー(文字のみ・下線がスライド・末尾に「+」・あふれたらホイールでスクロール)
    2. ShelfButton     : アイコン+ラベルのアイテム(描画のみ)
    3. ShelfPage       : アイテムをフロー配置するページ
                         - 中ボタンドラッグで移動(挿入ラインで移動先を表示 / Escでキャンセル)
                         - 右クリック: ラベルの変更 / 削除 / すべて削除(確認ダイアログ)
    4. ShelfTabWidget  : ShelfTabBar + ページ(QScrollArea)

【使い方】
    shelf = ShelfTabWidget()
    page = shelf.addShelf("Modeling")
    page.addItem("Move", icon=icon_move, color="#e88a9c", tooltip="移動", callback=lambda: print("move"))
    page.itemTriggered.connect(lambda item: print(item.label()))
    page.itemMoved.connect(lambda src, dst: ...)     # 並び替え後に通知

【ダイアログの差し替え】(Mayaの作法に合わせたい場合はサブクラス/上書きしてください)
    ShelfPage.askLabel(current) -> str | None         ラベル変更の入力
    ShelfPage.confirmDeleteAll() -> bool              「すべて削除」の確認
    ShelfTabWidget.askShelfName(default) -> str | None  「+」/名前変更の入力
    ShelfTabWidget.confirmDeleteShelf(name) -> bool   アイテムが入ったタブ削除の確認

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python shelf_tabs.py
    - Maya:  import shelf_tabs; shelf_tabs.show_demo()
"""
from PySide6 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt

# ---------------------------------------------------------------------------
# 配色
# ---------------------------------------------------------------------------
COLOR_BG = QtGui.QColor("#3c3c3c")
COLOR_BASELINE = QtGui.QColor("#2e2e2e")
COLOR_ACCENT = QtGui.QColor("#5285a6")
COLOR_TAB = QtGui.QColor("#b4b4b4")
COLOR_TAB_HOVER = QtGui.QColor("#e0e0e0")
COLOR_TAB_SELECTED = QtGui.QColor("#ffffff")
COLOR_ITEM_HOVER = QtGui.QColor("#4b4b4b")
COLOR_ITEM_PRESSED = QtGui.QColor("#333333")
COLOR_LABEL = QtGui.QColor("#d0d0d0")
COLOR_DROP = QtGui.QColor("#64b5f6")
COLOR_HINT = QtGui.QColor("#777777")


# ---------------------------------------------------------------------------
# ヘルパ
# ---------------------------------------------------------------------------
def _em(widget, ratio):
    """フォント高さ基準の長さ(px)。UIスケール/DPIが変わっても比率が崩れない。"""
    return max(1, round(widget.fontMetrics().height() * ratio))


def _wrap_lines(text, font, width, max_lines):
    """text を width で折り返し、max_lines を超える分は最終行を … で省略して返す。"""
    if not text:
        return []
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
    fm = QtGui.QFontMetrics(font)
    out = [text[s:s + n].strip() for s, n in spans[:max_lines]]
    if len(spans) > max_lines:
        out[-1] = fm.elidedText(text[spans[max_lines - 1][0]:].strip(),
                                Qt.ElideRight, width)
    return out


def _ease(kind, t):
    return QtCore.QEasingCurve(kind).valueForProgress(max(0.0, min(1.0, t)))


# ---------------------------------------------------------------------------
# デモ用ベクターアイコン  fn(painter, QRectF, QColor)
# ---------------------------------------------------------------------------
def _pen(p, color, w):
    pen = QtGui.QPen(color, w)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)


def icon_move(p, r, c):
    _pen(p, c, max(1.5, r.width() * 0.08))
    cx, cy, k = r.center().x(), r.center().y(), r.width() * 0.4
    p.drawLine(QtCore.QPointF(cx - k, cy), QtCore.QPointF(cx + k, cy))
    p.drawLine(QtCore.QPointF(cx, cy - k), QtCore.QPointF(cx, cy + k))
    a = k * 0.35
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        tip = QtCore.QPointF(cx + dx * k, cy + dy * k)
        p.drawLine(tip, QtCore.QPointF(tip.x() - dx * a - dy * a, tip.y() - dy * a - dx * a))
        p.drawLine(tip, QtCore.QPointF(tip.x() - dx * a + dy * a, tip.y() - dy * a + dx * a))


def icon_copy(p, r, c):
    _pen(p, c, max(1.5, r.width() * 0.08))
    s = r.width()
    p.drawRoundedRect(QtCore.QRectF(r.left() + s * .1, r.top() + s * .1, s * .5, s * .6), 2, 2)
    p.drawRoundedRect(QtCore.QRectF(r.left() + s * .4, r.top() + s * .3, s * .5, s * .6), 2, 2)


def icon_link(p, r, c):
    _pen(p, c, max(1.5, r.width() * 0.09))
    s = r.width()
    p.drawRoundedRect(QtCore.QRectF(r.left() + s * .05, r.top() + s * .32, s * .55, s * .36), s * .18, s * .18)
    p.drawRoundedRect(QtCore.QRectF(r.left() + s * .40, r.top() + s * .32, s * .55, s * .36), s * .18, s * .18)


def icon_brush(p, r, c):
    _pen(p, c, max(1.5, r.width() * 0.09))
    s = r.width()
    p.drawLine(QtCore.QPointF(r.left() + s * .85, r.top() + s * .12),
               QtCore.QPointF(r.left() + s * .4, r.top() + s * .57))
    p.setBrush(c)
    p.drawEllipse(QtCore.QPointF(r.left() + s * .28, r.top() + s * .72), s * .16, s * .16)


def icon_cursor(p, r, c):
    s = r.width()
    poly = QtGui.QPolygonF([QtCore.QPointF(r.left() + s * .2, r.top() + s * .1),
                            QtCore.QPointF(r.left() + s * .2, r.top() + s * .85),
                            QtCore.QPointF(r.left() + s * .42, r.top() + s * .65),
                            QtCore.QPointF(r.left() + s * .6, r.top() + s * .92),
                            QtCore.QPointF(r.left() + s * .72, r.top() + s * .86),
                            QtCore.QPointF(r.left() + s * .55, r.top() + s * .6),
                            QtCore.QPointF(r.left() + s * .82, r.top() + s * .58)])
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    p.drawPolygon(poly)


def icon_grid(p, r, c):
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    s = r.width()
    g = s * .38
    for ix in range(2):
        for iy in range(2):
            p.drawRoundedRect(QtCore.QRectF(r.left() + s * .1 + ix * (g + s * .04),
                                            r.top() + s * .1 + iy * (g + s * .04), g, g), 2, 2)


# ===========================================================================
# 1. タブバー
# ===========================================================================
class ShelfTabBar(QtWidgets.QWidget):
    """文字だけのフラットなタブ + 下線 + 末尾の「+」。"""
    currentChanged = QtCore.Signal(int)
    addRequested = QtCore.Signal()
    tabRenameRequested = QtCore.Signal(int)
    tabDeleteRequested = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs = []
        self._cur = -1
        self._hover = -2            # -1: 「+」, 0..: タブ
        self._pressed = -2
        self._offset = 0
        self._kb_focus = False
        self._span = None           # 描画中の下線 (left, right) ※コンテンツ座標
        self._from = self._to = None
        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setDuration(260)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.valueChanged.connect(self._on_anim)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    # ---- 公開API ----
    def count(self):
        return len(self._tabs)

    def currentIndex(self):
        return self._cur

    def tabText(self, i):
        return self._tabs[i]

    def addTab(self, text):
        self._tabs.append(text)
        if self._cur < 0:
            self._cur = 0
            self._snap()
            self.currentChanged.emit(0)
        self._after_change()
        return len(self._tabs) - 1

    def setTabText(self, i, text):
        self._tabs[i] = text
        self._after_change()

    def removeTab(self, i):
        if not 0 <= i < len(self._tabs):
            return
        del self._tabs[i]
        old = self._cur
        if not self._tabs:
            self._cur = -1
        elif i < old:
            self._cur = old - 1
        elif i == old:
            self._cur = min(old, len(self._tabs) - 1)
        self._after_change()
        self.currentChanged.emit(self._cur)

    def setCurrentIndex(self, i):
        if i == self._cur or not 0 <= i < len(self._tabs):
            return
        self._cur = i
        self._ensure_visible(i)
        self._start_underline()
        self.update()
        self.currentChanged.emit(i)

    # ---- 寸法 ----
    def _metrics(self):
        return dict(h=_em(self, 2.3), padx=_em(self, 1.0), margin=_em(self, 0.5),
                    plus=_em(self, 2.4))

    def sizeHint(self):
        return QtCore.QSize(_em(self, 20), _em(self, 2.3))

    def minimumSizeHint(self):
        return QtCore.QSize(_em(self, 6), _em(self, 2.3))

    def _geometry(self):
        """(rects[コンテンツ座標], plus_rect[ウィジェット座標], avail, overflow)"""
        m = self._metrics()
        fm = self.fontMetrics()
        x = float(m["margin"])
        rects = []
        for t in self._tabs:
            w = fm.horizontalAdvance(t) + 2 * m["padx"]
            rects.append(QtCore.QRectF(x, 0, w, m["h"]))
            x += w
        total = x
        overflow = total + m["plus"] > self.width()
        if overflow:
            plus = QtCore.QRectF(self.width() - m["plus"], 0, m["plus"], m["h"])
            avail = self.width() - m["plus"]
        else:
            plus = QtCore.QRectF(total, 0, m["plus"], m["h"])
            avail = self.width()
        return rects, plus, avail, overflow, total

    def _clamp_offset(self):
        rects, _, avail, overflow, total = self._geometry()
        mx = max(0, round(total - avail)) if overflow else 0
        self._offset = max(0, min(self._offset, mx))

    def _ensure_visible(self, i):
        rects, _, avail, overflow, _t = self._geometry()
        if not overflow or not 0 <= i < len(rects):
            self._offset = 0
            return
        r = rects[i]
        if r.left() < self._offset:
            self._offset = int(r.left() - self._metrics()["margin"])
        elif r.right() > self._offset + avail:
            self._offset = int(r.right() - avail + self._metrics()["margin"])
        self._clamp_offset()

    # ---- 下線 ----
    def _target_span(self):
        rects = self._geometry()[0]
        if not 0 <= self._cur < len(rects):
            return None
        r = rects[self._cur]
        inset = self._metrics()["padx"] * 0.5
        return (r.left() + inset, r.right() - inset)

    def _snap(self):
        self._anim.stop()
        self._span = self._target_span()
        self._from = self._to = self._span

    def _start_underline(self):
        target = self._target_span()
        if target is None or self._span is None or not self.isVisible():
            self._snap()
            return
        self._from = self._span
        self._to = target
        self._anim.stop()
        self._anim.start()

    def _on_anim(self, t):
        if self._from is None or self._to is None:
            return
        (l0, r0), (l1, r1) = self._from, self._to
        right = l1 >= l0
        e_lead = _ease(QtCore.QEasingCurve.OutCubic, t)
        e_trail = _ease(QtCore.QEasingCurve.InOutCubic, t)
        el, er = (e_trail, e_lead) if right else (e_lead, e_trail)
        self._span = (l0 + (l1 - l0) * el, r0 + (r1 - r0) * er)
        self.update()

    def _after_change(self):
        self._clamp_offset()
        self._snap()
        self.updateGeometry()
        self.update()

    def resizeEvent(self, e):
        self._clamp_offset()
        if self._anim.state() != QtCore.QAbstractAnimation.Running:
            self._snap()

    def showEvent(self, e):
        self._snap()

    # ---- ヒットテスト ----
    def _hit(self, pos):
        rects, plus, avail, overflow, _t = self._geometry()
        if plus.contains(pos):
            return -1
        if pos.x() > avail and overflow:
            return -2
        for i, r in enumerate(rects):
            if r.translated(-self._offset, 0).contains(pos):
                return i
        return -2

    # ---- マウス ----
    def mouseMoveEvent(self, e):
        h = self._hit(e.position())
        if h != self._hover:
            self._hover = h
            self.setCursor(Qt.PointingHandCursor if h > -2 else Qt.ArrowCursor)
            self.update()

    def leaveEvent(self, e):
        self._hover = -2
        self.update()

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        h = self._hit(e.position())
        self._pressed = h
        if h >= 0:
            self._kb_focus = False
            self.setCurrentIndex(h)
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        h = self._hit(e.position())
        if self._pressed == -1 and h == -1:
            self.addRequested.emit()
        self._pressed = -2
        self.update()

    def wheelEvent(self, e):
        rects, _, avail, overflow, _t = self._geometry()
        if not overflow:
            e.ignore()
            return
        d = e.angleDelta().y() or e.angleDelta().x()
        self._offset -= d // 2
        self._clamp_offset()
        self.update()
        e.accept()

    def contextMenuEvent(self, e):
        h = self._hit(QtCore.QPointF(e.pos()))
        if h < 0:
            return
        menu = self._build_tab_menu(h)
        menu.exec(e.globalPos())

    def _build_tab_menu(self, i):
        menu = QtWidgets.QMenu(self)
        a = menu.addAction("タブ名を変更…")
        a.triggered.connect(lambda: self.tabRenameRequested.emit(i))
        d = menu.addAction("タブを削除")
        d.setEnabled(self.count() > 1)
        d.triggered.connect(lambda: self.tabDeleteRequested.emit(i))
        return menu

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
        n = self.count()
        if k == Qt.Key_Left and n:
            self._kb_focus = True
            self.setCurrentIndex(max(0, self._cur - 1))
        elif k == Qt.Key_Right and n:
            self._kb_focus = True
            self.setCurrentIndex(min(n - 1, self._cur + 1))
        elif k == Qt.Key_Home and n:
            self.setCurrentIndex(0)
        elif k == Qt.Key_End and n:
            self.setCurrentIndex(n - 1)
        else:
            e.ignore()
            return
        self.update()

    # ---- 描画 ----
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        m = self._metrics()
        h = self.height()
        rects, plus, avail, overflow, _t = self._geometry()
        p.fillRect(self.rect(), self.palette().window())
        p.fillRect(QtCore.QRect(0, h - 1, self.width(), 1), COLOR_BASELINE)

        p.save()
        p.setClipRect(QtCore.QRectF(0, 0, avail if overflow else self.width(), h))
        p.translate(-self._offset, 0)
        text_h = h - 3
        for i, r in enumerate(rects):
            if i == self._cur:
                col = COLOR_TAB_SELECTED
            elif i == self._hover:
                col = COLOR_TAB_HOVER
            else:
                col = COLOR_TAB
            p.setPen(col)
            p.drawText(QtCore.QRectF(r.left(), 0, r.width(), text_h),
                       Qt.AlignCenter, self._tabs[i])
        if self._span is not None and self._cur >= 0:
            l, rr = self._span
            p.setPen(Qt.NoPen)
            p.setBrush(COLOR_ACCENT)
            p.drawRect(QtCore.QRectF(l, h - 2, rr - l, 2))
        if self._kb_focus and self.hasFocus() and 0 <= self._cur < len(rects):
            pen = QtGui.QPen(COLOR_ACCENT, 1)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(rects[self._cur].adjusted(1, 3, -1, -4), 3, 3)
        p.restore()

        # 「+」(オーバーフロー時は右端に固定)
        if overflow:
            p.fillRect(QtCore.QRectF(plus.left() - 1, 0, plus.width() + 1, h - 1),
                       self.palette().window())
        col = COLOR_TAB_SELECTED if self._hover == -1 else COLOR_TAB
        if self._pressed == -1 and self._hover == -1:
            col = COLOR_ACCENT
        pen = QtGui.QPen(col, max(1.5, m["h"] * 0.06))
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        c = QtCore.QPointF(plus.center().x(), (h - 3) / 2.0)
        k = m["h"] * 0.17
        p.drawLine(QtCore.QPointF(c.x() - k, c.y()), QtCore.QPointF(c.x() + k, c.y()))
        p.drawLine(QtCore.QPointF(c.x(), c.y() - k), QtCore.QPointF(c.x(), c.y() + k))


# ===========================================================================
# 2. アイテム
# ===========================================================================
class ShelfButton(QtWidgets.QWidget):
    """アイコン + 下にラベル。描画のみ。移動/メニューは親の ShelfPage が処理する。"""
    clicked = QtCore.Signal()

    def __init__(self, label, icon=None, color=None, parent=None):
        super().__init__(parent)
        self._label = label
        self._icon = icon                    # fn(painter, QRectF, QColor) か QIcon
        self._color = QtGui.QColor(color) if color else QtGui.QColor("#cccccc")
        self._callback = None
        self._data = None
        self._hover = False
        self._down = False
        self._ghosted = False
        self._kb_focus = False
        self._press_pos = QtCore.QPoint()
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.TabFocus)

    # ---- アクセサ ----
    def label(self):
        return self._label

    def setLabel(self, text):
        self._label = text
        self.update()

    def data(self):
        return self._data

    def setData(self, d):
        self._data = d

    def setCallback(self, fn):
        self._callback = fn

    def setIcon(self, icon):
        self._icon = icon
        self.update()

    def setColor(self, color):
        self._color = QtGui.QColor(color)
        self.update()

    def page(self):
        w = self.parentWidget()
        return w if isinstance(w, ShelfPage) else None

    # ---- マウス ----
    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        pg = self.page()
        if e.button() == Qt.LeftButton:
            self._down = True
            self._kb_focus = False
            self.update()
            e.accept()
        elif e.button() == Qt.MiddleButton and pg is not None:
            self._press_pos = e.position().toPoint()
            pg._drag_press(self, e.globalPosition().toPoint(), self._press_pos)
            e.accept()
        else:
            e.ignore()

    def mouseMoveEvent(self, e):
        pg = self.page()
        if pg is not None and pg._drag_item is self:
            pg._drag_move(e.globalPosition().toPoint())
            e.accept()

    def mouseReleaseEvent(self, e):
        pg = self.page()
        if e.button() == Qt.MiddleButton and pg is not None and pg._drag_item is self:
            pg._drag_release(e.globalPosition().toPoint())
            e.accept()
        elif e.button() == Qt.LeftButton and self._down:
            self._down = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
                self._fire()
            e.accept()

    def _fire(self):
        self.clicked.emit()
        pg = self.page()
        if pg is not None:
            pg.itemTriggered.emit(self)
        if self._callback:
            self._callback()

    def contextMenuEvent(self, e):
        pg = self.page()
        if pg is not None:
            pg._show_item_menu(self, e.globalPos())
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
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space):
            self._kb_focus = True
            self._fire()
        elif e.key() == Qt.Key_Menu:
            pg = self.page()
            if pg is not None:
                pg._show_item_menu(self, self.mapToGlobal(self.rect().center()))
        else:
            e.ignore()

    # ---- 描画 ----
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        if self._ghosted:
            p.setOpacity(0.3)
        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        if self._down and self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(COLOR_ITEM_PRESSED)
            p.drawRoundedRect(r, 5, 5)
        elif self._hover:
            p.setPen(Qt.NoPen)
            p.setBrush(COLOR_ITEM_HOVER)
            p.drawRoundedRect(r, 5, 5)
        if self._kb_focus and self.hasFocus():
            p.setPen(QtGui.QPen(COLOR_ACCENT, 1))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r, 5, 5)

        pad = _em(self, 0.4)
        isz = _em(self, 2.2)
        icon_rect = QtCore.QRectF((self.width() - isz) / 2.0, pad, isz, isz)
        if callable(self._icon):
            p.save()
            self._icon(p, icon_rect, self._color)
            p.restore()
        elif isinstance(self._icon, QtGui.QIcon):
            self._icon.paint(p, icon_rect.toRect())

        font = self.font()
        fm = QtGui.QFontMetrics(font)
        lines = _wrap_lines(self._label, font, self.width() - 2 * pad, 2)
        y = pad + isz + _em(self, 0.3)
        p.setPen(COLOR_LABEL)
        p.setFont(font)
        for ln in lines:
            p.drawText(QtCore.QRectF(0, y, self.width(), fm.height()),
                       Qt.AlignHCenter | Qt.AlignTop, ln)
            y += fm.height()


# ===========================================================================
# 3. ページ(フロー配置 + 中ドラッグ移動 + 右クリックメニュー)
# ===========================================================================
class _Overlay(QtWidgets.QWidget):
    """挿入ラインとドラッグ中のゴーストを最前面に描くための透過ウィジェット。"""

    def __init__(self, page):
        super().__init__(page)
        self._page = page
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WA_NoSystemBackground)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        self._page._paint_overlay(p)


class ShelfPage(QtWidgets.QWidget):
    itemTriggered = QtCore.Signal(object)       # ShelfButton
    itemMoved = QtCore.Signal(int, int)         # 移動元index, 移動後index
    itemRenamed = QtCore.Signal(object, str)    # ShelfButton, 新ラベル
    itemRemoved = QtCore.Signal(object)         # ShelfButton(削除直前)
    cleared = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []
        self._cols = 1
        # ドラッグ状態
        self._drag_item = None
        self._drag_active = False
        self._drag_start = QtCore.QPoint()
        self._drag_grab = QtCore.QPoint()
        self._drag_pos = QtCore.QPointF()
        self._drag_pixmap = None
        self._drop_index = -1
        self._drop_line = None
        self._overlay = _Overlay(self)
        self._overlay.show()
        self.setMinimumWidth(_em(self, 6))
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.MinimumExpanding)

    # ---- 公開API ----
    def count(self):
        return len(self._items)

    def items(self):
        return list(self._items)

    def addItem(self, label, icon=None, color=None, tooltip="", callback=None,
                data=None, index=None):
        it = ShelfButton(label, icon, color, self)
        it.setToolTip(tooltip)
        it.setCallback(callback)
        it.setData(data)
        if index is None or index >= len(self._items):
            self._items.append(it)
        else:
            self._items.insert(max(0, index), it)
        it.show()
        self._relayout()
        return it

    def removeItem(self, item):
        if item not in self._items:
            return
        if self._drag_item is item:
            self._end_drag()
        self._items.remove(item)
        item.hide()
        item.setParent(None)
        item.deleteLater()
        self._relayout()

    def clear(self):
        self._end_drag()
        for it in self._items:
            it.hide()
            it.setParent(None)
            it.deleteLater()
        self._items = []
        self._relayout()

    def moveItem(self, src, dst):
        if src == dst or not (0 <= src < len(self._items)) or not (0 <= dst < len(self._items)):
            return
        it = self._items.pop(src)
        self._items.insert(dst, it)
        self._relayout()
        self.itemMoved.emit(src, dst)

    # ---- ダイアログ(差し替え可能) ----
    def askLabel(self, current):
        text, ok = QtWidgets.QInputDialog.getText(self, "ラベルの変更", "ラベル:", text=current)
        text = text.strip()
        return text if ok and text else None

    def confirmDeleteAll(self):
        box = QtWidgets.QMessageBox(self)
        box.setIcon(QtWidgets.QMessageBox.Warning)
        box.setWindowTitle("すべて削除")
        box.setText("このシェルフのアイテムをすべて削除しますか?")
        box.setInformativeText("この操作は元に戻せません。")
        yes = box.addButton("すべて削除", QtWidgets.QMessageBox.DestructiveRole)
        cancel = box.addButton("キャンセル", QtWidgets.QMessageBox.RejectRole)
        box.setDefaultButton(cancel)
        box.setEscapeButton(cancel)
        box.exec()
        return box.clickedButton() is yes

    # ---- レイアウト ----
    def _cell(self):
        em_h = self.fontMetrics().height()
        w = _em(self, 5.0)
        pad = _em(self, 0.4)
        h = pad + _em(self, 2.2) + _em(self, 0.3) + em_h * 2 + pad
        return w, h

    def _margins(self):
        return _em(self, 0.5), _em(self, 0.25)       # 外余白, アイテム間隔

    def _calc_cols(self, width):
        cw, _ch = self._cell()
        m, sp = self._margins()
        return max(1, (width - 2 * m + sp) // (cw + sp))

    def _cell_rect(self, i):
        cw, ch = self._cell()
        m, sp = self._margins()
        r, c = divmod(i, self._cols)
        return QtCore.QRect(m + c * (cw + sp), m + r * (ch + sp), cw, ch)

    def _needed_height(self, cols):
        cw, ch = self._cell()
        m, sp = self._margins()
        rows = max(1, -(-len(self._items) // max(1, cols)))
        return 2 * m + rows * ch + (rows - 1) * sp

    def _relayout(self):
        cw, ch = self._cell()
        self._cols = self._calc_cols(self.width())
        for i, it in enumerate(self._items):
            it.setFixedSize(cw, ch)
            it.setGeometry(self._cell_rect(i))
        self.setMinimumHeight(self._needed_height(self._cols))
        self._overlay.setGeometry(self.rect())
        self._overlay.raise_()
        self.update()
        self._overlay.update()

    def resizeEvent(self, e):
        self._relayout()

    def sizeHint(self):
        cw, _ch = self._cell()
        m, sp = self._margins()
        return QtCore.QSize(2 * m + cw * 4 + sp * 3, self._needed_height(4))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self._needed_height(self._calc_cols(w))

    # ---- 中ドラッグ ----
    def _drag_press(self, item, global_pos, local_pos):
        self._drag_item = item
        self._drag_active = False
        self._drag_start = global_pos
        self._drag_grab = local_pos

    def _drag_move(self, global_pos):
        if self._drag_item is None:
            return
        if not self._drag_active:
            if (global_pos - self._drag_start).manhattanLength() < QtWidgets.QApplication.startDragDistance():
                return
            self._drag_active = True
            pm = QtGui.QPixmap(self._drag_item.size())
            pm.fill(Qt.transparent)
            self._drag_item.render(pm, QtCore.QPoint(), QtGui.QRegion(),
                                   QtWidgets.QWidget.DrawChildren)
            self._drag_pixmap = pm
            self._drag_item._ghosted = True
            self._drag_item.update()
            self.grabKeyboard()
            self.setCursor(Qt.ClosedHandCursor)
        self._drag_pos = QtCore.QPointF(self.mapFromGlobal(global_pos))
        self._drop_index, self._drop_line = self._drop_target(self._drag_pos)
        self._overlay.update()

    def _drag_release(self, global_pos):
        if self._drag_item is None:
            return
        if self._drag_active:
            pos = QtCore.QPointF(self.mapFromGlobal(global_pos))
            if self.rect().contains(pos.toPoint()):
                idx, _line = self._drop_target(pos)
                src = self._items.index(self._drag_item)
                dst = idx - 1 if idx > src else idx
                self._end_drag()
                if idx >= 0 and dst != src:
                    self.moveItem(src, dst)
                return
        self._end_drag()

    def _end_drag(self):
        if self._drag_item is not None:
            try:
                self._drag_item._ghosted = False
                self._drag_item.update()
            except RuntimeError:
                pass
        if self._drag_active:
            self.releaseKeyboard()
            self.unsetCursor()
        self._drag_item = None
        self._drag_active = False
        self._drag_pixmap = None
        self._drop_index = -1
        self._drop_line = None
        self._overlay.update()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape and self._drag_item is not None:
            self._end_drag()
            e.accept()
        else:
            super().keyPressEvent(e)

    def _drop_target(self, pos):
        """pos(ページ座標)に対する (挿入index, 挿入ラインrect)。移動しない位置ならラインはNone。"""
        n = len(self._items)
        if n == 0:
            return -1, None
        cw, ch = self._cell()
        m, sp = self._margins()
        rows = -(-n // self._cols)
        row = int(max(0, min(rows - 1, (pos.y() - m) // (ch + sp))))
        start = row * self._cols
        end = min(n, start + self._cols)
        idx = end
        for j in range(start, end):
            if pos.x() < self._cell_rect(j).center().x():
                idx = j
                break
        if idx < end:
            x = self._cell_rect(idx).left() - sp / 2.0
        else:
            x = self._cell_rect(idx - 1).right() + 1 + sp / 2.0
        y = self._cell_rect(start).top()
        line = QtCore.QRectF(x - 1, y, 2, ch)
        src = self._items.index(self._drag_item) if self._drag_item in self._items else -1
        if idx == src or idx == src + 1:
            line = None
        return idx, line

    # ---- 描画 ----
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), self.palette().window())
        if not self._items:
            p.setPen(COLOR_HINT)
            p.drawText(self.rect(), Qt.AlignCenter, "(アイテムなし)")

    def _paint_overlay(self, p):
        if self._drop_line is not None and self._drag_active:
            r = self._drop_line
            cap = _em(self, 0.3)
            p.setPen(Qt.NoPen)
            p.setBrush(COLOR_DROP)
            p.drawRoundedRect(r, 1, 1)
            p.drawRoundedRect(QtCore.QRectF(r.center().x() - cap, r.top(), cap * 2, 2), 1, 1)
            p.drawRoundedRect(QtCore.QRectF(r.center().x() - cap, r.bottom() - 2, cap * 2, 2), 1, 1)
        if self._drag_active and self._drag_pixmap is not None:
            p.setOpacity(0.75)
            dpr = self._drag_pixmap.devicePixelRatio() or 1.0
            top_left = self._drag_pos - QtCore.QPointF(self._drag_grab)
            p.drawPixmap(top_left, self._drag_pixmap)
            _ = dpr

    # ---- メニュー ----
    def _build_menu(self, item=None):
        menu = QtWidgets.QMenu(self)
        if item is not None:
            a = menu.addAction("ラベルを変更…")
            a.triggered.connect(lambda: self._rename_item(item))
            d = menu.addAction("削除")
            d.triggered.connect(lambda: self._remove_item(item))
            menu.addSeparator()
        all_ = menu.addAction("すべて削除…")
        all_.setEnabled(bool(self._items))
        all_.triggered.connect(self._delete_all)
        return menu

    def _show_item_menu(self, item, global_pos):
        self._build_menu(item).exec(global_pos)

    def contextMenuEvent(self, e):
        self._build_menu(None).exec(e.globalPos())

    def _rename_item(self, item):
        text = self.askLabel(item.label())
        if text and text != item.label():
            item.setLabel(text)
            self.itemRenamed.emit(item, text)

    def _remove_item(self, item):
        self.itemRemoved.emit(item)
        self.removeItem(item)

    def _delete_all(self):
        if not self._items:
            return
        if self.confirmDeleteAll():
            self.clear()
            self.cleared.emit()


# ===========================================================================
# 4. タブウィジェット
# ===========================================================================
class ShelfTabWidget(QtWidgets.QWidget):
    currentChanged = QtCore.Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._pages = []
        self._scrolls = []
        self._bar = ShelfTabBar(self)
        self._stack = QtWidgets.QStackedWidget(self)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self._bar)
        lay.addWidget(self._stack, 1)
        self._bar.currentChanged.connect(self._on_bar_changed)
        self._bar.addRequested.connect(self._on_add)
        self._bar.tabRenameRequested.connect(self._on_rename)
        self._bar.tabDeleteRequested.connect(self._on_delete)

    # ---- 公開API ----
    def tabBar(self):
        return self._bar

    def count(self):
        return len(self._pages)

    def shelf(self, i):
        return self._pages[i]

    def currentShelf(self):
        i = self._bar.currentIndex()
        return self._pages[i] if 0 <= i < len(self._pages) else None

    def currentIndex(self):
        return self._bar.currentIndex()

    def setCurrentIndex(self, i):
        self._bar.setCurrentIndex(i)

    def shelfName(self, i):
        return self._bar.tabText(i)

    def addShelf(self, name):
        page = ShelfPage()
        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                             "QScrollArea > QWidget > QWidget { background: transparent; }")
        scroll.setWidget(page)
        self._pages.append(page)
        self._scrolls.append(scroll)
        self._stack.addWidget(scroll)
        self._bar.addTab(name)
        return page

    def removeShelf(self, i):
        if not 0 <= i < len(self._pages):
            return
        scroll = self._scrolls.pop(i)
        self._pages.pop(i)
        self._stack.removeWidget(scroll)
        scroll.deleteLater()
        self._bar.removeTab(i)
        self._stack.setCurrentIndex(max(0, self._bar.currentIndex()))

    # ---- ダイアログ(差し替え可能) ----
    def askShelfName(self, default=""):
        text, ok = QtWidgets.QInputDialog.getText(self, "シェルフ名", "シェルフ名:", text=default)
        text = text.strip()
        return text if ok and text else None

    def confirmDeleteShelf(self, name):
        r = QtWidgets.QMessageBox.question(
            self, "タブを削除", f"「{name}」とその中のアイテムを削除しますか?",
            QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No, QtWidgets.QMessageBox.No)
        return r == QtWidgets.QMessageBox.Yes

    # ---- 内部 ----
    def _default_name(self):
        n = self.count() + 1
        names = {self._bar.tabText(i) for i in range(self.count())}
        while f"Shelf {n}" in names:
            n += 1
        return f"Shelf {n}"

    def _on_bar_changed(self, i):
        if 0 <= i < self._stack.count():
            self._stack.setCurrentIndex(i)
        self.currentChanged.emit(i)

    def _on_add(self):
        name = (self.askShelfName(self._default_name()) or "").strip()
        if name:
            self.addShelf(name)
            self.setCurrentIndex(self.count() - 1)

    def _on_rename(self, i):
        name = (self.askShelfName(self._bar.tabText(i)) or "").strip()
        if name:
            self._bar.setTabText(i, name)

    def _on_delete(self, i):
        if self.count() <= 1:
            return
        if self._pages[i].count() and not self.confirmDeleteShelf(self._bar.tabText(i)):
            return
        self.removeShelf(i)


# ===========================================================================
# デモ
# ===========================================================================
DEMO_OBJECT_NAME = "shelfTabsDemoWindow"

_PINK, _ORANGE, _GREEN, _BLUE = "#e88a9c", "#e3a35c", "#7cbf76", "#6fb1e8"


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
        self.setWindowTitle("shelf_tabs demo")
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, COLOR_BG)
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#dddddd"))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#2b2b2b"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#dddddd"))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#505050"))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#dddddd"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        self.shelf = ShelfTabWidget()
        self.status = QtWidgets.QLabel("アイコン: クリックで実行 / 中ドラッグで移動 / 右クリックでメニュー")
        self.status.setContentsMargins(10, 6, 10, 6)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addWidget(self.shelf, 1)
        lay.addWidget(self.status)

        def run(name):
            return lambda: self.status.setText(f"実行: {name}")

        specs = {
            "Modeling": [("Move", icon_move, _PINK), ("Copy", icon_copy, _ORANGE),
                         ("Link Objects", icon_link, _GREEN), ("Brush", icon_brush, _BLUE),
                         ("Select", icon_cursor, "#cccccc"), ("Grid", icon_grid, _ORANGE),
                         ("Extrude Faces Along Curve", icon_move, _PINK), ("Bevel", icon_copy, _GREEN),
                         ("Bridge", icon_link, _BLUE), ("Merge", icon_grid, _PINK)],
            "Rigging": [("Joint", icon_cursor, _GREEN), ("IK", icon_link, _ORANGE),
                        ("Skin", icon_brush, _PINK), ("Control", icon_grid, _BLUE)],
            "Anim": [("Key", icon_move, _ORANGE), ("Graph", icon_link, _GREEN)],
        }
        for name, items in specs.items():
            page = self.shelf.addShelf(name)
            for label, icon, col in items:
                page.addItem(label, icon, col, tooltip=label, callback=run(label))
            page.itemMoved.connect(lambda s, d: self.status.setText(f"移動: {s} → {d}"))
            page.itemRenamed.connect(lambda it, t: self.status.setText(f"ラベル変更: {t}"))
            page.itemRemoved.connect(lambda it: self.status.setText(f"削除: {it.label()}"))
            page.cleared.connect(lambda: self.status.setText("すべて削除しました"))
        self.resize(480, 360)


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