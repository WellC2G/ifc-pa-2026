import ifcopenshell
import ifcopenshell.geom
import tempfile
import multiprocessing
from pathlib import Path

def get_element_geometry(model: ifcopenshell.file) -> dict:
    try:
        temp_dir = Path(tempfile.gettempdir())
        projects = model.by_type("IfcProject")
        project_id = projects[0].GlobalId if projects else "unknown_project"
        cache_folder = temp_dir / f"ifc_brep_{project_id}"

        if cache_folder.exists() and any(cache_folder.iterdir()):
            print(f"B-Rep cache found: {cache_folder}")
            brep_files = list(cache_folder.glob("*.brep"))

            return {
                "dir_path": str(cache_folder),
                "elements_count": len(brep_files)
            }

        print("Starting B-Rep generation...")
        cache_folder.mkdir(parents=True, exist_ok=True)
        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)
        settings.set("iterator-output", ifcopenshell.ifcopenshell_wrapper.SERIALIZED)
        settings.set("boolean-attempt-2d", True)

        exclude_classes = [
            "IfcSpace",
            "IfcOpeningElement",
            "IfcAnnotation",
            "IfcGrid"
        ]

        elements_to_exclude = []
        for cls_name in exclude_classes:
            elements_to_exclude.extend(model.by_type(cls_name))

        num_cores = multiprocessing.cpu_count()
        iterator = ifcopenshell.geom.iterator(
            settings,
            model,
            num_threads=num_cores,
            exclude=elements_to_exclude
        )

        if not iterator.initialize():
            return {"error": "The model has no 3D geometry or the file is corrupted."}

        elements_count = 0

        while True:
            shape = iterator.get()
            global_id = shape.guid

            brep_string = shape.geometry.brep_data

            if brep_string:
                file_path = cache_folder / f"{global_id}.brep"
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(brep_string)
                elements_count += 1

            if not iterator.next():
                break

        print(f"Successfully generated {elements_count} B-Rep files.")

        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"+str(cache_folder)+"!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")

        return {
            "dir_path": str(cache_folder),
            "elements_count": elements_count
        }

    except Exception as e:
        return {"error": f"Error generating B-Rep: {str(e)}"}