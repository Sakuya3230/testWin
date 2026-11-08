# -*- coding: utf-8 -*-

from ..qt import QtCore, QtWidgets, QtGui


"""
custom_labels.py
PySide6 (Maya 2027 対応) 描画ベースのカスタムラベル サンプル集

収録:
    1. SimpleLabel       : 基本形。色/配置/省略表示(elide)対応
    2. BadgeLabel        : 角丸のバッジ(ステータス表示向け)
    3. FancyTextLabel    : アウトライン / ドロップシャドウ / グラデーション文字
    4. IconTextLabel     : アイコン + テキスト
    5. HeaderLabel       : セクション見出し(テキスト + 右に伸びる罫線)

Maya外でも動作確認できるよう、maya への依存は show_demo() 内だけにしています。
    - 単体:  python custom_labels.py
    - Maya:  import custom_labels; custom_labels.show_demo()
"""

Qt = QtCore.Qt


# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------
def _em(widget, ratio):
    """フォント高さ基準の長さ(px)。UIスケール/DPIが変わっても比率が崩れない。"""
    return max(1, round(widget.fontMetrics().height() * ratio))


class _LabelBase(QtWidgets.QWidget):
    """テキスト系ラベルの共通基底。text / alignment / elide のプロパティを持つ。"""

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text
        self._align = Qt.AlignLeft | Qt.AlignVCenter
        self._elide = Qt.ElideRight
        # 横は伸縮可、縦は sizeHint 固定(QLabel と同じ挙動)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

    # --- text -------------------------------------------------------------
    def text(self):
        return self._text

    def setText(self, text):
        if text == self._text:
            return
        self._text = text
        self.updateGeometry()  # sizeHint が変わるので必須
        self.update()

    # --- alignment --------------------------------------------------------
    def alignment(self):
        return self._align

    def setAlignment(self, align):
        self._align = align
        self.update()

    # --- elide ------------------------------------------------------------
    def setElideMode(self, mode):
        self._elide = mode
        self.update()

    # --- 派生クラスで上書きする内容領域(余白を除いた矩形) -------------------
    def _content_rect(self):
        return self.rect()

    def _elided(self, width):
        return self.fontMetrics().elidedText(self._text, self._elide, int(width))

    # フォントや有効状態が変わったら再計算/再描画
    def changeEvent(self, e):
        if e.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.EnabledChange,
                        QtCore.QEvent.PaletteChange):
            self.updateGeometry()
            self.update()
        super().changeEvent(e)


# ---------------------------------------------------------------------------
# 1. SimpleLabel : 基本形
# ---------------------------------------------------------------------------
class SimpleLabel(_LabelBase):
    """最小構成のカスタムラベル。色指定が無ければ palette(WindowText) を使う。"""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._color = None  # None の場合は palette から取得

    def setColor(self, color):
        self._color = QtGui.QColor(color) if color is not None else None
        self.update()

    def _pad(self):
        return _em(self, 0.25)

    def sizeHint(self):
        fm = self.fontMetrics()
        pad = self._pad()
        return QtCore.QSize(fm.horizontalAdvance(self._text) + pad * 2,
                            fm.height() + pad * 2)

    def minimumSizeHint(self):
        # 省略表示するので、最小幅は「…」+αで十分
        fm = self.fontMetrics()
        pad = self._pad()
        return QtCore.QSize(fm.horizontalAdvance("...") + pad * 2, fm.height() + pad * 2)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        pad = self._pad()
        rect = self.rect().adjusted(pad, pad, -pad, -pad)

        if self._color is not None and self.isEnabled():
            color = self._color
        else:
            # 無効状態は palette が自動でグレーにしてくれる
            color = self.palette().color(QtGui.QPalette.WindowText)
        p.setPen(color)
        p.drawText(rect, int(self._align), self._elided(rect.width()))


# ---------------------------------------------------------------------------
# 2. BadgeLabel : 角丸バッジ
# ---------------------------------------------------------------------------
class BadgeLabel(_LabelBase):
    """ピル型(完全な角丸)の背景付きラベル。背景色から文字色を自動決定。"""

    def __init__(self, text="", color="#3b9b6e", parent=None):
        super().__init__(text, parent)
        self._bg = QtGui.QColor(color)
        self._align = Qt.AlignCenter
        # バッジは中身の幅に合わせる(横に伸ばさない)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def setBadgeColor(self, color):
        self._bg = QtGui.QColor(color)
        self.update()

    def sizeHint(self):
        fm = self.fontMetrics()
        h_pad = _em(self, 0.7)
        v_pad = _em(self, 0.2)
        return QtCore.QSize(fm.horizontalAdvance(self._text) + h_pad * 2,
                            fm.height() + v_pad * 2)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        bg = QtGui.QColor(self._bg)
        if not self.isEnabled():
            bg = QtGui.QColor(110, 110, 110)

        # 背景の明るさで文字色を切り替える(視認性確保)
        fg = QtGui.QColor("#ffffff") if bg.lightness() < 150 else QtGui.QColor("#202020")

        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = r.height() / 2
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, radius, radius)

        p.setPen(fg)
        p.drawText(r, int(Qt.AlignCenter), self._text)


# ---------------------------------------------------------------------------
# 3. FancyTextLabel : アウトライン / シャドウ / グラデーション
# ---------------------------------------------------------------------------
class FancyTextLabel(_LabelBase):
    """
    QPainterPath にテキストを変換して描くラベル。
    塗り(単色 or グラデーション) + アウトライン + ドロップシャドウを組み合わせ可能。
    ※ パス描画はヒンティングが効かないため、小さい文字には向きません。
       見出し・ロゴ・大きめの表示用に使うのがおすすめです。
    """

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self._fill_colors = [QtGui.QColor("#ffffff")]  # 2色以上ならグラデーション
        self._outline_color = None
        self._outline_width = 0.0
        self._shadow_color = None
        self._shadow_offset = QtCore.QPointF(2, 2)
        self._align = Qt.AlignHCenter | Qt.AlignVCenter

    # --- 設定 -------------------------------------------------------------
    def setFill(self, *colors):
        """setFill('#fff') で単色、setFill('#f80', '#f0a') で横グラデーション。"""
        self._fill_colors = [QtGui.QColor(c) for c in colors]
        self.update()

    def setOutline(self, color, width=2.0):
        self._outline_color = QtGui.QColor(color) if color else None
        self._outline_width = width
        self.updateGeometry()
        self.update()

    def setShadow(self, color, dx=2.0, dy=2.0):
        self._shadow_color = QtGui.QColor(color) if color else None
        self._shadow_offset = QtCore.QPointF(dx, dy)
        self.updateGeometry()
        self.update()

    # --- サイズ -----------------------------------------------------------
    def _margin(self):
        """アウトライン・シャドウがはみ出さない分の余白。"""
        m = self._outline_width
        if self._shadow_color is not None:
            m += max(abs(self._shadow_offset.x()), abs(self._shadow_offset.y()))
        return int(m) + _em(self, 0.15)

    def sizeHint(self):
        fm = self.fontMetrics()
        m = self._margin()
        return QtCore.QSize(fm.horizontalAdvance(self._text) + m * 2,
                            fm.height() + m * 2)

    def minimumSizeHint(self):
        fm = self.fontMetrics()
        m = self._margin()
        return QtCore.QSize(fm.horizontalAdvance("...") + m * 2, fm.height() + m * 2)

    # --- 描画 -------------------------------------------------------------
    def _build_path(self, rect):
        fm = self.fontMetrics()
        text = fm.elidedText(self._text, self._elide, int(rect.width()))
        w = fm.horizontalAdvance(text)

        if self._align & Qt.AlignRight:
            x = rect.right() - w
        elif self._align & Qt.AlignHCenter:
            x = rect.center().x() - w / 2
        else:
            x = rect.left()
        # 縦は中央揃え。addText は「ベースライン位置」を指定する点に注意
        y = rect.center().y() + (fm.ascent() - fm.descent()) / 2

        path = QtGui.QPainterPath()
        path.addText(QtCore.QPointF(x, y), self.font(), text)
        return path

    def paintEvent(self, e):
        m = self._margin()
        rect = QtCore.QRectF(self.rect()).adjusted(m, m, -m, -m)
        path = self._build_path(rect)
        if path.isEmpty():
            return

        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        # 1) シャドウ
        if self._shadow_color is not None:
            shadow = QtGui.QPainterPath(path)
            shadow.translate(self._shadow_offset)
            if self._outline_color is not None:
                p.setPen(QtGui.QPen(self._shadow_color, self._outline_width * 2,
                                    Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
                p.drawPath(shadow)
            p.fillPath(shadow, self._shadow_color)

        # 2) アウトライン(太さ2倍で描いて、あとで塗りを重ねる → 外側だけに出る)
        if self._outline_color is not None and self._outline_width > 0:
            pen = QtGui.QPen(self._outline_color, self._outline_width * 2,
                             Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.drawPath(path)

        # 3) 塗り
        colors = self._fill_colors
        if len(colors) >= 2:
            b = path.boundingRect()
            grad = QtGui.QLinearGradient(b.left(), 0, b.right(), 0)
            last = len(colors) - 1
            for i, c in enumerate(colors):
                grad.setColorAt(i / last, c)
            brush = QtGui.QBrush(grad)
        else:
            brush = QtGui.QBrush(colors[0])
        if not self.isEnabled():
            brush = QtGui.QBrush(self.palette().color(QtGui.QPalette.WindowText))
        p.fillPath(path, brush)


# ---------------------------------------------------------------------------
# 4. IconTextLabel : アイコン + テキスト
# ---------------------------------------------------------------------------
class IconTextLabel(_LabelBase):
    """左にアイコン、右にテキスト。アイコンサイズはフォント高さに追従。"""

    def __init__(self, text="", icon=None, parent=None):
        super().__init__(text, parent)
        self._icon = icon if icon is not None else QtGui.QIcon()

    def setIcon(self, icon):
        self._icon = icon
        self.updateGeometry()
        self.update()

    def _icon_size(self):
        return self.fontMetrics().height()  # フォントに追従 → UIスケールに強い

    def _spacing(self):
        return _em(self, 0.4)

    def _pad(self):
        return _em(self, 0.25)

    def sizeHint(self):
        fm = self.fontMetrics()
        pad = self._pad()
        w = fm.horizontalAdvance(self._text) + pad * 2
        if not self._icon.isNull():
            w += self._icon_size() + self._spacing()
        return QtCore.QSize(w, fm.height() + pad * 2)

    def minimumSizeHint(self):
        fm = self.fontMetrics()
        pad = self._pad()
        w = fm.horizontalAdvance("...") + pad * 2
        if not self._icon.isNull():
            w += self._icon_size() + self._spacing()
        return QtCore.QSize(w, fm.height() + pad * 2)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        pad = self._pad()
        rect = self.rect().adjusted(pad, pad, -pad, -pad)

        if not self._icon.isNull():
            s = self._icon_size()
            icon_rect = QtCore.QRect(rect.left(), rect.center().y() - s // 2 + 1, s, s)
            mode = QtGui.QIcon.Normal if self.isEnabled() else QtGui.QIcon.Disabled
            self._icon.paint(p, icon_rect, Qt.AlignCenter, mode)
            rect.setLeft(rect.left() + s + self._spacing())

        p.setPen(self.palette().color(QtGui.QPalette.WindowText))
        p.drawText(rect, int(self._align), self._elided(rect.width()))


# ---------------------------------------------------------------------------
# 5. HeaderLabel : セクション見出し
# ---------------------------------------------------------------------------
class HeaderLabel(_LabelBase):
    """左にアクセントバー、テキスト、残りの幅いっぱいに罫線。ツールUIの区切りに便利。"""

    def __init__(self, text="", accent="#e8913a", parent=None):
        super().__init__(text, parent)
        self._accent = QtGui.QColor(accent)

    def setAccent(self, color):
        self._accent = QtGui.QColor(color)
        self.update()

    def _bar_w(self):
        return max(2, _em(self, 0.2))

    def _gap(self):
        return _em(self, 0.5)

    def sizeHint(self):
        fm = self.fontMetrics()
        w = self._bar_w() + self._gap() + fm.horizontalAdvance(self._text) + self._gap() * 2
        return QtCore.QSize(w, fm.height() + _em(self, 0.5))

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        fm = self.fontMetrics()
        h = self.height()
        bar_w, gap = self._bar_w(), self._gap()

        # アクセントバー
        p.fillRect(QtCore.QRect(0, 2, bar_w, h - 4), self._accent)

        # テキスト(太字にしたい場合は font().setBold(True) を呼び出し側で)
        x = bar_w + gap
        text_w = fm.horizontalAdvance(self._text)
        text_rect = QtCore.QRect(x, 0, text_w, h)
        p.setPen(self.palette().color(QtGui.QPalette.WindowText))
        p.drawText(text_rect, int(Qt.AlignLeft | Qt.AlignVCenter), self._text)

        # 罫線(ピクセルを綺麗に出すため +0.5 は使わず整数座標で)
        line_x = text_rect.right() + gap
        if line_x < self.width():
            p.setPen(self.palette().color(QtGui.QPalette.Mid))
            y = h // 2
            p.drawLine(line_x, y, self.width() - 1, y)


# ---------------------------------------------------------------------------
# デモ
# ---------------------------------------------------------------------------
DEMO_OBJECT_NAME = "customLabelsDemo"


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
        self.setWindowTitle("Custom Labels Demo")
        self.setWindowFlags(Qt.Window)
        self.resize(420, 480)

        # Mayaっぽいダーク配色(Maya内では親のスタイルが効くので不要だが、単体確認用)
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(68, 68, 68))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(220, 220, 220))
        pal.setColor(QtGui.QPalette.Mid, QtGui.QColor(110, 110, 110))
        # setColor(role, color) は全グループに効くので、無効色は別途指定する
        pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText,
                     QtGui.QColor(120, 120, 120))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(10)

        # 1. SimpleLabel
        lay.addWidget(HeaderLabel("1. SimpleLabel"))
        simple = SimpleLabel("通常ラベル(パレット色)")
        colored = SimpleLabel("色指定ラベル")
        colored.setColor("#7fd1ff")
        elided = SimpleLabel("これはとても長いテキストで、幅が足りないと省略表示されます。ウィンドウ幅を変えて確認")
        disabled = SimpleLabel("無効状態のラベル")
        disabled.setEnabled(False)
        for w in (simple, colored, elided, disabled):
            lay.addWidget(w)

        # 2. BadgeLabel
        lay.addWidget(HeaderLabel("2. BadgeLabel", "#3b9b6e"))
        badges = QtWidgets.QHBoxLayout()
        for text, color in (("OK", "#3b9b6e"), ("WARNING", "#e0b030"),
                            ("ERROR", "#d9534f"), ("INFO", "#4a90d9")):
            badges.addWidget(BadgeLabel(text, color))
        badges.addStretch()
        lay.addLayout(badges)

        # 3. FancyTextLabel
        lay.addWidget(HeaderLabel("3. FancyTextLabel", "#d9534f"))
        f = QtGui.QFont(self.font())
        f.setPointSize(f.pointSize() + 8)
        f.setBold(True)

        outline = FancyTextLabel("Outline")
        outline.setFont(f)
        outline.setFill("#ffffff")
        outline.setOutline("#222222", 2.5)

        shadow = FancyTextLabel("Drop Shadow")
        shadow.setFont(f)
        shadow.setFill("#ffe08a")
        shadow.setShadow(QtGui.QColor(0, 0, 0, 160), 3, 3)

        gradient = FancyTextLabel("Gradient Text")
        gradient.setFont(f)
        gradient.setFill("#ff9a3c", "#ff3c8e", "#7a5cff")
        gradient.setOutline("#1a1a1a", 1.5)
        gradient.setShadow(QtGui.QColor(0, 0, 0, 120), 2, 2)

        for w in (outline, shadow, gradient):
            lay.addWidget(w)

        # 4. IconTextLabel
        lay.addWidget(HeaderLabel("4. IconTextLabel", "#4a90d9"))
        style = self.style()
        lay.addWidget(IconTextLabel("情報メッセージ",
                                    style.standardIcon(QtWidgets.QStyle.SP_MessageBoxInformation)))
        lay.addWidget(IconTextLabel("警告メッセージ",
                                    style.standardIcon(QtWidgets.QStyle.SP_MessageBoxWarning)))

        lay.addStretch()


def show_demo():
    """Maya内でもスタンドアロンでも使えるデモ表示。多重生成を防ぐ。"""
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    # 既存ウィンドウを閉じる(スクリプト再実行時の二重表示対策)
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