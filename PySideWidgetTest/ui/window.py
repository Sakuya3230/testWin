# -*- coding: utf-8 -*-
"""カスタムウィジェットを配置するための空の Maya 子ウィンドウ。"""
from .. import constants
from .qt import QtWidgets, Qt, wrapInstance, isValid

from .widgets.label import TitleLabel, WrapLabel

__all__ = ["PySideWidgetTestWindow", "maya_main_window", "show_window", "close_windows"]


def maya_main_window():
    """Maya のメインウィンドウを QWidget として返す。"""
    try:
        from maya import OpenMayaUI
    except ImportError:
        return None
    pointer = OpenMayaUI.MQtUtil.mainWindow()
    return wrapInstance(int(pointer), QtWidgets.QWidget) if pointer else None


class PySideWidgetTestWindow(QtWidgets.QMainWindow):
    """空の central widget とレイアウトを持つテスト用メインウィンドウ。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName(constants.WINDOW_OBJECT_NAME)
        self.setWindowTitle(constants.WINDOW_TITLE)
        self.setWindowFlags(Qt.Window)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.resize(800, 600)

        self.central_widget = QtWidgets.QWidget(self)
        self.content_layout = QtWidgets.QVBoxLayout(self.central_widget)
        self.setCentralWidget(self.central_widget)

        self.title_label = TitleLabel("ウエイト", 16, "#EB7D7D", self)
        self.title_label1 = WrapLabel("これはとても長い分を改行してみやすくするためのウィジェットだよ。", self)
        self.content_layout.addWidget(self.title_label)
        self.content_layout.addWidget(self.title_label1)

def close_windows():
    """Maya の Widget ツリーから既存のテストウィンドウを閉じる。"""
    app = QtWidgets.QApplication.instance()
    if app is None:
        return
    for widget in app.allWidgets():
        if widget.objectName() == constants.WINDOW_OBJECT_NAME and isValid(widget):
            widget.close()
            widget.deleteLater()


def show_window():
    """既存のテストウィンドウを閉じてから新しく開く。"""
    close_windows()
    window = PySideWidgetTestWindow(maya_main_window())
    window.show()
    return window
