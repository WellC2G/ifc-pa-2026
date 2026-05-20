import os
import glob
import concurrent.futures
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, QTimer, Qt

from OCC.Display.backend import load_backend

from OCC.Core.AIS import AIS_Shape
from OCC.Core.Quantity import (
    Quantity_NOC_CYAN, 
    Quantity_Color, 
    Quantity_NOC_GOLDENROD,
    Quantity_NOC_ORANGE,
    Quantity_NOC_RED
)
from OCC.Core.Prs3d import Prs3d_LineAspect
from OCC.Core.Aspect import Aspect_TOL_SOLID
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib

load_backend("pyqt6")

from OCC.Core.gp import gp_Vec, gp_Trsf
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Display.qtDisplay import qtViewer3d
from OCC.Core.BRepTools import breptools
from OCC.Core.BRep import BRep_Builder
from OCC.Core.TopoDS import TopoDS_Shape


def _load_brep_file(file_path):
    builder = BRep_Builder()
    shape = TopoDS_Shape()
    breptools.Read(shape, file_path, builder)
    return file_path, shape

class IFCViewport(QWidget):
    element_selected_signal = pyqtSignal(str)

    element_moved_signal = pyqtSignal(str, float, float, float)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = qtViewer3d(self)
        self.layout.addWidget(self.canvas)

        self.ais_dict = {}
        self._is_updating_selection = False

        # === ПЕРЕМЕННЫЕ ДЛЯ ПЕРЕТАСКИВАНИЯ ===
        self._is_object_dragging = False
        self._dragged_ais = None
        self._drag_start_x3d = 0.0
        self._drag_start_y3d = 0.0
        self._drag_start_z3d = 0.0
        self._original_location = None

        # === ФЛАГ ИНИЦИАЛИЗАЦИИ ОКНА (исправление ошибки) ===
        self._is_configured = False

        # === ПЕРЕХВАТ СОБЫТИЙ МЫШИ ===
        self._original_mouseDoubleClickEvent = self.canvas.mouseDoubleClickEvent
        self.canvas.mouseDoubleClickEvent = self.on_canvas_double_click

        self._original_mousePressEvent = self.canvas.mousePressEvent
        self.canvas.mousePressEvent = self.on_canvas_mouse_press

        self._original_mouseMoveEvent = self.canvas.mouseMoveEvent
        self.canvas.mouseMoveEvent = self.on_canvas_mouse_move

        self._original_mouseReleaseEvent = self.canvas.mouseReleaseEvent
        self.canvas.mouseReleaseEvent = self.on_canvas_mouse_release

        self.cx = 0.0
        self.cy = 0.0
        self.cz = 0.0

    def showEvent(self, event):
        super().showEvent(event)

        # Проверяем, инициализировал ли qtViewer3d сам себя
        if not hasattr(self.canvas, '_display') or self.canvas._display is None:
            self.canvas.InitDriver()

        # Настраиваем фон и сохраняем ссылку на display только один раз
        if not self._is_configured:
            self.display = self.canvas._display
            if self.display:
                self.display.set_bg_gradient_color([51, 51, 51], [51, 51, 51])
                self.display.FitAll()
                self._is_configured = True

        self.canvas.update()

    def load_model(self, dir_path: str):
        self.display.EraseAll()
        self.ais_dict.clear()

        builder = BRep_Builder()
        brep_files = glob.glob(os.path.join(dir_path, "*.brep"))

        for file_path in brep_files:
            shape = TopoDS_Shape()
            breptools.Read(shape, file_path, builder)

            my_ais_shape = AIS_Shape(shape)
            drawer = my_ais_shape.Attributes()

            drawer.SetFaceBoundaryDraw(True)
            cyan_color = Quantity_Color(Quantity_NOC_CYAN)

            if drawer.FaceBoundaryAspect() is None:
                new_aspect = Prs3d_LineAspect(cyan_color, Aspect_TOL_SOLID, 1.5)
                drawer.SetFaceBoundaryAspect(new_aspect)
            else:
                drawer.FaceBoundaryAspect().SetColor(cyan_color)
                drawer.FaceBoundaryAspect().SetWidth(1.5)

            self.display.Context.Display(my_ais_shape, False)

            filename = os.path.basename(file_path)
            global_id = os.path.splitext(filename)[0]
            self.ais_dict[my_ais_shape] = global_id

        self.display.Context.UpdateCurrentViewer()
        self.display.FitAll()

    def on_canvas_double_click(self, event):
        self._original_mouseDoubleClickEvent(event)

        if event.button() == Qt.MouseButton.LeftButton:

            if self._is_updating_selection:
                return

            self.display.Context.InitSelected()
            if self.display.Context.MoreSelected():
                selected_ais = self.display.Context.SelectedInteractive()

                found_guid = None
                for ais, guid in self.ais_dict.items():
                    if str(ais.this) == str(selected_ais.this) or ais == selected_ais:
                        found_guid = guid
                        break

                if found_guid:
                    QTimer.singleShot(10, lambda g=found_guid: self.element_selected_signal.emit(g))

    def select_and_rotate(self, global_id):
        target_ais = None
        for ais, guid in self.ais_dict.items():
            if guid == global_id:
                target_ais = ais
                break

        self._is_updating_selection = True

        if target_ais:
            self.display.Context.ClearSelected(False)
            self.display.Context.SetSelected(target_ais, True)
            self.display.Context.UpdateCurrentViewer()

            bbox = Bnd_Box()
            
            # Apply dynamic location to the shape before computing the bounding box
            if self.display.Context.HasLocation(target_ais):
                loc = self.display.Context.Location(target_ais)
                transformed_shape = target_ais.Shape().Moved(loc)
                brepbndlib.Add(transformed_shape, bbox)
            else:
                brepbndlib.Add(target_ais.Shape(), bbox)
                
            xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
            self.cx = (xmin + xmax) / 2.0
            self.cy = (ymin + ymax) / 2.0
            self.cz = (zmin + zmax) / 2.0

            self.display.View.SetAt(self.cx, self.cy, self.cz)

            max_size = max(xmax - xmin, ymax - ymin, zmax - zmin)
            if max_size > 0:
                self.display.View.SetSize(max_size * 1.5)

            self.display.View.ZFitAll()
        else:
            self.display.Context.ClearSelected(True)

        self._is_updating_selection = False

    def move_object_visually(self, global_id, dx, dy, dz):
        target_ais = None
        for ais, guid in self.ais_dict.items():
            if guid == global_id:
                target_ais = ais
                break

        if target_ais:
            translation = gp_Trsf()
            translation.SetTranslation(gp_Vec(dx, dy, dz))

            if self.display.Context.HasLocation(target_ais):
                orig_trsf = self.display.Context.Location(target_ais).Transformation()
            else:
                orig_trsf = gp_Trsf()

            new_trsf = translation.Multiplied(orig_trsf)
            new_loc = TopLoc_Location(new_trsf)

            self.display.Context.SetLocation(target_ais, new_loc)
            self.display.Context.UpdateCurrentViewer()

    def on_canvas_mouse_press(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.button() == Qt.MouseButton.LeftButton:
            x, y = event.pos().x(), event.pos().y()

            self.display.Context.MoveTo(x, y, self.display.View, True)
            if self.display.Context.HasDetected():
                self._dragged_ais = self.display.Context.DetectedInteractive()
                self._is_object_dragging = True

                # ИСПОЛЬЗУЕМ БЕЗОПАСНУЮ ФУНКЦИЮ (без крашей)
                self._drag_start_x3d, self._drag_start_y3d, self._drag_start_z3d, _, _, _ = self.display.View.ConvertWithProj(
                    x, y)

                if self.display.Context.HasLocation(self._dragged_ais):
                    self._original_location = self.display.Context.Location(self._dragged_ais)
                else:
                    self._original_location = TopLoc_Location()

        self._original_mousePressEvent(event)

    def on_canvas_mouse_move(self, event):
        if self._is_object_dragging and self._dragged_ais:
            x, y = event.pos().x(), event.pos().y()

            # ИСПОЛЬЗУЕМ БЕЗОПАСНУЮ ФУНКЦИЮ
            curr_x3d, curr_y3d, curr_z3d, _, _, _ = self.display.View.ConvertWithProj(x, y)

            self._last_dx = curr_x3d - self._drag_start_x3d
            self._last_dy = curr_y3d - self._drag_start_y3d
            self._last_dz = curr_z3d - self._drag_start_z3d

            # БЕЗОПАСНАЯ МАТЕМАТИКА (чтобы объект не исчезал)
            translation = gp_Trsf()
            translation.SetTranslation(gp_Vec(self._last_dx, self._last_dy, self._last_dz))

            orig_trsf = self._original_location.Transformation()
            new_trsf = translation.Multiplied(orig_trsf)  # C++ метод умножения

            new_loc = TopLoc_Location(new_trsf)

            # Применение и обновление экрана
            self.display.Context.SetLocation(self._dragged_ais, new_loc)
            self.display.Context.UpdateCurrentViewer()
            return

        self._original_mouseMoveEvent(event)

    def on_canvas_mouse_release(self, event):
        # Завершаем перетаскивание
        if self._is_object_dragging:
            if self._dragged_ais:

                moved_guid = None
                for ais, guid in self.ais_dict.items():
                    if str(ais.this) == str(self._dragged_ais.this) or ais == self._dragged_ais:
                        moved_guid = guid
                        break

                if moved_guid and (abs(self._last_dx) > 1e-8 or abs(self._last_dy) > 1e-8 or abs(self._last_dz) > 1e-8):
                    self.element_moved_signal.emit(moved_guid, self._last_dx, self._last_dy, self._last_dz)

            # Сбрасываем флаги
            self._is_object_dragging = False
            self._dragged_ais = None
            self._original_location = None
            self._last_dx = 0.0
            self._last_dy = 0.0
            self._last_dz = 0.0
            return

        self._original_mouseReleaseEvent(event)
        self._last_dz = 0.0
        return