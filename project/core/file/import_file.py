import ifcopenshell
import ifcopenshell.api
from core.edit_data.edit_hierarchy import edit_element_hierarchy

def import_ifc_model(main_model: ifcopenshell.file, file_path_to_import: str) -> dict:
    try:
        import_model = ifcopenshell.open(file_path_to_import)
        
        main_projects = main_model.by_type("IfcProject")
        if not main_projects:
            return {"success": False, "error": "Main model has no IfcProject."}
        
        main_project = main_projects[0]
        
        imported_elements = import_model.by_type("IfcElement")
        if not imported_elements:
            return {"success": False, "error": "Imported file has no physical elements (IfcElement)."}

        reuse_identities = {}
        appended_guids = []
        
        for element in imported_elements:
            try:
                # project.append_asset is ideal for merging types, materials, properties, and geometries
                new_element = ifcopenshell.api.run(
                    "project.append_asset",
                    main_model,
                    library=import_model,
                    element=element,
                    reuse_identities=reuse_identities
                )
                
                # Make the new element a child of the main IfcProject
                edit_element_hierarchy(main_model, new_element.GlobalId, main_project.GlobalId)
                
                appended_guids.append(new_element.GlobalId)
            except Exception as e:
                print(f"Failed to import element {element.GlobalId}: {e}")
        
        return {
            "success": True,
            "message": f"Successfully imported {len(appended_guids)} elements.",
            "appended_guids": appended_guids
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to import IFC model: {str(e)}"}
