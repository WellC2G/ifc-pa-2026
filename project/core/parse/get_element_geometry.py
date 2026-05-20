import ifcopenshell
import ifcopenshell.geom
import tempfile
import multiprocessing
import concurrent.futures
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
        import ifcopenshell.util.unit
        unit_scale = ifcopenshell.util.unit.calculate_unit_scale(model)
        print(f"Model unit scale: {unit_scale}")

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

        def write_brep(file_path, data):
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(data)

        # Функция для масштабирования BREP если нужно
        from OCC.Core.gp import gp_Trsf, gp_Pnt
        from OCC.Core.BRepBuilderAPI import BRepBuilderAPI_Transform
        from OCC.Core.BRepTools import breptools
        from OCC.Core.BRep import BRep_Builder
        from OCC.Core.TopoDS import TopoDS_Shape
        import io

        def scale_shape_to_meters(brep_data, scale):
            if abs(scale - 1.0) < 1e-9:
                return brep_data
            
            builder = BRep_Builder()
            shape = TopoDS_Shape()
            
            # Читаем из строки
            with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.brep') as tmp:
                tmp.write(brep_data)
                tmp_path = tmp.name
            
            try:
                breptools.Read(shape, tmp_path, builder)
                
                trsf = gp_Trsf()
                trsf.SetScale(gp_Pnt(0,0,0), scale)
                
                transformed_shape = BRepBuilderAPI_Transform(shape, trsf).Shape()
                
                with tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.brep') as tmp2:
                    tmp2_path = tmp2.name
                
                breptools.Write(transformed_shape, tmp2_path)
                with open(tmp2_path, 'r') as f:
                    new_data = f.read()
                
                Path(tmp_path).unlink(missing_ok=True)
                Path(tmp2_path).unlink(missing_ok=True)
                return new_data
            except:
                return brep_data

        with concurrent.futures.ThreadPoolExecutor(max_workers=num_cores) as executor:
            futures = []
            while True:
                shape = iterator.get()
                global_id = shape.guid

                brep_string = shape.geometry.brep_data

                if brep_string:
                    # МАСШТАБИРУЕМ В МЕТРЫ ПЕРЕД ЗАПИСЬЮ
                    final_brep = scale_shape_to_meters(brep_string, unit_scale)
                    
                    file_path = cache_folder / f"{global_id}.brep"
                    futures.append(executor.submit(write_brep, file_path, final_brep))
                    elements_count += 1

                if not iterator.next():
                    break
            
            concurrent.futures.wait(futures)

        print(f"Successfully generated {elements_count} B-Rep files.")

        return {
            "dir_path": str(cache_folder),
            "elements_count": elements_count
        }

    except Exception as e:
        return {"error": f"Error generating B-Rep: {str(e)}"}