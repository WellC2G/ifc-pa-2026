from viewport import IFCViewport

import sys

from PyQt6.QtWidgets import ( 
    QApplication, 
    QWidget, 
    QVBoxLayout, 
    QTreeWidget,
    QMainWindow, 
    QSplitter,
    QTextEdit,
    QFileDialog,
    QTreeWidgetItem
    )
from PyQt6.QtCore import (
    Qt,
    QSettings,
    )
from PyQt6.QtGui import QAction

class MainWindow(QMainWindow):
    def __init__(self):
        # parent's constructor (QMainWindow)
        super().__init__()

        # title and default suze
        self.setWindowTitle("IFC editor")
        self.resize(800, 600)

        # initialization settings for load settings after last close
        self.settings = QSettings("Degustation", "IFCEditor")

        # build main interface
        self.__init_ui()
        self.__create_menu()

        # load settings (AFTER BUILD ALL WIDGETS)
        self.__restore_settings()


    def __init_ui(self):
        # two main widget
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # create another widget

        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.h_splitter = QSplitter(Qt.Orientation.Horizontal)

        # tree, bottom_panel and viewport NOW JUST plugs
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Struct of IFC")

        self.viewport = IFCViewport()
        # self.viewport.setStyleSheet("background-color: #333333;")

        self.bottom_panel = QTextEdit()
        self.bottom_panel.setPlaceholderText("Place for logs")

        # add plugs to splitter
        self.h_splitter.addWidget(self.tree)
        self.h_splitter.addWidget(self.viewport)

        self.v_splitter.addWidget(self.h_splitter)
        self.v_splitter.addWidget(self.bottom_panel)

        # set default size on first open
        self.v_splitter.setSizes([500, 100])

        # add all to main widgets
        main_layout.addWidget(self.v_splitter)
        main_widget.setLayout(main_layout)

        # add main widget to MainWindow
        self.setCentralWidget(main_widget)

        # just status bar
        self.statusBar().showMessage("Ready to work")

        # create root of tree
        project_node = QTreeWidgetItem(self.tree, ["Project: House"])

        # childs
        floor_node = QTreeWidgetItem(project_node, ["Floor 1"])

        wall_node = QTreeWidgetItem(floor_node, ["Wall_Basic_200mm"])
        wall_node2 = QTreeWidgetItem(floor_node, ["Wall_Basic_100mm"])

        # open all nodes
        self.tree.expandAll()

        self.tree.itemClicked.connect(self.__on_tree_click)

    def __create_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        open_action = QAction("Open", self)
        exit_action = QAction("Exit", self)
        

        exit_action.triggered.connect(self.close)
        open_action.triggered.connect(self.__open_file)

        file_menu.addAction(open_action)
        file_menu.addAction(exit_action)

    def __restore_settings(self):
        """mehtod for save size window and splitters"""
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        v_state = self.settings.value("v_splitter_state")
        if v_state:
            self.v_splitter.restoreState(v_state)

        h_state = self.settings.value("h_splitter_state")
        if h_state:
            self.h_splitter.restoreState(h_state)

    def __on_tree_click(self, item, column):
        node_name = item.text(column)
        self.bottom_panel.append(f"Clicked on: {node_name}")

    def __open_file(self):
        file_path, filter_type = QFileDialog.getOpenFileName(
            self,
            "Select IFC Model",
            "",
            "IFC Files (*.ifc);;All Files (*)"
        )

        if file_path:
            self.bottom_panel.append(f"File selected: {file_path}")

    def closeEvent(self, event):
        """this method called before close app"""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("v_splitter_state", self.v_splitter.saveState())
        self.settings.setValue("h_splitter_state", self.h_splitter.saveState())

        super().closeEvent(event)

app = QApplication(sys.argv)

window = MainWindow()
window.show()

app.exec()