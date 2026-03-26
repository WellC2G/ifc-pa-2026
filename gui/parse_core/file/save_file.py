import ifcopenshell
from pathlib import Path


def save_ifc_model(model: ifcopenshell.file, file_path: str) -> dict:
    try:
        path = Path(file_path)

        path.parent.mkdir(parents=True, exist_ok=True)

        model.write(str(path))

        return {"success": True, "path": str(path)}

    except PermissionError:
        return {
            "success": False,
            "error": "Permission denied. Check if the IFC file is currently open in another application (e.g., Revit, Navisworks)."
        }
    except Exception as e:
        return {"success": False, "error": f"Failed to save IFC model: {str(e)}"}