from gui.viewport import IFCViewport
from core.parse.get_project_hierarchy import get_project_hierarchy
from core.parse.get_element_geometry import get_element_geometry
from core.parse.get_properties_by_global_id import get_properties_by_global_id
from core.file.save_file import save_ifc_model
from core.edit_data.edit_data import update_element_properties

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
    QThread,
    Qt,
    QSettings,
    pyqtSignal,
    )
from PyQt6.QtGui import QAction

class GeometryWorker(QThread):
    finished_signal = pyqtSignal(dict)

    def __init__(self, model):
        super().__init__()
        self.model = model

    def run(self):
        geom_data = get_element_geometry(self.model)
        
        self.finished_signal.emit(geom_data)

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
        self.h_splitter_2 = QSplitter(Qt.Orientation.Horizontal)

        # tree, bottom_panel and viewport NOW JUST plugs
        self.tree = QTreeWidget()
        self.tree.setHeaderLabel("Struct of IFC")

        self.viewport = IFCViewport()
        # self.viewport.setStyleSheet("background-color: #333333;")

        self.bottom_panel = QTextEdit()
        self.bottom_panel.setPlaceholderText("Place for logs")

        self.property_tree = QTreeWidget()
        self.property_tree.setHeaderLabels(["Property", "Value"])
        self.property_tree.setAlternatingRowColors(True)

        # add plugs to splitter
        self.h_splitter.addWidget(self.tree)
        self.h_splitter.addWidget(self.viewport)

        self.h_splitter_2.addWidget(self.bottom_panel)
        self.h_splitter_2.addWidget(self.property_tree)

        self.v_splitter.addWidget(self.h_splitter)
        self.v_splitter.addWidget(self.h_splitter_2)

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
        self.tree.itemDoubleClicked.connect(self.__on_tree_double_click)

        self.property_tree.itemChanged.connect(self.__on_property_edited)

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
        save_action = QAction("Save", self)
        exit_action = QAction("Exit", self)
        

        exit_action.triggered.connect(self.close)
        open_action.triggered.connect(self.__open_file)
        save_action.triggered.connect(self.__save_file)

        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(exit_action)

    def __save_file(self):
        # Проверяем, есть ли что сохранять
        if not hasattr(self, 'model'):
            self.bottom_panel.append("Ошибка: Нет открытого файла для сохранения.")
            return

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save IFC Model",
            "",
            "IFC Files (*.ifc)"
        )

        if file_path:
            self.bottom_panel.append(f"Сохранение в {file_path}...")

            result = save_ifc_model(self.model, file_path)
            
            if result.get("success"):
                self.bottom_panel.append(f"Успех: Файл сохранен -> {result['path']}")
            else:
                self.bottom_panel.append(f"Ошибка сохранения: {result.get('error')}")


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

    def __on_tree_double_click(self, item, column):
        display_text = item.text(0)
        global_id = item.data(0, Qt.ItemDataRole.UserRole)

        if not hasattr(self, 'model'):
            return
        
        self.current_global_id = global_id

        self.current_tree_item = item

        self.bottom_panel.append(f"Загрузка свойств для: {display_text}")

        self.current_properties = get_properties_by_global_id(self.model, global_id)

        self.property_tree.blockSignals(True)
        self.property_tree.clear()

        props = self.current_properties.get("Properties", {})
        if props:
            props_root = QTreeWidgetItem(self.property_tree, ["Properties", ""])
            
            for group_name, group_data in props.items():
                group_node = QTreeWidgetItem(props_root, [str(group_name), ""])
                
                for key, value in group_data.items():
                    row = QTreeWidgetItem(group_node,[str(key), str(value)])

                    row.setFlags(row.flags() | Qt.ItemFlag.ItemIsEditable)

                    row.setData(0, Qt.ItemDataRole.UserRole, ("Properties", group_name, key))

        classifications = self.current_properties.get("Classification",[])
        if classifications:
            class_root = QTreeWidgetItem(self.property_tree, ["Classification", ""])
            for idx, cls in enumerate(classifications):
                cls_node = QTreeWidgetItem(class_root,[f"Class {idx+1}: {cls.get('Name', '')}", ""])
                for key, value in cls.items():
                    QTreeWidgetItem(cls_node,[str(key), str(value)]) # Без флага Editable

        relations = self.current_properties.get("Relations", [])
        if relations:
            rel_root = QTreeWidgetItem(self.property_tree,["Relations", ""])
            for rel in relations:
                QTreeWidgetItem(rel_root,[str(rel.get("Type", "")), str(rel.get("Name", ""))])

        self.property_tree.expandAll()
        self.property_tree.blockSignals(False)

    def __on_property_edited(self, item, column):
        if column != 1:
            return

        path = item.data(0, Qt.ItemDataRole.UserRole)
        if not path:
            return 

        new_value = item.text(1)

        if len(path) == 3 and path[0] == "Properties":
            _, group_name, key = path
            self.current_properties["Properties"][group_name][key] = new_value
            self.bottom_panel.append(f"[Изменено в памяти] {group_name} -> {key} = {new_value}")

            if group_name == "Element Specific" and key in ("Name", "IfcEntity"):
                if hasattr(self, 'current_tree_item') and self.current_tree_item:
                    props = self.current_properties["Properties"]["Element Specific"]
                    current_name = props.get("Name", "")
                    current_type = props.get("IfcEntity", "")

                    new_display_text = f"[{current_type}] {current_name}"
                    self.current_tree_item.setText(0, new_display_text)

                    if key == "IfcEntity":
                        self.current_tree_item.setData(0, Qt.ItemDataRole.UserRole + 1, current_type)
        
        update_result = update_element_properties(
            self.model, 
            self.current_global_id, 
            self.current_properties
        )

        if update_result.get("success"):
            self.bottom_panel.append(f"[Core] {update_result['message']}")
        else:
            self.bottom_panel.append(f"[Core Error] Не удалось обновить IFC: {update_result.get('error')}")

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
                self.bottom_panel.append("Чтение IFC файла...")
                QApplication.processEvents() 
                self.model = ifcopenshell.open(file_path)

                self.bottom_panel.append("Построение дерева проекта...")
                QApplication.processEvents()
                hierarchy_list = get_project_hierarchy(self.model)
                self.__build_tree_ui(hierarchy_list, self.tree)
                self.tree.expandAll()

                self.bottom_panel.append("Генерация 3D геометрии в фоновом потоке...")
                
                self.geom_worker = GeometryWorker(self.model)
                self.geom_worker.finished_signal.connect(self.__on_geometry_loaded)
                self.geom_worker.start()

            except Exception as e:
                self.bottom_panel.append(f"Ошибка чтения файла: {e}")

    def __on_geometry_loaded(self, geom_data):
        if "error" in geom_data:
            self.bottom_panel.append(f"Ошибка 3D: {geom_data['error']}")
        else:
            vtm_path = geom_data["dir_path"]
            elements_count = geom_data["elements_count"]
            
            self.bottom_panel.append(f"Геометрия создана! Элементов: {elements_count}")
            # Передаем файл во вьюпорт
            self.viewport.load_model(vtm_path)
            self.bottom_panel.append("Успех: Модель загружена и отрисована!")

    def closeEvent(self, event):
        """this method called before close app"""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("v_splitter_state", self.v_splitter.saveState())
        self.settings.setValue("h_splitter_state", self.h_splitter.saveState())

        super().closeEvent(event)