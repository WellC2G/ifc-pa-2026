import ifcopenshell
import ifcopenshell.api

def edit_element_hierarchy(model: ifcopenshell.file, element_guid: str, new_parent_guid: str) -> dict:
    try:
        element = model.by_guid(element_guid)
        new_parent = model.by_guid(new_parent_guid)

        if not element:
            return {"success": False, "error": f"Element with GUID {element_guid} not found."}
        if not new_parent:
            return {"success": False, "error": f"New parent with GUID {new_parent_guid} not found."}

        if element_guid == new_parent_guid:
            return {"success": False, "error": "Element cannot be its own parent."}

        try:
            ifcopenshell.api.run("spatial.unassign_container", model, product=element)
        except Exception:
            pass

        try:
            ifcopenshell.api.run("aggregate.unassign_object", model, product=element)
        except Exception:
            pass

        is_spatial_parent = new_parent.is_a("IfcSpatialElement") or new_parent.is_a("IfcSpatialStructureElement")
        is_physical_element = element.is_a("IfcElement")

        if is_spatial_parent and is_physical_element:
            ifcopenshell.api.run(
                "spatial.assign_container",
                model,
                products=[element],
                relating_structure=new_parent
            )
        else:
            ifcopenshell.api.run(
                "aggregate.assign_object",
                model,
                products=[element],
                relating_object=new_parent
            )

        element_name = getattr(element, "Name", element.is_a())
        parent_name = getattr(new_parent, "Name", new_parent.is_a())

        return {
            "success": True,
            "message": f"Success: [{element_name}] moved to [{parent_name}]"
        }

    except Exception as e:
        return {"success": False, "error": f"Critical core error: {str(e)}"}