# -*- coding: utf-8 -*-
"""PySideWidgetTest のモジュールを依存順に読み直す。"""
import importlib
import sys

__all__ = ["MODULES", "UI_MODULES", "reload", "reload_modules", "reload_module"]

MODULES = [
    "PySideWidgetTest.constants",
]

UI_MODULES = [
    "PySideWidgetTest.ui",
    "PySideWidgetTest.ui.qt",
    "PySideWidgetTest.ui.widgets.label",
    "PySideWidgetTest.ui.widgets.button",
    "PySideWidgetTest.ui.widgets",
    "PySideWidgetTest.ui.window",
]

_LAST = ["PySideWidgetTest.api", "PySideWidgetTest"]


def _available(name):
    try:
        importlib.import_module(name)
        return True
    except ImportError:
        return False


def reload_module(module_name):
    if module_name in sys.modules:
        return importlib.reload(sys.modules[module_name])
    return importlib.import_module(module_name)


def reload():
    """reloader 自身を読み直して返す。"""
    return reload_module(__name__)


def reload_modules():
    """Maya と PySide が利用できる場合に UI を含めて読み直す。"""
    in_maya = _available("maya.OpenMayaUI")
    has_qt = _available("PySide6") or _available("PySide2")
    if "PySideWidgetTest.ui.window" in sys.modules:
        sys.modules["PySideWidgetTest.ui.window"].close_windows()
    names = list(MODULES)
    if in_maya and has_qt:
        names += UI_MODULES
    names += _LAST
    modules = [reload_module(name) for name in names]
    unlisted = sorted(
        name for name in sys.modules
        if name.startswith("PySideWidgetTest.")
        and name not in names
        and name != __name__
        and sys.modules[name] is not None
    )
    if unlisted:
        print("PySideWidgetTest: reloader に無い未リロードのモジュール: {}".format(
            ", ".join(unlisted)))
    return modules
