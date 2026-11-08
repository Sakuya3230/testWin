"""
item_table.py
PySide6 (Maya 2027 対応) ヘッダー付きアイテムビュー(モデル/ビュー方式)

    チェック | ファイル        | 適用先メッシュ | インフル | チェック
    [✓]      | body_GEO.npy    | body_GEO       |      54  | (OK)
    [✓]      | head_GEO.npy    | head_GEO       |      22  | (ジョイント不足 2)

構成:
    FileTableModel   : データ(QAbstractTableModel)。行は dict のリスト
    ItemTableView    : QTableView を整えたビュー(グリッド線なし・行の交互色・ホバー行・フラットなヘッダー)
    FlatHeader       : フラットなヘッダー(列ごとの文字揃え対応)
    デリゲート        : TextDelegate(文字)/ CheckDelegate(チェックボックス)/ BadgeDelegate(ピル型バッジ)

【なぜ QTableView か】
    - 「列のある単純な一覧」なので、ツリー(階層)機能はいらない → QTableView が素直
      (QTreeView + setRootIsDecorated(False) でも見た目は作れるが、階層用の余計な機能が付いてくる)
    - QTableWidget / QTreeWidget(アイテムベース)は手軽だが、セルごとに QTableWidgetItem を作るため
      行数が増えると重く、チェック・バッジのような独自描画もしにくい
    - モデル/ビュー + デリゲートなら、データと見た目が分離でき、数万行でも軽い(描画は見えている行だけ)

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python item_table.py
    - Maya:  import item_table; item_table.show_demo()
"""
from PySide6 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt


def _em(widget, ratio):
    """フォント高さ基準の長さ(px)。UIスケール/DPIが変わっても比率が崩れない。"""
    return max(1, round(widget.fontMetrics().height() * ratio))


def _is_checked(value):
    """CheckStateRole の値(Qt.CheckState / int / bool のどれで来ても)をboolに。"""
    return getattr(value, "value", value) in (2, True)


# 参考画像から実測した配色
COLOR_PANEL = "#3a3a3a"
COLOR_ROW_A = "#3a3a3a"
COLOR_ROW_B = "#363636"
COLOR_LINE = "#444444"
COLOR_HEADER_BG = "#303030"
COLOR_HEADER_TEXT = "#bbbbbb"
COLOR_TEXT = "#d1d1d1"
COLOR_TEXT_DIM = "#bebebe"
COLOR_TEXT_MUTED = "#9a9a9a"
COLOR_SELECTED = "#3f5266"

# バッジ: kind -> (背景, 文字)
BADGE_COLORS = {
    "ok": ("#3d5c3a", "#9fe39a"),
    "warn": ("#5c4428", "#f0b464"),
    "error": ("#5c3b43", "#f0a0b0"),
    "info": ("#34495e", "#8fc4f0"),
}


# ===========================================================================
# 1. モデル
# ===========================================================================
class FileTableModel(QtCore.QAbstractTableModel):
    """
    1行 = dict(file=str, mesh=str, influence=int, status=(text, kind), checked=bool)
    列: [チェック, ファイル, 適用先メッシュ, インフル, チェック結果(バッジ)]
    """

    COL_CHECK, COL_FILE, COL_MESH, COL_INFL, COL_STATUS = range(5)
    HEADERS = ["", "ファイル", "適用先メッシュ", "インフル", "チェック"]

    BadgeRole = Qt.UserRole + 1           # (text, kind) を返す
    checkedChanged = QtCore.Signal()       # チェック状態が変わった

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
        row, col = self._rows[index.row()], index.column()

        if role == Qt.CheckStateRole and col == self.COL_CHECK:
            return Qt.Checked if row.get("checked") else Qt.Unchecked

        if role == Qt.DisplayRole:
            if col == self.COL_FILE:
                return row.get("file", "")
            if col == self.COL_MESH:
                return row.get("mesh") or "（メッシュなし）"
            if col == self.COL_INFL:
                return str(row.get("influence", ""))
            if col == self.COL_STATUS:
                return row.get("status", ("", ""))[0]

        elif role == Qt.TextAlignmentRole:
            if col == self.COL_INFL:
                return int(Qt.AlignRight | Qt.AlignVCenter)
            return int(Qt.AlignLeft | Qt.AlignVCenter)

        elif role == Qt.ForegroundRole:
            if col == self.COL_MESH and not row.get("mesh"):
                return QtGui.QBrush(QtGui.QColor(COLOR_TEXT_MUTED))
            if col in (self.COL_MESH, self.COL_INFL):
                return QtGui.QBrush(QtGui.QColor(COLOR_TEXT_DIM))

        elif role == self.BadgeRole and col == self.COL_STATUS:
            return row.get("status")

        elif role == Qt.ToolTipRole and col == self.COL_FILE:
            return row.get("file", "")
        return None

    def setData(self, index, value, role=Qt.EditRole):
        if index.isValid() and role == Qt.CheckStateRole and index.column() == self.COL_CHECK:
            self._rows[index.row()]["checked"] = _is_checked(value)
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            self.checkedChanged.emit()
            return True
        return False

    def flags(self, index):
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == self.COL_CHECK:
            f |= Qt.ItemIsUserCheckable
        return f

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                return self.HEADERS[section]
            if role == Qt.TextAlignmentRole:
                align = Qt.AlignRight if section == self.COL_INFL else Qt.AlignLeft
                return int(align | Qt.AlignVCenter)
        return None

    # --- 便利メソッド ---------------------------------------------------------
    def row(self, i):
        return self._rows[i]

    def addRow(self, row):
        n = len(self._rows)
        self.beginInsertRows(QtCore.QModelIndex(), n, n)
        self._rows.append(row)
        self.endInsertRows()

    def removeRow(self, row, parent=QtCore.QModelIndex()):
        if not (0 <= row < len(self._rows)):
            return False
        self.beginRemoveRows(parent, row, row)
        del self._rows[row]
        self.endRemoveRows()
        self.checkedChanged.emit()
        return True

    def setRows(self, rows):
        self.beginResetModel()
        self._rows = list(rows)
        self.endResetModel()
        self.checkedChanged.emit()

    def checkedRows(self):
        return [i for i, r in enumerate(self._rows) if r.get("checked")]

    def setAllChecked(self, on):
        for r in self._rows:
            r["checked"] = bool(on)
        if self._rows:
            self.dataChanged.emit(self.index(0, self.COL_CHECK),
                                  self.index(len(self._rows) - 1, self.COL_CHECK), [Qt.CheckStateRole])
        self.checkedChanged.emit()


# ===========================================================================
# 2. デリゲート(描画)
# ===========================================================================
class _RowDelegate(QtWidgets.QStyledItemDelegate):
    """行の背景(交互色/選択/ホバー)と下の区切り線を描く共通基底。"""

    def _paint_row_bg(self, p, option, index):
        view = option.widget
        base = QtGui.QColor(COLOR_ROW_A if index.row() % 2 == 0 else COLOR_ROW_B)
        if option.state & QtWidgets.QStyle.State_Selected:
            color = QtGui.QColor(COLOR_SELECTED)
        elif getattr(view, "hoverRow", lambda: -1)() == index.row():
            color = base.lighter(112)
        else:
            color = base
        p.fillRect(option.rect, color)
        p.setPen(QtGui.QColor(COLOR_LINE))
        p.drawLine(option.rect.bottomLeft(), option.rect.bottomRight())

    def paint(self, p, option, index):
        p.save()
        self._paint_row_bg(p, option, index)
        self._paint_content(p, option, index)
        p.restore()

    def _paint_content(self, p, option, index):
        pass


class TextDelegate(_RowDelegate):
    """文字セル。文字揃え・文字色はモデルの TextAlignmentRole / ForegroundRole に従う。"""

    def _paint_content(self, p, option, index):
        text = index.data(Qt.DisplayRole) or ""
        align = index.data(Qt.TextAlignmentRole)
        align = int(align) if align is not None else int(Qt.AlignLeft | Qt.AlignVCenter)
        brush = index.data(Qt.ForegroundRole)
        color = brush.color() if isinstance(brush, QtGui.QBrush) else QtGui.QColor(COLOR_TEXT)
        pad = _em(option.widget, 0.8) if option.widget else 8
        rect = option.rect.adjusted(pad, 0, -pad, -1)
        p.setFont(option.font)
        p.setPen(color)
        p.drawText(rect, align, option.fontMetrics.elidedText(text, Qt.ElideRight, rect.width()))


def draw_check_box(p, rect, checked, hover=False):
    """チェックボックスを rect(QRectF)の中に描く。custom_checkbox.py と同じ見た目の静的版。"""
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


class CheckDelegate(_RowDelegate):
    """チェックボックスのセル。クリック/Spaceで CheckStateRole をトグルする。"""

    def _box_rect(self, option):
        s = _em(option.widget, 1.3) if option.widget else 18
        r = QtCore.QRectF(0, 0, s, s)
        r.moveCenter(QtCore.QRectF(option.rect).center())
        return r

    def _paint_content(self, p, option, index):
        checked = _is_checked(index.data(Qt.CheckStateRole))
        hover = bool(option.state & QtWidgets.QStyle.State_MouseOver)
        draw_check_box(p, self._box_rect(option), checked, hover)

    def editorEvent(self, event, model, option, index):
        if not (index.flags() & Qt.ItemIsUserCheckable and index.flags() & Qt.ItemIsEnabled):
            return False
        t = event.type()
        if t == QtCore.QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            if not option.rect.contains(event.position().toPoint()):
                return False
        elif t == QtCore.QEvent.KeyPress and event.key() in (Qt.Key_Space, Qt.Key_Select):
            pass
        else:
            return False
        new = Qt.Unchecked if _is_checked(index.data(Qt.CheckStateRole)) else Qt.Checked
        model.setData(index, new, Qt.CheckStateRole)
        return True


class BadgeDelegate(_RowDelegate):
    """BadgeRole の (text, kind) をピル型バッジで描く。kind は BADGE_COLORS のキー。"""

    def _paint_content(self, p, option, index):
        badge = index.data(FileTableModel.BadgeRole)
        if not badge or not badge[0]:
            return
        text, kind = badge
        bg, fg = BADGE_COLORS.get(kind, BADGE_COLORS["info"])
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        font = QtGui.QFont(option.font)
        font.setPointSizeF(max(6.0, font.pointSizeF() * 0.92))
        fm = QtGui.QFontMetrics(font)
        pad_x = _em(option.widget, 0.7)
        w = fm.horizontalAdvance(text) + pad_x * 2
        h = fm.height() + _em(option.widget, 0.35)
        r = QtCore.QRectF(option.rect.left() + _em(option.widget, 0.5),
                          option.rect.center().y() - h / 2, min(w, option.rect.width() - 4), h)
        p.setPen(Qt.NoPen)
        p.setBrush(QtGui.QColor(bg))
        p.drawRoundedRect(r, h / 2, h / 2)
        p.setFont(font)
        p.setPen(QtGui.QColor(fg))
        p.drawText(r, int(Qt.AlignCenter), fm.elidedText(text, Qt.ElideRight, int(r.width() - pad_x)))


# ===========================================================================
# 3. ヘッダーとビュー
# ===========================================================================
class FlatHeader(QtWidgets.QHeaderView):
    """フラットなヘッダー。文字揃えは headerData の TextAlignmentRole に従う。"""

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
        p.setPen(QtGui.QColor(COLOR_LINE))                  # 下の区切り線
        p.drawLine(rect.bottomLeft(), rect.bottomRight())
        p.restore()


class ItemTableView(QtWidgets.QTableView):
    """グリッド線なし・行の交互色・ホバー行・フラットなヘッダーに整えた QTableView。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hover_row = -1

        self.setHorizontalHeader(FlatHeader(Qt.Horizontal, self))
        self.verticalHeader().hide()
        self.setShowGrid(False)
        self.setFrameShape(QtWidgets.QFrame.NoFrame)
        self.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.setSelectionMode(QtWidgets.QAbstractItemView.ExtendedSelection)
        self.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setVerticalScrollMode(QtWidgets.QAbstractItemView.ScrollPerPixel)
        self.setTextElideMode(Qt.ElideRight)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

        # 行の外(行が少ない時の余白)もパネル色で塗る
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Base, QtGui.QColor(COLOR_PANEL))
        self.setPalette(pal)

        self._apply_metrics()

    def hoverRow(self):
        return self._hover_row

    def _apply_metrics(self):
        self.verticalHeader().setDefaultSectionSize(_em(self, 2.6))   # 行の高さ

    def setColumnLayout(self, fixed_em=None, stretch=None):
        """
        列幅を設定する。
            fixed_em: {列: フォント高さの何倍か}  固定幅
            stretch:  [列, ...]                   残りの幅を等分して伸縮
        """
        hdr = self.horizontalHeader()
        for col, em in (fixed_em or {}).items():
            hdr.setSectionResizeMode(col, QtWidgets.QHeaderView.Fixed)
            hdr.resizeSection(col, _em(self, em))
        for col in (stretch or []):
            hdr.setSectionResizeMode(col, QtWidgets.QHeaderView.Stretch)

    # --- ホバー行の追跡 ----------------------------------------------------------
    def _set_hover_row(self, row):
        if row != self._hover_row:
            self._hover_row = row
            self.viewport().update()

    def mouseMoveEvent(self, e):
        self._set_hover_row(self.rowAt(int(e.position().y())))
        super().mouseMoveEvent(e)

    def viewportEvent(self, e):
        if e.type() == QtCore.QEvent.Leave:
            self._set_hover_row(-1)
        return super().viewportEvent(e)

    def changeEvent(self, e):
        if e.type() == QtCore.QEvent.FontChange:
            self._apply_metrics()
        super().changeEvent(e)


def make_file_table(model=None, parent=None):
    """FileTableModel 用に、デリゲートと列幅をひととおり設定した ItemTableView を返す。"""
    view = ItemTableView(parent)
    view.setModel(model or FileTableModel())
    text, check, badge = TextDelegate(view), CheckDelegate(view), BadgeDelegate(view)
    M = FileTableModel
    view.setItemDelegateForColumn(M.COL_CHECK, check)
    view.setItemDelegateForColumn(M.COL_FILE, text)
    view.setItemDelegateForColumn(M.COL_MESH, text)
    view.setItemDelegateForColumn(M.COL_INFL, text)
    view.setItemDelegateForColumn(M.COL_STATUS, badge)
    view.setColumnLayout(fixed_em={M.COL_CHECK: 2.8, M.COL_INFL: 5.0, M.COL_STATUS: 11},
                         stretch=[M.COL_FILE, M.COL_MESH])
    return view


# ===========================================================================
# デモ
# ===========================================================================
DEMO_OBJECT_NAME = "itemTableDemo"

DEMO_ROWS = [
    dict(file="body_GEO.npy", mesh="body_GEO", influence=54, status=("OK", "ok"), checked=True),
    dict(file="head_GEO.npy", mesh="head_GEO", influence=22, status=("ジョイント不足 2", "warn"), checked=True),
    dict(file="hand_L_GEO.json", mesh="hand_L_GEO", influence=18, status=("OK", "ok"), checked=True),
    dict(file="teeth_GEO.json", mesh="", influence=4, status=("適用先なし", "error"), checked=False),
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


class _PanelButton(QtWidgets.QAbstractButton):
    """デモ用の簡易フラットボタン(warn=True でオレンジ枠)。"""

    def __init__(self, text, warn=False, parent=None):
        super().__init__(parent)
        self.setText(text)
        self._warn = warn
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def sizeHint(self):
        fm = self.fontMetrics()
        return QtCore.QSize(fm.horizontalAdvance(self.text()) + _em(self, 2.0), _em(self, 2.1))

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        hover, down = self.underMouse(), self.isDown()
        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        if self._warn:
            bg, fg, border = QtGui.QColor("#4a3c2c"), QtGui.QColor("#f8dcbb"), QtGui.QColor("#e0a15c")
        else:
            bg, fg, border = QtGui.QColor("#5d5d5d"), QtGui.QColor("#dddddd"), None
        if down:
            bg = bg.darker(115)
        elif hover:
            bg = bg.lighter(118)
        p.setBrush(bg)
        p.setPen(QtGui.QPen(border, 1.2) if border else Qt.NoPen)
        p.drawRoundedRect(r, _em(self, 0.25), _em(self, 0.25))
        p.setPen(fg)
        p.drawText(self.rect(), int(Qt.AlignCenter), self.text())


class DemoWindow(QtWidgets.QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(DEMO_OBJECT_NAME)
        self.setWindowTitle("Item Table Demo")
        self.setWindowFlags(Qt.Window)
        self.resize(780, 400)

        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#444444"))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#dddddd"))
        pal.setColor(QtGui.QPalette.Text, QtGui.QColor(COLOR_TEXT))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)

        # --- パネル(角丸の背景) ---
        panel = QtWidgets.QFrame()
        panel.setObjectName("panel")
        panel.setStyleSheet(f"#panel {{ background: {COLOR_PANEL}; border-radius: 6px; }}")
        outer.addWidget(panel)
        lay = QtWidgets.QVBoxLayout(panel)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # --- タイトル行 ---
        head = QtWidgets.QHBoxLayout()
        head.setContentsMargins(14, 12, 14, 10)
        head.setSpacing(8)
        self.title = QtWidgets.QLabel("インポートファイル")
        f = self.title.font()
        f.setBold(True)
        self.title.setFont(f)
        self.count = QtWidgets.QLabel()
        cp = self.count.palette()
        cp.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#a7a7a7"))
        self.count.setPalette(cp)
        head.addWidget(self.title)
        head.addWidget(self.count)
        head.addStretch()
        head.setSpacing(8)
        self.btn_add = _PanelButton("＋ ファイル追加")
        self.btn_folder = _PanelButton("フォルダから")
        self.btn_remove = _PanelButton("除外")
        for b in (self.btn_add, self.btn_folder, self.btn_remove):
            head.addWidget(b)
        lay.addLayout(head)

        # --- テーブル ---
        self.model = FileTableModel([dict(r) for r in DEMO_ROWS])
        self.view = make_file_table(self.model)
        lay.addWidget(self.view, 1)

        # --- フッター ---
        foot = QtWidgets.QHBoxLayout()
        foot.setContentsMargins(12, 10, 12, 12)
        foot.setSpacing(8)
        self.btn_check = _PanelButton("チェック実行")
        self.btn_remap = _PanelButton("インフルエンスのリマップ…", warn=True)
        self.status = QtWidgets.QLabel("head_GEO: 2 ジョイントが見つかりません")
        sp = self.status.palette()
        sp.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#f0dcc0"))
        self.status.setPalette(sp)
        foot.addWidget(self.btn_check)
        foot.addWidget(self.btn_remap)
        foot.addWidget(self.status, 1)
        lay.addLayout(foot)

        # --- 接続 ---
        self.model.checkedChanged.connect(self._update_count)
        self.model.rowsInserted.connect(self._update_count)
        self.model.rowsRemoved.connect(self._update_count)
        self.btn_add.clicked.connect(self._add_row)
        self.btn_remove.clicked.connect(self._remove_selected)
        self.btn_check.clicked.connect(self._run_check)
        self._n = 0
        self._update_count()

    def _update_count(self, *_):
        self.count.setText(f"{self.model.rowCount()} 件・{len(self.model.checkedRows())} 件選択")

    def _add_row(self):
        self._n += 1
        self.model.addRow(dict(file=f"new_{self._n}_GEO.npy", mesh=f"new_{self._n}_GEO", influence=10 + self._n,
                               status=("OK", "ok"), checked=True))
        self.view.scrollToBottom()

    def _remove_selected(self):
        for r in sorted({i.row() for i in self.view.selectionModel().selectedRows()}, reverse=True):
            self.model.removeRow(r)

    def _run_check(self):
        bad = [self.model.row(i)["file"] for i in range(self.model.rowCount())
               if self.model.row(i)["status"][1] != "ok"]
        self.status.setText(f"要確認: {', '.join(bad)}" if bad else "問題はありません")


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