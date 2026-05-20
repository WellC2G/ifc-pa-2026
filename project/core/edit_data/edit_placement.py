import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.placement
import ifcopenshell.util.unit
import tempfile
import shutil
from pathlib import Path


def move_ifc_element(model: ifcopenshell.file, guid: str, dx: float, dy: float, dz: float) -> dict:
    try:
        element = model.by_guid(guid)
        if not element:
            return {"success": False, "error": f"Элемент с GUID {guid} не найден."}

        if not getattr(element, "ObjectPlacement", None):
            return {"success": False, "error": "У элемента нет ObjectPlacement."}

        # Получаем текущую локальную матрицу (в единицах модели)
        matrix = ifcopenshell.util.placement.get_local_placement(element.ObjectPlacement)

        # Получаем масштабный коэффициент модели (например, 0.001 для мм)
        scale = ifcopenshell.util.unit.calculate_unit_scale(model)

        # Конвертируем текущую матрицу в метры (SI)
        # Масштабируем только часть смещения (translation), если мы хотим работать в метрах
        matrix[0][3] *= scale
        matrix[1][3] *= scale
        matrix[2][3] *= scale

        # Добавляем дельту из вьюпорта (которая теперь всегда в метрах)
        matrix[0][3] += dx
        matrix[1][3] += dy
        matrix[2][3] += dz

        matrix_list = matrix.tolist()

        # Записываем обратно, указывая is_si=True
        # API само конвертирует метры обратно в единицы модели (мм и т.д.)
        ifcopenshell.api.run(
            "geometry.edit_object_placement",
            model,
            product=element,
            matrix=matrix_list,
            is_si=True
        )

        return {
            "success": True,
            "message": f"Смещение элемента {guid} выполнено (в памяти). [{dx:.2f}, {dy:.2f}, {dz:.2f}] м"
        }

    except Exception as e:
        return {"success": False, "error": f"Ошибка обновления координат: {str(e)}"}