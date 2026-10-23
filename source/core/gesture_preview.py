"""A separate, local-only gesture monitor. No second camera is opened here."""
from PyQt6.QtCore import Qt,QTimer,QRectF,QPointF
from PyQt6.QtGui import QColor,QFont,QImage,QPainter,QPen
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QLabel,QPushButton,QCheckBox,QMessageBox

CONNECTIONS=((0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),(5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),(13,17),(0,17),(17,18),(18,19),(19,20))
LABELS={'point':'Point · move pointer','pinch':'Pinch · click','scroll':'Two fingers · scroll','fist':'Fist · play/pause','palm':'Open palm · input paused','other':'Adjust your hand angle'}

class HandCanvas(QWidget):
    def __init__(self,service,parent=None):
        super().__init__(parent);self.service=service;self.setMinimumSize(320,240)
        self.setAccessibleName('Live local gesture preview with hand landmarks')
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(),QColor('#090909'));state=self.service.preview()
        frame=state['frame'];width,height=(frame[1],frame[2]) if frame else (640,480)
        scale=min(self.width()/width,self.height()/height)
        target=QRectF((self.width()-width*scale)/2,(self.height()-height*scale)/2,width*scale,height*scale)
        if frame:
            image=QImage(frame[0],width,height,width*3,QImage.Format.Format_RGB888).mirrored(True,False)
            p.drawImage(target,image)
        elif not state['landmarks']:
            p.setPen(QColor('#dddddd'));p.setFont(QFont('Segoe UI',12))
            text='Start PC webcam in the Gestures panel.' if state['mode']=='off' else 'Waiting for your hand…'
            p.drawText(self.rect().adjusted(24,24,-24,-24),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,text)
        points=[QPointF(target.left()+(1-x)*target.width(),target.top()+y*target.height()) for x,y,z in state['landmarks']]
        p.setPen(QPen(QColor('#eeeeee'),3))
        for a,b in CONNECTIONS:
            if len(points)==21:p.drawLine(points[a],points[b])
        p.setBrush(QColor('#ffffff'));p.setPen(Qt.PenStyle.NoPen)
        for point in points:p.drawEllipse(point,4,4)
        p.end()

class GesturePreview(QWidget):
    def __init__(self,service,parent=None):
        super().__init__(parent,Qt.WindowType.Window)
        self.service=service;self.setWindowTitle('JARVIS — Gesture View');self.resize(720,660)
        self.setMinimumSize(360,420)
        self.setStyleSheet('QWidget {background:#090909;color:#eeeeee;font-family:Segoe UI;font-size:14px;} QPushButton {background:#292929;border:1px solid #999999;border-radius:8px;padding:10px;}')
        layout=QVBoxLayout(self);self.title=QLabel('Gesture camera is off');self.title.setWordWrap(True);layout.addWidget(self.title)
        self.canvas=HandCanvas(service);layout.addWidget(self.canvas,1)
        self.detected=QLabel('No hand detected');self.detected.setStyleSheet('font-size:20px;font-weight:600;padding:8px;');layout.addWidget(self.detected)
        self.detail=QLabel();self.detail.setWordWrap(True);layout.addWidget(self.detail)
        self.control=QCheckBox('Windows pointer control — ON to move the cursor');self.control.setMinimumHeight(44)
        self.control.toggled.connect(self.permission);layout.addWidget(self.control)
        top=QCheckBox('Keep this preview on top');top.toggled.connect(self._on_top);layout.addWidget(top)
        stop=QPushButton('STOP camera and gestures');stop.setMinimumHeight(44);stop.clicked.connect(service.stop);layout.addWidget(stop)
        hint=QLabel('Closing this window stops gestures. iPad video stays on the iPad; this window shows its hand landmarks.');hint.setWordWrap(True);layout.addWidget(hint)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(80);self.refresh()
    def _on_top(self,checked):
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint,checked);self.show()
    def permission(self,checked):
        try:self.service.set_control(checked)
        except Exception as error:
            self.control.blockSignals(True);self.control.setChecked(False);self.control.blockSignals(False)
            QMessageBox.information(self,'Pointer control',str(error))
    def refresh(self):
        state=self.service.preview();source={'pc':'PC webcam · local video','remote':'iPad · hand landmarks only','off':'Camera is off'}[state['mode']]
        self.title.setText(source+' · '+('Windows control ON' if state['control'] else 'Preview only'))
        self.control.blockSignals(True);self.control.setChecked(state['control']);self.control.blockSignals(False);self.control.setEnabled(state['mode']!='off')
        self.detected.setText(LABELS.get(state['gesture'],'No hand detected') if state['landmarks'] else 'No hand detected')
        self.detail.setText(state['message']);self.canvas.update()
    def closeEvent(self,event):
        self.service.stop();self.timer.stop();super().closeEvent(event)
    def showEvent(self,event):
        self.timer.start(80);super().showEvent(event)

def open_preview(owner):
    from core.gestures import service
    window=getattr(owner,'_gesture_preview',None)
    if window is None:
        window=GesturePreview(service,owner);owner._gesture_preview=window
    window.show();window.raise_();window.activateWindow();return window
