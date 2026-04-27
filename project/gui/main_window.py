import os
import shutil

from gui.viewport import IFCViewport
from core.parse.get_project_hierarchy import get_project_hierarchy
from core.parse.get_element_geometry import get_element_geometry
from core.parse.get_properties_by_global_id import get_properties_by_global_id
from core.file.save_file import save_ifc_model
from core.edit_data.edit_data import update_element_properties
from core.edit_data.edit_hierarchy import edit_element_hierarchy
from core.edit_data.edit_placement import move_ifc_element

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


class ProjectTreeWidget(QTreeWidget):
    item_dropped_signal = pyqtSignal(QTreeWidgetItem, QTreeWidgetItem, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDragDropMode(QTreeWidget.DragDropMode.InternalMove)

        self.setAutoScroll(True)
        self.setAutoScrollMargin(30)

    def dragEnterEvent(self, event):
        super().dragEnterEvent(event)
        event.accept()

    def dragMoveEvent(self, event):
        super().dragMoveEvent(event)
        event.accept()

    def dropEvent(self, event):
        dragged_item = self.currentItem()
        target_item = self.itemAt(event.position().toPoint())

        if not dragged_item or not target_item or dragged_item == target_item:
            event.ignore()
            return

        element_guid = dragged_item.data(0, Qt.ItemDataRole.UserRole)
        parent_guid = target_item.data(0, Qt.ItemDataRole.UserRole)

        if element_guid and parent_guid:
            self.item_dropped_signal.emit(dragged_item, target_item, element_guid, parent_guid)

        event.ignore()

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

        self.setStyleSheet(self.themes["Dark"])

    def __init_ui(self):
        # two main widget
        main_widget = QWidget()
        main_layout = QVBoxLayout()

        # create another widget

        self.v_splitter = QSplitter(Qt.Orientation.Vertical)
        self.h_splitter = QSplitter(Qt.Orientation.Horizontal)
        self.h_splitter_2 = QSplitter(Qt.Orientation.Horizontal)

        # tree, bottom_panel and viewport NOW JUST plugs
        self.tree = ProjectTreeWidget()
        self.tree.setHeaderLabel("Struct of IFC")

        self.tree.item_dropped_signal.connect(self.__on_hierarchy_dropped)

        self.viewport = IFCViewport()
        #self.viewport.setStyleSheet("background-color: #333333;")

        self.bottom_panel = QTextEdit()
        self.bottom_panel.setPlaceholderText("Place for logs")

        self.property_tree = QTreeWidget()
        self.property_tree.setHeaderLabels(["Property", "Value"])
        self.property_tree.setAlternatingRowColors(True)

        # add plugs to splitter
        self.viewport.setMinimumSize(200, 200) 

        # add plugs to splitter
        self.h_splitter.addWidget(self.tree)
        self.h_splitter.addWidget(self.viewport)

        self.h_splitter_2.addWidget(self.bottom_panel)
        self.h_splitter_2.addWidget(self.property_tree)

        self.v_splitter.addWidget(self.h_splitter)
        self.v_splitter.addWidget(self.h_splitter_2)

        # set default size on first open
        self.v_splitter.setSizes([500, 100])
        
        # ДОБАВЛЕНО: Явно задаем размеры для горизонтальных сплиттеров 
        # (Дерево: 200px, Viewport: 600px)
        self.h_splitter.setSizes([200, 600]) 
        self.h_splitter_2.setSizes([600, 200])

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

        self.viewport.element_selected_signal.connect(self.__on_viewport_element_selected)

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
        settings_menu = menu_bar.addMenu("Settings")

        theme_menu = settings_menu.addMenu("Theme")

        self.themes = {
            "Light": """
                QMainWindow, QWidget {
                    background-color: #f3f3f3; /* Светло-серый фон приложения */
                    color: #333333; /* Темно-серый текст для хорошей читаемости */
                }

                QTreeView, QTextEdit, QTableView {
                    background-color: #ffffff; /* Чисто белый фон для данных */
                    border: 1px solid #cccccc; /* Светлые границы */
                    gridline-color: #cccccc;
                }

                QHeaderView::section {
                    background-color: #e8e8e8; /* Слегка выделенный фон заголовков */
                    color: #333333;
                    border: 1px solid #cccccc;
                    padding: 2px;
                }

                QPushButton {
                    background-color: #e4e4e4;
                    color: #333333;
                    border: 1px solid #cccccc;
                    border-radius: 4px;
                    padding: 4px;
                }

                QPushButton:hover {
                    background-color: #ebebeb;
                    border: 1px solid #b3b3b3;
                }

                QPushButton:pressed {
                    background-color: #dadada;
                }

                QScrollBar:vertical {
                    border: none;
                    background: #f3f3f3;
                    width: 14px;
                    margin: 0px 0px 0px 0px;
                }
                QScrollBar::handle:vertical {
                    background: #c1c1c1; /* Серый ползунок */
                    min-height: 20px;
                    border-radius: 7px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #a8a8a8; /* Более темный серый при наведении */
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    border: none;
                    background: none;
                }
            """,
            "Dark": """
                QMainWindow, QWidget {
                    background-color: #1e1e1e; /* Темно-серый фон */
                    color: #d4d4d4; /* Светло-серый/белый текст */
                }

                QTreeView, QTextEdit, QTableView {
                    background-color: #252526;
                    border: 1px solid #3c3c3c;
                    gridline-color: #3c3c3c;
                }

                QHeaderView::section {
                    background-color: #2d2d30;
                    color: #d4d4d4;
                    border: 1px solid #3c3c3c;
                }

                QPushButton {
                    background-color: #333333;
                    color: #ffffff;
                    border: 1px solid #555555;
                    border-radius: 4px;
                }

                QPushButton:hover {
                    background-color: #444444;
                    border: 1px solid #888888;
                }

                QPushButton:pressed {
                    background-color: #222222;
                }

                QScrollBar:vertical {
                    border: none;
                    background: #1e1e1e;
                    width: 14px;
                    margin: 0px 0px 0px 0px;
                }
                QScrollBar::handle:vertical {
                    background: #424242;
                    min-height: 20px;
                    border-radius: 7px;
                }
                QScrollBar::handle:vertical:hover {
                    background: #4f4f4f;
                }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                    border: none;
                    background: none;
                }
            """,
        }

        open_action = QAction("Open", self)
        save_action = QAction("Save", self)
        exit_action = QAction("Exit", self)
        

        for theme_name in self.themes.keys():
            action = QAction(theme_name, self)
            
            # Используем ту самую правильную лямбду с сохранением имени
            action.triggered.connect(lambda checked, name=theme_name: self.change_theme(name))
            
            # Добавляем действие (цвет) в подменю Theme
            theme_menu.addAction(action)

        exit_action.triggered.connect(self.close)
        open_action.triggered.connect(self.__open_file)
        save_action.triggered.connect(self.__save_file)

        file_menu.addAction(open_action)
        file_menu.addAction(save_action)
        file_menu.addAction(exit_action)
    
    def change_theme(self, theme_name):
        style = self.themes.get(theme_name, "")
        self.setStyleSheet(style)
        print(f"Применена тема: {theme_name}")

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
                try:
                    projects = self.model.by_type("IfcProject")
                    project_id = projects[0].GlobalId if projects else "unknown_project"
                    cache_dir = f"C:/ifc_cache/ifc_brep_{project_id}"

                    if os.path.exists(cache_dir):
                        shutil.rmtree(cache_dir)
                        self.bottom_panel.append(
                            "Сброс кэша геометрии выполнен. При следующем открытии модель будет перестроена.")
                except Exception as e:
                    self.bottom_panel.append(f"Внимание: Не удалось очистить кэш: {e}")
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

        self.viewport.select_and_rotate(global_id)
        
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

    def __on_hierarchy_dropped(self, dragged_item, target_item, element_guid, parent_guid):
        if not hasattr(self, 'model'):
            return

        self.bottom_panel.append(f"Attempting to move element...")

        result = edit_element_hierarchy(self.model, element_guid, parent_guid)

        if result.get("success"):
            self.bottom_panel.append(f"[Core] {result['message']}")

            self.tree.setUpdatesEnabled(False)

            old_parent = dragged_item.parent()

            if old_parent:
                old_parent.takeChild(old_parent.indexOfChild(dragged_item))
            else:
                self.tree.takeTopLevelItem(self.tree.indexOfTopLevelItem(dragged_item))

            target_item.addChild(dragged_item)
            target_item.setExpanded(True)

            self.tree.clearSelection()
            dragged_item.setSelected(True)
            self.tree.scrollToItem(dragged_item)

            self.tree.setUpdatesEnabled(True)

        else:
            self.bottom_panel.append(f"[Core Error] Failed to move: {result.get('error')}")
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
            brep_path = geom_data["dir_path"]
            elements_count = geom_data["elements_count"]
            
            self.bottom_panel.append(f"Геометрия создана! Элементов: {elements_count}")
            # Передаем файл во вьюпорт
            self.viewport.load_model(brep_path)
            self.bottom_panel.append("Успех: Модель загружена и отрисована!")

    def __on_viewport_element_selected(self, global_id):
        self.bottom_panel.append(f"Выбран элемент из 3D: {global_id}")

        target_item = None
        for i in range(self.tree.topLevelItemCount()):
            top_item = self.tree.topLevelItem(i)
            if top_item.data(0, Qt.ItemDataRole.UserRole) == global_id:
                target_item = top_item
                break
            target_item = self.__find_item_by_guid(top_item, global_id)
            if target_item:
                break

        if target_item:
            self.tree.setCurrentItem(target_item)
            self.tree.scrollToItem(target_item)
            self.__on_tree_double_click(target_item, 0)

    def __find_item_by_guid(self, parent_item, guid):
        """Рекурсивный поиск элемента по дереву"""
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.data(0, Qt.ItemDataRole.UserRole) == guid:
                return child
            found = self.__find_item_by_guid(child, guid)
            if found:
                return found
        return None

    def __on_element_moved(self, guid, dx, dy, dz):
        if not hasattr(self, 'model'):
            return

        self.bottom_panel.append(f"Перемещение объекта {guid} на вектор: [{dx:.2f}, {dy:.2f}, {dz:.2f}]")

        result = move_ifc_element(self.model, guid, dx, dy, dz)

        if result.get("success"):
            self.bottom_panel.append(f"[Core] {result['message']}")
        else:
            self.bottom_panel.append(f"[Core Error] {result.get('error')}")

    def closeEvent(self, event):
        """this method called before close app"""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("v_splitter_state", self.v_splitter.saveState())
        self.settings.setValue("h_splitter_state", self.h_splitter.saveState())

        super().closeEvent(event)