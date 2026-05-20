from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, 
    QPushButton, QListWidget, QListWidgetItem, QLabel,
    QMessageBox, QGroupBox, QFormLayout
)
from PyQt6.QtCore import Qt, pyqtSignal
import ifcopenshell

class FindEditWindow(QWidget):
    # Signal to notify main window to select and focus on an element
    element_selected_signal = pyqtSignal(str)
    # Signal to notify main window that properties were updated (to refresh UI if needed)
    properties_updated_signal = pyqtSignal()

    def __init__(self, model, parent=None):
        super().__init__(parent)
        self.model = model
        self.setWindowTitle("Find and Edit Elements")
        self.resize(500, 600)
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
        self.results_list = QListWidget()
        self.results_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.results_list.itemSelectionChanged.connect(self.__on_selection_changed)
        layout.addWidget(QLabel("Search Results (Hold Ctrl for multi-selection):"))
        layout.addWidget(self.results_list)

        # --- Batch Edit Section ---
        edit_group = QGroupBox("Batch Edit Properties")
        edit_layout = QFormLayout()
        
        self.prop_name_input = QLineEdit()
        self.prop_name_input.setPlaceholderText("e.g. Name, Description, LoadBearing")
        
        self.prop_value_input = QLineEdit()
        self.prop_value_input.setPlaceholderText("New value...")
        
        apply_btn = QPushButton("Apply to Selected")
        apply_btn.clicked.connect(self.__on_apply_properties)
        
        edit_layout.addRow("Property Name:", self.prop_name_input)
        edit_layout.addRow("New Value:", self.prop_value_input)
        edit_layout.addWidget(apply_btn)
        
        edit_group.setLayout(edit_layout)
        layout.addWidget(edit_group)

    def __on_search(self):
        query = self.search_input.text().strip().lower()
        if not query:
            return

        self.results_list.clear()
        
        # We search through all products
        elements = self.model.by_type("IfcProduct")
        
        for el in elements:
            name = str(el.Name).lower() if el.Name else ""
            guid = str(el.GlobalId).lower()
            ifc_type = el.is_a().lower()
            
            if query in name or query in guid or query in ifc_type:
                display_text = f"[{el.is_a()}] {el.Name if el.Name else 'Unnamed'} ({el.GlobalId})"
                item = QListWidgetItem(display_text)
                item.setData(Qt.ItemDataRole.UserRole, el.GlobalId)
                self.results_list.addItem(item)

    def __on_selection_changed(self):
        selected_items = self.results_list.selectedItems()
        if len(selected_items) == 1:
            guid = selected_items[0].data(Qt.ItemDataRole.UserRole)
            self.element_selected_signal.emit(guid)

    def __on_apply_properties(self):
        selected_items = self.results_list.selectedItems()
        if not selected_items:
            QMessageBox.warning(self, "Error", "No elements selected.")
            return

        prop_name = self.prop_name_input.text().strip()
        prop_value = self.prop_value_input.text().strip()

        if not prop_name:
            QMessageBox.warning(self, "Error", "Please enter a property name.")
            return

        guids = [item.data(Qt.ItemDataRole.UserRole) for item in selected_items]
        elements = [self.model.by_guid(g) for g in guids]

        # Check if all selected elements have this property
        # For simplicity in this implementation, we check direct attributes 
        # (like Name, Description) and Property Sets.
        
        for el in elements:
            if not self.__has_property(el, prop_name):
                QMessageBox.critical(self, "Error", 
                    f"Element {el.GlobalId} does not have property '{prop_name}'. "
                    "Batch edit cancelled.")
                return

        # Apply changes
        count = 0
        try:
            for el in elements:
                if self.__update_element_property(el, prop_name, prop_value):
                    count += 1
            
            QMessageBox.information(self, "Success", f"Updated {count} elements.")
            self.properties_updated_signal.emit()
        except ValueError as ve:
            QMessageBox.critical(self, "Type Error", str(ve))
        except Exception as e:
            QMessageBox.critical(self, "Error", f"An unexpected error occurred: {e}")

    def __has_property(self, element, prop_name):
        # 1. Check direct attributes
        if hasattr(element, prop_name):
            return True
        
        # 2. Check Property Sets
        for definition in element.IsDefinedBy:
            if definition.is_a("IfcRelDefinesByProperties"):
                property_set = definition.RelatingPropertyDefinition
                if property_set.is_a("IfcPropertySet"):
                    for prop in property_set.HasProperties:
                        if prop.Name == prop_name:
                            return True
        return False

    def __update_element_property(self, element, prop_name, prop_value):
        # 1. Update direct attributes
        if hasattr(element, prop_name):
            try:
                # Basic type detection for attributes
                attr_val = getattr(element, prop_name)
                converted_val = self.__validate_and_convert(prop_value, type(attr_val))
                setattr(element, prop_name, converted_val)
                return True
            except Exception as e:
                print(f"Attr update failed: {e}")

        # 2. Update Property Sets
        updated = False
        for definition in element.IsDefinedBy:
            if definition.is_a("IfcRelDefinesByProperties"):
                property_set = definition.RelatingPropertyDefinition
                if property_set.is_a("IfcPropertySet"):
                    for prop in property_set.HasProperties:
                        if prop.Name == prop_name:
                            if prop.is_a("IfcPropertySingleValue"):
                                try:
                                    current_val = prop.NominalValue
                                    if current_val:
                                        ifc_type = current_val.is_a()
                                        # Map IFC types to Python types for validation
                                        target_py_type = self.__get_python_type_from_ifc(ifc_type)
                                        
                                        validated_val = self.__validate_and_convert(prop_value, target_py_type)
                                        
                                        # Create new value entity
                                        new_val = self.model.create_entity(ifc_type, validated_val)
                                        prop.NominalValue = new_val
                                    else:
                                        # Default to IfcLabel if no previous value type known
                                        prop.NominalValue = self.model.create_entity("IfcLabel", prop_value)
                                    updated = True
                                except Exception as e:
                                    raise ValueError(f"Property '{prop_name}' expects {current_val.is_a() if current_val else 'string'}. Error: {e}")
        return updated

    def __get_python_type_from_ifc(self, ifc_type):
        if "Integer" in ifc_type: return int
        if "Real" in ifc_type or "Length" in ifc_type or "Area" in ifc_type or "Volume" in ifc_type: return float
        if "Boolean" in ifc_type or "Logical" in ifc_type: return bool
        return str

    def __validate_and_convert(self, value, target_type):
        if target_type == bool:
            v = value.lower()
            if v in ("true", "1", "yes", "t"): return True
            if v in ("false", "0", "no", "f"): return False
            raise ValueError(f"Cannot convert '{value}' to Boolean")
        
        if target_type == int:
            return int(value)
        
        if target_type == float:
            return float(value)
            
        return str(value)
