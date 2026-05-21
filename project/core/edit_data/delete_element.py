import ifcopenshell
import ifcopenshell.api

def delete_ifc_element(model: ifcopenshell.file, guid: str) -> dict:
    """
    Completely removes an IFC element and its associated relationships.
    Uses ifcopenshell.api.root.remove_product for high-level compliance.
    """
    try:
        element = model.by_guid(guid)
        if not element:
            return {"success": False, "error": f"Element with GUID {guid} not found."}

        element_name = str(getattr(element, "Name", guid))
        element_type = element.is_a()

        # check if it is a product (most physical elements are)
        if element.is_a("IfcProduct"):
            ifcopenshell.api.run("root.remove_product", model, product=element)
        else:
            # fallback for non-product entities (e.g. types, relations etc)
            model.remove(element)

        return {
            "success": True, 
            "message": f"Successfully deleted {element_type} [{element_name}].",
            "guid": guid
        }

    except Exception as e:
        return {"success": False, "error": f"Failed to delete element: {str(e)}"}
