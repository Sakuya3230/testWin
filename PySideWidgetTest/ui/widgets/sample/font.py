from PySide6 import QtGui

db = QtGui.QFontDatabase()
for family in db.families():
    for style in db.styles(family):
        print(family, "-", style)