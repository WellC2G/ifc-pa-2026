import ifcopenshell
import ifcopenshell.util.element


def get_properties_by_global_id(model: ifcopenshell.file, global_id: str) -> dict:
    try:
        ifc_object = model.by_id(global_id)

        if not ifc_object:
            return {"error": f"Объект с GlobalId '{global_id}' не найден в модели."}

    except Exception as e:
        return {"error": f"Сбой при поиске объекта '{global_id}': {str(e)}"}

    gui_data = {
        "Базовые атрибуты": {},
        "Наборы свойств (Property Sets)": {}
    }

    raw_attributes = ifc_object.get_info()
    for key, value in raw_attributes.items():
        if value is not None and isinstance(value, (str, int, float, bool)):
            gui_data["Базовые атрибуты"][key] = value

    psets = ifcopenshell.util.element.get_psets(ifc_object)

    if psets:
        for pset_name, properties in psets.items():
            properties.pop('id', None)

            if properties:
                gui_data["Наборы свойств (Property Sets)"][pset_name] = properties

    return gui_data