import ifcopenshell
import ifcopenshell.api


def update_element_properties(model: ifcopenshell.file, global_id: str, full_data: dict) -> dict:

    try:
        element = model.by_id(global_id)
        if not element:
            return {"success": False, "error": f"Element '{global_id}' not found."}

        if "Properties" not in full_data:
            return {"success": False, "error": "Missing 'Properties' block in the provided data."}

        properties_block = full_data["Properties"]

        if "Element Specific" in properties_block:
            base_attrs = properties_block["Element Specific"]

            if "Name" in base_attrs:
                element.Name = base_attrs["Name"] if base_attrs["Name"] else None

            if "Description" in base_attrs:
                element.Description = base_attrs["Description"] if base_attrs["Description"] else None

        for pset_name, pset_values in properties_block.items():
            if pset_name == "Element Specific":
                continue

            existing_pset = None
            if hasattr(element, "IsDefinedBy"):
                for rel in element.IsDefinedBy:
                    if rel.is_a("IfcRelDefinesByProperties"):
                        if getattr(rel.RelatingPropertyDefinition, "Name", None) == pset_name:
                            existing_pset = rel.RelatingPropertyDefinition
                            break

            if existing_pset:
                ifcopenshell.api.run(
                    "pset.edit_pset",
                    model,
                    pset=existing_pset,
                    properties=pset_values
                )
            else:
                new_pset = ifcopenshell.api.run(
                    "pset.add_pset",
                    model,
                    product=element,
                    name=pset_name
                )
                ifcopenshell.api.run(
                    "pset.edit_pset",
                    model,
                    pset=new_pset,
                    properties=pset_values
                )

        return {"success": True, "message": f"Properties for '{global_id}' successfully updated."}

    except Exception as e:
        return {"success": False, "error": f"Update error: {str(e)}"}