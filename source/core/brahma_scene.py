"""Locally embedded 3D scene with a restricted asset-only request policy."""
import json
from pathlib import Path
from PyQt6.QtCore import Qt,QTimer,QUrl,pyqtSignal
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QWidget,QVBoxLayout,QLabel
from PyQt6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile,QWebEngineSettings,QWebEngineUrlRequestInterceptor
from PyQt6.QtWebEngineWidgets import QWebEngineView
from core.gestures import ROOT

class LocalSceneRequests(QWebEngineUrlRequestInterceptor):
    def __init__(self,folder,parent=None):super().__init__(parent);self.folder=Path(folder).resolve();self.blocked=[]
    def interceptRequest(self,info):
        url=info.requestUrl();scheme=url.scheme();allowed=scheme in ('data','blob','about')
        if scheme=='file':allowed=Path(url.toLocalFile()).resolve().is_relative_to(self.folder)
        if not allowed:self.blocked.append(url.toString());info.block(True)

class Scene(QWidget):
    motionPreference=pyqtSignal(bool)
    def __init__(self):
        super().__init__();self.state='INITIALISING';self.speaking=False;self.muted=False;self.reduced=False;self.hud_style='3d';self._assistant_name='JARVIS';self._audio=0.;self.ready=False;self._last=None
        self.setMinimumSize(280,280);layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        self.profile=QWebEngineProfile(self);self.profile.setHttpCacheType(QWebEngineProfile.HttpCacheType.MemoryHttpCache);self.profile.setPersistentCookiesPolicy(QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies)
        folder=ROOT/'assets/echo-reference'
        if (ROOT/'share-edition.json').is_file() or not (folder/'index.html').is_file():folder=ROOT/'assets/echo-core'
        self.guard=LocalSceneRequests(folder,self.profile);self.profile.setUrlRequestInterceptor(self.guard)
        self.view=QWebEngineView(self);self.page=QWebEnginePage(self.profile,self.view);self.view.setPage(self.page);self.page.setBackgroundColor(QColor('#000000'))
        settings=self.page.settings();settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls,False);settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls,True);settings.setAttribute(QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture,True);settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled,True)
        self.page.permissionRequested.connect(lambda permission:permission.deny());self.page.loadFinished.connect(self.loaded)
        layout.addWidget(self.view,1);self.title=QLabel('J . A . R . V . I . S .');self.title.setAlignment(Qt.AlignmentFlag.AlignCenter);self.title.setStyleSheet('color:#f4f4f4;background:#000;font-size:22px;padding:4px;');layout.addWidget(self.title)
        self.caption=QLabel('Loading spatial core…');self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter);self.caption.setStyleSheet('color:#b8b8b8;background:#000;font-size:11px;padding:8px;');layout.addWidget(self.caption)
        self.view.load(QUrl.fromLocalFile(str((folder/'index.html').resolve())))
        self.timer=QTimer(self);self.timer.timeout.connect(self.refresh);self.timer.start(100)
    def loaded(self,success):
        if success:self.page.runJavaScript('window.__ORB__ ? window.__ORB__.getState() : null',self.initialized)
        else:self.caption.setText('The local 3D scene could not load.')
    def initialized(self,state):
        self.ready=bool(state and state.get('ready'))
        if self.ready:
            self.reduced=bool(state.get('reduced'));self.motionPreference.emit(self.reduced)
            self.page.runJavaScript('window.setCompactMode(true)');self.refresh()
        else:self.caption.setText('3D requires a working WebGL graphics context. Check graphics acceleration.')
    def set_audio_level(self,value):self._audio=max(0.,min(1.,float(value)))
    def push_visemes(self,*args):pass
    def glance(self,*args,**kwargs):pass
    def refresh(self):
        if not self.ready:return
        state='MUTED' if self.muted else {'PROCESSING':'THINKING','INITIALISING':'IDLE','PREVIEW':'IDLE'}.get(self.state,self.state)
        values=(state,round(self._audio,2),self.reduced)
        if values!=self._last:
            script='window.setBrahmaState('+json.dumps(state)+');window.setAudioLevel('+str(values[1])+');'
            if self._last is None or self.reduced!=self._last[2]:
                script+='window.setReducedMotion('+json.dumps(bool(self.reduced))+');'
                script+=('window.pauseBrahmaBackground();' if self.reduced else 'window.resumeBrahmaBackground();')
            self.page.runJavaScript(script);self._last=values
        self.caption.setText(('MICROPHONE MUTED' if self.muted else self.state.replace('_',' '))+'  ·  DRAG TO ROTATE · SCROLL TO ZOOM')
    def closeEvent(self,event):
        self.timer.stop();self.page.runJavaScript('window.pauseBrahmaBackground()');super().closeEvent(event)
