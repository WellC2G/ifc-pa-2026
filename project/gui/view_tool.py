from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
    QPushButton, QTreeWidget, QTreeWidgetItem, QLabel,
    QMessageBox, QGroupBox, QToolButton
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon
import ifcopenshell

class ViewWindow(QWidget):
    # Signal to notify main window to change element visibility
    visibility_changed_signal = pyqtSignal(str, bool) # guid, visible
    # Signal to notify main window to select and focus on an element
    element_selected_signal = pyqtSignal(str)

    def __init__(self, model, viewport, parent=None):
        super().__init__(parent)
        self.model = model
        self.viewport = viewport
        self.setWindowTitle("View - Visibility Control")
        self.resize(500, 600)
        self.visibility_states = {} # guid -> bool
        self.__init_ui()

    def __init_ui(self):
        layout = QVBoxLayout(self)

        # --- Search Section ---
        search_group = QGroupBox("Search Elements")
        search_layout = QVBoxLayout()
        
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by Name, GlobalID or Type...")
        self.search_input.returnPressed.connect(self.__on_search)
        
        search_btn = QPushButton("Search")
        search_btn.clicked.connect(self.__on_search)
        
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(search_btn)
        search_group.setLayout(search_layout)
        layout.addWidget(search_group)

        # --- Results Section ---
        self.results_tree = QTreeWidget()
        self.results_tree.setHeaderLabel("Elements")
        self.results_tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.results_tree.itemClicked.connect(self.__on_item_clicked)
        
        results_header_layout = QHBoxLayout()
        results_header_layout.addWidget(QLabel("Elements (Expand to see children):"))
        
        self.select_all_btn = QPushButton("Select All")
        self.select_all_btn.clicked.connect(self.__on_select_all)
        results_header_layout.addWidget(self.select_all_btn)
        
        layout.addLayout(results_header_layout)
        layout.addWidget(self.results_tree)

        # --- Batch Visibility Section ---
        visibility_group = QGroupBox("Visibility Control")
        visibility_layout = QHBoxLayout()
        
        hide_btn = QPushButton("Hide Selected")
        hide_btn.clicked.connect(lambda: self.__on_batch_visibility(False))
        
        unhide_btn = QPushButton("Unhide Selected")
        unhide_btn.clicked.connect(lambda: self.__on_batch_visibility(True))
        
        visibility_layout.addWidget(hide_btn)
        visibility_layout.addWidget(unhide_btn)
        
        visibility_group.setLayout(visibility_layout)
        layout.addWidget(visibility_group)

    def __on_search(self):
        query = self.search_input.text().strip().lower()
        if not query:
            return

        self.results_tree.clear()
        self.visited_guids = set() # Prevent infinite recursion and redundant top-level items
        
        # We search through all products and find matches
        elements = self.model.by_type("IfcProduct")
        
        for el in elements:
            # Skip if already added as a child of a previous search result
            if el.GlobalId in self.visited_guids:
                continue

            name = str(el.Name).lower() if getattr(el, "Name", None) else ""
            guid = str(el.GlobalId).lower()
            ifc_type = el.is_a().lower()
            
            if query in name or query in guid or query in ifc_type:
                self.__add_element_to_tree(el)

    def __add_element_to_tree(self, element, parent_item=None):
        if not element or element.GlobalId in self.visited_guids and parent_item is None:
            return None
        
        self.visited_guids.add(element.GlobalId)
        
        display_text = f"[{element.is_a()}] {element.Name if getattr(element, 'Name', None) else 'Unnamed'} ({element.GlobalId})"
        
        if parent_item is None:
            item = QTreeWidgetItem(self.results_tree, [display_text])
        else:
            item = QTreeWidgetItem(parent_item, [display_text])
            
        item.setData(0, Qt.ItemDataRole.UserRole, element.GlobalId)
        
        # Add eye icon button
        self.__add_eye_button(item)
        
        # Optionally add children if they exist (spatial structure)
        if hasattr(element, "ContainsElements"):
            for rel in element.ContainsElements:
                for sub_el in getattr(rel, "RelatedElements", []):
                    self.__add_element_to_tree(sub_el, item)
        
        if hasattr(element, "IsDecomposedBy"):
            for rel in element.IsDecomposedBy:
                for sub_el in getattr(rel, "RelatedObjects", []):
                    if sub_el.is_a("IfcProduct"):
                        self.__add_element_to_tree(sub_el, item)
                        
        return item

    def __add_eye_button(self, item):
        btn = QToolButton()
        btn.setFixedSize(24, 24)
        guid = item.data(0, Qt.ItemDataRole.UserRole)
        is_visible = self.visibility_states.get(guid, True)
        
        self.__update_eye_icon(btn, is_visible)
        btn.clicked.connect(lambda: self.__toggle_visibility(item))
        
        if self.results_tree.columnCount() < 2:
            self.results_tree.setColumnCount(2)
            self.results_tree.setColumnWidth(1, 40)
            self.results_tree.setHeaderLabels(["Element", "View"])
            
        self.results_tree.setItemWidget(item, 1, btn)

    def __update_eye_icon(self, btn, is_visible):
        # More robust icon handling to prevent crashes on different Qt versions/environments
        try:
            # Use theme icons if available, otherwise fallback to text
            if is_visible:
                icon = QIcon.fromTheme("view-visible", QIcon.fromTheme("visibility"))
            else:
                icon = QIcon.fromTheme("view-hidden", QIcon.fromTheme("visibility-off"))
            
            if not icon.isNull():
                btn.setIcon(icon)
                btn.setText("")
            else:
                btn.setText("👁" if is_visible else "❌")
        except Exception:
            btn.setText("👁" if is_visible else "❌")

    def __toggle_visibility(self, item):
        guid = item.data(0, Qt.ItemDataRole.UserRole)
        current_visible = self.visibility_states.get(guid, True)
        new_visible = not current_visible
        
        self.__set_recursive_visibility(item, new_visible)

    def __set_recursive_visibility(self, item, visible):
        guid = item.data(0, Qt.ItemDataRole.UserRole)
        self.visibility_states[guid] = visible
        
        # Update icon
        btn = self.results_tree.itemWidget(item, 1)
        if btn:
            self.__update_eye_icon(btn, visible)
            
        # Notify viewport
        self.visibility_changed_signal.emit(guid, visible)
        
        # Recurse for children
        for i in range(item.childCount()):
            self.__set_recursive_visibility(item.child(i), visible)

    def __on_item_clicked(self, item, column):
        if column == 0:
            guid = item.data(0, Qt.ItemDataRole.UserRole)
            self.element_selected_signal.emit(guid)

    def __on_select_all(self):
        self.results_tree.selectAll()

    def __on_batch_visibility(self, visible):
        selected_items = self.results_tree.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "No elements selected.")
            return

        for item in selected_items:
            self.__set_recursive_visibility(item, visible)

    def sync_visibility(self, guid, visible):
        """Called by main window when visibility is changed elsewhere (e.g. main tree)"""
        self.visibility_states[guid] = visible
        # Find item in results and update icon
        item = self.__find_item_by_guid(self.results_tree.invisibleRootItem(), guid)
        if item:
            btn = self.results_tree.itemWidget(item, 1)
            if btn:
                self.__update_eye_icon(btn, visible)

    def __find_item_by_guid(self, parent_item, guid):
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            if child.data(0, Qt.ItemDataRole.UserRole) == guid:
                return child
            found = self.__find_item_by_guid(child, guid)
            if found:
                return found
        return None
