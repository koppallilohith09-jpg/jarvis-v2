"""Manual eye preview, nine-point calibration, validation, and dwell toolbar."""
import time
import numpy as np
from PyQt6.QtCore import Qt,QTimer,QPointF,QRectF
from PyQt6.QtGui import QColor,QPainter,QPen,QImage
from PyQt6.QtWidgets import QWidget,QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QCheckBox,QComboBox,QMessageBox,QApplication,QProgressBar
from core.eye_control import service

TARGETS=[(x,y) for y in (.12,.5,.88) for x in (.12,.5,.88)]
VALIDATE=[(.3,.3),(.7,.3),(.7,.7),(.3,.7)]

class CalibrationView(QWidget):
    def __init__(self,parent=None,auto_start=True):
        super().__init__(None,Qt.WindowType.Window|Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowTitle('JARVIS — Eye calibration');self.index=0;self.started=0;self.features=[];self.targets=[];self.errors=[];self.result=''
        self.setStyleSheet('background:#080808;color:#eeeeee');self.service=service
        service.set_control(False)
        self.start_button=QPushButton('Start calibration',self);self.start_button.clicked.connect(self.begin)
        self.enable_button=QPushButton('Enable eye pointer',self);self.enable_button.clicked.connect(self.enable);self.enable_button.hide()
        self.close_button=QPushButton('Cancel / close',self);self.close_button.clicked.connect(self.close)
        for button in (self.start_button,self.enable_button,self.close_button):button.setMinimumHeight(48)
        self.hint='Click Start calibration, then look at each dot until it moves.'
        screen=QApplication.primaryScreen();self.setGeometry(screen.geometry());self.showFullScreen()
        self.timer=QTimer(self);self.timer.timeout.connect(self.tick);self.timer.start(40)
        if auto_start:
            self.hint='Calibration starts in 3 seconds. Look at the first dot; ESC cancels.'
            QTimer.singleShot(3000,lambda:self.begin() if self.isVisible() and not self.started and not self.result else None)
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.fillRect(self.rect(),QColor('#080808'))
        p.setPen(QColor('#eeeeee'));p.drawText(self.rect().adjusted(24,24,-24,-24),Qt.AlignmentFlag.AlignTop|Qt.AlignmentFlag.AlignHCenter,'Keep your head still and look at the moving dot.\n'+self.hint)
        if self.result:
            p.drawText(self.rect().adjusted(80,80,-80,-80),Qt.AlignmentFlag.AlignCenter|Qt.TextFlag.TextWordWrap,self.result);return
        x,y=(TARGETS+VALIDATE)[min(self.index,12)];point=QPointF(x*self.width(),y*self.height())
        p.setBrush(QColor('#ffffff'));p.setPen(QPen(QColor('#dddddd'),2));p.drawEllipse(point,15,15)
        progress=max(0,min(1,(time.monotonic()-self.started-.7)/1.2)) if self.started else 0
        p.setBrush(Qt.BrushStyle.NoBrush);p.setPen(QPen(QColor('#999999'),5));p.drawArc(QRectF(point.x()-27,point.y()-27,54,54),90*16,-round(progress*360*16))
        p.setPen(QColor('#eeeeee'));p.drawText(self.rect().adjusted(20,20,-20,-35),Qt.AlignmentFlag.AlignBottom|Qt.AlignmentFlag.AlignHCenter,('Validation ' if self.index>=9 else 'Calibration ')+str(self.index+1)+' / 13')
    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Escape:self.close()
        elif event.key()==Qt.Key.Key_Space:self.begin()
    def resizeEvent(self,event):
        self.start_button.setGeometry(self.width()//2-250,self.height()-90,240,50)
        self.enable_button.setGeometry(self.width()//2-250,self.height()-90,240,50)
        self.close_button.setGeometry(self.width()//2+10,self.height()-90,240,50)
        super().resizeEvent(event)
    def begin(self):
        self.result='';self.index=0;self.features=[];self.targets=[];self.errors=[];self.started=time.monotonic()
        from core.eye_control import Calibration
        service.set_control(False);service.pointer_mode='gaze';service.calibration=Calibration();self.start_button.hide();self.enable_button.hide()
        self.hint='Look at the dot. It advances when enough eye samples arrive. ESC cancels.'
    def enable(self):
        try:service.set_control(True);self.close()
        except Exception as error:QMessageBox.information(self,'Eye pointer',str(error))
    def tick(self):
        now=time.monotonic();self.update()
        if not self.started or self.result or now-self.started<1.9:return
        count=service.sample_count(self.started+.7)
        if count<8 and now-self.started<8:
            self.hint=f'Keep looking at the dot. Collecting eye samples: {count}/8';return
        try:
            feature=service.capture(self.started+.7)
            target=(TARGETS+VALIDATE)[self.index]
            if self.index<9:
                self.features.append(feature);self.targets.append(target)
                if self.index==8:service.calibration.fit(self.features,self.targets)
            else:self.errors.append(float(np.linalg.norm(service.calibration.predict(feature)-target)))
            self.index+=1;self.started=now
            if self.index==13:
                error=float(np.mean(self.errors))
                if error>.20:
                    service.calibration.weights=None;service.calibration.validated=False
                    self.result='Validation was not accurate enough ('+str(round(error*100))+'% of screen). Adjust camera/lighting and press SPACE to retry. ESC closes.'
                    self.start_button.setText('Retry calibration');self.start_button.show()
                else:
                    service.calibration.validated=True
                    service.message='Calibration passed. Validation error: '+str(round(error*100))+'% of screen. Click Enable eye pointer to start moving the cursor.'
                    self.result=service.message;self.enable_button.show()
                self.started=0
        except Exception as error:
            service.calibration.weights=None;service.calibration.validated=False;self.result=str(error)+'\nClick Retry calibration, or Cancel.';self.started=0
            self.start_button.setText('Retry calibration');self.start_button.show()
    def closeEvent(self,event):
        self.timer.stop()
        if self.started:service.calibration.weights=None;service.calibration.validated=False
        super().closeEvent(event)

class EyeCanvas(QWidget):
    def __init__(self):super().__init__();self.setMinimumSize(320,230)
    def paintEvent(self,event):
        state=service.snapshot();p=QPainter(self);p.fillRect(self.rect(),QColor('#080808'));frame=state['frame']
        if not frame:
            p.setPen(QColor('#eeeeee'));p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'Start eye camera to see the local preview.');return
        rgb,w,h=frame;scale=min(self.width()/w,self.height()/h);target=QRectF((self.width()-w*scale)/2,(self.height()-h*scale)/2,w*scale,h*scale)
        p.drawImage(target,QImage(rgb,w,h,w*3,QImage.Format.Format_RGB888).mirrored(True,False))
        p.setBrush(QColor('#ffffff'));p.setPen(Qt.PenStyle.NoPen)
        for index in (33,133,159,145,362,263,386,374,468,473):
            if len(state['points'])>index:
                x,y=state['points'][index];p.drawEllipse(QPointF(target.x()+(1-x)*target.width(),target.y()+y*target.height()),3,3)

class EyePanel(QDialog):
    def __init__(self,parent):
        super().__init__(parent);self.setWindowTitle('JARVIS — Eye control');self.resize(700,660)
        layout=QVBoxLayout(self);label=QLabel('Webcam eye pointer · local processing\n1. Start camera   2. Calibrate   3. Allow pointer   4. Optionally enable dwell clicks\nKeep your head still. This webcam estimate needs good lighting and may be imprecise. Ctrl+Alt+G stops input; the physical mouse corner failsafe also stops it.');label.setWordWrap(True);layout.addWidget(label)
        self.camera=QComboBox()
        self._setup_generation=0
        for index in range(5):self.camera.addItem('PC camera '+str(index),index)
        layout.addWidget(self.camera)
        setup=QPushButton('SET UP EYE CURSOR — camera + calibration');setup.setMinimumHeight(48);setup.clicked.connect(self.setup_cursor);layout.addWidget(setup)
        head=QPushButton('START HEAD-ASSISTED CURSOR — no gaze calibration');head.setMinimumHeight(48);head.clicked.connect(self.setup_head);layout.addWidget(head)
        self.canvas=EyeCanvas();layout.addWidget(self.canvas,1)
        row=QHBoxLayout();self.start=QPushButton('Start eye camera');self.start.clicked.connect(self.begin);row.addWidget(self.start)
        self.calibrate=QPushButton('Calibrate eyes');self.calibrate.clicked.connect(self.calibration);row.addWidget(self.calibrate);layout.addLayout(row)
        self.allow=QCheckBox('Allow my eyes to move the Windows pointer');self.allow.toggled.connect(self.permission);layout.addWidget(self.allow)
        self.clicks=QCheckBox('Dwell for 1.35 seconds to click (move away to repeat)');self.clicks.toggled.connect(self.permission);layout.addWidget(self.clicks)
        actions=QHBoxLayout();self.action=QComboBox()
        for title,value in [('Left click','click'),('Right click once','right'),('Double click once','double'),('Drag / release on next dwell','drag'),('Scroll up','up'),('Scroll down','down')]:self.action.addItem(title,value)
        self.action.currentIndexChanged.connect(lambda: self.choose());actions.addWidget(self.action)
        keyboard=QPushButton('Windows on-screen keyboard');keyboard.clicked.connect(self.keyboard);actions.addWidget(keyboard);layout.addLayout(actions)
        self.progress=QProgressBar();self.progress.setRange(0,100);self.progress.setFormat('Dwell: %p%');layout.addWidget(self.progress)
        self.status=QLabel();self.status.setWordWrap(True);layout.addWidget(self.status)
        stop=QPushButton('STOP eye camera and Windows input');stop.setMinimumHeight(46);stop.clicked.connect(service.stop);layout.addWidget(stop)
        toolbar=QPushButton('Open large eye mouse toolbar');toolbar.clicked.connect(self.toolbar);layout.addWidget(toolbar)
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(80);self.refresh()
    def begin(self):
        try:service.start(self.camera.currentData())
        except Exception as error:QMessageBox.information(self,'Eye camera',str(error))
    def setup_cursor(self):
        self._setup_generation+=1;generation=self._setup_generation
        if not service.active:self.begin()
        def ready(attempt=0):
            if generation!=self._setup_generation or not service.active:return
            if service.snapshot()['feature'] is not None:self.calibration();return
            if attempt<50:QTimer.singleShot(200,lambda:ready(attempt+1));return
            QMessageBox.information(self,'Eye cursor','Both open eyes must be visible before calibration. Adjust lighting and camera position, then click SET UP EYE CURSOR again.')
        QTimer.singleShot(200,ready)
    def setup_head(self):
        self._setup_generation+=1;generation=self._setup_generation
        if not service.active:self.begin()
        def ready(attempt=0):
            if generation!=self._setup_generation or not service.active:return
            if service.snapshot()['feature'] is not None:
                try:service.set_head_control(True,self.clicks.isChecked())
                except Exception as error:QMessageBox.information(self,'Head cursor',str(error))
                return
            if attempt<50:QTimer.singleShot(200,lambda:ready(attempt+1))
            else:QMessageBox.information(self,'Head cursor','Keep your face and both open eyes visible, then try again.')
        QTimer.singleShot(200,ready)
    def calibration(self):
        if not service.active:return
        self._calibration=CalibrationView(self)
    def permission(self):
        try:
            if service.pointer_mode=='head' and self.sender() is self.clicks:service.set_control(service.control,self.clicks.isChecked())
            else:
                service.pointer_mode='gaze';service.set_control(self.allow.isChecked(),self.clicks.isChecked())
        except Exception as error:
            self.allow.blockSignals(True);self.allow.setChecked(False);self.allow.blockSignals(False);QMessageBox.information(self,'Eye control',str(error))
    def choose(self):
        with service.lock:
            service.action=self.action.currentData()
            # Selecting a mode by dwelling on the toolbar must not immediately
            # fire the newly selected action on that same toolbar button.
            service.dwell.fired=True
    def keyboard(self):
        import pyautogui
        pyautogui.hotkey('win','ctrl','o')
    def toolbar(self):
        self._toolbar=QWidget(None,Qt.WindowType.Window|Qt.WindowType.WindowStaysOnTopHint);self._toolbar.setWindowTitle('JARVIS eye mouse toolbar');row=QHBoxLayout(self._toolbar)
        for name,action in [('Left','click'),('Right','right'),('Double','double'),('Drag/release','drag'),('Scroll ↑','up'),('Scroll ↓','down')]:
            button=QPushButton(name);button.setMinimumSize(105,70)
            def select(checked=False,value=action):
                index=self.action.findData(value);self.action.setCurrentIndex(index)
            button.clicked.connect(select);row.addWidget(button)
        stop=QPushButton('STOP');stop.setMinimumSize(100,70);stop.clicked.connect(service.stop);row.addWidget(stop)
        self._toolbar.show()
    def refresh(self):
        state=service.snapshot();self.canvas.update()
        step=('Head cursor ON — move your head to steer. This is head tracking, not gaze.' if state['control'] and state['pointer_mode']=='head' else 'Eye cursor ON — look where you want to move.' if state['control'] else 'Calibration passed — tick Allow my eyes to move the Windows pointer.' if state['calibrated'] else 'Pointer OFF — choose head-assisted cursor or calibrate gaze.' if state['active'] else 'Choose a cursor setup to begin.')
        self.status.setText(step+'\n'+state['message']+('\nEyes visible' if state['feature'] is not None else '\nNo open eyes detected; pointer pauses.'))
        self.start.setEnabled(not state['active']);self.camera.setEnabled(not state['active']);self.calibrate.setEnabled(state['active'])
        self.allow.setEnabled(state['active'] and state['calibrated']);self.clicks.setEnabled(state['control']);self.progress.setValue(round(state['dwell']*100))
        self.allow.blockSignals(True);self.allow.setChecked(state['control'] and state['pointer_mode']=='gaze');self.allow.blockSignals(False)
        if state['action']!=self.action.currentData():
            self.action.blockSignals(True);self.action.setCurrentIndex(self.action.findData(state['action']));self.action.blockSignals(False)
    def closeEvent(self,event):
        self._setup_generation+=1
        service.stop();self.timer.stop()
        for item in ('_calibration','_toolbar'):
            if getattr(self,item,None):getattr(self,item).close()
        super().closeEvent(event)

def open_panel(parent):
    existing=getattr(parent,'_eye_dialog',None)
    if existing and existing.isVisible():existing.raise_();return existing
    panel=EyePanel(parent);parent._eye_dialog=panel;panel.show();return panel
