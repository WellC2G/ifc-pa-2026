import os
import glob
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from OCC.Display.backend import load_backend

from OCC.Core.AIS import AIS_Shape
from OCC.Core.Quantity import Quantity_NOC_CYAN, Quantity_Color
from OCC.Core.Prs3d import Prs3d_Drawer, Prs3d_LineAspect
from OCC.Core.Aspect import Aspect_TOL_SOLID

load_backend("pyqt6")

from OCC.Display.qtDisplay import qtViewer3d
from OCC.Core.BRepTools import breptools
from OCC.Core.BRep import BRep_Builder
from OCC.Core.TopoDS import TopoDS_Shape


class IFCViewport(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.canvas = qtViewer3d(self)
        self.layout.addWidget(self.canvas)

        self.canvas.InitDriver()
        self.display = self.canvas._display

        self.display.set_bg_gradient_color([51, 51, 51], [51, 51, 51])

    def showEvent(self, event):
        super().showEvent(event)
        # Принудительно инициализируем драйвер, если он еще не готов
        self.canvas.InitDriver()
        # Посылаем сигнал виджету обновить свои размеры под layout
        self.canvas.update()
        # Если модель уже была загружена к этому моменту, подгоняем камеру
        if hasattr(self, 'display'):
            self.display.FitAll()

    def load_model(self, dir_path: str):
        self.display.EraseAll()
        builder = BRep_Builder()
        brep_files = glob.glob(os.path.join(dir_path, "*.brep"))

        for file_path in brep_files:
            shape = TopoDS_Shape()
            breptools.Read(shape, file_path, builder)

            # Создаем интерактивный объект
            my_ais_shape = AIS_Shape(shape)
            drawer = my_ais_shape.Attributes()
            
            # Включаем отрисовку ребер (границ граней)
            drawer.SetFaceBoundaryDraw(True)
            
            # Настраиваем цвет
            cyan_color = Quantity_Color(Quantity_NOC_CYAN)
            
            # Если аспект еще не создан (None), инициализируем его
            if drawer.FaceBoundaryAspect() is None:
                # Параметры: Цвет, Тип линии, Толщина
                new_aspect = Prs3d_LineAspect(cyan_color, Aspect_TOL_SOLID, 1.5)
                drawer.SetFaceBoundaryAspect(new_aspect)
            else:
                # Если уже есть, просто обновляем
                drawer.FaceBoundaryAspect().SetColor(cyan_color)
                drawer.FaceBoundaryAspect().SetWidth(1.5)
            
            # Устанавливаем материал или цвет самого тела (опционально)
            # self.display.Context.SetColor(my_ais_shape, Quantity_Color(Quantity_NOC_WHITE), False)

            # Отображаем в контексте без немедленного обновления (для скорости)
            self.display.Context.Display(my_ais_shape, False)

        # Однократное обновление после загрузки всех файлов
        self.display.Context.UpdateCurrentViewer()
        self.display.FitAll()