
"""
custom_buttons.py
PySide6 (Maya 2027 対応) 描画ベースのカスタムボタン サンプル集

収録:
    1. FlatButton        : フラットボタン(variant / アイコン付き / チェック可 / ホバーアニメ)
    2. IconButton        : アイコンのみのツールバー向けボタン(チェック可)
    3. ToggleSwitch      : スライドするトグルスイッチ(ラベル付き)
    4. ColorSwatchButton : 色見本ボタン(クリックでカラーダイアログ、colorChanged シグナル)

すべて QAbstractButton を継承しているので、clicked / toggled / setCheckable /
setEnabled / Space・Enter 操作などは Qt が面倒を見てくれます。
こちらで書くのは「見た目(paintEvent)」と「サイズ(sizeHint)」と「ホバーアニメ」だけ。

Maya外でも動作確認できるよう、maya への依存は _maya_main_window() 内だけです。
    - 単体:  python custom_buttons.py
    - Maya:  import custom_buttons; custom_buttons.show_demo()
"""
from PySide6 import QtCore, QtGui, QtWidgets

Qt = QtCore.Qt


# ---------------------------------------------------------------------------
# 共通ヘルパー
# ---------------------------------------------------------------------------
def _em(widget, ratio):
    """フォント高さ基準の長さ(px)。UIスケール/DPIが変わっても比率が崩れない。"""
    return max(1, round(widget.fontMetrics().height() * ratio))


def _lerp_color(a, b, t):
    """2色の線形補間(アニメーション用)。"""
    t = max(0.0, min(1.0, t))
    return QtGui.QColor(
        round(a.red() + (b.red() - a.red()) * t),
        round(a.green() + (b.green() - a.green()) * t),
        round(a.blue() + (b.blue() - a.blue()) * t),
        round(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def _text_color_for(bg):
    """背景の明るさから読みやすい文字色を選ぶ。"""
    return QtGui.QColor("#ffffff") if bg.lightness() < 150 else QtGui.QColor("#202020")


# ---------------------------------------------------------------------------
# 共通基底: ホバーアニメーション付きボタン
# ---------------------------------------------------------------------------
class _AnimatedButton(QtWidgets.QAbstractButton):
    """
    ホバーの進行度 _hover_t (0.0 -> 1.0) をアニメーションで持つ基底クラス。
    派生クラスは paintEvent で _hover_t を使って色を補間するだけでよい。
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        # TabFocus: Tabキーで来たときだけフォーカスが当たる。
        # → マウスクリックでフォーカス枠が出てしまうのを避けられる。
        self.setFocusPolicy(Qt.TabFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)

        self._hover_t = 0.0
        self._hover_anim = QtCore.QVariantAnimation(self)
        self._hover_anim.setDuration(120)
        self._hover_anim.valueChanged.connect(self._on_hover_value)

    def _on_hover_value(self, v):
        self._hover_t = float(v)
        self.update()

    def _animate_hover(self, target):
        a = self._hover_anim
        a.stop()
        a.setStartValue(self._hover_t)
        a.setEndValue(float(target))
        a.start()

    def enterEvent(self, e):
        if self.isEnabled():
            self._animate_hover(1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._animate_hover(0.0)
        super().leaveEvent(e)

    def changeEvent(self, e):
        if e.type() == QtCore.QEvent.EnabledChange and not self.isEnabled():
            # 無効化されるとleaveが来ないことがあるのでホバー状態をリセット
            self._hover_anim.stop()
            self._hover_t = 0.0
        if e.type() in (QtCore.QEvent.FontChange, QtCore.QEvent.EnabledChange,
                        QtCore.QEvent.PaletteChange):
            self.updateGeometry()
            self.update()
        super().changeEvent(e)

    def _draw_focus_ring(self, p, rect, radius):
        if self.hasFocus():
            p.setBrush(Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 190), 1.5))
            p.drawRoundedRect(QtCore.QRectF(rect).adjusted(2, 2, -2, -2), radius, radius)


# ---------------------------------------------------------------------------
# 1. FlatButton
# ---------------------------------------------------------------------------
class FlatButton(_AnimatedButton):
    """
    フラットな角丸ボタン。
      - variant:  "primary" / "secondary" / "danger"
      - setIcon() でアイコン付き(QAbstractButton標準のAPIをそのまま使う)
      - setCheckable(True) でトグルボタン(チェック中は明るく+白枠)
    """

    VARIANTS = {
        "primary": "#3b82c4",
        "secondary": "#5c5c5c",
        "danger": "#c4483b",
    }

    def __init__(self, text="", variant="primary", icon=None, parent=None):
        super().__init__(parent)
        self.setText(text)
        self._variant = variant
        if icon is not None:
            self.setIcon(icon)
        self.setSizePolicy(QtWidgets.QSizePolicy.Minimum, QtWidgets.QSizePolicy.Fixed)

    def setVariant(self, variant):
        self._variant = variant
        self.update()

    # --- サイズ(全部フォント基準) ------------------------------------------
    def _h_pad(self):
        return _em(self, 0.9)

    def _v_pad(self):
        return _em(self, 0.4)

    def _icon_size(self):
        return _em(self, 1.1)

    def _spacing(self):
        return _em(self, 0.4)

    def sizeHint(self):
        fm = self.fontMetrics()
        # +1: horizontalAdvance は整数に丸めた値だが elidedText は小数幅で判定するため、
        #     ぴったりの幅だと誤って省略されることがある。1pxの余裕を持たせる。
        w = fm.horizontalAdvance(self.text()) + 1 + self._h_pad() * 2
        if not self.icon().isNull():
            w += self._icon_size() + (self._spacing() if self.text() else 0)
        h = max(fm.height(), self._icon_size() if not self.icon().isNull() else 0)
        return QtCore.QSize(w, h + self._v_pad() * 2)

    def minimumSizeHint(self):
        return self.sizeHint()

    # --- 描画 ---------------------------------------------------------------
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)

        base = QtGui.QColor(self.VARIANTS.get(self._variant, self._variant))
        if not self.isEnabled():
            bg = QtGui.QColor(85, 85, 85)
        elif self.isDown():
            bg = base.darker(118)
        else:
            if self.isChecked():
                base = base.lighter(125)
            bg = _lerp_color(base, base.lighter(115), self._hover_t)
        fg = _text_color_for(bg) if self.isEnabled() else QtGui.QColor(140, 140, 140)

        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = _em(self, 0.3)
        p.setPen(Qt.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, radius, radius)

        # チェック中は内側に細い白枠
        if self.isChecked() and self.isEnabled():
            p.setBrush(Qt.NoBrush)
            p.setPen(QtGui.QPen(QtGui.QColor(255, 255, 255, 200), 1.5))
            p.drawRoundedRect(r.adjusted(1.5, 1.5, -1.5, -1.5), radius, radius)

        # アイコン + テキストを「ひとかたまり」にして中央寄せ
        fm = self.fontMetrics()
        has_icon = not self.icon().isNull()
        isz = self._icon_size() if has_icon else 0
        gap = self._spacing() if (has_icon and self.text()) else 0
        # r は0.5pxずつ内側に縮めた矩形なので、幅は self.width() から計算する
        # (r.width() を使うと sizeHint ぴったりのとき1pxの差で省略されてしまう)
        avail = self.width() - self._h_pad() * 2 - isz - gap
        text = fm.elidedText(self.text(), Qt.ElideRight, max(0, avail))
        total = isz + gap + fm.horizontalAdvance(text)
        x = r.center().x() - total / 2

        if has_icon:
            mode = QtGui.QIcon.Normal if self.isEnabled() else QtGui.QIcon.Disabled
            icon_rect = QtCore.QRect(round(x), round(r.center().y() - isz / 2), isz, isz)
            self.icon().paint(p, icon_rect, Qt.AlignCenter, mode)
            x += isz + gap

        p.setPen(fg)
        text_rect = QtCore.QRectF(x, r.top(), fm.horizontalAdvance(text) + 1, r.height())
        p.drawText(text_rect, int(Qt.AlignLeft | Qt.AlignVCenter), text)

        self._draw_focus_ring(p, self.rect(), radius)


# ---------------------------------------------------------------------------
# 2. IconButton
# ---------------------------------------------------------------------------
class IconButton(_AnimatedButton):
    """
    アイコンのみの正方形ボタン。普段は背景なし、ホバーで薄い背景、チェック中はアクセント背景。
    ツールバー/ショートカット列向け。説明は setToolTip() で付ける。
    """

    def __init__(self, icon=None, parent=None):
        super().__init__(parent)
        if icon is not None:
            self.setIcon(icon)
        self._accent = QtGui.QColor("#4a90d9")
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def setAccentColor(self, color):
        self._accent = QtGui.QColor(color)
        self.update()

    def sizeHint(self):
        s = _em(self, 1.9)
        return QtCore.QSize(s, s)

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        r = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        radius = _em(self, 0.3)

        if self.isEnabled():
            # ベース: ホバーで白を薄く重ねる
            bg = QtGui.QColor(255, 255, 255, round(38 * self._hover_t))
            if self.isChecked():
                bg = QtGui.QColor(self._accent)
                bg.setAlpha(150 + round(50 * self._hover_t))
            if self.isDown():
                bg = QtGui.QColor(255, 255, 255, 70)
            p.setPen(Qt.NoPen)
            p.setBrush(bg)
            p.drawRoundedRect(r, radius, radius)

        s = _em(self, 1.15)
        icon_rect = QtCore.QRect(0, 0, s, s)
        icon_rect.moveCenter(self.rect().center())
        mode = QtGui.QIcon.Normal if self.isEnabled() else QtGui.QIcon.Disabled
        self.icon().paint(p, icon_rect, Qt.AlignCenter, mode)

        self._draw_focus_ring(p, self.rect(), radius)


# ---------------------------------------------------------------------------
# 3. ToggleSwitch
# ---------------------------------------------------------------------------
class ToggleSwitch(_AnimatedButton):
    """
    スライド式のON/OFFスイッチ。右にラベル文字を置ける。
    つまみ位置は toggled をトリガーに別アニメーションで 0.0 <-> 1.0 を補間する。
    """

    def __init__(self, text="", checked=False, parent=None):
        super().__init__(parent)
        self.setText(text)
        self.setCheckable(True)
        self._on_color = QtGui.QColor("#3b9b6e")
        self._off_color = QtGui.QColor("#6a6a6a")

        self._pos = 1.0 if checked else 0.0
        self._pos_anim = QtCore.QVariantAnimation(self)
        self._pos_anim.setDuration(140)
        self._pos_anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)
        self._pos_anim.valueChanged.connect(self._on_pos_value)
        # 初期状態はアニメーションなしで反映したいので、接続前にセット
        super().setChecked(checked)
        self.toggled.connect(self._on_toggled)

        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def setOnColor(self, color):
        self._on_color = QtGui.QColor(color)
        self.update()

    # --- アニメ ---------------------------------------------------------------
    def _on_pos_value(self, v):
        self._pos = float(v)
        self.update()

    def _on_toggled(self, checked):
        a = self._pos_anim
        a.stop()
        a.setStartValue(self._pos)
        a.setEndValue(1.0 if checked else 0.0)
        a.start()

    # --- サイズ ---------------------------------------------------------------
    def _track_h(self):
        return _em(self, 1.3)

    def _track_w(self):
        return round(self._track_h() * 1.9)

    def _gap(self):
        return _em(self, 0.5)

    def sizeHint(self):
        fm = self.fontMetrics()
        w = self._track_w()
        if self.text():
            w += self._gap() + fm.horizontalAdvance(self.text())
        return QtCore.QSize(w + 2, max(self._track_h(), fm.height()) + 4)

    def minimumSizeHint(self):
        return self.sizeHint()

    # --- 描画 -----------------------------------------------------------------
    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.45)

        th, tw = self._track_h(), self._track_w()
        track = QtCore.QRectF(1, (self.height() - th) / 2, tw, th)

        # トラック: つまみ位置に連動して色をブレンド、ホバーで少し明るく
        track_color = _lerp_color(self._off_color, self._on_color, self._pos)
        track_color = _lerp_color(track_color, track_color.lighter(120), self._hover_t)
        p.setPen(Qt.NoPen)
        p.setBrush(track_color)
        p.drawRoundedRect(track, th / 2, th / 2)

        # つまみ
        d = th - 4
        x = track.left() + 2 + (tw - th) * self._pos
        p.setBrush(QtGui.QColor("#f2f2f2"))
        p.drawEllipse(QtCore.QRectF(x, track.top() + 2, d, d))

        # ラベル
        if self.text():
            p.setPen(self.palette().color(QtGui.QPalette.WindowText))
            text_rect = QtCore.QRectF(track.right() + self._gap(), 0,
                                      self.width() - track.right() - self._gap(), self.height())
            p.drawText(text_rect, int(Qt.AlignLeft | Qt.AlignVCenter), self.text())

        self._draw_focus_ring(p, track.toRect().adjusted(-1, -1, 1, 1), th / 2)


# ---------------------------------------------------------------------------
# 4. ColorSwatchButton
# ---------------------------------------------------------------------------
class ColorSwatchButton(_AnimatedButton):
    """色見本ボタン。クリックで QColorDialog を開き、確定したら colorChanged を発行。"""

    colorChanged = QtCore.Signal(QtGui.QColor)

    def __init__(self, color="#e8913a", parent=None):
        super().__init__(parent)
        self._color = QtGui.QColor(color)
        self.clicked.connect(self._pick)
        self.setSizePolicy(QtWidgets.QSizePolicy.Fixed, QtWidgets.QSizePolicy.Fixed)

    def color(self):
        return QtGui.QColor(self._color)

    def setColor(self, color):
        color = QtGui.QColor(color)
        if color == self._color:
            return
        self._color = color
        self.update()
        self.colorChanged.emit(color)

    def _pick(self):
        c = QtWidgets.QColorDialog.getColor(self._color, self.window(), "色を選択")
        if c.isValid():
            self.setColor(c)

    def sizeHint(self):
        return QtCore.QSize(_em(self, 3.0), _em(self, 1.5))

    def minimumSizeHint(self):
        return self.sizeHint()

    def paintEvent(self, e):
        p = QtGui.QPainter(self)
        p.setRenderHint(QtGui.QPainter.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.45)

        r = QtCore.QRectF(self.rect()).adjusted(1, 1, -1, -1)
        radius = _em(self, 0.3)

        p.setPen(Qt.NoPen)
        p.setBrush(self._color)
        p.drawRoundedRect(r, radius, radius)

        # 枠: 通常はMid色、ホバーで白へ
        border = _lerp_color(self.palette().color(QtGui.QPalette.Mid),
                             QtGui.QColor("#ffffff"), self._hover_t)
        p.setBrush(Qt.NoBrush)
        p.setPen(QtGui.QPen(border, 1.5))
        p.drawRoundedRect(r, radius, radius)

        self._draw_focus_ring(p, self.rect(), radius)


# ---------------------------------------------------------------------------
# デモ
# ---------------------------------------------------------------------------
DEMO_OBJECT_NAME = "customButtonsDemo"


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
        self.setWindowTitle("Custom Buttons Demo")
        self.setWindowFlags(Qt.Window)
        self.resize(460, 420)

        # Mayaっぽいダーク配色(Maya内では親のスタイルが効くので単体確認用)
        pal = self.palette()
        pal.setColor(QtGui.QPalette.Window, QtGui.QColor(68, 68, 68))
        pal.setColor(QtGui.QPalette.WindowText, QtGui.QColor(220, 220, 220))
        pal.setColor(QtGui.QPalette.Mid, QtGui.QColor(110, 110, 110))
        pal.setColor(QtGui.QPalette.Disabled, QtGui.QPalette.WindowText,
                     QtGui.QColor(120, 120, 120))
        self.setPalette(pal)
        self.setAutoFillBackground(True)

        style = self.style()
        SP = QtWidgets.QStyle

        lay = QtWidgets.QVBoxLayout(self)
        lay.setSpacing(8)

        def header(text):
            lb = QtWidgets.QLabel(text)
            f = lb.font()
            f.setBold(True)
            lb.setFont(f)
            lb.setContentsMargins(0, 6, 0, 0)
            lay.addWidget(lb)

        # 1. FlatButton
        header("1. FlatButton")
        row = QtWidgets.QHBoxLayout()
        b_primary = FlatButton("Apply", "primary", style.standardIcon(SP.SP_DialogApplyButton))
        b_second = FlatButton("Cancel", "secondary")
        b_danger = FlatButton("Delete", "danger", style.standardIcon(SP.SP_TrashIcon))
        b_check = FlatButton("Toggle", "secondary")
        b_check.setCheckable(True)
        b_off = FlatButton("Disabled", "primary")
        b_off.setEnabled(False)
        for b in (b_primary, b_second, b_danger, b_check, b_off):
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)

        # 2. IconButton
        header("2. IconButton")
        row = QtWidgets.QHBoxLayout()
        icon_btns = []
        for icon_id, tip in ((SP.SP_FileDialogNewFolder, "新規フォルダ"),
                             (SP.SP_BrowserReload, "再読み込み"),
                             (SP.SP_DialogSaveButton, "保存")):
            b = IconButton(style.standardIcon(icon_id))
            b.setToolTip(tip)
            b.setCheckable(True)
            icon_btns.append(b)
            row.addWidget(b)
        row.addStretch()
        lay.addLayout(row)

        # 3. ToggleSwitch
        header("3. ToggleSwitch")
        sw1 = ToggleSwitch("Auto Key", checked=True)
        sw2 = ToggleSwitch("Wireframe")
        sw3 = ToggleSwitch("Locked", checked=True)
        sw3.setEnabled(False)
        for sw in (sw1, sw2, sw3):
            lay.addWidget(sw)

        # 4. ColorSwatchButton
        header("4. ColorSwatchButton")
        row = QtWidgets.QHBoxLayout()
        swatches = [ColorSwatchButton(c) for c in ("#e8913a", "#4a90d9", "#3b9b6e")]
        for s in swatches:
            row.addWidget(s)
        row.addStretch()
        lay.addLayout(row)

        # シグナル確認用のログ表示
        self.log = QtWidgets.QLabel("(操作するとここに表示)")
        lay.addStretch()
        lay.addWidget(self.log)

        b_primary.clicked.connect(lambda: self._say("Apply clicked"))
        b_check.toggled.connect(lambda c: self._say(f"Toggle checked={c}"))
        for sw, name in ((sw1, "Auto Key"), (sw2, "Wireframe")):
            sw.toggled.connect(lambda c, n=name: self._say(f"{n} = {c}"))
        for s in swatches:
            s.colorChanged.connect(lambda c: self._say(f"color -> {c.name()}"))

        # 外から参照できるように保持(テスト用)
        self.widgets = dict(primary=b_primary, check=b_check, icons=icon_btns,
                            sw1=sw1, sw2=sw2, swatches=swatches)

    def _say(self, msg):
        self.log.setText(msg)


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