"""
collapsible_frames.py
PySide6 (Maya 2027 対応) おりたたみフレーム

    ▶ Transform            ← ヘッダー(4種類: arrow / bar / card / line)
    ┌──────────────┐
    │  中身         │      ← クリックでアニメーションしながら開閉。中身は縮まず「隠れていく」
    └──────────────┘
    ▶ Display              ← 上のフレームを閉じると、下のフレームが詰まって上がってくる

収録:
    1. CollapsibleFrame   : ヘッダー + 中身。開閉アニメーション付き
         STYLE_ARROW  文字 + 回転する矢印、下に細い線(Maya のセクション風)
         STYLE_BAR    塗りつぶしバー + 三角 + 右端にバッジ
         STYLE_CARD   角丸カード + 太字タイトル + バッジ + 右端の +/−(縦棒がすっと消える)
         STYLE_LINE   タイトル + 右へ伸びる罫線 + 右端のシェブロン
    2. CollapsibleColumn  : フレームを縦に積むスクロールエリア
                            閉じると下のフレームが詰まる / アコーディオン(同時に1つだけ開く) / 全開閉

【使い方】
    col = CollapsibleColumn()
    f = CollapsibleFrame("Transform", style=CollapsibleFrame.STYLE_BAR, badge="3")
    f.addWidget(QtWidgets.QLabel("中身"))          # f.contentLayout() で自由にレイアウト
    col.addFrame(f)
    col.setExclusive(True)                          # アコーディオン
    f.toggled.connect(lambda opened: ...)
    f.setExpanded(False)                            # アニメーション付き。setExpanded(False, animated=False) で即時

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python collapsible_frames.py
    - Maya:  import collapsible_frames; collapsible_frames.show_demo()
"""
from PySide6 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt
QWIDGETSIZE_MAX = 16777215

# ---------------------------------------------------------------------------
# 配色
# ---------------------------------------------------------------------------
C_TEXT = QtGui.QColor("#dddddd")
C_TEXT_HOVER = QtGui.QColor("#ffffff")
C_ICON = QtGui.QColor("#aaaaaa")
C_HAIR = QtGui.QColor("#2e2e2e")
C_RULE = QtGui.QColor("#5a5a5a")
C_BAR = QtGui.QColor("#505050")
C_BAR_HOVER = QtGui.QColor("#5a5a5a")
C_BAR_BODY = QtGui.QColor("#434343")
C_CARD = QtGui.QColor("#454545")
C_CARD_BORDER = QtGui.QColor("#585858")
C_CARD_HOVER = QtGui.QColor(255, 255, 255, 18)
C_ACCENT = QtGui.QColor("#5285a6")
C_BADGE_BG = QtGui.QColor("#34495e")
C_BADGE_FG = QtGui.QColor("#cfe5f7")


def _em(widget, ratio):
    """フォント高さ基準の長さ(px)。UIスケール/DPIが変わっても比率が崩れない。"""
    return max(1, round(widget.fontMetrics().height() * ratio))


def _round_path(rect, r, top=True, bottom=True):
    """上側/下側だけ角丸にできる角丸矩形パス。"""
    path = QtGui.QPainterPath()
    x, y, w, h = rect.x(), rect.y(), rect.width(), rect.height()
    rt = r if top else 0
    rb = r if bottom else 0
    path.moveTo(x + rt, y)
    path.lineTo(x + w - rt, y)
    if rt:
        path.arcTo(x + w - 2 * rt, y, 2 * rt, 2 * rt, 90, -90)
    path.lineTo(x + w, y + h - rb)
    if rb:
        path.arcTo(x + w - 2 * rb, y + h - 2 * rb, 2 * rb, 2 * rb, 0, -90)
    path.lineTo(x + rb, y + h)
    if rb:
        path.arcTo(x, y + h - 2 * rb, 2 * rb, 2 * rb, -90, -90)
    path.lineTo(x, y + rt)
    if rt:
        path.arcTo(x, y, 2 * rt, 2 * rt, 180, -90)
    path.closeSubpath()
    return path


# ===========================================================================
# ヘッダー
# ===========================================================================
class _Header(QtWidgets.QWidget):
    clicked = QtCore.Signal()

    def __init__(self, frame):
        super().__init__(frame)
        self._frame = frame
        self._hover = False
        self._down = False
        self._kb_focus = False
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def _height(self):
        s = self._frame._style
        k = {CollapsibleFrame.STYLE_ARROW: 2.0, CollapsibleFrame.STYLE_BAR: 2.2,
             CollapsibleFrame.STYLE_CARD: 2.6, CollapsibleFrame.STYLE_LINE: 2.0}[s]
        return _em(self, k)

    def sizeHint(self):
        fm = self.fontMetrics()
        return QtCore.QSize(fm.horizontalAdvance(self._frame._title) + _em(self, 5), self._height())

    def minimumSizeHint(self):
        return QtCore.QSize(_em(self, 6), self._height())

    # ---- 入力 ----
    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._down = True
            self._kb_focus = False
            self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._down:
            self._down = False
            self.update()
            if self.rect().contains(e.position().toPoint()):
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

    # ---- 描画 ----
    def _chevron(self, p, c, size, angle, color):
        p.save()
        p.translate(c)
        p.rotate(angle)
        pen = QtGui.QPen(color, max(1.4, size * 0.28))
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)
        p.drawPolyline([QtCore.QPointF(-size * .45, -size), QtCore.QPointF(size * .45, 0),
                        QtCore.QPointF(-size * .45, size)])
        p.restore()

    def _triangle(self, p, c, size, angle, color):
        p.save()
        p.translate(c)
        p.rotate(angle)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPolygon([QtCore.QPointF(-size * .6, -size), QtCore.QPointF(size * .8, 0),
                       QtCore.QPointF(-size * .6, size)])
        p.restore()

    def _badge(self, p, right, cy):
        text = self._frame._badge
        if not text:
            return right
        font = QtGui.QFont(self.font())
        font.setPointSizeF(max(6.0, font.pointSizeF() * 0.85)) if font.pointSizeF() > 0 else None
        fm = QtGui.QFontMetrics(font)
        w = fm.horizontalAdvance(text) + _em(self, 1.0)
        h = fm.height() + _em(self, 0.1)
        r = QtCore.QRectF(right - w, cy - h / 2.0, w, h)
        p.setPen(Qt.NoPen)
        p.setBrush(C_BADGE_BG)
        p.drawRoundedRect(r, h / 2.0, h / 2.0)
        p.setFont(font)
        p.setPen(C_BADGE_FG)
        p.drawText(r, Qt.AlignCenter, text)
        p.setFont(self.font())
        return r.left() - _em(self, 0.5)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setRenderHint(QtGui.QPainter.TextAntialiasing)
        f = self._frame
        t = f._t
        w, h = self.width(), self.height()
        cy = h / 2.0
        em = self.fontMetrics().height()
        text_col = C_TEXT_HOVER if (self._hover or self._down) else C_TEXT
        title = f._title
        s = f._style
        r = QtCore.QRectF(self.rect())

        if s == CollapsibleFrame.STYLE_ARROW:
            pad = em * 0.4
            self._chevron(p, QtCore.QPointF(pad + em * 0.35, cy), em * 0.3, 90 * t, C_ICON)
            x = pad + em * 1.2
            right = self._badge(p, w - pad, cy)
            p.setPen(text_col)
            fm = self.fontMetrics()
            p.drawText(QtCore.QRectF(x, 0, max(1, right - x), h), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(title, Qt.ElideRight, int(right - x)))
            p.fillRect(QtCore.QRectF(0, h - 1, w, 1), C_HAIR)
            focus_rect = r.adjusted(1, 1, -1, -1)

        elif s == CollapsibleFrame.STYLE_BAR:
            p.fillRect(r, C_BAR_HOVER if self._hover else C_BAR)
            pad = em * 0.6
            self._triangle(p, QtCore.QPointF(pad + em * 0.2, cy), em * 0.28, 90 * t, C_ICON)
            x = pad + em * 1.1
            right = self._badge(p, w - pad, cy)
            p.setPen(text_col)
            p.drawText(QtCore.QRectF(x, 0, max(1, right - x), h), Qt.AlignVCenter | Qt.AlignLeft,
                       self.fontMetrics().elidedText(title, Qt.ElideRight, int(right - x)))
            focus_rect = r.adjusted(1, 1, -1, -1)

        elif s == CollapsibleFrame.STYLE_CARD:
            rr = _em(self, 0.35)
            if self._hover:
                p.setPen(Qt.NoPen)
                p.setBrush(C_CARD_HOVER)
                p.drawPath(_round_path(r, rr, True, t < 0.01 and True))
            pad = em * 0.9
            # +/− アイコン(縦棒が t で縮む)
            c = QtCore.QPointF(w - pad - em * 0.1, cy)
            k = em * 0.32
            pen = QtGui.QPen(C_ICON, max(1.5, em * 0.11))
            pen.setCapStyle(Qt.RoundCap)
            p.setPen(pen)
            p.drawLine(QtCore.QPointF(c.x() - k, c.y()), QtCore.QPointF(c.x() + k, c.y()))
            kv = k * (1.0 - t)
            if kv > 0.3:
                p.drawLine(QtCore.QPointF(c.x(), c.y() - kv), QtCore.QPointF(c.x(), c.y() + kv))
            right = self._badge(p, c.x() - k - em * 0.7, cy)
            font = QtGui.QFont(self.font())
            font.setBold(True)
            p.setFont(font)
            p.setPen(text_col)
            p.drawText(QtCore.QRectF(pad, 0, max(1, right - pad), h), Qt.AlignVCenter | Qt.AlignLeft,
                       QtGui.QFontMetrics(font).elidedText(title, Qt.ElideRight, int(right - pad)))
            focus_rect = r.adjusted(2, 2, -2, -2)

        else:  # STYLE_LINE
            pad = em * 0.2
            fm = self.fontMetrics()
            chev_x = w - em * 0.9
            right = self._badge(p, chev_x - em * 0.9, cy)
            tw = min(fm.horizontalAdvance(title) + 2, max(1, int(right - pad - em)))
            p.setPen(text_col)
            p.drawText(QtCore.QRectF(pad, 0, tw + 2, h), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(title, Qt.ElideRight, tw))
            x0 = pad + tw + em * 0.7
            x1 = min(right, chev_x - em * 1.0)
            if x1 > x0:
                p.fillRect(QtCore.QRectF(x0, cy - 0.5, x1 - x0, 1), C_RULE)
            self._chevron(p, QtCore.QPointF(chev_x, cy), em * 0.28, 90 - 180 * t, C_ICON)
            focus_rect = r.adjusted(1, 1, -1, -1)

        if self._kb_focus and self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QtGui.QPen(C_ACCENT, 1))
            p.drawRoundedRect(focus_rect, 3, 3)


# ===========================================================================
# 中身のクリップ(縮めずに隠す)
# ===========================================================================
class _Clip(QtWidgets.QWidget):
    """inner を常にフルサイズで配置し、自身の高さだけを変えて「隠れていく」見せ方にする。"""

    def __init__(self, inner, parent=None):
        super().__init__(parent)
        self.inner = inner
        inner.setParent(self)
        inner.installEventFilter(self)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Preferred)

    def inner_height(self, width):
        lay = self.inner.layout()
        width = max(1, width)
        if lay is not None:
            if lay.hasHeightForWidth():
                return lay.totalHeightForWidth(width)
            return lay.sizeHint().height()
        return self.inner.sizeHint().height()

    def _place(self):
        w = self.width()
        self.inner.setGeometry(0, 0, w, self.inner_height(w))

    def resizeEvent(self, e):
        self._place()

    def eventFilter(self, obj, ev):
        if obj is self.inner and ev.type() == QtCore.QEvent.LayoutRequest:
            self.updateGeometry()
            self._place()
        return False

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, w):
        return self.inner_height(w)

    def sizeHint(self):
        w = max(self.inner.sizeHint().width(), 1)
        return QtCore.QSize(w, self.inner_height(self.width() if self.width() > 1 else w))

    def minimumSizeHint(self):
        return QtCore.QSize(self.inner.minimumSizeHint().width(), 0)


# ===========================================================================
# フレーム
# ===========================================================================
class CollapsibleFrame(QtWidgets.QWidget):
    STYLE_ARROW = "arrow"
    STYLE_BAR = "bar"
    STYLE_CARD = "card"
    STYLE_LINE = "line"

    toggled = QtCore.Signal(bool)            # 開いたら True(アニメーション開始時に発火)

    def __init__(self, title="", style="arrow", badge="", expanded=True, parent=None):
        super().__init__(parent)
        if style not in (self.STYLE_ARROW, self.STYLE_BAR, self.STYLE_CARD, self.STYLE_LINE):
            raise ValueError(f"unknown style: {style}")
        self._title = title
        self._badge = badge
        self._style = style
        self._expanded = bool(expanded)
        self._t = 1.0 if expanded else 0.0
        self._animate = True
        self._duration = 200

        self._header = _Header(self)
        self._inner = QtWidgets.QWidget()
        self._inner_lay = QtWidgets.QVBoxLayout(self._inner)
        self._inner_lay.setSpacing(4)
        self._clip = _Clip(self._inner, self)
        self._lay = QtWidgets.QVBoxLayout(self)
        self._lay.setSpacing(0)
        self._lay.addWidget(self._header)
        self._lay.addWidget(self._clip)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Maximum)

        self._anim = QtCore.QVariantAnimation(self)
        self._anim.setEasingCurve(QtCore.QEasingCurve.InOutCubic)
        self._anim.valueChanged.connect(self._on_anim)
        self._anim.finished.connect(self._on_finished)
        self._header.clicked.connect(self.toggle)

        self._apply_style()
        if not expanded:
            self._clip.hide()

    # ---- 公開API ----
    def style(self):
        return self._style

    def title(self):
        return self._title

    def setTitle(self, text):
        self._title = text
        self._header.updateGeometry()
        self._header.update()

    def setBadge(self, text):
        self._badge = text
        self._header.update()

    def contentLayout(self):
        return self._inner_lay

    def addWidget(self, w, *args, **kw):
        self._inner_lay.addWidget(w, *args, **kw)

    def addLayout(self, lay, *args, **kw):
        self._inner_lay.addLayout(lay, *args, **kw)

    def isExpanded(self):
        return self._expanded

    def setAnimationEnabled(self, on):
        self._animate = bool(on)

    def setDuration(self, ms):
        self._duration = max(0, int(ms))

    def toggle(self):
        self.setExpanded(not self._expanded)

    def setExpanded(self, expanded, animated=True):
        expanded = bool(expanded)
        if expanded == self._expanded:
            return
        self._expanded = expanded
        end = 1.0 if expanded else 0.0
        if not (animated and self._animate and self._duration > 0 and self.isVisible()):
            self._anim.stop()
            self._t = end
            self._release()
            self._clip.setVisible(expanded)
            self._header.update()
            self.updateGeometry()
        else:
            self._anim.stop()
            self._clip.show()
            self._anim.setStartValue(self._t)
            self._anim.setEndValue(end)
            self._anim.setDuration(max(40, round(self._duration * abs(end - self._t))))
            self._anim.start()
        self.toggled.emit(expanded)

    # ---- 内部 ----
    def _apply_style(self):
        em = self.fontMetrics().height()
        s = self._style
        if s == self.STYLE_ARROW:
            self._lay.setContentsMargins(0, 0, 0, 0)
            self._inner_lay.setContentsMargins(round(em * 1.6), round(em * 0.4), round(em * 0.4), round(em * 0.6))
        elif s == self.STYLE_BAR:
            self._lay.setContentsMargins(0, 0, 0, 0)
            self._inner_lay.setContentsMargins(round(em * 0.8), round(em * 0.6), round(em * 0.8), round(em * 0.7))
        elif s == self.STYLE_CARD:
            self._lay.setContentsMargins(1, 1, 1, 1)
            self._inner_lay.setContentsMargins(round(em * 0.9), round(em * 0.2), round(em * 0.9), round(em * 0.8))
        else:
            self._lay.setContentsMargins(0, 0, 0, 0)
            self._inner_lay.setContentsMargins(round(em * 0.2), round(em * 0.4), round(em * 0.2), round(em * 0.6))

    def _release(self):
        self._clip.setMinimumHeight(0)
        self._clip.setMaximumHeight(QWIDGETSIZE_MAX)

    def _on_anim(self, v):
        self._t = float(v)
        full = self._clip.inner_height(self._clip.width())
        self._clip.setFixedHeight(max(0, round(full * self._t)))
        self._header.update()
        self.update()

    def _on_finished(self):
        self._t = 1.0 if self._expanded else 0.0
        self._release()
        self._clip.setVisible(self._expanded)
        self._header.update()
        self.updateGeometry()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect())
        if self._style == self.STYLE_CARD:
            rr = _em(self, 0.35)
            rect = r.adjusted(0.5, 0.5, -0.5, -0.5)
            p.setPen(QtGui.QPen(C_CARD_BORDER, 1))
            p.setBrush(C_CARD)
            p.drawRoundedRect(rect, rr, rr)
        elif self._style == self.STYLE_BAR:
            body = QtCore.QRectF(0, self._header.height(), r.width(), max(0.0, r.height() - self._header.height()))
            p.fillRect(body, C_BAR_BODY)


# ===========================================================================
# 縦に積むカラム
# ===========================================================================
class CollapsibleColumn(QtWidgets.QScrollArea):
    """フレームを縦に積むスクロールエリア。閉じると下のフレームが詰まる(末尾のストレッチで上詰め)。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setStyleSheet("QScrollArea { background: transparent; border: none; }"
                           "QScrollArea > QWidget > QWidget { background: transparent; }")
        self._frames = []
        self._exclusive = False
        self._body = QtWidgets.QWidget()
        self._lay = QtWidgets.QVBoxLayout(self._body)
        m = 8
        self._lay.setContentsMargins(m, m, m, m)
        self._lay.setSpacing(6)
        self._lay.addStretch(1)
        self.setWidget(self._body)

    def addFrame(self, frame):
        return self.insertFrame(len(self._frames), frame)

    def insertFrame(self, index, frame):
        index = max(0, min(index, len(self._frames)))
        self._frames.insert(index, frame)
        self._lay.insertWidget(index, frame)
        frame.toggled.connect(lambda opened, f=frame: self._on_toggled(f, opened))
        return frame

    def frames(self):
        return list(self._frames)

    def setExclusive(self, on):
        self._exclusive = bool(on)
        if on:
            opened = [f for f in self._frames if f.isExpanded()]
            for f in opened[1:]:
                f.setExpanded(False)

    def expandAll(self):
        for f in self._frames:
            f.setExpanded(True)

    def collapseAll(self):
        for f in self._frames:
            f.setExpanded(False)

    def _on_toggled(self, frame, opened):
        if self._exclusive and opened:
            for f in self._frames:
                if f is not frame:
                    f.setExpanded(False)


# ===========================================================================
# デモ
# ===========================================================================
DEMO_OBJECT_NAME = "collapsibleFramesDemoWindow"

LOREM = ("折りたたみフレームの中身は、閉じるときに縮むのではなく下から隠れていきます。"
         "ラベルが折り返す内容でも、開閉中にレイアウトが崩れません。")


def _maya_main_window():
    """Mayaが無い環境では None を返す(単体実行できるように)。"""
    try:
        from maya import OpenMayaUI as omui
        from shiboken6 import wrapInstance
    except ImportError:
        return None
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


def _grid_rows(names):
    w = QtWidgets.QWidget()
    g = QtWidgets.QGridLayout(w)
    g.setContentsMargins(0, 0, 0, 0)
    g.setHorizontalSpacing(8)
    g.setVerticalSpacing(4)
    for r, n in enumerate(names):
        g.addWidget(QtWidgets.QLabel(n), r, 0)
        sp = QtWidgets.QDoubleSpinBox()
        sp.setRange(-9999, 9999)
        g.addWidget(sp, r, 1)
    g.setColumnStretch(1, 1)
    return w


def _wrap_label(text):
    lb = QtWidgets.QLabel(text)
    lb.setWordWrap(True)
    return lb


class DemoWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Window)
        self.setObjectName(DEMO_OBJECT_NAME)
        self.setWindowTitle("collapsible_frames demo")
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#3c3c3c"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#dddddd"))
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#2b2b2b"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#dddddd"))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#505050"))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#dddddd"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        self.column = CollapsibleColumn()
        specs = [
            ("Transform", CollapsibleFrame.STYLE_ARROW, ""),
            ("Display", CollapsibleFrame.STYLE_BAR, "3"),
            ("Materials", CollapsibleFrame.STYLE_CARD, "12"),
            ("Notes", CollapsibleFrame.STYLE_LINE, ""),
            ("Extra Attributes", CollapsibleFrame.STYLE_BAR, ""),
        ]
        for title, style, badge in specs:
            f = CollapsibleFrame(title, style, badge, expanded=(title != "Extra Attributes"))
            if title == "Transform":
                f.addWidget(_grid_rows(["Translate X", "Translate Y", "Translate Z"]))
            elif title == "Display":
                for n in ("Visibility", "Template", "Show Bounding Box"):
                    f.addWidget(QtWidgets.QCheckBox(n))
            elif title == "Materials":
                f.addWidget(_wrap_label(LOREM))
                for n in ("lambert1", "blinn2", "standardSurface3"):
                    f.addWidget(QtWidgets.QPushButton(n))
            elif title == "Notes":
                f.addWidget(_wrap_label(LOREM + LOREM))
            else:
                f.addWidget(_grid_rows(["Custom A", "Custom B"]))
            self.column.addFrame(f)

        self.btn_open = QtWidgets.QPushButton("すべて展開")
        self.btn_close = QtWidgets.QPushButton("すべて折りたたむ")
        self.chk_acc = QtWidgets.QCheckBox("アコーディオン")
        self.chk_anim = QtWidgets.QCheckBox("アニメーション")
        self.chk_anim.setChecked(True)
        self.btn_open.clicked.connect(self.column.expandAll)
        self.btn_close.clicked.connect(self.column.collapseAll)
        self.chk_acc.toggled.connect(self.column.setExclusive)
        self.chk_anim.toggled.connect(lambda on: [f.setAnimationEnabled(on) for f in self.column.frames()])

        bar = QtWidgets.QHBoxLayout()
        bar.setContentsMargins(8, 8, 8, 0)
        for w in (self.btn_open, self.btn_close, self.chk_acc, self.chk_anim):
            bar.addWidget(w)
        bar.addStretch(1)
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        lay.addLayout(bar)
        lay.addWidget(self.column, 1)
        self.resize(420, 640)


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