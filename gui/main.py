from viewport import IFCViewport
from parse_core.get_data.get_project_hierarchy import get_project_hierarchy
from parse_core.get_data.get_element_geometry import get_element_geometry

import os
os.environ["QT_QPA_PLATFORM"] = "windows"
os.environ["LIBGL_ALWAYS_SOFTWARE"] = "1"

import sys
import ifcopenshell

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

from PyQt6.QtCore import QThread, pyqtSignal

class GeometryWorker(QThread):
    # Создаем сигнал, который вернет словарь (dict) с результатами, когда закончит работу
    finished_signal = pyqtSignal(dict)

    def __init__(self, model):
        super().__init__()
        self.model = model

    def run(self):
        # Всё, что находится внутри метода run(), выполняется в отдельном потоке!
        # Сюда мы переносим вашу тяжелую функцию
        geom_data = get_element_geometry(self.model)
        
        # Когда генерация закончена, отправляем данные обратно в главное окно
        self.finished_signal.emit(geom_data)

class MainWindow(QMainWindow):
    def __on_geometry_ready(self, geom_data):
        """Этот метод вызовется автоматически, когда фоновый поток закончит расчеты"""
        
        if "error" in geom_data:
            self.bottom_panel.append(f"Ошибка 3D: {geom_data['error']}")
        else:
            vtm_path = geom_data["dir_path"]
            elements_count = geom_data["elements_count"]
            
            self.bottom_panel.append(f"Геометрия создана! Элементов: {elements_count}")
            self.bottom_panel.append(f"Файл геометрии: {vtm_path}")
            
            # 4. ОТПРАВЛЯЕМ ФАЙЛ ВО ВЬЮПОРТ ДЛЯ ОТРИСОВКИ
            self.viewport.load_model(vtm_path)
            
            self.bottom_panel.append("Успех: Модель загружена и отрисована!")
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

    def __build_tree_ui(self, node_list:list, parent_item):
        for node in node_list:
            display_text = f"[{node['Type']}] {node['Name']}"

            item = QTreeWidgetItem(parent_item, [display_text])

            item.setData(0, Qt.ItemDataRole.UserRole, node["GlobalId"])
            item.setData(0, Qt.ItemDataRole.UserRole + 1, node["Type"])

            children = node.get("Children", [])
            if children:
                self.__build_tree_ui(children, item)


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
        display_text = item.text(column)

        global_id = item.data(0, Qt.ItemDataRole.UserRole)
        ifc_type = item.data(0, Qt.ItemDataRole.UserRole + 1)

        self.bottom_panel.append(f"Clicked on: {display_text}")
        self.bottom_panel.append(f"--Hide GloabalId: {global_id}")
        self.bottom_panel.append(f"--Hide Type: {ifc_type}")

    def __open_file(self):
        file_path, filter_type = QFileDialog.getOpenFileName(
            self,
            "Select IFC Model",
            "",
            "IFC Files (*.ifc);;All Files (*)"
        )


        if file_path:
            self.bottom_panel.append(f"File selected: {file_path}")

            self.tree.clear()

            try:
                # 1. Загружаем модель
                self.bottom_panel.append("Чтение IFC файла...")
                QApplication.processEvents() # Обновляем UI, чтобы не завис
                model = ifcopenshell.open(file_path)

                # 2. Строим дерево
                self.bottom_panel.append("Построение дерева проекта...")
                QApplication.processEvents()
                hierarchy_list = get_project_hierarchy(model)
                self.__build_tree_ui(hierarchy_list, self.tree)
                self.tree.expandAll()

                # 3. Извлекаем 3D-геометрию В ФОНОВОМ ПОТОКЕ
                self.bottom_panel.append("Генерация 3D геометрии запущена в фоне (интерфейс не зависнет!)...")
                
                # Создаем воркер и передаем ему модель
                self.worker = GeometryWorker(model)
                
                # Подключаем сигнал успешного завершения к новому методу
                self.worker.finished_signal.connect(self.__on_geometry_ready)
                
                # ЗАПУСКАЕМ ПОТОК
                self.worker.start()

            except Exception as e:
                self.bottom_panel.append(f"Ошибка чтения файла: {e}")

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