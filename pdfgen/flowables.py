from reportlab.pdfbase.pdfform import textFieldRelative
from reportlab.platypus.flowables import Flowable


class TextField(Flowable):
    def __init__(self, name, width=100, height=20, value=None):
        self.name = name
        self.width = width
        self.height = height
        self.value = value

    def wrap(self, *args):
        return (self.width, self.height)

    def draw(self):
        self.canv.saveState()
        textFieldRelative(self.canv, self.name, 0, 0, self.width, self.height, value=self.value)
        self.canv.restoreState() 
