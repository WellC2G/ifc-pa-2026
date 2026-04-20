import os
import glob
from PyQt6.QtWidgets import QWidget, QVBoxLayout

from OCC.Display.backend import load_backend
load_backend("pyqt6")

from OCC.Display.qtDisplay import qtViewer3d
from OCC.Core.BRepTools import breptools_Read
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

    def load_model(self, dir_path: str):
        self.display.EraseAll()

        builder = BRep_Builder()
        
        brep_files = glob.glob(os.path.join(dir_path, "*.brep"))

        for file_path in brep_files:
            shape = TopoDS_Shape()
            
            breptools_Read(shape, file_path, builder)

            self.display.DisplayShape(shape, update=False, color="WHITE")

        self.display.FitAll()