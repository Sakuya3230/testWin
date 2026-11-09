"""
radial_menu.py
PySide6 (Maya 2027 対応) ラジアルメニュー

      ┌ 外周: 選択中の項目のサブメニュー(弧に沿って並ぶ)
      │      ╭──── 書き出し ────╮
      │   バインド   ミラー        置換
      │  ジョイント〉 ( Skin ) ─ ウエイト〉   加算 / 減算 / 正規化 …
      │   メッシュ〉   スムース
      │      ╰── 読み込み・適用 ──╯
      └ 中央: カーソルが中央にある間は「キャンセル」

操作(マーキングメニュー方式): ドラッグで出現 → 方向で項目を選ぶ → ボタンを離すと実行
    - 中央で離す / Esc : キャンセル
    - 〉付きの項目(サブメニューあり)は、外周に弧状のサブ項目が出る。外へ動かして選び、離すと実行

収録:
    1. RadialItem         : 項目データ(ラベル/アイコン/色/種類/コールバック/子項目)
    2. RadialMenu         : メニュー本体(透過の最前面ウィンドウ)。popup(グローバル座標) で表示
    3. RadialMenuTrigger  : 「ウィンドウがアクティブな時の Ctrl+右ボタン押下」で出すトリガー(押した瞬間に表示。修飾キー/ボタン/タイミングは変更可)
    4. RadialButton       : 丸ボタン。左右どちらのドラッグでもメニューを出す(ドラッグしないクリックは clicked)

【使い方】
    menu = RadialMenu(title="Skin", subtitle="中央でキャンセル")
    menu.addItem("書き出し", icon=icon_upload, kind=RadialItem.PRIMARY, callback=export)   # 上から時計回りに並ぶ
    w = menu.addItem("ウエイト", color="#e8879b")
    w.addChild("置換", callback=...)               # 子を持つと〉付き + 外周サブメニュー
    menu.triggered.connect(lambda item: print(item.path()))     # 例: ['ウエイト', '置換']

    trigger = RadialMenuTrigger(menu, my_window)    # Ctrl+右ボタンを押した瞬間に表示(my_window がアクティブな時)
    btn = RadialButton(menu=menu)                   # 丸ボタン: 左右ボタンの押下で出現(setShowOnPress(False) でドラッグ開始に変更可)

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python radial_menu.py
    - Maya:  import radial_menu; radial_menu.show_demo()
             2層目の最大数テスト: radial_menu.show_demo(sub_count=12)  (ウィンドウ左上の数値でも変更可)
             修正を反映するとき: import importlib; importlib.reload(radial_menu)
"""
import math
import traceback

from PySide6 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt

# ---------------------------------------------------------------------------
# 配色
# ---------------------------------------------------------------------------
C_DISC = QtGui.QColor("#1e1f21")
C_DISC_EDGE = QtGui.QColor("#3d3e42")
C_CENTER_EDGE = QtGui.QColor("#4a4b4f")
C_CENTER_HOVER = QtGui.QColor("#2a2b2e")
C_TITLE = QtGui.QColor("#ffffff")
C_SUBTITLE = QtGui.QColor("#8e8f93")
C_PILL = QtGui.QColor("#3b3b3d")
C_PILL_EDGE = QtGui.QColor("#58595c")
C_TEXT = QtGui.QColor("#e8e8e8")
C_PRIMARY = QtGui.QColor("#3d6f9f")
C_PRIMARY_SEL = QtGui.QColor("#4a82b5")
C_SECONDARY = QtGui.QColor("#2a3d52")
C_SECONDARY_SEL = QtGui.QColor("#34506d")
C_BLUE_EDGE = QtGui.QColor("#86b6dd")
C_BLUE_SEL_EDGE = QtGui.QColor("#b5d8f5")
C_DEFAULT_ACCENT = QtGui.QColor("#7fb0e0")
C_DARK = QtGui.QColor("#2c2c2e")


def _em(widget, ratio):
    """フォント高さ基準の長さ(px)。UIスケール/DPIが変わっても比率が崩れない。"""
    return max(1, round(widget.fontMetrics().height() * ratio))


def _mix(a, b, t):
    """a に b を比率 t で混ぜる。"""
    a, b = QtGui.QColor(a), QtGui.QColor(b)
    return QtGui.QColor(round(a.red() + (b.red() - a.red()) * t),
                        round(a.green() + (b.green() - a.green()) * t),
                        round(a.blue() + (b.blue() - a.blue()) * t))


def _wrap_deg(a):
    """角度を -180..180 に。"""
    return (a + 180.0) % 360.0 - 180.0


# ---------------------------------------------------------------------------
# アイコン  fn(painter, QRectF, QColor)
# ---------------------------------------------------------------------------
def _icon_pen(p, c, r):
    pen = QtGui.QPen(c, max(1.4, r.width() * 0.12))
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.NoBrush)


def _tray(p, r):
    s, x, y = r.width(), r.left(), r.top()
    p.drawPolyline([QtCore.QPointF(x + s * .12, y + s * .62), QtCore.QPointF(x + s * .12, y + s * .9),
                    QtCore.QPointF(x + s * .88, y + s * .9), QtCore.QPointF(x + s * .88, y + s * .62)])


def icon_upload(p, r, c):
    _icon_pen(p, c, r)
    s, x, y = r.width(), r.left(), r.top()
    _tray(p, r)
    p.drawLine(QtCore.QPointF(x + s * .5, y + s * .68), QtCore.QPointF(x + s * .5, y + s * .1))
    p.drawPolyline([QtCore.QPointF(x + s * .28, y + s * .32), QtCore.QPointF(x + s * .5, y + s * .1),
                    QtCore.QPointF(x + s * .72, y + s * .32)])


def icon_download(p, r, c):
    _icon_pen(p, c, r)
    s, x, y = r.width(), r.left(), r.top()
    _tray(p, r)
    p.drawLine(QtCore.QPointF(x + s * .5, y + s * .1), QtCore.QPointF(x + s * .5, y + s * .68))
    p.drawPolyline([QtCore.QPointF(x + s * .28, y + s * .46), QtCore.QPointF(x + s * .5, y + s * .68),
                    QtCore.QPointF(x + s * .72, y + s * .46)])


def icon_radial(p, r, c):
    """丸ボタン用: 中心の点と周囲の8つの点。"""
    p.setPen(Qt.NoPen)
    p.setBrush(c)
    cx, cy, s = r.center().x(), r.center().y(), r.width()
    p.drawEllipse(QtCore.QPointF(cx, cy), s * .1, s * .1)
    for i in range(8):
        a = math.radians(i * 45)
        p.drawEllipse(QtCore.QPointF(cx + math.cos(a) * s * .38, cy + math.sin(a) * s * .38), s * .06, s * .06)


# ===========================================================================
# 項目
# ===========================================================================
class RadialItem:
    NORMAL = "normal"        # 灰色のピル(色付きの点)
    PRIMARY = "primary"      # 青の塗りつぶし
    SECONDARY = "secondary"  # 青の枠線

    def __init__(self, label, icon=None, color=None, kind="normal", callback=None,
                 data=None, enabled=True):
        self.label = label
        self.icon = icon                     # fn(painter, QRectF, QColor)
        self.color = QtGui.QColor(color) if color else None
        self.kind = kind
        self.callback = callback
        self.data = data
        self.enabled = enabled
        self.children = []
        self.parent = None

    def addChild(self, label, **kw):
        c = RadialItem(label, **kw)
        c.parent = self
        c.color = c.color or self.color
        self.children.append(c)
        return c

    def accent(self):
        if self.kind in (self.PRIMARY, self.SECONDARY):
            return C_BLUE_SEL_EDGE
        return self.color or C_DEFAULT_ACCENT

    def path(self):
        out, it = [], self
        while it is not None:
            out.append(it.label)
            it = it.parent
        return out[::-1]


# ===========================================================================
# メニュー本体
# ===========================================================================
class _Geo:
    pass


class RadialMenu(QtWidgets.QWidget):
    triggered = QtCore.Signal(object)       # RadialItem(実行された項目)
    canceled = QtCore.Signal()

    def __init__(self, parent=None, title="", subtitle=""):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self._title = title
        self._subtitle = subtitle
        self._items = []
        self._sel = None             # 選択中の第1階層 index
        self._sub = None             # 選択中のサブ index
        self._open = None            # サブメニューを開いている第1階層 index
        self._cursor = None          # QPointF (ローカル座標)
        self._in_center = False
        self._prev_active = None     # 表示前にアクティブだったウィンドウ(閉じたら戻す)

    # ---- 公開API ----
    def setTitle(self, title, subtitle=None):
        self._title = title
        if subtitle is not None:
            self._subtitle = subtitle

    def addItem(self, label, **kw):
        it = RadialItem(label, **kw)
        self._items.append(it)
        return it

    def setItems(self, items):
        self._items = list(items)

    def items(self):
        return list(self._items)

    def clear(self):
        self._items = []

    def popup(self, global_pos):
        """global_pos を中心にメニューを出し、マウスとキーボードを掴む(ボタンを押している間に呼ぶ)。"""
        g = self._geo()
        self._sel = self._sub = self._open = None
        self._in_center = True
        self.resize(g.S, g.S)
        gp = QtCore.QPoint(int(global_pos.x()), int(global_pos.y()))
        self.move(gp.x() - g.S // 2, gp.y() - g.S // 2)
        self._cursor = QtCore.QPointF(g.S / 2.0, g.S / 2.0)
        prev = QtWidgets.QApplication.activeWindow()
        if prev is not None and prev is not self:
            self._prev_active = prev
        self.show()
        self.raise_()
        self.grabMouse()
        self.grabKeyboard()
        self.update()

    def isOpen(self):
        return self.isVisible()

    # ---- 幾何 ----
    def _geo(self):
        g = _Geo()
        em = self.fontMetrics().height()
        g.em = em
        g.R = em * 14.0
        g.rc = g.R * 0.225
        g.rsub = g.R * 1.47
        g.ph = em * 2.4
        g.padx = em * 1.1
        g.S = int(2 * (g.rsub + em * 6.0))
        g.C = QtCore.QPointF(g.S / 2.0, g.S / 2.0)
        return g

    def _angle(self, i, n):
        """項目 i の角度(度, 画面座標: 0=右, 90=下)。上から時計回り。"""
        return -90.0 + i * 360.0 / max(1, n)

    def _item_w(self, it, g, sub=False):
        fm = self.fontMetrics()
        f = QtGui.QFont(self.font())
        if it.kind == RadialItem.PRIMARY:
            f.setBold(True)
        w = QtGui.QFontMetrics(f).horizontalAdvance(it.label) + g.padx * 2
        if not sub:
            if it.icon is not None:
                w += g.em * 1.7
            elif it.color is not None or it.kind == RadialItem.NORMAL:
                w += g.em * 1.2
            if it.children:
                w += g.em * 1.3
        return w

    def _item_rects(self, g):
        n = len(self._items)
        rects = []
        for i, it in enumerate(self._items):
            a = math.radians(self._angle(i, n))
            ux, uy = math.cos(a), math.sin(a)
            w = self._item_w(it, g)
            r_ring = g.R * 0.69
            cx = g.C.x() + ux * r_ring + ux * max(0.0, w / 2 - g.em * 3)
            cy = g.C.y() + uy * r_ring
            rects.append(QtCore.QRectF(cx - w / 2, cy - g.ph / 2, w, g.ph))
        return rects

    def _sub_radius(self, g, idx):
        return g.rsub

    def _sub_angles(self, g, idx):
        """サブ項目の角度。ピルの実寸と向きに応じて間隔を決める(上下方向は横に並ぶので広く、左右は縦に並ぶので狭い)。"""
        it = self._items[idx]
        m = len(it.children)
        base = self._angle(idx, len(self._items))
        if m <= 1:
            return [base] * m
        rs = self._sub_radius(g, idx)
        ph = g.ph * 0.84
        ws = [self._item_w(ch, g, sub=True) for ch in it.children]
        gap = g.em * 0.35
        off = 0.0                                   # 中央寄せ後の位置で判定するため数回繰り返す

        def rect_at(ang, w):
            ar = math.radians(ang)
            return QtCore.QRectF(math.cos(ar) * rs - w / 2.0, math.sin(ar) * rs - ph / 2.0, w, ph)

        for _pass in range(5):
            angs = [0.0]
            for k in range(m - 1):
                prev = rect_at(base + off + angs[-1], ws[k]).adjusted(-gap / 2, -gap / 2, gap / 2, gap / 2)
                a = angs[-1] + 0.5
                for _ in range(600):                # 隣のピルと重ならなくなるまで 0.25° ずつ進める
                    cur = rect_at(base + off + a, ws[k + 1]).adjusted(-gap / 2, -gap / 2, gap / 2, gap / 2)
                    if not prev.intersects(cur):
                        break
                    a += 0.25
                angs.append(a)
            if _pass < 4:                           # 最後の回は off を固定して、判定した配置のまま返す
                off = -(angs[0] + angs[-1]) / 2.0
        return [base + a + off for a in angs]

    def _sub_step_deg(self, g, idx):
        """サブ項目の平均間隔(度)。"""
        a = self._sub_angles(g, idx)
        if len(a) > 1:
            return (a[-1] - a[0]) / (len(a) - 1)
        return math.degrees(g.ph * 1.45 / self._sub_radius(g, idx))

    def _sub_rects(self, g, idx):
        out = []
        it = self._items[idx]
        rs = self._sub_radius(g, idx)
        for ch, a in zip(it.children, self._sub_angles(g, idx)):
            ar = math.radians(a)
            w = self._item_w(ch, g, sub=True)
            cx = g.C.x() + math.cos(ar) * rs
            cy = g.C.y() + math.sin(ar) * rs
            out.append(QtCore.QRectF(cx - w / 2, cy - g.ph * 0.42, w, g.ph * 0.84))
        return out

    # ---- 選択 ----
    def _update_selection(self, pos):
        g = self._geo()
        self._cursor = QtCore.QPointF(pos)
        d = self._cursor - g.C
        dist = math.hypot(d.x(), d.y())
        n = len(self._items)
        self._in_center = dist < g.rc
        if self._in_center or n == 0:
            self._sel = self._sub = self._open = None
            self.update()
            return
        ang = math.degrees(math.atan2(d.y(), d.x()))

        # サブメニューが開いていて、円盤の外へ出たら、角度でサブ項目を選ぶ
        if self._open is not None and dist > g.R * 0.9:
            sub = self._sub_angles(g, self._open)
            step = self._sub_step_deg(g, self._open)
            base = self._angle(self._open, n)
            delta = _wrap_deg(ang - base)
            half = (sub[-1] - sub[0]) / 2.0 + step * 0.75
            if abs(delta) <= half:
                k = min(range(len(sub)), key=lambda j: abs(_wrap_deg(ang - sub[j])))
                ch = self._items[self._open].children[k]
                self._sel = self._open
                self._sub = k if ch.enabled else None
                self.update()
                return

        # 方向(セクター)で第1階層を選ぶ
        idx = min(range(n), key=lambda i: abs(_wrap_deg(ang - self._angle(i, n))))
        if not self._items[idx].enabled:
            self._sel = self._sub = self._open = None
        elif idx != self._sel:
            self._sel = idx
            self._sub = None
            self._open = idx if self._items[idx].children else None
        self.update()

    def _current(self):
        """実行対象の項目(なければ None)。"""
        if self._in_center or self._sel is None:
            return None
        it = self._items[self._sel]
        if self._sub is not None:
            return it.children[self._sub]
        if it.children:
            return None                  # サブ項目を選ばずに離した → キャンセル
        return it

    # ---- 入力 ----
    def mouseMoveEvent(self, e):
        try:
            self._update_selection(e.position())
        except Exception:
            traceback.print_exc()

    def mousePressEvent(self, e):
        e.accept()

    def mouseReleaseEvent(self, e):
        try:
            self._update_selection(e.position())
            it = self._current()
            self._close()
            if it is None:
                self.canceled.emit()
            else:
                self.triggered.emit(it)
                if it.callback:
                    it.callback()
        except Exception:
            traceback.print_exc()
            self._close()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self._close()
            self.canceled.emit()
            e.accept()
        else:
            e.ignore()

    def _close(self):
        self.releaseMouse()
        self.releaseKeyboard()
        self.hide()
        self._sel = self._sub = self._open = None
        prev = self._prev_active
        if prev is not None and prev is not self:
            try:
                prev.activateWindow()    # 呼び出し元ウィンドウを非アクティブのままにしない
            except RuntimeError:
                pass

    def hideEvent(self, e):
        self.releaseMouse()
        self.releaseKeyboard()

    # ---- 描画 ----
    def paintEvent(self, e):
        try:
            self._paint()
        except Exception:
            traceback.print_exc()

    def _paint(self):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        g = self._geo()
        C, R, rc = g.C, g.R, g.rc

        # 円盤
        p.setPen(QtGui.QPen(C_DISC_EDGE, 1.5))
        p.setBrush(C_DISC)
        p.drawEllipse(C, R, R)

        # 中央
        p.setPen(QtGui.QPen(C_CENTER_EDGE, 2))
        p.setBrush(C_CENTER_HOVER if self._in_center else C_DISC)
        p.drawEllipse(C, rc, rc)
        tf = QtGui.QFont(self.font())
        tf.setBold(True)
        sf = QtGui.QFont(self.font())
        if sf.pointSizeF() > 0:
            sf.setPointSizeF(sf.pointSizeF() * 0.85)
        th = QtGui.QFontMetrics(tf).height()
        sh = QtGui.QFontMetrics(sf).height()
        top = C.y() - (th + (sh if self._subtitle else 0)) / 2.0
        p.setFont(tf)
        p.setPen(C_TITLE)
        p.drawText(QtCore.QRectF(C.x() - rc, top, rc * 2, th), Qt.AlignCenter, self._title)
        if self._subtitle:
            p.setFont(sf)
            p.setPen(C_SUBTITLE)
            p.drawText(QtCore.QRectF(C.x() - rc, top + th, rc * 2, sh), Qt.AlignCenter, self._subtitle)
        p.setFont(self.font())

        rects = self._item_rects(g)

        # 選択中の項目と中央を結ぶ線
        if self._sel is not None and not self._in_center:
            r = rects[self._sel]
            it = self._items[self._sel]
            v = C - r.center()
            tx = (r.width() / 2.0) / abs(v.x()) if abs(v.x()) > 1e-6 else 1e9
            ty = (r.height() / 2.0) / abs(v.y()) if abs(v.y()) > 1e-6 else 1e9
            t = min(tx, ty)
            p0 = r.center() + v * t
            ln = math.hypot(v.x(), v.y())
            p1 = C - v * (rc / ln) if ln > 0 else C
            pen = QtGui.QPen(it.accent(), 2)
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(p1, p0)

        # 項目(選択中を最後に)
        order = [i for i in range(len(rects)) if i != self._sel]
        if self._sel is not None:
            order.append(self._sel)
        for i in order:
            self._draw_item(p, g, self._items[i], rects[i], selected=(i == self._sel and not self._in_center))

        # サブメニュー
        if self._open is not None:
            self._draw_sub(p, g, self._open)

    def _draw_item(self, p, g, it, r, selected):
        em = g.em
        p.save()
        if not it.enabled:
            p.setOpacity(0.4)
        accent = it.accent()
        kind = it.kind
        bold = False
        if kind == RadialItem.PRIMARY:
            bg = C_PRIMARY_SEL if selected else C_PRIMARY
            edge = QtGui.QPen(C_BLUE_SEL_EDGE, 2) if selected else Qt.NoPen
            bold = True
        elif kind == RadialItem.SECONDARY:
            bg = C_SECONDARY_SEL if selected else C_SECONDARY
            edge = QtGui.QPen(C_BLUE_SEL_EDGE if selected else C_BLUE_EDGE, 2 if selected else 1.2)
            bold = selected
        else:
            bg = _mix(C_DARK, accent, 0.32) if selected else C_PILL
            edge = QtGui.QPen(accent, 2) if selected else QtGui.QPen(C_PILL_EDGE, 1)
            bold = selected
        p.setPen(edge)
        p.setBrush(bg)
        rr = r.adjusted(1, 1, -1, -1)
        p.drawRoundedRect(rr, rr.height() / 2, rr.height() / 2)

        # 中身: [アイコン or 点] テキスト [〉]
        f = QtGui.QFont(self.font())
        f.setBold(bold)
        fm = QtGui.QFontMetrics(f)
        x = r.left() + g.padx
        cy = r.center().y()
        if it.icon is not None:
            s = em * 1.0
            p.save()
            it.icon(p, QtCore.QRectF(x, cy - s / 2, s, s), QtGui.QColor("#ffffff"))
            p.restore()
            x += em * 1.7
        elif it.color is not None or kind == RadialItem.NORMAL:
            d = em * 0.62
            p.setPen(Qt.NoPen)
            p.setBrush(it.color or C_DEFAULT_ACCENT)
            p.drawEllipse(QtCore.QPointF(x + d / 2, cy), d / 2, d / 2)
            x += em * 1.2
        p.setFont(f)
        p.setPen(QtGui.QColor("#ffffff") if (selected or kind != RadialItem.NORMAL) else C_TEXT)
        tw = fm.horizontalAdvance(it.label)
        p.drawText(QtCore.QRectF(x, r.top(), tw + 2, r.height()), Qt.AlignVCenter | Qt.AlignLeft, it.label)
        if it.children:
            cx = r.right() - g.padx * 0.9
            s = em * 0.26
            pen = QtGui.QPen(QtGui.QColor("#dddddd"), max(1.3, em * 0.1))
            pen.setCapStyle(Qt.RoundCap)
            pen.setJoinStyle(Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPolyline([QtCore.QPointF(cx - s * .5, cy - s), QtCore.QPointF(cx + s * .5, cy),
                            QtCore.QPointF(cx - s * .5, cy + s)])
        p.restore()

    def _draw_sub(self, p, g, idx):
        parent = self._items[idx]
        accent = parent.accent()
        angles = self._sub_angles(g, idx)
        step = self._sub_step_deg(g, idx)
        rs = self._sub_radius(g, idx)
        # 点線の弧
        a0, a1 = angles[0] - step * 0.9, angles[-1] + step * 0.9
        pen = QtGui.QPen(_mix(C_DARK, accent, 0.5), 1)
        pen.setStyle(Qt.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        rc = QtCore.QRectF(g.C.x() - rs, g.C.y() - rs, rs * 2, rs * 2)
        p.drawArc(rc, int(-a1 * 16), int((a1 - a0) * 16))
        # ピル
        for k, (ch, r) in enumerate(zip(parent.children, self._sub_rects(g, idx))):
            sel = (k == self._sub)
            p.save()
            if not ch.enabled:
                p.setOpacity(0.4)
            col = ch.color or accent
            p.setPen(QtGui.QPen(col if sel else _mix(C_DARK, col, 0.5), 1.8 if sel else 1))
            p.setBrush(_mix(C_DARK, col, 0.42 if sel else 0.16))
            rr = r.adjusted(1, 1, -1, -1)
            p.drawRoundedRect(rr, rr.height() / 2, rr.height() / 2)
            f = QtGui.QFont(self.font())
            f.setBold(sel)
            p.setFont(f)
            p.setPen(QtGui.QColor("#ffffff") if sel else C_TEXT)
            p.drawText(r, Qt.AlignCenter, ch.label)
            p.restore()


# ===========================================================================
# トリガー: アクティブなウィンドウでの Ctrl+右ボタン
# ===========================================================================
_MOD_MASK = Qt.ControlModifier | Qt.ShiftModifier | Qt.AltModifier | Qt.MetaModifier


class RadialMenuTrigger(QtCore.QObject):
    """widget(またはその子孫)上で modifiers+button を押したらメニューを出す(既定: 押した瞬間に表示)。
    show_on_press=False にするとドラッグが始まってから表示する。widget のウィンドウがアクティブな時だけ反応する。"""

    def __init__(self, menu, widget, button=Qt.RightButton, modifiers=Qt.ControlModifier,
                 show_on_press=True):
        super().__init__(widget)
        self._show_on_press = bool(show_on_press)
        self._menu = menu
        self._widget = widget
        self._button = button
        self._mods = modifiers
        self._pending = False
        self._start = QtCore.QPoint()
        self._enabled = True
        QtWidgets.QApplication.instance().installEventFilter(self)

    def setEnabled(self, on):
        self._enabled = bool(on)
        self._pending = False

    def setShowOnPress(self, on):
        """True: 押した瞬間に表示 / False: ドラッグ開始で表示。"""
        self._show_on_press = bool(on)

    def _applies(self, obj):
        w = self._widget
        return (isinstance(obj, QtWidgets.QWidget) and (obj is w or w.isAncestorOf(obj))
                and w.window().isActiveWindow())

    def eventFilter(self, obj, ev):
        try:
            t = ev.type()
            if not self._enabled or obj is self._menu:
                return False
            if t == QtCore.QEvent.MouseButtonPress:
                if (ev.button() == self._button and (ev.modifiers() & _MOD_MASK) == self._mods
                        and self._applies(obj)):
                    self._start = ev.globalPosition().toPoint()
                    if self._show_on_press:
                        self._pending = False
                        self._menu.popup(self._start)       # 押した瞬間に表示。以降の移動/離しはメニューが受ける
                    else:
                        self._pending = True
                    return True
            elif self._pending and t == QtCore.QEvent.MouseMove:
                if not (ev.buttons() & self._button):
                    self._pending = False
                    return False
                d = ev.globalPosition().toPoint() - self._start
                if d.manhattanLength() >= QtWidgets.QApplication.startDragDistance():
                    self._pending = False
                    self._menu.popup(self._start)
                return True
            elif self._pending and t == QtCore.QEvent.MouseButtonRelease:
                if ev.button() == self._button:
                    self._pending = False
                    return True
        except Exception:
            traceback.print_exc()
        return False


# ===========================================================================
# 丸ボタン: 左右どちらのドラッグでもメニューを出す
# ===========================================================================
class RadialButton(QtWidgets.QAbstractButton):
    def __init__(self, text="", icon=None, menu=None, parent=None):
        super().__init__(parent)
        self.setText(text)
        self._icon_fn = icon if icon is not None else icon_radial
        self._menu = menu
        self._center_on_button = True
        self._show_on_press = True
        self._press_pos = None
        self._press_btn = None
        self._hover = False
        self._kb_focus = False
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def setRadialMenu(self, menu):
        self._menu = menu

    def radialMenu(self):
        return self._menu

    def setShowOnPress(self, on):
        """True: 押した瞬間にメニューを表示(左右どちらでも。クリックでは clicked は出ない) /
        False: ドラッグ開始で表示(ドラッグしない左クリックは clicked)。"""
        self._show_on_press = bool(on)

    def setCenterOnButton(self, on):
        """True: ボタン中心にメニューを出す / False: 押した位置に出す。"""
        self._center_on_button = bool(on)

    def sizeHint(self):
        d = _em(self, 3.2)
        return QtCore.QSize(d, d)

    def hitButton(self, pos):
        c = QtCore.QPointF(self.rect().center())
        r = min(self.width(), self.height()) / 2.0
        return math.hypot(pos.x() - c.x(), pos.y() - c.y()) <= r

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def focusInEvent(self, e):
        self._kb_focus = e.reason() in (Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason)
        super().focusInEvent(e)
        self.update()

    def focusOutEvent(self, e):
        self._kb_focus = False
        super().focusOutEvent(e)
        self.update()

    def mousePressEvent(self, e):
        self._kb_focus = False
        if e.button() in (Qt.LeftButton, Qt.RightButton) and self._hit(e.position()):
            if self._show_on_press and self._menu is not None:
                gp = self.mapToGlobal(self.rect().center()) if self._center_on_button \
                    else e.globalPosition().toPoint()
                self.setDown(False)
                self._hover = False
                self.update()
                e.accept()
                self._menu.popup(gp)
                return
            self._press_pos = e.position()
            self._press_btn = e.button()
            if e.button() == Qt.LeftButton:
                super().mousePressEvent(e)       # 通常のクリック用に押下状態にする
            else:
                e.accept()                       # QAbstractButton は右ボタンを無視するので自前で受ける
        else:
            e.ignore()

    def _hit(self, pos):
        return self.hitButton(QtCore.QPoint(int(pos.x()), int(pos.y())))

    def mouseMoveEvent(self, e):
        if self._press_btn is not None and self._menu is not None:
            d = e.position() - self._press_pos
            if (abs(d.x()) + abs(d.y())) >= QtWidgets.QApplication.startDragDistance():
                gp = self.mapToGlobal(self.rect().center()) if self._center_on_button \
                    else e.globalPosition().toPoint() - d.toPoint()
                self._press_btn = None
                self._press_pos = None
                self.setDown(False)
                self._hover = False
                self.update()
                self._menu.popup(gp)
                return
        if self._press_btn == Qt.LeftButton:
            super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        btn, self._press_btn, self._press_pos = self._press_btn, None, None
        if btn == Qt.LeftButton:
            super().mouseReleaseEvent(e)         # ドラッグしなければ clicked
        else:
            self.setDown(False)
            self.update()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(1.5, 1.5, -1.5, -1.5)
        if self.isDown():
            bg = QtGui.QColor("#303032")
        elif self._hover:
            bg = QtGui.QColor("#4a4a4d")
        else:
            bg = C_PILL
        p.setPen(QtGui.QPen(C_PILL_EDGE, 1.2))
        p.setBrush(bg)
        p.drawEllipse(r)
        s = r.width() * 0.56
        self._icon_fn(p, QtCore.QRectF(r.center().x() - s / 2, r.center().y() - s / 2, s, s), C_TEXT)
        if self._kb_focus and self.hasFocus():
            p.setPen(QtGui.QPen(QtGui.QColor("#5285a6"), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(r.adjusted(-1, -1, 1, 1))


# ===========================================================================
# デモ
# ===========================================================================
DEMO_OBJECT_NAME = "radialMenuDemoWindow"

PINK, ORANGE, GREEN, PURPLE = "#e8879b", "#e8a05a", "#7fc77a", "#b497e8"


def _maya_main_window():
    """Mayaが無い環境では None を返す(単体実行できるように)。"""
    try:
        from maya import OpenMayaUI as omui
        from shiboken6 import wrapInstance
    except ImportError:
        return None
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


STRESS_LABELS = ["置換", "加算", "減算", "正規化", "刈り込み", "頂点コピー", "頂点ペースト", "ミラーリング",
                 "スムース", "ロック", "アンロック", "ヒストリ削除", "一括適用", "反転", "リセット", "全選択"]


def build_demo_menu(parent=None, sub_count=None):
    """デモ用メニュー。sub_count を指定すると、第1層の8項目すべてに sub_count 個の2層目を入れる(最大数テスト用)。"""
    m = RadialMenu(parent, title="Skin", subtitle="中央でキャンセル")
    top = [("書き出し", dict(icon=icon_upload, kind=RadialItem.PRIMARY)),
           ("ミラー", dict(color=PINK)), ("ウエイト", dict(color=PINK)), ("スムース", dict(color=PINK)),
           ("読み込み・適用", dict(icon=icon_download, kind=RadialItem.SECONDARY)),
           ("メッシュ", dict(color=GREEN)), ("ジョイント", dict(color=ORANGE)),
           ("バインドポーズへ", dict(color=PURPLE))]
    default_children = {
        "ウエイト": ("置換", "加算", "減算", "正規化", "刈り込み", "頂点コピー", "頂点ペースト"),
        "メッシュ": ("結合", "分離", "複製"),
        "ジョイント": ("作成", "削除", "向きを揃える", "ミラー"),
    }
    for label, kw in top:
        it = m.addItem(label, **kw)
        if sub_count:
            for k in range(int(sub_count)):
                it.addChild(STRESS_LABELS[k % len(STRESS_LABELS)] + ("" if k < len(STRESS_LABELS) else str(k)))
        else:
            for name in default_children.get(label, ()):
                it.addChild(name)
    return m


class DemoWindow(QtWidgets.QWidget):
    """何もないウィンドウ。アクティブ時に Ctrl+右ボタンを押す、または丸ボタンを押すとメニューが出る。"""

    def __init__(self, parent=None, sub_count=None):
        super().__init__(parent, Qt.Window)
        self.setObjectName(DEMO_OBJECT_NAME)
        self.setWindowTitle("radial_menu demo")
        self.menu = build_demo_menu(self, sub_count)
        self.trigger = RadialMenuTrigger(self.menu, self)
        self.button = RadialButton(menu=self.menu, parent=self)
        self.hint = QtWidgets.QLabel("Ctrl + 右ボタン、または丸ボタンを左右どちらかで押す(押したままドラッグして選び、離して実行)", self)
        self.hint.setStyleSheet("color: #8e8f93;")
        self.status = QtWidgets.QLabel("", self)
        self.status.setStyleSheet("color: #cfd1d4;")
        self.menu.triggered.connect(lambda it: self.status.setText("実行: " + " > ".join(it.path())))
        self.menu.canceled.connect(lambda: self.status.setText("キャンセル"))
        self.button.clicked.connect(lambda: self.status.setText("丸ボタン: クリック"))
        # 2層目の数を切り替えて最大数をテストする(0 = 標準デモ)
        self.spin_label = QtWidgets.QLabel("2層目の数(全項目に適用 / 0 = 標準):", self)
        self.spin_label.setStyleSheet("color: #8e8f93;")
        self.spin = QtWidgets.QSpinBox(self)
        self.spin.setRange(0, 30)
        self.spin.setValue(int(sub_count or 0))
        self.spin.valueChanged.connect(self._on_sub_count)
        self.resize(760, 600)
        self._place()

    def _on_sub_count(self, n):
        """メニューの中身を作り直す(次に出すときから反映)。"""
        self.menu.setItems(build_demo_menu(None, n or None).items())
        self.status.setText(f"2層目: {n} 個" if n else "標準メニュー")

    def _place(self):
        self.hint.move(16, 12)
        self.hint.adjustSize()
        self.status.move(16, self.hint.y() + self.hint.height() + 6)
        self.status.resize(self.width() - 32, self.status.sizeHint().height())
        self.spin_label.adjustSize()
        self.spin_label.move(16, self.status.y() + self.status.height() + 10)
        self.spin.move(self.spin_label.x() + self.spin_label.width() + 8, self.spin_label.y() - 3)
        self.button.move(24, self.height() - self.button.height() - 24)

    def resizeEvent(self, e):
        self._place()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.fillRect(self.rect(), QtGui.QColor("#2a2c30"))
        p.setPen(QtGui.QColor("#33353a"))
        step = 40
        for x in range(0, self.width(), step):
            p.drawLine(x, 0, x, self.height())
        for y in range(0, self.height(), step):
            p.drawLine(0, y, self.width(), y)


def show_demo(sub_count=None):
    """Maya内でもスタンドアロンでも使えるデモ表示。多重生成を防ぐ。
    sub_count=12 のように指定すると、全項目に2層目を12個入れた状態で開始(画面左上の数値でも変更できる)。"""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    for w in app.allWidgets():
        if w.objectName() == DEMO_OBJECT_NAME:
            w.close()
            w.deleteLater()
    win = DemoWindow(_maya_main_window(), sub_count)
    win.show()
    return win


if __name__ == "__main__":
    import sys
    _app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
    _win = show_demo()
    sys.exit(_app.exec())