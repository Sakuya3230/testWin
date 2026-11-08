# -*- coding: utf-8 -*-

from ..qt import QtCore, QtWidgets, QtGui, Qt


class LabelBase(QtWidgets.QWidget):

    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text
        self._align = Qt.AlignLeft | Qt.AlignVCenter
        self._elide = Qt.ElideRight

        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

    def text(self):
        return self._text

    def setText(self, text):
        self._text = text
        self.updateGeometry()
        self.update()

    def alignment(self):
        return self._align

    def setAlignment(self, align):
        self._align = align
        self.update()

    def elideMode(self):
        return self._elide

    def setElideMode(self, mode):
        self._elide = mode
        self.update()

    def changeEvent(self, event):
        if event.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.EnabledChange,
                            QtCore.QEvent.PaletteChange):
            self.updateGeometry()
            self.update()
        super().changeEvent(event)

    def _content_rect(self):
        return self.rect()

    def _elided(self, width):
        return self.fontMetrics().elidedText(self._text, self._elide, int(width))

# ----------------------------------------------------------------------
# Test1
# ----------------------------------------------------------------------
class TitleLabel(LabelBase):

    def __init__(self, text="", size=12, color=None, parent=None):
        super().__init__(text, parent)
        self._size  = size
        self._color = QtGui.QColor(color) if color is not None else None

    def fontSize(self):
        return self._size

    def setFontSize(self, size):
        self._size = size
        self.updateGeometry()
        self.update()

    def color(self):
        return self._color

    def setColor(self, color):
        self._color = QtGui.QColor(color) if color is not None else None
        self.update()

    def _label_font(self):
        font = self.font()
        font.setFamily("Noto Sans JP")
        font.setWeight(QtGui.QFont.Weight.Black)
        font.setPointSizeF(max(1, self._size))
        return font

    def _label_metrics(self):
        return QtGui.QFontMetrics(self._label_font())

    def _padding(self, metrics):
        return max(1, round(metrics.height() * 0.25))

    def sizeHint(self):
        fm = self._label_metrics()
        pad = self._padding(fm)
        return QtCore.QSize(fm.horizontalAdvance(self._text) + pad * 2,
                            fm.height() + pad * 2)

    def minimumSizeHint(self):
        fm = self._label_metrics()
        pad = self._padding(fm)
        return QtCore.QSize(fm.horizontalAdvance("...") + pad * 2,
                            fm.height() + pad * 2)

    def paintEvent(self, event):
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.TextAntialiasing)

        font = self._label_font()
        fm = QtGui.QFontMetrics(font)
        pad = self._padding(fm)
        rect = self._content_rect().adjusted(pad, pad, -pad, -pad)

        if self._color is not None and self.isEnabled():
            color = self._color
        else:
            color = self.palette().color(QtGui.QPalette.WindowText)

        painter.setPen(color)
        painter.setFont(font)

        text = fm.elidedText(self._text, self._elide, int(rect.width()))
        painter.drawText(rect, int(self._align), text)


class _Layout:
    """1回分のレイアウト結果(特定の幅に対するもの)。"""
    __slots__ = ("layout", "lines", "tops", "shown", "elided_text", "height")
 
    def __init__(self):
        self.layout = None      # QTextLayout (lines が参照するので保持必須)
        self.lines = []         # QTextLine のリスト(全行)
        self.tops = []          # 各行の上端Y
        self.shown = 0          # 実際に表示する行数(最大行数で切った後)
        self.elided_text = None  # 最終行を省略表示する場合、その文字列
        self.height = 0.0


class WrapLabel(QtWidgets.QWidget):
    """折り返しラベル。QTextLayout で測定と描画を行う(両者で同じ結果を使うのでズレない)。"""
 
    WRAP_WORD = QtGui.QTextOption.WrapAtWordBoundaryOrAnywhere  # 単語優先、無理なら文字単位
    WRAP_ANYWHERE = QtGui.QTextOption.WrapAnywhere             # 常に文字単位
    WRAP_WORD_ONLY = QtGui.QTextOption.WordWrap                # 単語境界のみ(長い単語ははみ出す)
 
    def __init__(self, text="", parent=None):
        super().__init__(parent)
        self._text = text
        self._align = Qt.AlignLeft | Qt.AlignTop
        self._color = None          # None → palette(WindowText)
        self._line_spacing = 1.0    # 行間倍率
        self._max_lines = 0         # 0 = 無制限
        self._wrap_mode = self.WRAP_WORD
        self._preferred_em = 24.0   # sizeHint の幅の上限(フォント高さの何倍か)
        self._cache_key = None
        self._cache_val = None
 
        # ★ height-for-width を有効にする
        pol = QtWidgets.QSizePolicy(QtWidgets.QSizePolicy.Preferred,
                                    QtWidgets.QSizePolicy.Preferred)
        pol.setHeightForWidth(True)
        self.setSizePolicy(pol)
 
    # --- 公開API ----------------------------------------------------------
    def text(self):
        return self._text
 
    def setText(self, text):
        if text != self._text:
            self._text = text
            self._relayout()
 
    def setAlignment(self, align):
        """水平: AlignLeft/Center/Right/Justify、垂直: AlignTop/VCenter/Bottom。"""
        self._align = align
        self._relayout()
 
    def setColor(self, color):
        self._color = QtGui.QColor(color) if color is not None else None
        self.update()
 
    def setLineSpacing(self, ratio):
        """行間の倍率。1.0 = 標準、1.5 = 1.5倍。"""
        self._line_spacing = max(0.5, float(ratio))
        self._relayout()
 
    def setMaxLines(self, n):
        """表示する最大行数。超えた分は最終行の末尾を「…」で省略。0で無制限。"""
        self._max_lines = max(0, int(n))
        self._relayout()
 
    def setWrapMode(self, mode):
        self._wrap_mode = mode
        self._relayout()
 
    def setPreferredWidthEm(self, em):
        """余裕がある時にこの幅(フォント高さ×em)まで広げて表示する。"""
        self._preferred_em = float(em)
        self.updateGeometry()
 
    # --- 余白(派生クラスで上書き可能) ---------------------------------------
    def _insets(self):
        m = self.contentsMargins()
        return m.left(), m.top(), m.right(), m.bottom()
 
    # --- レイアウト(キャッシュ付き) ----------------------------------------
    def _relayout(self):
        self._cache_key = None
        self.updateGeometry()
        self.update()
 
    def _build(self, width):
        width = max(1, int(width))
        halign = self._align & Qt.AlignHorizontal_Mask
        key = (width, self._text, self.font().toString(), int(halign),
               self._line_spacing, self._max_lines, self._wrap_mode.value)
        if key == self._cache_key:
            return self._cache_val
 
        res = _Layout()
        text = self._text.replace("\r\n", "\n").replace("\n", _LINE_SEP)
        layout = QtGui.QTextLayout(text, self.font())
        opt = QtGui.QTextOption()
        opt.setWrapMode(self._wrap_mode)
        opt.setAlignment(halign)
        layout.setTextOption(opt)
 
        y = 0.0
        layout.beginLayout()
        while True:
            line = layout.createLine()
            if not line.isValid():
                break
            line.setLineWidth(width)
            line.setPosition(QtCore.QPointF(0, y))
            res.lines.append(line)
            res.tops.append(y)
            y += line.height() * self._line_spacing
        layout.endLayout()
        res.layout = layout
 
        n = len(res.lines)
        res.shown = n
        if self._max_lines and n > self._max_lines:
            res.shown = self._max_lines
            # 最終行以降の残り全部を1行にまとめて、右端を「…」で省略
            start = res.lines[res.shown - 1].textStart()
            rest = text[start:].replace(_LINE_SEP, " ")
            res.elided_text = self.fontMetrics().elidedText(rest, Qt.ElideRight, width)
 
        if res.shown:
            last = res.shown - 1
            res.height = res.tops[last] + res.lines[last].height()
        else:  # 空文字でも1行分の高さは確保
            res.height = self.fontMetrics().height()
 
        self._cache_key, self._cache_val = key, res
        return res
 
    # --- サイズ(height-for-width) -------------------------------------------
    def hasHeightForWidth(self):
        return True
 
    def heightForWidth(self, w):
        l, t, r, b = self._insets()
        return int(self._build(w - l - r).height + 0.999) + t + b
 
    def _natural_text_width(self):
        fm = self.fontMetrics()
        return max((fm.horizontalAdvance(s) for s in self._text.split("\n")), default=0)
 
    def sizeHint(self):
        l, t, r, b = self._insets()
        text_w = min(self._natural_text_width() + 1, round(self.fontMetrics().height() * self._preferred_em))
        w = max(1, text_w) + l + r
        return QtCore.QSize(w, self.heightForWidth(w))
 
    def minimumSizeHint(self):
        # 最小幅は数文字ぶん。高さは幅に依存するので heightForWidth に任せる
        l, t, r, b = self._insets()
        w = _em(self, 3.0) + l + r
        return QtCore.QSize(w, self.fontMetrics().height() + t + b)
 
    # --- イベント ---------------------------------------------------------------
    def changeEvent(self, e):
        if e.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.EnabledChange,
                        QtCore.QEvent.PaletteChange):
            self._relayout()
        super().changeEvent(e)
 
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        l, t, r, b = self._insets()
        self._paint_text(p, QtCore.QRect(l, t, self.width() - l - r, self.height() - t - b))
 
    def _paint_text(self, p, rect):
        """rect の中に折り返しテキストを描く(派生クラスから再利用できる)。"""
        res = self._build(rect.width())
        color = self._color if (self._color is not None and self.isEnabled()) \
            else self.palette().color(QtGui.QPalette.WindowText)
        p.setPen(color)
        p.setFont(self.font())
 
        # 縦揃え: 余白があれば上/中央/下に寄せる
        free = rect.height() - res.height
        if self._align & Qt.AlignVCenter:
            oy = rect.top() + max(0.0, free / 2)
        elif self._align & Qt.AlignBottom:
            oy = rect.top() + max(0.0, free)
        else:
            oy = rect.top()
        origin = QtCore.QPointF(rect.left(), oy)
 
        for i in range(res.shown):
            line = res.lines[i]
            if res.elided_text is not None and i == res.shown - 1:
                # 省略する最終行は自前で描く(ベースライン基準なので他の行と揃う)
                fm = self.fontMetrics()
                w = fm.horizontalAdvance(res.elided_text)
                if self._align & Qt.AlignRight:
                    x = rect.width() - w
                elif self._align & Qt.AlignHCenter:
                    x = (rect.width() - w) / 2
                else:
                    x = 0
                base = QtCore.QPointF(origin.x() + x, origin.y() + res.tops[i] + line.ascent())
                p.drawText(base, res.elided_text)
            else:
                line.draw(p, origin)