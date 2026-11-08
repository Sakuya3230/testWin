"""
remap_view.py
PySide6 (Maya 2027 対応) インフルエンス(ジョイント)リマップ用のビュー

    ファイル内のインフルエンス名  →  シーン内のジョイント を対応づける画面。
    自動対応(名前一致/名前空間/位置)の結果を確認し、未対応や推定の行を手で直して「適用」する。

構成:
    RemapRow / RemapModel / RemapFilterProxy
        : データ。1行 = 1インフルエンス。状態は ok / guess(推定) / unassigned(未対応) / zero(ウエイト0) / skip
          フィルタ「要確認」= ok 以外で skip でないもの / 「対応済み」= ok と skip
    RemapTableView
        : 表。行のクリックでチェック(Shift+クリックで範囲)、宛先欄のクリックで候補ポップアップ
    JointPickerPopup
        : 宛先の候補ポップアップ(検索・近い順の候補・Mayaで選択中のジョイント・スキップ)
    RemapPanel
        : 画面全体(ヘッダー/フィルタ/自動対応ルール/一括操作バー/表/フッター)

【Maya 連携は差し込み式】 ウィジェット自体は maya.cmds に依存せず、次のフックで繋ぎます。
    panel.setSceneJoints(["root_JNT", ...])             # シーンのジョイント一覧
    panel.setCandidateProvider(lambda src: [(joint, "距離 0.40・親子が近い"), ...])   # 近い順の候補
    panel.setSelectedJointProvider(lambda: cmds.ls(sl=True, type="joint")[:1] or [])    # Mayaで選択中
    panel.applied.connect(lambda mapping: ...)          # {ファイル側の名前: シーン側の名前}

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python remap_view.py
    - Maya:  import remap_view; remap_view.show_demo()
"""
import difflib
import json
from dataclasses import dataclass

from PySide6 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt


# ===========================================================================
# 共通ヘルパー / 配色(参考画像から実測)
# ===========================================================================
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


COLOR_PANEL = "#3a3a3a"
COLOR_ROW_A = "#3a3a3a"
COLOR_ROW_B = "#363636"
COLOR_ROW_CHECKED = "#2f4558"
COLOR_LINE = "#444444"
COLOR_HEADER_BG = "#303030"
COLOR_HEADER_TEXT = "#b8b8b8"
COLOR_FIELD_BG = "#2b2b2b"
COLOR_FIELD_BORDER = "#5a5a5a"
COLOR_ACCENT = "#5285a6"
COLOR_WARN = "#e0a15c"
COLOR_TEXT = "#e2e2e2"
COLOR_TEXT_DIM = "#9a9a9a"

# バッジ: kind -> (背景, 文字)
BADGE_COLORS = {
    "warn": ("#5c4428", "#f3d5b2"),
    "ok": ("#3d5c3a", "#c6efc2"),
    "info": ("#34495e", "#bcdcf7"),
    "muted": ("#4a4a4a", "#bdbdbd"),
    "error": ("#5c3b43", "#f6cbd3"),
}

# 状態コード -> (表示, バッジ種別)
STATUS_INFO = {
    "ok": ("OK", "ok"),
    "guess": ("推定", "info"),
    "unassigned": ("未対応", "warn"),
    "zero": ("ウエイト 0", "warn"),
    "skip": ("スキップ", "muted"),
}
REVIEW_STATUSES = ("guess", "unassigned", "zero")     # 「要確認」に入る状態


def mirror_name(name):
    """L_/R_ などの左右を入れ替えた名前を返す。左右の表記が無ければ None。"""
    for a, b in (("L_", "R_"), ("Left", "Right"), ("_L", "_R"), ("_l_", "_r_")):
        for x, y in ((a, b), (b, a)):
            if x in name:
                return name.replace(x, y, 1)
    return None


# ===========================================================================
# 1. データ
# ===========================================================================
@dataclass
class RemapRow:
    src: str                       # ファイル側のインフルエンス名
    verts: int                     # 影響頂点数
    dest: str = None               # シーン側のジョイント名(未割当は None)
    reason: tuple = None           # 対応づけの根拠 (表示, バッジ種別)  例: ("名前一致", "info")
    status: str = "unassigned"     # ok / guess / unassigned / zero / skip
    checked: bool = False


class RemapModel(QtCore.QAbstractTableModel):
    COL_CHECK, COL_SRC, COL_VERTS, COL_DEST, COL_STATUS = range(5)
    HEADERS = ["", "ファイルのインフルエンス", "影響頂点", "宛先（シーン）", "状態"]
    RowRole = Qt.UserRole + 1

    changed = QtCore.Signal()      # どの変更でも発行(件数・フッターの更新用)

    def __init__(self, rows=None, parent=None):
        super().__init__(parent)
        self._rows = list(rows or [])

    # --- 必須実装 ----------------------------------------------------------
    def rowCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QtCore.QModelIndex()):
        return 0 if parent.isValid() else len(self.HEADERS)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        row = self._rows[index.row()]
        if role == self.RowRole:
            return row
        if role == Qt.DisplayRole:
            return {self.COL_SRC: row.src, self.COL_VERTS: str(row.verts),
                    self.COL_DEST: row.dest or "", self.COL_STATUS: STATUS_INFO[row.status][0]}.get(index.column())
        if role == Qt.CheckStateRole and index.column() == self.COL_CHECK:
            return Qt.Checked if row.checked else Qt.Unchecked
        return None

    def flags(self, index):
        return Qt.ItemIsEnabled

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self.HEADERS[section]
            if role == Qt.TextAlignmentRole:
                align = Qt.AlignRight if section == self.COL_VERTS else Qt.AlignLeft
                return int(align | Qt.AlignVCenter)
        return None

    # --- 参照 ----------------------------------------------------------------
    def row(self, i):
        return self._rows[i]

    def rows(self):
        return list(self._rows)

    def counts(self):
        """(要確認, 対応済み, 全体)"""
        review = sum(r.status in REVIEW_STATUSES for r in self._rows)
        return review, len(self._rows) - review, len(self._rows)

    def checkedRows(self):
        return [i for i, r in enumerate(self._rows) if r.checked]

    def unresolved(self):
        """未対応(影響頂点を持つのに宛先が無い)の (件数, 頂点数)。"""
        rows = [r for r in self._rows if r.status == "unassigned"]
        return len(rows), sum(r.verts for r in rows)

    def mapping(self):
        """{ファイル側の名前: シーン側の名前}。未割当・スキップは含めない。"""
        return {r.src: r.dest for r in self._rows if r.dest and r.status != "skip"}

    # --- 更新 ----------------------------------------------------------------
    def _touch(self, i):
        self.dataChanged.emit(self.index(i, 0), self.index(i, self.columnCount() - 1))
        self.changed.emit()

    def setRows(self, rows):
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()
        self.changed.emit()

    def setChecked(self, i, on):
        if self._rows[i].checked != bool(on):
            self._rows[i].checked = bool(on)
            self._touch(i)

    def clearChecked(self):
        for i in self.checkedRows():
            self.setChecked(i, False)

    def setDest(self, i, dest, reason=("手動", "info"), status="ok"):
        r = self._rows[i]
        r.dest, r.reason, r.status = dest, reason, status
        self._touch(i)

    def setSkip(self, i):
        r = self._rows[i]
        r.dest, r.reason, r.status = None, None, "skip"
        self._touch(i)

    def loadMapping(self, mapping):
        """{src: dest} を適用する(保存済みの対応表の読み込み)。戻り値は適用した行数。"""
        n = 0
        for i, r in enumerate(self._rows):
            if r.src in mapping and mapping[r.src]:
                self.setDest(i, mapping[r.src], ("対応表", "info"), "ok")
                n += 1
        return n


class RemapFilterProxy(QtCore.QSortFilterProxyModel):
    """要確認/対応済み/すべて + 名前検索。"""

    MODE_REVIEW, MODE_DONE, MODE_ALL = range(3)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mode = self.MODE_ALL
        self._text = ""

    def setFilterMode(self, mode):
        self._mode = mode
        self.invalidateFilter()

    def setSearchText(self, text):
        self._text = text.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent):
        row = self.sourceModel().row(source_row)
        review = row.status in REVIEW_STATUSES
        if self._mode == self.MODE_REVIEW and not review:
            return False
        if self._mode == self.MODE_DONE and review:
            return False
        if self._text:
            return self._text in row.src.lower() or self._text in (row.dest or "").lower()
        return True


# ===========================================================================
# 2. 小さな部品
# ===========================================================================
class _Button(QtWidgets.QAbstractButton):
    """フラットなボタン。variant: normal / primary / flat。"""

    COLORS = {"normal": ("#5d5d5d", "#dddddd"), "primary": ("#4e7fa8", "#ffffff"),
              "bar": ("#4a5f73", "#e8eef4"), "flat": (None, "#cccccc")}

    def __init__(self, text="", variant="normal", parent=None):
        super().__init__(parent)
        self.setText(text)
        self._variant = variant
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def _bold_font(self):
        f = QtGui.QFont(self.font())
        f.setBold(self._variant == "primary")
        return f

    def sizeHint(self):
        fm = QtGui.QFontMetrics(self._bold_font())
        h = _em(self, 2.1)
        w = h if self.text() == "×" else fm.horizontalAdvance(self.text()) + _em(self, 2.0)
        return QtCore.QSize(w, h)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.5)
        bg, fg = self.COLORS[self._variant]
        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        hover, down = self.underMouse() and self.isEnabled(), self.isDown()
        if bg is None:
            if hover or down:
                p.setPen(Qt.NoPen)
                p.setBrush(QtGui.QColor(255, 255, 255, 30 if hover and not down else 55))
                p.drawRoundedRect(r, _em(self, 0.25), _em(self, 0.25))
        else:
            c = QtGui.QColor(bg)
            c = c.darker(115) if down else (c.lighter(118) if hover else c)
            p.setPen(Qt.NoPen)
            p.setBrush(c)
            p.drawRoundedRect(r, _em(self, 0.25), _em(self, 0.25))
        p.setFont(self._bold_font())
        p.setPen(QtGui.QColor(fg))
        pad = _em(self, 0.6)
        text = QtGui.QFontMetrics(self._bold_font()).elidedText(self.text(), Qt.ElideRight,
                                                               max(0, self.width() - pad * 2))
        p.drawText(self.rect(), int(Qt.AlignCenter), text)


class SearchBox(QtWidgets.QWidget):
    """虫眼鏡アイコン付きの検索欄(角丸の暗い入力欄)。"""

    textChanged = QtCore.Signal(str)

    def __init__(self, placeholder="", parent=None):
        super().__init__(parent)
        self.edit = QtWidgets.QLineEdit(self)
        self.edit.setPlaceholderText(placeholder)
        self.edit.setFrame(False)
        self.edit.setStyleSheet("QLineEdit { background: transparent; border: none; color: #dddddd; }")
        pal = self.edit.palette()
        pal.setColor(QtGui.QPalette.PlaceholderText, QtGui.QColor("#8a8a8a"))
        self.edit.setPalette(pal)
        self.edit.textChanged.connect(self.textChanged)
        self.edit.installEventFilter(self)
        self.setSizePolicy(QtWidgets.QSizePolicy.Preferred, QtWidgets.QSizePolicy.Fixed)

    def text(self):
        return self.edit.text()

    def setText(self, t):
        self.edit.setText(t)

    def setPlaceholderText(self, t):
        self.edit.setPlaceholderText(t)

    def sizeHint(self):
        return QtCore.QSize(_em(self, 14), _em(self, 2.1))

    def resizeEvent(self, e):
        left = _em(self, 2.1)
        self.edit.setGeometry(left, 1, max(0, self.width() - left - _em(self, 0.5)), self.height() - 2)

    def eventFilter(self, obj, e):
        if obj is self.edit and e.type() in (QtCore.QEvent.FocusIn, QtCore.QEvent.FocusOut):
            self.update()
        return super().eventFilter(obj, e)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = _em(self, 0.3)
        p.setBrush(QtGui.QColor(COLOR_FIELD_BG))
        p.setPen(QtGui.QPen(QtGui.QColor(COLOR_ACCENT if self.edit.hasFocus() else "#4a4a4a"), 1))
        p.drawRoundedRect(r, radius, radius)
        # 虫眼鏡
        s = _em(self, 0.95)
        cx, cy = _em(self, 1.05), self.height() / 2 - 1
        p.setBrush(Qt.NoBrush)
        p.setPen(QtGui.QPen(QtGui.QColor("#a8a8a8"), max(1.3, s * 0.11), Qt.SolidLine, Qt.RoundCap))
        p.drawEllipse(QtCore.QPointF(cx, cy), s * 0.33, s * 0.33)
        p.drawLine(QtCore.QPointF(cx + s * 0.25, cy + s * 0.25), QtCore.QPointF(cx + s * 0.5, cy + s * 0.5))


class FilterPills(QtWidgets.QWidget):
    """「要確認 5 / 対応済み 49 / すべて 54」のようなピル型の絞り込みタブ。"""

    currentChanged = QtCore.Signal(int)

    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self._items = []          # dict(text, count, kind)
        self._current = 0
        self._hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)
        for text, count, kind in (items or []):
            self.addItem(text, count, kind)

    def addItem(self, text, count=0, kind="muted"):
        self._items.append(dict(text=text, count=count, kind=kind))
        self.updateGeometry()
        self.update()

    def setCount(self, i, n):
        self._items[i]["count"] = n
        self.updateGeometry()
        self.update()

    def currentIndex(self):
        return self._current

    def setCurrentIndex(self, i):
        if 0 <= i < len(self._items) and i != self._current:
            self._current = i
            self.update()
            self.currentChanged.emit(i)

    def _bold(self):
        f = QtGui.QFont(self.font())
        f.setBold(True)
        return f

    def _badge_font(self):
        f = QtGui.QFont(self.font())
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() * 0.88)
        return f

    def _badge_w(self, it):
        return QtGui.QFontMetrics(self._badge_font()).horizontalAdvance(str(it["count"])) + _em(self, 0.9)

    def _pill_rect(self, i):
        fm = QtGui.QFontMetrics(self._bold())
        x = 1.0
        for k, it in enumerate(self._items):
            w = _em(self, 1.1) * 2 + fm.horizontalAdvance(it["text"]) + _em(self, 0.5) + self._badge_w(it)
            if k == i:
                return QtCore.QRectF(x, 1, w, self.height() - 2)
            x += w + _em(self, 0.5)
        return QtCore.QRectF()

    def sizeHint(self):
        if not self._items:
            return QtCore.QSize(10, _em(self, 2.4))
        last = len(self._items) - 1
        # 高さが未確定でも幅が取れるよう、一時的に高さを仮定して計算
        fm = QtGui.QFontMetrics(self._bold())
        w = 2.0 + sum(_em(self, 1.1) * 2 + fm.horizontalAdvance(it["text"]) + _em(self, 0.5) + self._badge_w(it)
                      for it in self._items) + _em(self, 0.5) * last
        return QtCore.QSize(int(w), _em(self, 2.4))

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        for i, it in enumerate(self._items):
            r = self._pill_rect(i)
            sel, hov = i == self._current, i == self._hover
            bg = QtGui.QColor("#454545" if sel else ("#444444" if hov else "#3f3f3f"))
            border = QtGui.QPen(QtGui.QColor("#ececec" if sel else "#5a5a5a"), 1.6 if sel else 1)
            p.setBrush(bg)
            p.setPen(border)
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), r.height() / 2, r.height() / 2)

            font = self._bold() if sel else self.font()
            fm = QtGui.QFontMetrics(self._bold())
            p.setFont(font)
            p.setPen(QtGui.QColor("#ffffff" if sel else "#d0d0d0"))
            tx = r.left() + _em(self, 1.1)
            p.drawText(QtCore.QRectF(tx, r.top(), fm.horizontalAdvance(it["text"]) + 1, r.height()),
                       int(Qt.AlignLeft | Qt.AlignVCenter), it["text"])

            bw = self._badge_w(it)
            bf = self._badge_font()
            bh = QtGui.QFontMetrics(bf).height() + _em(self, 0.15)
            br = QtCore.QRectF(tx + fm.horizontalAdvance(it["text"]) + _em(self, 0.5),
                               r.center().y() - bh / 2, bw, bh)
            bgc, fgc = ("#5c4428", "#f3d5b2") if it["kind"] == "warn" else ("#2c2c2c", "#c8c8c8")
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor(bgc))
            p.drawRoundedRect(br, bh / 2, bh / 2)
            p.setFont(bf)
            p.setPen(QtGui.QColor(fgc))
            p.drawText(br, int(Qt.AlignCenter), str(it["count"]))

    def _index_at(self, pos):
        for i in range(len(self._items)):
            if self._pill_rect(i).contains(pos):
                return i
        return -1

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position())
        if i != self._hover:
            self._hover = i
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mouseReleaseEvent(self, e):
        i = self._index_at(e.position())
        if e.button() == Qt.LeftButton and i >= 0:
            self.setCurrentIndex(i)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Left:
            self.setCurrentIndex(self._current - 1)
        elif e.key() == Qt.Key_Right:
            self.setCurrentIndex(self._current + 1)
        else:
            super().keyPressEvent(e)


class _RulesHeader(QtWidgets.QAbstractButton):
    """「▸ 自動対応ルール  名前一致 › 名前空間を無視 › …」の折りたたみヘッダー。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self._summary = ""
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def setSummary(self, text):
        self._summary = text
        self.update()

    def sizeHint(self):
        return QtCore.QSize(_em(self, 20), _em(self, 2.4))

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect())
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor("#424242" if self.underMouse() else "#3e3e3e"))
        p.drawRoundedRect(r, _em(self, 0.3), _em(self, 0.3))

        # シェブロン(閉: ▸ / 開: ▾)
        cx, cy, s = _em(self, 1.1), r.center().y(), _em(self, 0.3)
        p.setPen(QtGui.QPen(QtGui.QColor("#c8c8c8"), 1.6, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if self.isChecked():
            p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(cx - s, cy - s * 0.5), QtCore.QPointF(cx, cy + s * 0.5),
                                            QtCore.QPointF(cx + s, cy - s * 0.5)]))
        else:
            p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(cx - s * 0.5, cy - s), QtCore.QPointF(cx + s * 0.5, cy),
                                            QtCore.QPointF(cx - s * 0.5, cy + s)]))
        bold = QtGui.QFont(self.font())
        bold.setBold(True)
        fm = QtGui.QFontMetrics(bold)
        x = _em(self, 2.1)
        p.setFont(bold)
        p.setPen(QtGui.QColor("#e8e8e8"))
        title = "自動対応ルール"
        p.drawText(QtCore.QRectF(x, 0, fm.horizontalAdvance(title) + 1, r.height()),
                   int(Qt.AlignLeft | Qt.AlignVCenter), title)
        x += fm.horizontalAdvance(title) + _em(self, 0.7)
        p.setFont(self.font())
        p.setPen(QtGui.QColor("#a8a8a8"))
        text = self.fontMetrics().elidedText(self._summary, Qt.ElideRight, int(r.width() - x - _em(self, 0.6)))
        p.drawText(QtCore.QRectF(x, 0, r.width() - x, r.height()), int(Qt.AlignLeft | Qt.AlignVCenter), text)


class RulesBar(QtWidgets.QWidget):
    """自動対応ルールの折りたたみ。閉じている時は有効なルールの要約を表示、開くとON/OFFできる。"""

    rulesChanged = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rules = []        # [key, label, enabled]
        self._checks = []
        lay = QtWidgets.QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        self._head = _RulesHeader()
        lay.addWidget(self._head)
        self._body = QtWidgets.QWidget()
        self._body_lay = QtWidgets.QHBoxLayout(self._body)
        self._body_lay.setContentsMargins(_em(self, 1.0), 2, 0, 2)
        self._body_lay.setSpacing(_em(self, 1.2))
        self._body.setVisible(False)
        lay.addWidget(self._body)
        self._head.toggled.connect(self._body.setVisible)

    def setRules(self, rules):
        """rules: [(key, 表示名, 有効か), ...]  表示順 = 適用順。"""
        self._rules = [list(r) for r in rules]
        for c in self._checks:
            c.setParent(None)
        self._checks = []
        for i, (key, label, on) in enumerate(self._rules):
            cb = QtWidgets.QCheckBox(label)
            cb.setChecked(on)
            cb.toggled.connect(lambda v, i=i: self._toggle(i, v))
            self._body_lay.addWidget(cb)
            self._checks.append(cb)
        self._body_lay.addStretch()
        self._refresh()

    def rules(self):
        return [tuple(r) for r in self._rules]

    def enabledKeys(self):
        return [r[0] for r in self._rules if r[2]]

    def _toggle(self, i, v):
        self._rules[i][2] = bool(v)
        self._refresh()
        self.rulesChanged.emit()

    def _refresh(self):
        self._head.setSummary(" › ".join(r[1] for r in self._rules if r[2]) or "(すべて無効)")


class BulkBar(QtWidgets.QWidget):
    """チェックした行が1つ以上ある時に出る一括操作バー。"""

    assignRequested = QtCore.Signal()
    mirrorRequested = QtCore.Signal()
    skipRequested = QtCore.Signal()
    clearRequested = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._n = 0
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(_em(self, 0.9), _em(self, 0.5), _em(self, 0.6), _em(self, 0.5))
        lay.setSpacing(_em(self, 0.5))
        self._label = QtWidgets.QLabel()
        f = self._label.font()
        f.setBold(True)
        self._label.setFont(f)
        lay.addWidget(self._label)
        lay.addStretch()
        self.btn_assign = _Button("宛先を一括指定…", "primary")
        self.btn_mirror = _Button("左右を入れ替え", "bar")
        self.btn_skip = _Button("スキップ", "bar")
        self.btn_clear = _Button("×", "flat")
        for b in (self.btn_assign, self.btn_mirror, self.btn_skip, self.btn_clear):
            lay.addWidget(b)
        self.btn_assign.clicked.connect(self.assignRequested)
        self.btn_mirror.clicked.connect(self.mirrorRequested)
        self.btn_skip.clicked.connect(self.skipRequested)
        self.btn_clear.clicked.connect(self.clearRequested)
        self.setCount(0)

    def setCount(self, n):
        self._n = n
        self._label.setText(f"{n} 件を選択中")
        self.setVisible(n > 0)

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor("#2f4558"))
        p.drawRoundedRect(QtCore.QRectF(self.rect()), _em(self, 0.35), _em(self, 0.35))


# ===========================================================================
# 3. 表(ヘッダー / デリゲート / ビュー)
# ===========================================================================
class FlatHeader(QtWidgets.QHeaderView):
    def __init__(self, orientation=Qt.Horizontal, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(False)
        self.setHighlightSections(False)
        self.setSectionsMovable(False)
        self.setStretchLastSection(False)

    def sizeHint(self):
        s = super().sizeHint()
        s.setHeight(_em(self, 2.0))
        return s

    def paintSection(self, p, rect, logicalIndex):
        p.save()
        p.fillRect(rect, QtGui.QColor(COLOR_HEADER_BG))
        model = self.model()
        text = model.headerData(logicalIndex, self.orientation(), Qt.DisplayRole) or ""
        align = model.headerData(logicalIndex, self.orientation(), Qt.TextAlignmentRole)
        align = int(align) if align is not None else int(Qt.AlignLeft | Qt.AlignVCenter)
        pad = _em(self, 0.8)
        p.setFont(self.font())
        p.setPen(QtGui.QColor(COLOR_HEADER_TEXT))
        r = rect.adjusted(pad, 0, -pad, 0)
        p.drawText(r, align, self.fontMetrics().elidedText(text, Qt.ElideRight, r.width()))
        p.restore()


def draw_check_box(p, rect, checked, hover=False):
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    bw = max(1.5, rect.width() * 0.08)
    if checked:
        fill = QtGui.QColor("#2086ff" if hover else "#0075ff")
        border = fill
    else:
        fill = QtGui.QColor("#ffffff")
        border = QtGui.QColor("#b4b4b4" if hover else "#767676")
    p.setBrush(fill)
    p.setPen(QtGui.QPen(border, bw))
    h = bw / 2
    p.drawRoundedRect(rect.adjusted(h, h, -h, -h), rect.width() * 0.16, rect.width() * 0.16)
    if checked:
        w, l, t = rect.width(), rect.left(), rect.top()
        p.setBrush(Qt.NoBrush)
        p.setPen(QtGui.QPen(QtGui.QColor("#ffffff"), max(1.6, w * 0.13), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(l + w * 0.24, t + w * 0.53),
                                        QtCore.QPointF(l + w * 0.43, t + w * 0.72),
                                        QtCore.QPointF(l + w * 0.77, t + w * 0.30)]))


def draw_badge(p, widget, rect, text, kind, bold=True, scale=0.88):
    """rect の左端から、垂直中央にピル型バッジを描き、描いた幅を返す。"""
    bg, fg = BADGE_COLORS.get(kind, BADGE_COLORS["muted"])
    font = QtGui.QFont(widget.font())
    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF() * scale)
    font.setBold(bold)
    fm = QtGui.QFontMetrics(font)
    w = fm.horizontalAdvance(text) + _em(widget, 1.0)
    h = fm.height() + _em(widget, 0.25)
    r = QtCore.QRectF(rect.left(), rect.center().y() - h / 2, w, h)
    p.setRenderHint(QtGui.QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QtGui.QColor(bg))
    p.drawRoundedRect(r, h / 2, h / 2)
    p.setFont(font)
    p.setPen(QtGui.QColor(fg))
    p.drawText(r, int(Qt.AlignCenter), text)
    return w


def _badge_width(widget, text, bold=True, scale=0.88):
    font = QtGui.QFont(widget.font())
    if font.pointSizeF() > 0:
        font.setPointSizeF(font.pointSizeF() * scale)
    font.setBold(bold)
    return QtGui.QFontMetrics(font).horizontalAdvance(text) + _em(widget, 1.0)


class RemapDelegate(QtWidgets.QStyledItemDelegate):
    """全列の描画を担当(クリック処理はビュー側)。"""

    def paint(self, p, option, index):
        view = option.widget
        row = index.data(RemapModel.RowRole)
        p.save()
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        # --- 行の背景 ---
        base = QtGui.QColor(COLOR_ROW_A if index.row() % 2 == 0 else COLOR_ROW_B)
        if row.checked:
            base = QtGui.QColor(COLOR_ROW_CHECKED)
        if view.hoverRow() == index.row():
            base = base.lighter(110)
        p.fillRect(option.rect, base)
        p.setPen(QtGui.QColor(COLOR_LINE))
        p.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())

        col = index.column()
        pad = _em(view, 0.8)
        if col == RemapModel.COL_CHECK:
            s = _em(view, 1.3)
            r = QtCore.QRectF(0, 0, s, s)
            r.moveCenter(QtCore.QRectF(option.rect).center())
            hover = view.hoverCell() == (index.row(), col)
            draw_check_box(p, r, row.checked, hover)

        elif col == RemapModel.COL_SRC:
            p.setFont(option.font)
            p.setPen(QtGui.QColor(COLOR_TEXT))
            r = option.rect.adjusted(pad, 0, -pad, -1)
            p.drawText(r, int(Qt.AlignLeft | Qt.AlignVCenter),
                       option.fontMetrics.elidedText(row.src, Qt.ElideRight, r.width()))

        elif col == RemapModel.COL_VERTS:
            self._paint_verts(p, option, row, view)

        elif col == RemapModel.COL_DEST:
            self._paint_dest(p, option, index, row, view)

        elif col == RemapModel.COL_STATUS:
            text, kind = STATUS_INFO[row.status]
            r = QtCore.QRectF(option.rect.left() + _em(view, 0.4), option.rect.top(), 0, option.rect.height() - 1)
            draw_badge(p, view, r, text, kind)
        p.restore()

    def _paint_verts(self, p, option, row, view):
        # 「32 →」: 数字(右揃え)+ 矢印
        arrow_w = _em(view, 1.5)
        right = option.rect.right() - _em(view, 0.3)
        # 矢印
        cy = option.rect.center().y()
        ax1, ax0 = right - _em(view, 0.2), right - _em(view, 1.0)
        s = _em(view, 0.25)
        p.setPen(QtGui.QPen(QtGui.QColor("#a8a8a8"), 1.3, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawLine(QtCore.QPointF(ax0, cy), QtCore.QPointF(ax1, cy))
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(ax1 - s, cy - s), QtCore.QPointF(ax1, cy),
                                        QtCore.QPointF(ax1 - s, cy + s)]))
        # 数字
        font = QtGui.QFont(option.font)
        font.setBold(row.verts > 0)
        p.setFont(font)
        p.setPen(QtGui.QColor("#ffffff" if row.verts > 0 else COLOR_TEXT_DIM))
        r = QtCore.QRectF(option.rect.left(), option.rect.top(), right - arrow_w - option.rect.left(),
                          option.rect.height() - 1)
        p.drawText(r, int(Qt.AlignRight | Qt.AlignVCenter), str(row.verts))

    def _paint_dest(self, p, option, index, row, view):
        m = _em(view, 0.25)
        r = QtCore.QRectF(option.rect.adjusted(m, 4, -m, -5))
        radius = _em(view, 0.3)
        hover = view.hoverCell() == (index.row(), RemapModel.COL_DEST)
        is_open = view.openSourceRow() == view.model().mapToSource(index).row()
        needs = row.dest is None and row.status in ("unassigned", "zero")

        if is_open:
            border = QtGui.QColor(COLOR_ACCENT)
        elif needs:
            border = QtGui.QColor(COLOR_WARN)
        else:
            border = _lerp_color(QtGui.QColor(COLOR_FIELD_BORDER), QtGui.QColor("#8c8c8c"), 1.0 if hover else 0.0)
        p.setBrush(QtGui.QColor(COLOR_FIELD_BG))
        p.setPen(QtGui.QPen(border, 1.2 if (needs or is_open) else 1))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)

        pad = _em(view, 0.6)
        chev_w = _em(view, 1.2)
        right = r.right() - chev_w

        # シェブロン ⌄
        cx, cy, s = r.right() - _em(view, 0.85), r.center().y() + 0.5, _em(view, 0.22)
        p.setBrush(Qt.NoBrush)
        p.setPen(QtGui.QPen(QtGui.QColor("#c0c0c0"), 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        p.drawPolyline(QtGui.QPolygonF([QtCore.QPointF(cx - s, cy - s * 0.5), QtCore.QPointF(cx, cy + s * 0.5),
                                        QtCore.QPointF(cx + s, cy - s * 0.5)]))

        # 根拠バッジ(右寄せ)
        badge = None
        if row.dest and row.reason:
            badge = row.reason
        elif needs:
            badge = ("未割当", "warn")
        if badge:
            bw = _badge_width(view, badge[0])
            draw_badge(p, view, QtCore.QRectF(right - bw - _em(view, 0.2), r.top(), bw, r.height()),
                       badge[0], badge[1], bold=False)
            right -= bw + _em(view, 0.5)

        # 宛先名
        if row.dest:
            text, color = row.dest, QtGui.QColor(COLOR_TEXT)
        elif row.status == "skip":
            text, color = "スキップ", QtGui.QColor(COLOR_TEXT_DIM)
        else:
            text, color = "未割当 — クリックして選択", QtGui.QColor("#f3dcc0")
        p.setFont(option.font)
        p.setPen(color)
        tr = QtCore.QRectF(r.left() + pad, r.top(), max(0.0, right - r.left() - pad), r.height())
        p.drawText(tr, int(Qt.AlignLeft | Qt.AlignVCenter),
                   option.fontMetrics.elidedText(text, Qt.ElideRight, int(tr.width())))


class RemapTableView(QtWidgets.QTableView):
    """リマップ表。チェック(行クリック/Shift範囲/Space)と宛先欄クリックを扱う。"""

    destRequested = QtCore.Signal(QtCore.QModelIndex)   # 宛先欄がクリックされた(プロキシのindex)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover = (-1, -1)
        self._press = None
        self._last_toggled = -1      # Shift範囲選択の起点(プロキシの行)
        self._open_src_row = -1

        self.setHorizontalHeader(FlatHeader(Qt.Horizontal, self))
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor(COLOR_PANEL))
        self.setPalette(pal)
        self.setItemDelegate(RemapDelegate(self))
        self._apply_metrics()

    # --- 状態(デリゲートが参照) -------------------------------------------------
    def hoverRow(self):
        return self._hover[0]

    def hoverCell(self):
        return self._hover

    def openSourceRow(self):
        return self._open_src_row

    def setOpenSourceRow(self, row):
        self._open_src_row = row
        self.viewport().update()

    def _apply_metrics(self):
        self.verticalHeader().setDefaultSectionSize(_em(self, 2.5))

    def setupColumns(self):
        hdr = self.horizontalHeader()
        M = RemapModel
        for col, em in ((M.COL_CHECK, 2.6), (M.COL_VERTS, 5.6), (M.COL_DEST, 16.0), (M.COL_STATUS, 6.2)):
            hdr.setSectionResizeMode(col, QtWidgets.QHeaderView.Fixed)
            hdr.resizeSection(col, _em(self, em))
        hdr.setSectionResizeMode(M.COL_SRC, QtWidgets.QHeaderView.Stretch)

    def cellGlobalRect(self, index):
        r = self.visualRect(index)
        return QtCore.QRect(self.viewport().mapToGlobal(r.topLeft()), r.size())

    # --- チェックの操作 ----------------------------------------------------------
    def _toggle_row(self, proxy_row, shift=False):
        proxy = self.model()
        src = proxy.sourceModel()
        cur = src.row(proxy.mapToSource(proxy.index(proxy_row, 0)).row()).checked
        new = not cur
        if shift and self._last_toggled >= 0:
            lo, hi = sorted((self._last_toggled, proxy_row))
            rows = range(lo, hi + 1)
        else:
            rows = [proxy_row]
        for r in rows:
            src.setChecked(proxy.mapToSource(proxy.index(r, 0)).row(), new)
        self._last_toggled = proxy_row

    def toggleCurrentRow(self):
        i = self.currentIndex()
        if i.isValid():
            self._toggle_row(i.row())

    # --- イベント ------------------------------------------------------------------
    def mouseMoveEvent(self, e):
        i = self.indexAt(e.position().toPoint())
        h = (i.row(), i.column()) if i.isValid() else (-1, -1)
        if h != self._hover:
            self._hover = h
            self.viewport().update()
        self.setCursor(Qt.PointingHandCursor if i.isValid() else Qt.ArrowCursor)
        super().mouseMoveEvent(e)

    def viewportEvent(self, e):
        if e.type() == QtCore.QEvent.Leave:
            self._hover = (-1, -1)
            self.viewport().update()
        return super().viewportEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            i = self.indexAt(e.position().toPoint())
            self._press = (i.row(), i.column()) if i.isValid() else None
            if i.isValid():
                self.setCurrentIndex(i)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._press is not None:
            i = self.indexAt(e.position().toPoint())
            if i.isValid() and (i.row(), i.column()) == self._press:
                if i.column() == RemapModel.COL_DEST:
                    self.destRequested.emit(i)
                else:
                    self._toggle_row(i.row(), bool(e.modifiers() & Qt.ShiftModifier))
        self._press = None
        super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Space:
            self.toggleCurrentRow()
        elif e.key() in (Qt.Key_Return, Qt.Key_Enter):
            i = self.currentIndex()
            if i.isValid():
                self.destRequested.emit(self.model().index(i.row(), RemapModel.COL_DEST))
        else:
            super().keyPressEvent(e)

    def changeEvent(self, e):
        if e.type() == QtCore.QEvent.FontChange:
            self._apply_metrics()
        super().changeEvent(e)


# ===========================================================================
# 4. 候補ポップアップ
# ===========================================================================
class _CandidateList(QtWidgets.QWidget):
    """候補の行リスト(名前 + 右に補足)。ホバー/キー操作で強調、クリックで確定。"""

    activated = QtCore.Signal(int)

    MAX_ROWS = 8

    def __init__(self, parent=None):
        super().__init__(parent)
        self._items = []      # [(name, detail)]
        self._more = 0
        self._current = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)

    def setItems(self, items, more=0):
        self._items = list(items)
        self._more = more
        self._current = 0 if self._items else -1
        self.updateGeometry()
        self.update()

    def current(self):
        return self._current

    def move(self, delta):
        if self._items:
            self._current = (self._current + delta) % len(self._items)
            self.update()

    def _row_h(self):
        return _em(self, 2.3)

    def _gap(self):
        return _em(self, 0.2)

    def sizeHint(self):
        n = len(self._items) + (1 if self._more else 0)
        if n == 0:
            return QtCore.QSize(10, self._row_h())
        return QtCore.QSize(10, n * self._row_h() + (n - 1) * self._gap())

    def minimumSizeHint(self):
        return self.sizeHint()

    def _rect(self, i):
        return QtCore.QRectF(0, i * (self._row_h() + self._gap()), self.width(), self._row_h())

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        radius = _em(self, 0.3)
        pad = _em(self, 0.8)
        if not self._items:
            p.setPen(QtGui.QColor(COLOR_TEXT_DIM))
            p.drawText(QtCore.QRectF(0, 0, self.width(), self._row_h()), int(Qt.AlignCenter), "候補がありません")
            return
        for i, (name, detail) in enumerate(self._items):
            r = self._rect(i)
            p.setPen(Qt.NoPen)
            p.setBrush(QtGui.QColor("#2f4558" if i == self._current else "#2f2f2f"))
            p.drawRoundedRect(r, radius, radius)
            p.setFont(self.font())
            p.setPen(QtGui.QColor("#ffffff" if i == self._current else COLOR_TEXT))
            dw = self.fontMetrics().horizontalAdvance(detail) if detail else 0
            p.drawText(r.adjusted(pad, 0, -pad - dw - pad, 0), int(Qt.AlignLeft | Qt.AlignVCenter), name)
            if detail:
                small = QtGui.QFont(self.font())
                if small.pointSizeF() > 0:
                    small.setPointSizeF(small.pointSizeF() * 0.9)
                p.setFont(small)
                p.setPen(QtGui.QColor("#a8a8a8"))
                p.drawText(r.adjusted(0, 0, -pad, 0), int(Qt.AlignRight | Qt.AlignVCenter), detail)
        if self._more:
            r = self._rect(len(self._items))
            p.setFont(self.font())
            p.setPen(QtGui.QColor(COLOR_TEXT_DIM))
            p.drawText(r, int(Qt.AlignCenter), f"ほか {self._more} 件(絞り込んでください)")

    def _index_at(self, pos):
        for i in range(len(self._items)):
            if self._rect(i).contains(pos):
                return i
        return -1

    def mouseMoveEvent(self, e):
        i = self._index_at(e.position())
        if i >= 0 and i != self._current:
            self._current = i
            self.update()

    def mouseReleaseEvent(self, e):
        i = self._index_at(e.position())
        if e.button() == Qt.LeftButton and i >= 0:
            self.activated.emit(i)


class JointPickerPopup(QtWidgets.QFrame):
    """宛先の候補ポップアップ。検索 / 近い順の候補 / Mayaで選択中のジョイント / スキップ。"""

    picked = QtCore.Signal(str, str)     # (ジョイント名, 補足)
    skipped = QtCore.Signal()
    dismissed = QtCore.Signal()

    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self._candidates = []
        self._scene = []
        self._selected = ""

        lay = QtWidgets.QVBoxLayout(self)
        m = _em(self, 0.8)
        lay.setContentsMargins(m, m, m, m)
        lay.setSpacing(_em(self, 0.5))

        self.search = SearchBox("")
        lay.addWidget(self.search)
        self.section = QtWidgets.QLabel("候補（近い順）")
        f = self.section.font()
        f.setBold(True)
        if f.pointSizeF() > 0:
            f.setPointSizeF(f.pointSizeF() * 0.9)
        self.section.setFont(f)
        pal = self.section.palette()
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#b0b0b0"))
        self.section.setPalette(pal)
        lay.addWidget(self.section)
        self.list = _CandidateList()
        lay.addWidget(self.list)

        foot = QtWidgets.QHBoxLayout()
        foot.setSpacing(_em(self, 0.5))
        self.btn_maya = _Button("Maya で選択中のジョイント", "bar")
        self.btn_maya.setSizePolicy(QtWidgets.QSizePolicy.Expanding, QtWidgets.QSizePolicy.Fixed)
        self.btn_skip = _Button("スキップ", "normal")
        foot.addWidget(self.btn_maya, 1)
        foot.addWidget(self.btn_skip)
        lay.addLayout(foot)

        self.search.textChanged.connect(self._refresh)
        self.search.edit.installEventFilter(self)
        self.list.activated.connect(self._on_activated)
        self.btn_maya.clicked.connect(self._on_maya)
        self.btn_skip.clicked.connect(self._on_skip)

    # --- 設定して表示 -------------------------------------------------------------
    def open(self, candidates, scene_joints, selected_joint, anchor_rect, right_limit=None, min_width=None):
        """
        candidates:   [(ジョイント名, 補足), ...]  近い順
        anchor_rect:  基準にするウィジェットのグローバル矩形(この下に出す。入らなければ上)
        right_limit:  ポップアップの右端をこのグローバルXに揃える(Noneなら anchor の左端から)
        """
        self._candidates = list(candidates)
        self._scene = list(scene_joints)
        self._selected = selected_joint or ""
        self.search.setPlaceholderText(f"シーンのジョイントを検索 ({len(self._scene)})")
        self.search.setText("")
        self.btn_maya.setText(f"Maya で選択中のジョイント（{self._selected}）" if self._selected
                              else "Maya で選択中のジョイント")
        self.btn_maya.setEnabled(bool(self._selected))
        self._refresh("")

        w = min_width or _em(self, 28)
        self.setFixedWidth(w)
        self.adjustSize()
        h = self.sizeHint().height()
        screen = QtGui.QGuiApplication.screenAt(anchor_rect.center()) or QtGui.QGuiApplication.primaryScreen()
        sg = screen.availableGeometry()
        x = (right_limit - w) if right_limit is not None else anchor_rect.left()
        x = max(sg.left(), min(x, sg.right() - w))
        y = anchor_rect.bottom() + 2
        if y + h > sg.bottom():
            y = max(sg.top(), anchor_rect.top() - h - 2)
        self.move(x, y)
        self.show()
        self.search.edit.setFocus()

    def _refresh(self, text):
        text = text.strip().lower()
        if text:
            hits = [j for j in self._scene if text in j.lower()]
            shown = hits[:_CandidateList.MAX_ROWS]
            self.section.setText(f"検索結果 ({len(hits)})")
            self.list.setItems([(j, "") for j in shown], more=max(0, len(hits) - len(shown)))
        else:
            self.section.setText("候補（近い順）")
            self.list.setItems(self._candidates[:_CandidateList.MAX_ROWS])
        self.adjustSize()

    # --- 確定 ------------------------------------------------------------------------
    def _on_activated(self, i):
        name, detail = self.list._items[i]
        self.picked.emit(name, detail)
        self.close()

    def _on_maya(self):
        if self._selected:
            self.picked.emit(self._selected, "Maya で選択")
            self.close()

    def _on_skip(self):
        self.skipped.emit()
        self.close()

    def eventFilter(self, obj, e):
        if obj is self.search.edit and e.type() == QtCore.QEvent.KeyPress:
            if e.key() == Qt.Key_Down:
                self.list.move(+1)
                return True
            if e.key() == Qt.Key_Up:
                self.list.move(-1)
                return True
            if e.key() in (Qt.Key_Return, Qt.Key_Enter):
                if self.list.current() >= 0:
                    self._on_activated(self.list.current())
                return True
        return super().eventFilter(obj, e)

    def hideEvent(self, e):
        super().hideEvent(e)
        self.dismissed.emit()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        p.setBrush(QtGui.QColor("#333333"))
        p.setPen(QtGui.QPen(QtGui.QColor(COLOR_ACCENT), 1.2))
        p.drawRoundedRect(QtCore.QRectF(self.rect()).adjusted(0.6, 0.6, -0.6, -0.6), _em(self, 0.45), _em(self, 0.45))


# ===========================================================================
# 5. RemapPanel(画面全体)
# ===========================================================================
class RemapPanel(QtWidgets.QWidget):
    applied = QtCore.Signal(dict)       # 「適用」: {ファイル側の名前: シーン側の名前}
    cancelled = QtCore.Signal()
    closeRequested = QtCore.Signal()
    mappingSaved = QtCore.Signal(str)
    mappingLoaded = QtCore.Signal(str)

    def __init__(self, title="インフルエンスのリマップ", subtitle="", parent=None):
        super().__init__(parent)
        self._scene_joints = []
        self._candidate_provider = self._default_candidates
        self._selected_provider = lambda: ""
        self._bulk_mode = False

        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(COLOR_PANEL))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#dddddd"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#dddddd"))
        pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#5d5d5d"))
        pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#dddddd"))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        # --- モデル ---
        self.model = RemapModel()
        self.proxy = RemapFilterProxy(self)
        self.proxy.setSourceModel(self.model)

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        body = QtWidgets.QVBoxLayout()
        body.setContentsMargins(12, 10, 12, 8)
        body.setSpacing(8)
        root.addLayout(body, 1)

        # --- ヘッダー ---
        head = QtWidgets.QHBoxLayout()
        head.setSpacing(8)
        icon = QtWidgets.QLabel("⇌")
        ip = icon.palette()
        ip.setColor(QtGui.QPalette.WindowText, QtGui.QColor(COLOR_WARN))
        icon.setPalette(ip)
        self.title = QtWidgets.QLabel(title)
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.subtitle = QtWidgets.QLabel(subtitle)
        sp = self.subtitle.palette()
        sp.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#a8a8a8"))
        self.subtitle.setPalette(sp)
        self.btn_close = _Button("×", "flat")
        head.addWidget(icon)
        head.addWidget(self.title)
        head.addWidget(self.subtitle, 1)
        head.addWidget(self.btn_close)
        body.addLayout(head)

        # --- フィルタ行 ---
        frow = QtWidgets.QHBoxLayout()
        frow.setSpacing(8)
        self.pills = FilterPills([("要確認", 0, "warn"), ("対応済み", 0, "muted"), ("すべて", 0, "muted")])
        self.pills.setCurrentIndex(0)
        self.search = SearchBox("名前で絞り込み")
        self.search.setFixedWidth(_em(self, 16))
        frow.addWidget(self.pills)
        frow.addStretch()
        frow.addWidget(self.search)
        body.addLayout(frow)

        # --- 自動対応ルール ---
        self.rules = RulesBar()
        body.addWidget(self.rules)

        # --- 一括操作バー ---
        self.bulk = BulkBar()
        body.addWidget(self.bulk)

        # --- 表 ---
        self.view = RemapTableView()
        self.view.setModel(self.proxy)
        self.view.setupColumns()
        body.addWidget(self.view, 1)

        # --- フッター ---
        line = QtWidgets.QFrame()
        line.setFixedHeight(1)
        lp = line.palette()
        lp.setColor(QtGui.QPalette.Window, QtGui.QColor("#2c2c2c"))
        line.setPalette(lp)
        line.setAutoFillBackground(True)
        root.addWidget(line)

        foot = QtWidgets.QHBoxLayout()
        foot.setContentsMargins(12, 8, 12, 10)
        foot.setSpacing(8)
        self.btn_save = _Button("対応表を保存…")
        self.btn_load = _Button("対応表を読み込み…")
        self.status = QtWidgets.QLabel()
        self.status.setAlignment(Qt.AlignCenter)
        self.btn_cancel = _Button("キャンセル")
        self.btn_apply = _Button("適用", "primary")
        foot.addWidget(self.btn_save)
        foot.addWidget(self.btn_load)
        foot.addWidget(self.status, 1)
        foot.addWidget(self.btn_cancel)
        foot.addWidget(self.btn_apply)
        root.addLayout(foot)

        # --- ポップアップ(使い回し) ---
        self.popup = JointPickerPopup(self)
        self.popup.dismissed.connect(lambda: self.view.setOpenSourceRow(-1))

        # --- 接続 ---
        self.model.changed.connect(self._refresh_state)
        self.pills.currentChanged.connect(self.proxy.setFilterMode)
        self.search.textChanged.connect(self.proxy.setSearchText)
        self.view.destRequested.connect(self._on_dest_requested)
        self.bulk.assignRequested.connect(self._bulk_assign)
        self.bulk.mirrorRequested.connect(self._bulk_mirror)
        self.bulk.skipRequested.connect(self._bulk_skip)
        self.bulk.clearRequested.connect(self.model.clearChecked)
        self.btn_close.clicked.connect(self.closeRequested)
        self.btn_cancel.clicked.connect(self.cancelled)
        self.btn_apply.clicked.connect(lambda: self.applied.emit(self.mapping()))
        self.btn_save.clicked.connect(self._on_save)
        self.btn_load.clicked.connect(self._on_load)
        self.popup.picked.connect(self._on_picked)
        self.popup.skipped.connect(self._on_skipped)

        self.rules.setRules([("name", "名前一致", True), ("namespace", "名前空間を無視", True),
                             ("replace", "置換 1 件", True), ("position", "位置（許容 0.05）", True)])
        # 初期の絞り込みを反映(ピルの初期選択はシグナルが出ないので明示的に設定する)
        self.proxy.setFilterMode(self.pills.currentIndex())
        self._refresh_state()

    # ------------------------------------------------------------------
    # 外から差し込む部分
    # ------------------------------------------------------------------
    def setHeader(self, title, subtitle=""):
        self.title.setText(title)
        self.subtitle.setText(subtitle)

    def setRows(self, rows):
        self.model.setRows(rows)

    def setSceneJoints(self, joints):
        self._scene_joints = list(joints)

    def setCandidateProvider(self, fn):
        """fn(src_name) -> [(ジョイント名, 補足), ...](近い順)。省略時は名前の類似度で並べる。"""
        self._candidate_provider = fn or self._default_candidates

    def setSelectedJointProvider(self, fn):
        """fn() -> Mayaで選択中のジョイント名(無ければ空文字)。"""
        self._selected_provider = fn or (lambda: "")

    def mapping(self):
        return self.model.mapping()

    def _default_candidates(self, src):
        base = src.split(":")[-1]
        scored = sorted(self._scene_joints, key=lambda j: -difflib.SequenceMatcher(None, base.lower(), j.lower()).ratio())
        return [(j, f"類似度 {difflib.SequenceMatcher(None, base.lower(), j.lower()).ratio():.2f}") for j in scored[:5]]

    # ------------------------------------------------------------------
    # 状態の更新
    # ------------------------------------------------------------------
    def _refresh_state(self):
        review, done, total = self.model.counts()
        self.pills.setCount(0, review)
        self.pills.setCount(1, done)
        self.pills.setCount(2, total)
        self.bulk.setCount(len(self.model.checkedRows()))
        n, verts = self.model.unresolved()
        if n:
            self.status.setText(f"未対応 {n} 件（{verts} 頂点）が残っています")
        else:
            self.status.setText("すべて対応済みです")

    # ------------------------------------------------------------------
    # 宛先の選択(1行)
    # ------------------------------------------------------------------
    def _on_dest_requested(self, proxy_index):
        src_row = self.proxy.mapToSource(proxy_index).row()
        row = self.model.row(src_row)
        self._bulk_mode = False
        self._target_rows = [src_row]
        self.view.setOpenSourceRow(src_row)
        cell = self.view.cellGlobalRect(proxy_index)
        right = self.view.viewport().mapToGlobal(QtCore.QPoint(self.view.viewport().width() - 6, 0)).x()
        self.popup.open(self._candidate_provider(row.src), self._scene_joints, self._selected_provider(),
                        cell, right_limit=right)

    # ------------------------------------------------------------------
    # 一括操作
    # ------------------------------------------------------------------
    def _bulk_assign(self):
        rows = self.model.checkedRows()
        if not rows:
            return
        self._bulk_mode = True
        self._target_rows = rows
        btn = self.bulk.btn_assign
        anchor = QtCore.QRect(btn.mapToGlobal(QtCore.QPoint(0, 0)), btn.size())
        right = self.mapToGlobal(QtCore.QPoint(self.width() - 12, 0)).x()
        self.popup.open(self._candidate_provider(self.model.row(rows[0]).src), self._scene_joints,
                        self._selected_provider(), anchor, right_limit=right)

    def _bulk_mirror(self):
        scene = set(self._scene_joints)
        for i in self.model.checkedRows():
            r = self.model.row(i)
            m = mirror_name(r.dest) if r.dest else None
            if m and m in scene:
                self.model.setDest(i, m, ("左右反転", "info"), "guess")

    def _bulk_skip(self):
        for i in self.model.checkedRows():
            self.model.setSkip(i)

    def _on_picked(self, joint, detail):
        reason = ("手動", "info")
        for i in self._target_rows:
            self.model.setDest(i, joint, reason, "ok")

    def _on_skipped(self):
        for i in self._target_rows:
            self.model.setSkip(i)

    # ------------------------------------------------------------------
    # 対応表の保存/読み込み
    # ------------------------------------------------------------------
    def saveMapping(self, path):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.mapping(), f, ensure_ascii=False, indent=2)
        self.mappingSaved.emit(path)

    def loadMapping(self, path):
        with open(path, "r", encoding="utf-8") as f:
            n = self.model.loadMapping(json.load(f))
        self.mappingLoaded.emit(path)
        return n

    def _on_save(self):
        path, _ = QtWidgets.QFileDialog.getSaveFileName(self, "対応表を保存", "remap.json", "JSON (*.json)")
        if path:
            self.saveMapping(path)

    def _on_load(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "対応表を読み込み", "", "JSON (*.json)")
        if path:
            self.loadMapping(path)


# ===========================================================================
# デモ
# ===========================================================================
DEMO_OBJECT_NAME = "remapViewDemo"


def make_demo_data():
    """参考画像と同じ構成(54件: 要確認5 + 対応済み49)のデモデータと、シーンのジョイント一覧。"""
    rows = [
        RemapRow("spine04_JNT", 32, None, None, "unassigned"),
        RemapRow("tongue01_JNT", 0, None, None, "zero"),
        RemapRow("char:jaw_JNT", 214, "jaw_JNT", ("名前空間", "info"), "guess"),
        RemapRow("L_eyelid_JNT", 86, "L_eyelidUpper_JNT", ("位置 0.02", "info"), "guess"),
        RemapRow("R_eyelid_JNT", 84, "R_eyelidUpper_JNT", ("位置 0.02", "info"), "guess"),
    ]
    names = ["root_JNT", "hips_JNT", "spine01_JNT", "spine02_JNT", "spine03_JNT", "chest_JNT", "neck_JNT",
             "neck02_JNT", "head_JNT"]
    for side in ("L", "R"):
        names += [f"{side}_{p}_JNT" for p in ("clavicle", "shoulder", "elbow", "wrist")]
        names += [f"{side}_{f}{k:02d}_JNT" for f in ("thumb", "index", "middle", "ring") for k in (1, 2, 3)]
    for side in ("L", "R"):
        names += [f"{side}_{p}_JNT" for p in ("upleg", "knee", "ankle", "ball")]
    verts = [40, 177, 314, 451, 588, 725, 862, 99, 236]
    for i, n in enumerate(names):
        v = verts[i] if i < len(verts) else (37 * i) % 400 + 20
        rows.append(RemapRow(n, v, n, ("名前一致", "info"), "ok"))
    scene = names + ["jaw_JNT", "L_eyelidUpper_JNT", "R_eyelidUpper_JNT", "tongue_JNT", "spine_ik_JNT"]
    return rows, scene


def demo_candidates(src):
    """spine04_JNT だけ画像と同じ候補を返し、それ以外は名前の類似度で返すデモ用の関数。"""
    if src == "spine04_JNT":
        return [("chest_JNT", "距離 0.40・親子が近い"), ("spine03_JNT", "距離 1.20"), ("neck_JNT", "距離 2.80")]
    return None


def _maya_main_window():
    """Mayaが無い環境では None を返す(単体実行できるように)。"""
    try:
        from maya import OpenMayaUI as omui
        from shiboken6 import wrapInstance
    except ImportError:
        return None
    ptr = omui.MQtUtil.mainWindow()
    return wrapInstance(int(ptr), QtWidgets.QWidget) if ptr else None


class DemoWindow(RemapPanel):
    def __init__(self, parent=None):
        super().__init__("インフルエンスのリマップ", "head_GEO.npy → head_GEO（シーン）", parent)
        self.setObjectName(DEMO_OBJECT_NAME)
        self.setWindowTitle("Remap View Demo")
        self.setWindowFlags(Qt.Window)
        self.resize(700, 720)

        rows, scene = make_demo_data()
        self.setRows(rows)
        self.setSceneJoints(scene)

        def provider(src):
            c = demo_candidates(src)
            return c if c is not None else self._default_candidates(src)
        self.setCandidateProvider(provider)
        self.setSelectedJointProvider(lambda: "chest_JNT")     # Maya では cmds.ls(sl=True, type="joint") など
        self.closeRequested.connect(self.close)
        self.cancelled.connect(self.close)
        self.applied.connect(lambda m: print(f"applied: {len(m)} 件のマッピング"))


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