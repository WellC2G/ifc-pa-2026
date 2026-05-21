import os
import glob
import re
import concurrent.futures
from PyQt6.QtWidgets import QWidget, QVBoxLayout
from PyQt6.QtCore import pyqtSignal, QTimer, Qt

from OCC.Display.backend import load_backend

from OCC.Core.AIS import AIS_Shape
from OCC.Core.Quantity import (
    Quantity_NOC_CYAN,
    Quantity_Color,
    Quantity_NOC_GOLDENROD,
    Quantity_NOC_WHITE,
    Quantity_NOC_BLACK,
    Quantity_TOC_RGB
)
from OCC.Core.Prs3d import Prs3d_LineAspect
from OCC.Core.Aspect import Aspect_TOL_SOLID
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib

load_backend("pyqt6")

from OCC.Core.gp import gp_Vec, gp_Trsf, gp_Ax2, gp_Pnt, gp_Dir
from OCC.Core.TopLoc import TopLoc_Location
from OCC.Display.qtDisplay import qtViewer3d
from OCC.Core.BRepTools import breptools
from OCC.Core.BRep import BRep_Builder
from OCC.Core.TopoDS import TopoDS_Shape, TopoDS_Compound
from OCC.Core.BRepPrimAPI import BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeCone


def _load_brep_file(file_path):
    builder = BRep_Builder()
    shape = TopoDS_Shape()
    breptools.Read(shape, file_path, builder)
    return file_path, shape

def _is_same_ais(ais1, ais2):
    if ais1 is None or ais2 is None:
        return False
    if ais1 == ais2:
        return True
    try:
        s1 = str(ais1.this)
        s2 = str(ais2.this)
        m1 = re.search(r'0x[0-9a-fA-F]+', s1)
        m2 = re.search(r'0x[0-9a-fA-F]+', s2)
        if m1 and m2:
            return m1.group(0).lower() == m2.group(0).lower()
        return s1 == s2
    except:
        return False

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

        # === ПЕРЕМЕННЫЕ GIZMO ===
        self.gizmo_x = None
        self.gizmo_y = None
        self.gizmo_z = None
        self._gizmo_visible = False
        self._drag_axis = None
        self.gizmo_cx = 0.0
        self.gizmo_cy = 0.0
        self.gizmo_cz = 0.0
        self.gizmo_size = 1.0

        # Enable focus so it can receive key events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

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
        self._last_selected_ais = None

    def _update_selection_visual(self, new_ais):
        """Helper to manage manual color highlighting (White/Black for selection, Goldenrod/Cyan for default)."""
        goldenrod = Quantity_Color(Quantity_NOC_GOLDENROD)
        cyan = Quantity_Color(Quantity_NOC_CYAN)
        white = Quantity_Color(Quantity_NOC_WHITE)
        black = Quantity_Color(Quantity_NOC_BLACK)

        if self._last_selected_ais and not _is_same_ais(self._last_selected_ais, new_ais):
            # Revert old selection to default: Goldenrod surface, Cyan wireframe
            self.display.Context.SetColor(self._last_selected_ais, goldenrod, False)
            drawer = self._last_selected_ais.Attributes()
            if drawer.FaceBoundaryDraw():
                drawer.FaceBoundaryAspect().SetColor(cyan)
            self.display.Context.Redisplay(self._last_selected_ais, False)
        
        self._last_selected_ais = new_ais
        if self._last_selected_ais:
            # Apply selection style: White surface, Black wireframe
            self.display.Context.SetColor(self._last_selected_ais, white, False)
            drawer = self._last_selected_ais.Attributes()
            if drawer.FaceBoundaryDraw():
                drawer.FaceBoundaryAspect().SetColor(black)
            self.display.Context.Redisplay(self._last_selected_ais, False)
        
        self.display.Context.UpdateCurrentViewer()

    def set_element_visibility(self, global_id, visible):
        """Sets visibility for an element by its GlobalId."""
        target_ais = None
        for ais, guid in self.ais_dict.items():
            if guid == global_id:
                target_ais = ais
                break

        if target_ais:
            if visible:
                self.display.Context.Display(target_ais, True)
            else:
                self.display.Context.Erase(target_ais, True)
            self.display.Context.UpdateCurrentViewer()

    def _create_arrow(self, dx, dy, dz, r, g, b):
        length = 1.0
        # Делаем стержень чуть толще для лучшей видимости (с 0.02 до 0.03)
        radius = 0.03
        p1 = gp_Pnt(0, 0, 0)
        dir_vec = gp_Dir(dx, dy, dz)

        axis = gp_Ax2(p1, dir_vec)
        # Стержень
        cyl = BRepPrimAPI_MakeCylinder(axis, radius, length * 0.75).Shape()

        cone_axis_pnt = gp_Pnt(dx * length * 0.75, dy * length * 0.75, dz * length * 0.75)
        cone_axis = gp_Ax2(cone_axis_pnt, dir_vec)
        # Делаем наконечник чуть больше и выразительнее
        cone = BRepPrimAPI_MakeCone(cone_axis, radius * 3.0, 0, length * 0.25).Shape()

        comp = TopoDS_Compound()
        builder = BRep_Builder()
        builder.MakeCompound(comp)
        builder.Add(comp, cyl)
        builder.Add(comp, cone)

        ais_arrow = AIS_Shape(comp)
        color = Quantity_Color(r, g, b, Quantity_TOC_RGB)
        ais_arrow.SetColor(color)

        # Keep python references to the shapes to avoid garbage collection
        ais_arrow._shapes = (cyl, cone, comp)

        return ais_arrow

    def _init_gizmo(self):
        self.gizmo_x = self._create_arrow(1, 0, 0, 1.0, 0.0, 0.0)
        self.gizmo_y = self._create_arrow(0, 1, 0, 0.0, 1.0, 0.0)
        self.gizmo_z = self._create_arrow(0, 0, 1, 0.0, 0.0, 1.0)

    def _update_gizmo(self):
        if not self._is_configured or not self.gizmo_x: return

        self.display.Context.InitSelected()
        if not self.display.Context.MoreSelected():
            if self._dragged_ais:
                selected_ais = self._dragged_ais
            else:
                return
        else:
            selected_ais = self.display.Context.SelectedInteractive()

        found_target = None
        for ais, guid in self.ais_dict.items():
            if _is_same_ais(ais, selected_ais):
                found_target = ais
                break

        if not found_target:
            return

        bbox = Bnd_Box()
        if self.display.Context.HasLocation(found_target):
            loc = self.display.Context.Location(found_target)
            transformed_shape = found_target.Shape().Moved(loc)
            brepbndlib.Add(transformed_shape, bbox)
        else:
            brepbndlib.Add(found_target.Shape(), bbox)

        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        self.gizmo_cx = (xmin + xmax) / 2.0
        self.gizmo_cy = (ymin + ymax) / 2.0
        self.gizmo_cz = (zmin + zmax) / 2.0

        # --- УЛУЧШЕННОЕ МАСШТАБИРОВАНИЕ GIZMO ---
        dx = xmax - xmin
        dy = ymax - ymin
        dz = zmax - zmin
        max_dim = max(dx, dy, dz)

        # Делаем гизмо чуть больше радиуса объекта (50% + 15%), чтобы он всегда выступал наружу
        self.gizmo_size = max_dim * 0.65

        trsf = gp_Trsf()
        trsf.SetTranslation(gp_Vec(self.gizmo_cx, self.gizmo_cy, self.gizmo_cz))

        scale_trsf = gp_Trsf()
        scale_trsf.SetScale(gp_Pnt(0,0,0), self.gizmo_size)
        # Порядок: сначала масштаб, потом перенос
        trsf = trsf.Multiplied(scale_trsf)

        loc = TopLoc_Location(trsf)

        self.display.Context.SetLocation(self.gizmo_x, loc)
        self.display.Context.SetLocation(self.gizmo_y, loc)
        self.display.Context.SetLocation(self.gizmo_z, loc)

    def _show_gizmo(self):
        if not self._is_configured or not self.gizmo_x: return
        if self._gizmo_visible: return

        self._update_gizmo()
        if abs(self.gizmo_cx) < 1e-9 and abs(self.gizmo_cy) < 1e-9 and abs(self.gizmo_cz) < 1e-9:
            pass

        self.display.Context.Display(self.gizmo_x, False)
        self.display.Context.Display(self.gizmo_y, False)
        self.display.Context.Display(self.gizmo_z, False)
        self.display.Context.UpdateCurrentViewer()
        self._gizmo_visible = True

    def _hide_gizmo(self):
        if not self._is_configured or not self.gizmo_x: return
        if not self._gizmo_visible: return

        self.display.Context.Erase(self.gizmo_x, False)
        self.display.Context.Erase(self.gizmo_y, False)
        self.display.Context.Erase(self.gizmo_z, False)
        self.display.Context.UpdateCurrentViewer()
        self._gizmo_visible = False

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Control:
            self._show_gizmo()
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Control:
            self._hide_gizmo()
            self._drag_axis = None
        super().keyReleaseEvent(event)

    def showEvent(self, event):
        super().showEvent(event)

        if not hasattr(self.canvas, '_display') or self.canvas._display is None:
            self.canvas.InitDriver()

        if not self._is_configured:
            self.display = self.canvas._display
            if self.display:
                self.display.set_bg_gradient_color([51, 51, 51], [51, 51, 51])

                context = self.display.Context

                hi_style = context.HighlightStyle()
                hi_style.SetColor(Quantity_Color(Quantity_NOC_WHITE))
                hi_style.SetTransparency(0.3)
                try:
                    hi_style.SetMethod(1)
                except Exception:
                    pass
                context.SetHighlightStyle(hi_style)

                sel_style = context.SelectionStyle()
                sel_style.SetColor(Quantity_Color(Quantity_NOC_WHITE))
                sel_style.SetTransparency(0.0)
                try:
                    sel_style.SetMethod(1)
                except Exception:
                    pass

                sel_style.SetFaceBoundaryDraw(True)
                sel_aspect = Prs3d_LineAspect(Quantity_Color(Quantity_NOC_WHITE), Aspect_TOL_SOLID, 2.5)
                sel_style.SetFaceBoundaryAspect(sel_aspect)

                context.SetSelectionStyle(sel_style)

                self.display.FitAll()
                self._init_gizmo()
                self._is_configured = True

        self.canvas.update()

    def load_model(self, dir_path: str):
        self.display.EraseAll()
        self.ais_dict.clear()

        brep_files = glob.glob(os.path.join(dir_path, "*.brep"))

        def load_shape(file_path):
            builder = BRep_Builder()
            shape = TopoDS_Shape()
            breptools.Read(shape, file_path, builder)
            return file_path, shape

        cyan_color = Quantity_Color(Quantity_NOC_CYAN)
        new_aspect = Prs3d_LineAspect(cyan_color, Aspect_TOL_SOLID, 1.5)

        with concurrent.futures.ThreadPoolExecutor() as executor:
            future_to_path = {executor.submit(load_shape, fp): fp for fp in brep_files}
            for future in concurrent.futures.as_completed(future_to_path):
                try:
                    file_path, shape = future.result()
                    my_ais_shape = AIS_Shape(shape)
                    drawer = my_ais_shape.Attributes()

                    drawer.SetFaceBoundaryDraw(True)
                    if drawer.FaceBoundaryAspect() is None:
                        drawer.SetFaceBoundaryAspect(new_aspect)
                    else:
                        drawer.FaceBoundaryAspect().SetColor(cyan_color)
                        drawer.FaceBoundaryAspect().SetWidth(1.5)

                    self.display.Context.Display(my_ais_shape, False)

                    filename = os.path.basename(file_path)
                    global_id = os.path.splitext(filename)[0]
                    self.ais_dict[my_ais_shape] = global_id
                except Exception as exc:
                    print(f"File {future_to_path[future]} generated an exception: {exc}")

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
                self._update_selection_visual(selected_ais)

                found_guid = None
                for ais, guid in self.ais_dict.items():
                    if _is_same_ais(ais, selected_ais):
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

        self._update_selection_visual(target_ais)
        self._is_updating_selection = True

        if target_ais:
            self.display.Context.ClearSelected(False)
            self.display.Context.SetSelected(target_ais, True)
            self.display.Context.UpdateCurrentViewer()

            bbox = Bnd_Box()

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
            
            if self._gizmo_visible:
                self._update_gizmo()
                
            self.display.Context.UpdateCurrentViewer()

    def on_canvas_mouse_press(self, event):
        if event.modifiers() == Qt.KeyboardModifier.ControlModifier and event.button() == Qt.MouseButton.LeftButton:
            x, y = event.pos().x(), event.pos().y()

            self.display.Context.MoveTo(x, y, self.display.View, True)
            if self.display.Context.HasDetected():
                detected = self.display.Context.DetectedInteractive()

                self._drag_axis = None

                if _is_same_ais(detected, self.gizmo_x):
                    self._drag_axis = 'X'
                elif _is_same_ais(detected, self.gizmo_y):
                    self._drag_axis = 'Y'
                elif _is_same_ais(detected, self.gizmo_z):
                    self._drag_axis = 'Z'

                if self._drag_axis:
                    self.display.Context.InitSelected()
                    if self.display.Context.MoreSelected():
                        self._dragged_ais = self.display.Context.SelectedInteractive()
                        self._is_object_dragging = True
                    else:
                        self._is_object_dragging = False
                else:
                    self._dragged_ais = detected
                    self._is_object_dragging = True
                    self._drag_axis = 'ALL'

                if self._is_object_dragging:
                    self._drag_start_x3d, self._drag_start_y3d, self._drag_start_z3d, _, _, _ = self.display.View.ConvertWithProj(x, y)

                    if self.display.Context.HasLocation(self._dragged_ais):
                        self._original_location = self.display.Context.Location(self._dragged_ais)
                    else:
                        self._original_location = TopLoc_Location()
            return

        self._original_mousePressEvent(event)
        
        # Обновляем визуальное выделение при обычном клике
        self.display.Context.InitSelected()
        if self.display.Context.MoreSelected():
            self._update_selection_visual(self.display.Context.SelectedInteractive())
        else:
            self._update_selection_visual(None)

    def on_canvas_mouse_move(self, event):
        if self._is_object_dragging and self._dragged_ais:
            x, y = event.pos().x(), event.pos().y()

            curr_x3d, curr_y3d, curr_z3d, _, _, _ = self.display.View.ConvertWithProj(x, y)

            dx = curr_x3d - self._drag_start_x3d
            dy = curr_y3d - self._drag_start_y3d
            dz = curr_z3d - self._drag_start_z3d

            if self._drag_axis == 'X':
                dy = 0.0
                dz = 0.0
            elif self._drag_axis == 'Y':
                dx = 0.0
                dz = 0.0
            elif self._drag_axis == 'Z':
                dx = 0.0
                dy = 0.0

            self._last_dx = dx
            self._last_dy = dy
            self._last_dz = dz

            translation = gp_Trsf()
            translation.SetTranslation(gp_Vec(dx, dy, dz))

            orig_trsf = self._original_location.Transformation()
            new_trsf = translation.Multiplied(orig_trsf)

            new_loc = TopLoc_Location(new_trsf)
            self.display.Context.SetLocation(self._dragged_ais, new_loc)

            if hasattr(self, 'gizmo_x') and self._gizmo_visible:
                gizmo_base_trsf = gp_Trsf()
                gizmo_base_trsf.SetTranslation(gp_Vec(self.gizmo_cx, self.gizmo_cy, self.gizmo_cz))

                scale_trsf = gp_Trsf()
                scale_trsf.SetScale(gp_Pnt(0,0,0), self.gizmo_size)
                final_gizmo_trsf = translation.Multiplied(gizmo_base_trsf.Multiplied(scale_trsf))

                new_gizmo_loc = TopLoc_Location(final_gizmo_trsf)

                self.display.Context.SetLocation(self.gizmo_x, new_gizmo_loc)
                self.display.Context.SetLocation(self.gizmo_y, new_gizmo_loc)
                self.display.Context.SetLocation(self.gizmo_z, new_gizmo_loc)

            self.display.Context.UpdateCurrentViewer()
            return

        self._original_mouseMoveEvent(event)

    def on_canvas_mouse_release(self, event):
        if self._is_object_dragging:
            if self._dragged_ais:
                moved_guid = None
                for ais, guid in self.ais_dict.items():
                    if _is_same_ais(ais, self._dragged_ais):
                        moved_guid = guid
                        break

                if moved_guid and (abs(self._last_dx) > 1e-8 or abs(self._last_dy) > 1e-8 or abs(self._last_dz) > 1e-8):
                    self.gizmo_cx += self._last_dx
                    self.gizmo_cy += self._last_dy
                    self.gizmo_cz += self._last_dz

                    self.element_moved_signal.emit(moved_guid, self._last_dx, self._last_dy, self._last_dz)

            self._is_object_dragging = False
            self._dragged_ais = None
            self._original_location = None
            self._last_dx = 0.0
            self._last_dy = 0.0
            self._last_dz = 0.0
            self._drag_axis = None
            return

        self._original_mouseReleaseEvent(event)
        self._last_dz = 0.0
        return
