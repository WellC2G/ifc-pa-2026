import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.placement
import numpy as np
from core.edit_data.edit_placement import move_ifc_element
from core.edit_data.edit_data import update_element_properties
from core.edit_data.edit_hierarchy import edit_element_hierarchy
from core.parse.get_properties_by_global_id import get_properties_by_global_id

class Command:
    def execute(self):
        pass
    def undo(self):
        pass
    def redo(self):
        return self.execute()
    @property
    def element_guid(self):
        return None

class MoveCommand(Command):
    def __init__(self, model, guid, dx, dy, dz, viewport_callback=None):
        self.model = model
        self.guid = guid
        self.dx = dx
        self.dy = dy
        self.dz = dz
        self.viewport_callback = viewport_callback

    @property
    def element_guid(self):
        return self.guid

    def execute(self):
        res = move_ifc_element(self.model, self.guid, self.dx, self.dy, self.dz)
        if res.get("success") and self.viewport_callback:
            # We don't visually move on initial execute because the mouse drag already moved it.
            pass
        return res

    def undo(self):
        res = move_ifc_element(self.model, self.guid, -self.dx, -self.dy, -self.dz)
        if res.get("success") and self.viewport_callback:
            self.viewport_callback(self.guid, -self.dx, -self.dy, -self.dz)
        return res

    def redo(self):
        res = move_ifc_element(self.model, self.guid, self.dx, self.dy, self.dz)
        if res.get("success") and self.viewport_callback:
            self.viewport_callback(self.guid, self.dx, self.dy, self.dz)
        return res

class PropertyEditCommand(Command):
    def __init__(self, model, guid, path, old_value, new_value):
        self.model = model
        self.guid = guid
        self.path = path # (group, key)
        self.old_value = old_value
        self.new_value = new_value

    @property
    def element_guid(self):
        return self.guid

    def _update_prop(self, value):
        full_data = get_properties_by_global_id(self.model, self.guid)
        _, group, key = self.path
        if group not in full_data["Properties"]:
            full_data["Properties"][group] = {}
        full_data["Properties"][group][key] = value
        return update_element_properties(self.model, self.guid, full_data)

    def execute(self):
        return self._update_prop(self.new_value)

    def undo(self):
        return self._update_prop(self.old_value)

class HierarchyCommand(Command):
    def __init__(self, model, element_guid, old_parent_guid, new_parent_guid, main_window_callback=None):
        self.model = model
        self.element_guid_val = element_guid
        self.old_parent_guid = old_parent_guid
        self.new_parent_guid = new_parent_guid
        self.callback = main_window_callback

    @property
    def element_guid(self):
        return self.element_guid_val

    def execute(self):
        res = edit_element_hierarchy(self.model, self.element_guid_val, self.new_parent_guid)
        if res.get("success") and self.callback:
            # Only visual if it's a redo (initial drop handles its own UI)
            pass
        return res
        
    def redo(self):
        res = edit_element_hierarchy(self.model, self.element_guid_val, self.new_parent_guid)
        if res.get("success") and self.callback:
            self.callback(self.element_guid_val, self.new_parent_guid)
        return res

    def undo(self):
        res = edit_element_hierarchy(self.model, self.element_guid_val, self.old_parent_guid)
        if res.get("success") and self.callback:
            self.callback(self.element_guid_val, self.old_parent_guid)
        return res

class BatchPropertyEditCommand(Command):
    def __init__(self, model, guids, prop_name, new_value, tree_update_callback=None):
        self.model = model
        self.guids = guids
        self.prop_name = prop_name
        self.new_value = new_value
        self.old_states = {} # guid -> old_value
        self.tree_update_callback = tree_update_callback

    @property
    def element_guid(self):
        return self.guids[0] if self.guids else None

    def _get_current_value(self, element):
        # 1. Direct attributes
        if hasattr(element, self.prop_name):
            return getattr(element, self.prop_name)
        
        # 2. Property Sets
        for definition in element.IsDefinedBy:
            if definition.is_a("IfcRelDefinesByProperties"):
                property_set = definition.RelatingPropertyDefinition
                if property_set.is_a("IfcPropertySet"):
                    for prop in property_set.HasProperties:
                        if prop.Name == self.prop_name:
                            if prop.is_a("IfcPropertySingleValue") and prop.NominalValue:
                                return prop.NominalValue.wrappedValue
        return None

    def _update_element(self, element, value):
        if hasattr(element, self.prop_name):
            try:
                setattr(element, self.prop_name, value)
                return True
            except:
                return False

        for definition in element.IsDefinedBy:
            if definition.is_a("IfcRelDefinesByProperties"):
                property_set = definition.RelatingPropertyDefinition
                if property_set.is_a("IfcPropertySet"):
                    for prop in property_set.HasProperties:
                        if prop.Name == self.prop_name:
                            if prop.is_a("IfcPropertySingleValue"):
                                ifc_type = prop.NominalValue.is_a() if prop.NominalValue else "IfcLabel"
                                prop.NominalValue = self.model.create_entity(ifc_type, value)
                                return True
        return False

    def execute(self):
        self.old_states = {}
        success_count = 0
        for guid in self.guids:
            el = self.model.by_guid(guid)
            if el:
                self.old_states[guid] = self._get_current_value(el)
                if self._update_element(el, self.new_value):
                    success_count += 1
                    
        if self.tree_update_callback and self.prop_name == "Name":
            for guid in self.guids:
                self.tree_update_callback(guid, self.new_value)
                
        return {"success": True, "message": f"Updated {success_count} elements"}

    def undo(self):
        for guid, old_val in self.old_states.items():
            el = self.model.by_guid(guid)
            if el:
                self._update_element(el, old_val)
                
        if self.tree_update_callback and self.prop_name == "Name":
            for guid, old_val in self.old_states.items():
                self.tree_update_callback(guid, old_val)
                
        return {"success": True, "message": "Batch edit undone"}

class CommandManager:
    def __init__(self):
        self.undo_stack = []
        self.redo_stack = []

    def execute(self, command):
        result = command.execute()
        if result.get("success"):
            self.undo_stack.append(command)
            self.redo_stack.clear()
        return result

    def undo(self):
        if not self.undo_stack:
            return {"success": False, "error": "Nothing to undo"}
        
        command = self.undo_stack.pop()
        result = command.undo()
        if result.get("success"):
            self.redo_stack.append(command)
            result["command"] = command
        else:
            self.undo_stack.append(command)
        return result

    def redo(self):
        if not self.redo_stack:
            return {"success": False, "error": "Nothing to redo"}
        
        command = self.redo_stack.pop()
        result = command.redo()
        if result.get("success"):
            self.undo_stack.append(command)
            result["command"] = command
        else:
            self.redo_stack.append(command)
        return result

    def can_undo(self):
        return len(self.undo_stack) > 0

    def can_redo(self):
        return len(self.redo_stack) > 0
