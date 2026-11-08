"""
wrap_labels.py
PySide6 (Maya 2027 対応) 折り返し(ワードラップ)対応のカスタムラベル

収録:
    1. WrapLabel : 折り返しラベル本体
                   - 日本語/英語混在で折り返し(禁則処理は Qt のテキストエンジンに任せる)
                   - 水平揃え(左/中央/右/両端)、縦揃え、行間
                   - 最大行数を指定して、超えたら末尾を「…」で省略
                   - height-for-width 対応 → レイアウトに入れると幅に応じて高さが伸縮
    2. NoteLabel : WrapLabel の派生。アクセントバー + 背景付きのコールアウト(info/warn/error)

【折り返しラベルの肝: height-for-width】
    折り返すと「幅が決まって初めて高さが決まる」ため、通常の sizeHint だけでは足りません。
    レイアウトに「幅 -> 高さ」を教えるため、次の3点をセットで実装しています。
        1) QSizePolicy.setHeightForWidth(True)
        2) hasHeightForWidth() / heightForWidth(w)
        3) 幅ごとのレイアウト結果をキャッシュ(heightForWidth は頻繁に呼ばれるため)

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python wrap_labels.py
    - Maya:  import wrap_labels; wrap_labels.show_demo()
"""
from PySide6 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt

_LINE_SEP = ""  # QTextLayout 上の「強制改行」文字("\n" はこれに置換して渡す)


def _em(widget, ratio):
    """フォント高さ基準の長さ(px)。UIスケール/DPIが変わっても比率が崩れない。"""
    return max(1, round(widget.fontMetrics().height() * ratio))


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


# ---------------------------------------------------------------------------
# 1. WrapLabel
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# 2. NoteLabel
# ---------------------------------------------------------------------------
class NoteLabel(WrapLabel):
    """左にアクセントバー、薄い背景つきの注記ボックス。説明文・警告表示向け。"""

    KINDS = {
        "info": "#4a90d9",
        "success": "#3b9b6e",
        "warning": "#e0b030",
        "error": "#d9534f",
    }

    def __init__(self, text="", kind="info", parent=None):
        super().__init__(text, parent)
        self._accent = QtGui.QColor(self.KINDS.get(kind, kind))

    def setKind(self, kind):
        self._accent = QtGui.QColor(self.KINDS.get(kind, kind))
        self.update()

    def _bar_w(self):
        return max(3, _em(self, 0.25))

    def _insets(self):
        pad = _em(self, 0.6)
        return self._bar_w() + pad, pad, pad, pad

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect())
        radius = _em(self, 0.3)

        bg = QtGui.QColor(self._accent)
        bg.setAlpha(40 if self.isEnabled() else 15)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, radius, radius)

        # 左端のバー(背景の角丸にクリップして、はみ出さないようにする)
        clip = QtGui.QPainterPath()
        clip.addRoundedRect(r, radius, radius)
        p.setClipPath(clip)
        p.fillRect(QtCore.QRectF(0, 0, self._bar_w(), r.height()),
                   self._accent if self.isEnabled() else QtGui.QColor(110, 110, 110))
        p.setClipping(False)

        l, t, rr, b = self._insets()
        self._paint_text(p, QtCore.QRect(l, t, self.width() - l - rr, self.height() - t - b))


# ---------------------------------------------------------------------------
# HfwWindow : 折り返しラベルを載せるトップレベルウィンドウ用の基底クラス
# ---------------------------------------------------------------------------
class HfwWindow(QtWidgets.QWidget):
    """
    【Qt の制約への対処】
    Qt はトップレベルウィンドウの「最小の高さ」を height-for-width から計算してくれません。
    そのまま使うと、ウィンドウを狭くした時に折り返しラベルが押し潰されて文字が切れます。
    このクラスは、幅が変わるたびに「その幅で必要な最小の高さ」をウィンドウに設定します。

    折り返しラベルを置く独自ウィンドウは、QWidget の代わりにこれを継承してください。
    (QScrollArea の中に置く場合は Qt 側が height-for-width を扱うので不要です。)
    """

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
        # テキスト変更などで中身の高さが変わった場合にも追従する
        if e.type() == QtCore.QEvent.LayoutRequest:
            self._fit_min_height()
        return ok


# ---------------------------------------------------------------------------
# デモ
# ---------------------------------------------------------------------------
DEMO_OBJECT_NAME = "wrapLabelsDemo"

JP_TEXT = ("Mayaのシーン内にあるすべてのジョイントを選択し、スキンウェイトを一括で書き出します。"
           "書き出し先のフォルダが存在しない場合は自動的に作成されます。（ファイル名には半角英数字のみ使用してください。）")
EN_TEXT = ("This tool exports every selected joint and its skin weights. "
           "Superlongunbreakablewordlike_joint_name_L_arm_01_twist_02_end_jnt will be broken anywhere if needed.")


def _maya_main_window():
    """Mayaが無い環境では None を返す(単体実行できるように)。"""
    try:
        from maya import OpenMayaUI as omui
        from shiboken6 import wrapInstance
    except ImportError:
        return None
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


class DemoWindow(HfwWindow):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(DEMO_OBJECT_NAME)
        self.setWindowTitle("Wrap Labels Demo  (ウィンドウ幅を変えて確認)")
        self.setWindowFlags(Qt.Window)
        self.resize(440, 640)

        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(68, 68, 68))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(220, 220, 220))
        pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText, QtGui.QColor(120, 120, 120))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(6)

        def header(text):
            lb = QtWidgets.QLabel(text)
            f = lb.font()
            f.setBold(True)
            lb.setFont(f)
            lb.setContentsMargins(0, 8, 0, 0)
            lay.addWidget(lb)

        header("WrapLabel: 日本語(禁則処理あり)")
        lay.addWidget(WrapLabel(JP_TEXT))

        header("WrapLabel: 英語 + 長い単語 / 中央揃え")
        w = WrapLabel(EN_TEXT)
        w.setAlignment(Qt.AlignHCenter | Qt.AlignTop)
        lay.addWidget(w)

        header("WrapLabel: 行間 1.6 / 右揃え / 色指定")
        w = WrapLabel("行間を広げた右揃えのラベルです。長い文章でも、幅に合わせて自動で折り返され、高さも追従します。")
        w.setLineSpacing(1.6)
        w.setAlignment(Qt.AlignRight | Qt.AlignTop)
        w.setColor("#7fd1ff")
        lay.addWidget(w)

        header("WrapLabel: 最大2行で省略")
        w = WrapLabel(JP_TEXT)
        w.setMaxLines(2)
        lay.addWidget(w)

        header("NoteLabel")
        lay.addWidget(NoteLabel("情報: 選択中のジョイントのみが対象になります。階層ごと対象にしたい場合は、"
                                "先にルートジョイントを選択してください。", "info"))
        lay.addWidget(NoteLabel("警告: 同名のファイルが既にある場合は上書きされます。", "warning"))
        lay.addWidget(NoteLabel("エラー: 書き出し先のフォルダに書き込み権限がありません。", "error"))
        dis = NoteLabel("無効状態のノートラベルです。", "success")
        dis.setEnabled(False)
        lay.addWidget(dis)

        lay.addStretch()


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