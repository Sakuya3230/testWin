# -*- coding: utf-8 -*-
"""PySide6 を優先し、無ければ PySide2 を使う。"""
try:
    from PySide6 import QtCore, QtWidgets, QtGui
    from shiboken6 import wrapInstance, isValid
except ImportError:
    from PySide2 import QtCore, QtWidgets, QtGui
    from shiboken2 import wrapInstance, isValid

Qt = QtCore.Qt

__all__ = ["QtCore", "QtWidgets", "QtGui", "Qt", "wrapInstance", "isValid"]
