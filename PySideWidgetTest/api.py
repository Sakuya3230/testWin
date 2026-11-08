# -*- coding: utf-8 -*-
"""PySideWidgetTest の公開 API。"""

__all__ = ["show_window", "close_windows", "reload_modules"]


def show_window():
    """Maya のメインウィンドウを親にして、空のテストウィンドウを開く。"""
    from .ui.window import show_window as show
    return show()


def close_windows():
    """開いているテストウィンドウを閉じる。"""
    from .ui.window import close_windows as close
    close()


def reload_modules():
    """パッケージを依存順に読み直す。"""
    from . import reloader
    return reloader.reload().reload_modules()
