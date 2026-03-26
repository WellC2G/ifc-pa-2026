import ifcopenshell
import ifcopenshell.geom
import numpy as np
import pyvista as pv
import tempfile
import multiprocessing
from pathlib import Path


def get_element_geometry(model: ifcopenshell.file) -> dict:
    try:
        temp_dir = Path(tempfile.gettempdir())

        projects = model.by_type("IfcProject")
        project_id = projects[0].GlobalId if projects else "unknown_project"

        file_path = temp_dir / f"ifc_model_{project_id}.vtm"

        if file_path.exists():
            print(f"Cache found! Fast loading from: {file_path}")
            cached_model = pv.read(str(file_path))
            return {
                "file_path": str(file_path),
                "elements_count": cached_model.n_blocks
            }

        print("Cache not found. Starting geometry generation...")

        settings = ifcopenshell.geom.settings()
        settings.set("use-world-coords", True)
        settings.set("boolean-attempt-2d", True)
        settings.set("weld-vertices", True)
        settings.set("mesher-linear-deflection", 0.3)
        settings.set("mesher-angular-deflection", 0.5)

        num_cores = multiprocessing.cpu_count()
        iterator = ifcopenshell.geom.iterator(settings, model, num_cores)

        if not iterator.initialize():
            return {"error": "The model has no 3D geometry or the file is corrupted."}

        multiblock = pv.MultiBlock()

        while True:
            shape = iterator.get()
            global_id = shape.guid

            verts_np = np.array(shape.geometry.verts).reshape((-1, 3))
            faces_np = np.array(shape.geometry.faces).reshape((-1, 3))

            faces_pv = np.empty((faces_np.shape[0], 4), dtype=int)
            faces_pv[:, 0] = 3
            faces_pv[:, 1:] = faces_np
            faces_pv = faces_pv.flatten()

            mesh = pv.PolyData(verts_np, faces_pv)
            multiblock[global_id] = mesh

            if not iterator.next():
                break

        multiblock.save(str(file_path))
        print("Geometry successfully generated and saved to cache.")

        return {
            "file_path": str(file_path),
            "elements_count": multiblock.n_blocks
        }

    except Exception as e:
        return {"error": f"Error generating full geometry: {str(e)}"}