import sys

from PyQt6.QtWidgets import ( 
    QApplication, 
    QWidget, 
    QVBoxLayout, 
    QTreeWidget,
    QMainWindow, 
    QSplitter,
    QTextEdit,
    )
from PyQt6.QtCore import (
    Qt,
    QSettings,
    )
from PyQt6.QtGui import QAction

class MainWindow(QMainWindow):
    """
    todo:
        1) change constructor (__init__), bcs i think it`s very overload
            so many code/line in one method
        2) maybe add all widget to self, bcs it`s should be like fields in classic OOP (C++/Java)
    """
    def __init__(self): 
        super().__init__()

        self.settings = QSettings("Degustation", "IFCEditor")

        """python`s trash
        geometry = self.settings.value("geometry")
        if geometry: self.restoreGeometry(geometry)

        v_state = self.settings.value("v_splitter_state")
        if v_state: self.v_splitter.restoreState(v_state)
        """

        self.setWindowTitle("IFC editor")
        self.resize(800, 600)

        #main widgets
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        
        #splitters
        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.v_splitter.setSizes([500, 100])
        self.h_splitter = QSplitter(Qt.Orientation.Horizontal) 
        
        geometry = self.settings.value("geometry")
        if geometry: self.restoreGeometry(geometry)

        v_state = self.settings.value("v_splitter_state")
        if v_state: self.v_splitter.restoreState(v_state)

        #empty widgets (empty just now)
        tree = QTreeWidget()
        tree.setHeaderLabel("Struct of IFC")
        
        viewport = QWidget()
        viewport.setStyleSheet("background-color: #333333;") #just color

        bottom_panel = QTextEdit()
        bottom_panel.setPlaceholderText("Place for logs")

        self.h_splitter.addWidget(tree)
        self.h_splitter.addWidget(viewport)

        self.v_splitter.addWidget(self.h_splitter)
        self.v_splitter.addWidget(bottom_panel)


        main_layout.addWidget(self.v_splitter)

        main_widget.setLayout(main_layout)

        self.setCentralWidget(main_widget)
        self.statusBar().showMessage("Ready to work")

        self.__create_menu()

    def __create_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.close)

        file_menu.addAction(exit_action)

    def closeEvent(self, event):
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("v_splitter_state", self.v_splitter.saveState())

        super().closeEvent(event)

app = QApplication(sys.argv)

window = MainWindow()
window.show()

app.exec()