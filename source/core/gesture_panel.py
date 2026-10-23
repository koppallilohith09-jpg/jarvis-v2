"""Human-operated camera and input consent; model tools cannot arm control."""
def open_panel(parent):
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QDialog,QVBoxLayout,QLabel,QPushButton,QCheckBox,QComboBox
    from core.gestures import service
    existing=getattr(parent,'_gesture_dialog',None)
    if existing is not None and existing.isVisible():
        existing.raise_();existing.activateWindow();return existing
    dialog=QDialog(parent);dialog.setWindowTitle('Local gesture control');dialog.resize(540,430)
    layout=QVBoxLayout(dialog)
    info=QLabel('Choose the camera source. Images stay on that device.\nPoint: move pointer · pinch: click · two fingers: scroll\nHold fist: play/pause · open palm: pause input.\nCtrl+Alt+G stops control. Moving the physical mouse to a screen corner triggers the failsafe.')
    info.setWordWrap(True);layout.addWidget(info)
    consent=QCheckBox('Windows pointer control — move, click and scroll with my hand')
    dialog.control=consent
    layout.addWidget(consent)
    note=QLabel('Start the camera, then turn on Windows pointer control here or in Gesture View. Raise only your index finger to move; an open palm pauses movement.')
    note.setWordWrap(True);layout.addWidget(note)
    camera=QComboBox()
    dialog.camera=camera
    for index in range(5):camera.addItem('PC camera '+str(index)+(' (default)' if index==0 else ''),index)
    camera.setAccessibleName('PC webcam selection');camera.setMinimumHeight(36);layout.addWidget(camera)
    profile=QComboBox();profile.addItems(['Precise','Balanced','Fast']);profile.setCurrentText(service.motion.profile);profile.setAccessibleName('Hand cursor sensitivity');profile.setMinimumHeight(40);profile.currentTextChanged.connect(service.configure_motion);layout.addWidget(QLabel('Pointer response'));layout.addWidget(profile)
    clutch=QLabel('When your hand leaves view, the cursor stays put. Bring your hand back, then point to resume from that position. Use Fast for a wider reach or Precise for small targets.');clutch.setWordWrap(True);layout.addWidget(clutch)
    status=QLabel();status.setWordWrap(True);layout.addWidget(status)
    def permission(checked):
        if service.status()['mode']=='off':return
        try:service.set_control(checked)
        except Exception as error:
            consent.blockSignals(True);consent.setChecked(False);consent.blockSignals(False)
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(dialog,'Pointer control',str(error))
    consent.toggled.connect(permission)
    def start(source,control=None):
        try:
            service.arm(source,consent.isChecked() if control is None else control,camera.currentData())
            from core.gesture_preview import open_preview
            open_preview(dialog)
        except Exception as error:
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.information(dialog,'Gestures',str(error))
    cursor=QPushButton('START HAND CURSOR — camera + Windows control');cursor.setMinimumHeight(48);cursor.clicked.connect(lambda:start('pc',True));layout.addWidget(cursor)
    pc=QPushButton('Preview camera only');pc.clicked.connect(lambda:start('pc',False));layout.addWidget(pc)
    remote=QPushButton('Arm paired iPad camera');remote.clicked.connect(lambda:start('remote'));layout.addWidget(remote)
    preview=QPushButton('Open separate Gesture View');preview.setMinimumHeight(44)
    def show_preview():
        from core.gesture_preview import open_preview
        open_preview(dialog)
    preview.clicked.connect(show_preview);layout.addWidget(preview)
    stop=QPushButton('STOP gestures and release camera');stop.clicked.connect(service.stop);layout.addWidget(stop)
    for button in (pc,remote,stop):button.setMinimumHeight(44)
    help_text=QLabel('iPad: pair in Remote Control, then tap Gestures on its dashboard.\nStop before changing cameras or changing input permission.')
    help_text.setWordWrap(True);layout.addWidget(help_text)
    def refresh():
        state=service.status();status.setText(state['message']+'\nDetected: '+state['gesture'])
        active=state['mode']!='off'
        if active:
            consent.blockSignals(True);consent.setChecked(state['control']);consent.blockSignals(False)
        camera.setEnabled(not active);pc.setEnabled(not active);remote.setEnabled(not active);cursor.setEnabled(not active)
    timer=QTimer(dialog);timer.timeout.connect(refresh);timer.start(250);refresh()
    def finish():
        service.stop()
        if getattr(dialog,'_gesture_preview',None):dialog._gesture_preview.close()
    dialog.finished.connect(finish);dialog.show()
    parent._gesture_dialog=dialog
    return dialog
