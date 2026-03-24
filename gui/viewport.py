from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from OpenGL.GL import glClearColor, glClear, GL_COLOR_BUFFER_BIT

class IFCViewport(QOpenGLWidget):
    def __init__(self):
        super().__init__()

    def initializeGL(self):
        glClearColor(0.2, 0.2, 1.0, 1.0)

    def resizeGL(self, w, h):
        pass

    def paintGL(self):
        glClear(GL_COLOR_BUFFER_BIT)