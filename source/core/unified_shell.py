"""Original Qt dashboard inspired by the reviewed Brahma layout; local backend."""
import math,random,time
from datetime import datetime
from pathlib import Path
from PyQt6.QtCore import Qt,QTimer,QPointF,QRectF,pyqtSignal
from PyQt6.QtGui import QColor,QFont,QPainter,QPen,QRadialGradient,QPainterPath,QKeySequence,QShortcut
from PyQt6.QtWidgets import QWidget,QFrame,QLabel,QPushButton,QVBoxLayout,QHBoxLayout,QGridLayout,QStackedWidget,QScrollArea,QSizePolicy,QCheckBox,QComboBox,QProgressBar

BG='#000000';PANEL='#0c0c0c';EDGE='#333333';TEXT='#f4f4f4';MUTED='#b8b8b8';CYAN='#ffffff'
STYLE='''
QWidget { background:#05080e; color:#edf5fa; font-family:Segoe UI; font-size:13px; }
QWidget#UnifiedRoot { background:#05080e; color:#edf5fa; font-family:Segoe UI; font-size:13px; }
QFrame#Glass { background:#0c121c; border:1px solid #233a4c; border-radius:14px; }
QLabel { color:#edf5fa; background:transparent; border:none; }
QPushButton { color:#d7e7f2; background:#101b28; border:1px solid #2c4355; border-radius:9px; padding:9px 13px; font-size:12px; }
QPushButton:hover { background:#172e3c; border-color:#65e6f5; }
QPushButton:focus { border:2px solid #65e6f5; }
QPushButton:checked { background:#133441; color:#92f4ff; border-color:#4ba6b5; }
QPushButton:disabled { color:#768a9a; background:#0d151f; border-color:#263442; }
QPushButton#Primary { background:#75e8f4; color:#07131a; border:none; font-weight:600; }
QPushButton#Stop { background:#361c29; color:#ffd7e1; border-color:#96516b; }
QLineEdit { color:#eff9ff; background:#0b141e; border:1px solid #304b5d; border-radius:12px; padding:12px; font-size:14px; }
QLineEdit:focus { border-color:#65e6f5; }
QComboBox { color:#edf5fa; background:#111f2b; border:1px solid #304b5d; padding:9px; border-radius:7px; }
QTextEdit { color:#edf5fa; background:#0a111a; border:1px solid #263d50; border-radius:10px; padding:12px; }
QCheckBox { color:#dceaf4; spacing:10px; padding:5px; }
QScrollArea { background:transparent; border:none; }
QScrollBar:vertical { background:#0c141e; width:7px; } QScrollBar::handle:vertical { background:#35566a; border-radius:3px; min-height:30px; }
QProgressBar { color:#e8f7fc; background:#182330; border:1px solid #2c4355; border-radius:5px; text-align:center; }
QProgressBar::chunk { background:#307f91; }
'''
# The reference's monochrome direction applies to every shell component.
for _old,_new in {'#05080e':'#000000','#edf5fa':'#f4f4f4','#0c121c':'#0c0c0c','#233a4c':'#333333','#d7e7f2':'#dedede','#101b28':'#141414','#2c4355':'#383838','#172e3c':'#242424','#65e6f5':'#ffffff','#133441':'#252525','#92f4ff':'#ffffff','#4ba6b5':'#999999','#768a9a':'#828282','#0d151f':'#111111','#263442':'#333333','#75e8f4':'#f2f2f2','#07131a':'#080808','#361c29':'#292929','#ffd7e1':'#ffffff','#96516b':'#777777','#eff9ff':'#ffffff','#0b141e':'#101010','#304b5d':'#484848','#111f2b':'#161616','#0a111a':'#101010','#263d50':'#383838','#dceaf4':'#dedede','#0c141e':'#141414','#35566a':'#505050','#e8f7fc':'#eeeeee','#182330':'#202020','#307f91':'#777777'}.items():STYLE=STYLE.replace(_old,_new)

def label(text,size=12,color=TEXT,bold=False):
    item=QLabel(text);item.setWordWrap(True);item.setStyleSheet(f'font-size:{size}px;color:{color};font-weight:{600 if bold else 400};');return item
def button(text,callback,primary=False):
    item=QPushButton(text);item.setMinimumHeight(40);item.setCursor(Qt.CursorShape.PointingHandCursor);item.setAccessibleName(text)
    if primary:item.setObjectName('Primary')
    item.clicked.connect(callback);return item
def card(title,subtitle=''):
    frame=QFrame();frame.setObjectName('Glass');layout=QVBoxLayout(frame);layout.setContentsMargins(18,16,18,16);layout.setSpacing(12)
    layout.addWidget(label(title,12,CYAN,True))
    if subtitle:layout.addWidget(label(subtitle,12,MUTED))
    return frame,layout

class Orb(QWidget):
    def __init__(self):
        super().__init__();self.state='INITIALISING';self.speaking=False;self.muted=False;self._audio=0.;self._assistant_name='JARVIS';self.hud_style='orb';self.reduced=False;self.setMinimumSize(280,280)
        rng=random.Random(714);self.stars=[(rng.random(),rng.random(),rng.uniform(.5,1.6)) for _ in range(60)]
        n=580;golden=math.pi*(3-math.sqrt(5));self.dots=[]
        for i in range(n):
            y=1-2*(i+.5)/n;r=math.sqrt(1-y*y);a=i*golden;self.dots.append((r*math.cos(a),y,r*math.sin(a)))
        self.timer=QTimer(self);self.timer.timeout.connect(self.update);self.timer.start(40)
    def set_audio_level(self,value):self._audio=max(0.,min(1.,float(value)))
    def push_visemes(self,*args):pass
    def glance(self,*args,**kwargs):pass
    def paintEvent(self,event):
        p=QPainter(self);p.setRenderHint(QPainter.RenderHint.Antialiasing);p.fillRect(self.rect(),QColor(BG));w,h=self.width(),self.height()
        for x,y,r in self.stars:p.setPen(QColor(180,180,180,100));p.drawEllipse(QPointF(x*w,y*h),r,r)
        p.setPen(QPen(QColor(110,110,110,23),1))
        for x in range(0,w,44):p.drawLine(x,0,x,h)
        for y in range(0,h,44):p.drawLine(0,y,w,y)
        color=QColor('#eeeeee')
        if self.muted:color=QColor('#aaaaaa')
        cx,cy=w*.5,h*.44;radius=min(w*.30,h*.28);t=0 if self.reduced else time.monotonic()*.12
        radius*=1+(self._audio*.07 if not self.muted else 0)
        glow=QRadialGradient(QPointF(cx,cy),radius*1.8);c=QColor(color);c.setAlpha(45);glow.setColorAt(0,c);c.setAlpha(15);glow.setColorAt(.55,c);c.setAlpha(0);glow.setColorAt(1,c)
        p.setPen(Qt.PenStyle.NoPen);p.setBrush(glow);p.drawEllipse(QPointF(cx,cy),radius*1.8,radius*1.8)
        rotated=[]
        for x,y,z in self.dots:
            xx=x*math.cos(t)+z*math.sin(t);zz=-x*math.sin(t)+z*math.cos(t);yy=y*.94+zz*.15
            rotated.append((zz,cx+xx*radius,cy+yy*radius))
        p.setPen(Qt.PenStyle.NoPen)
        for z,x,y in sorted(rotated):
            c=QColor(color);c.setAlpha(round(45+(z+1)*85));p.setBrush(c);r=.8+(z+1)*.55;p.drawEllipse(QPointF(x,y),r,r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for angle,scale in ((-26,.35),(34,.62),(90,.86)):
            p.save();p.translate(cx,cy);p.rotate(angle);c=QColor(color);c.setAlpha(120);p.setPen(QPen(c,1));p.drawEllipse(QRectF(-radius*1.17,-radius*scale,radius*2.34,radius*scale*2));p.restore()
        p.setFont(QFont('Segoe UI',21,QFont.Weight.Light));p.setPen(QColor(TEXT));p.drawText(QRectF(0,cy+radius+35,w,40),Qt.AlignmentFlag.AlignCenter,'J . A . R . V . I . S .')
        state='MICROPHONE MUTED' if self.muted else self.state.replace('_',' ')
        p.setFont(QFont('Segoe UI',9));p.setPen(color);p.drawText(QRectF(0,cy+radius+78,w,30),Qt.AlignmentFlag.AlignCenter,state)
        p.setPen(QColor(MUTED));p.setFont(QFont('Segoe UI',9));p.drawText(QRectF(15,h-46,w-30,30),Qt.AlignmentFlag.AlignCenter,'Your voice. Your devices. One local assistant.')

class ChatFeed(QScrollArea):
    def __init__(self,shell):
        super().__init__();self.shell=shell;self._ai_name_lc='jarvis';self.setWidgetResizable(True);self.body=QWidget();self.body.setStyleSheet('background:transparent;');self.layout=QVBoxLayout(self.body);self.layout.setContentsMargins(0,0,6,8);self.layout.setSpacing(14);self.layout.addStretch();self.setWidget(self.body);self.bubbles=[]
        self.live={}
        self.add('JARVIS','Ready when you are. Ask a question, attach a file, or say “show modes.”',False)
    def add(self,role,text,user=False):
        bubble=QFrame();bubble.setObjectName('ChatBubble');bubble.setStyleSheet(f'QFrame#ChatBubble{{background:{"#252525" if user else "#131313"};border:1px solid {"#606060" if user else "#353535"};border-radius:12px;}}')
        layout=QVBoxLayout(bubble);layout.setContentsMargins(13,11,13,12);layout.addWidget(label(role+'  ·  '+datetime.now().strftime('%H:%M'),10,CYAN if user else MUTED,True));body=label(str(text)[:10000],13);body.setTextFormat(Qt.TextFormat.PlainText);body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse);layout.addWidget(body)
        self.layout.insertWidget(self.layout.count()-1,bubble);self.bubbles.append(bubble)
        if len(self.bubbles)>100:self.bubbles.pop(0).deleteLater()
        QTimer.singleShot(0,lambda:self.verticalScrollBar().setValue(self.verticalScrollBar().maximum()))
        return body
    def live_transcript(self,role,text):
        if role=='end':self.live.clear();return
        key='you' if role.casefold() in ('you','user') else 'jarvis'
        if key not in self.live:self.live[key]=self.add('YOU' if key=='you' else 'JARVIS',text,key=='you')
        else:self.live[key].setText(str(text)[:10000])
    def complete(self,key,text):
        body=self.live.pop(key,None)
        if body is not None:body.setText(str(text)[:10000])
        else:self.add('YOU' if key=='you' else 'JARVIS',text,key=='you')
    def append_log(self,text):
        prefix,sep,body=str(text).partition(':');key=prefix.strip().casefold()
        if key in ('you','user'):self.complete('you',body.strip())
        elif key in ('jarvis','assistant','model',self._ai_name_lc):self.complete('jarvis',body.strip())
        elif key in ('err','error') or 'failed' in str(text).casefold():self.add('JARVIS · STATUS',str(text))
        self.shell.operation.setText(str(text).removeprefix('SYS: ').strip()[:350]);self.shell.events.append(str(text))

class UnifiedShell:
    def __init__(self,window):
        self.window=window;self.events=[];self.pending=None;self.active_mode='assistant';self.eye_panel=None;self.hand_panel=None;self.mode_generation=0
        old=window.takeCentralWidget();self.root=QWidget();self.root.setObjectName('UnifiedRoot');self.root.setStyleSheet(STYLE);window.setCentralWidget(self.root);window._legacy_shell=old;old.setParent(self.root);old.hide()
        self.root.setAcceptDrops(True);self.root.dragEnterEvent=self.drag_enter;self.root.dropEvent=self.drop
        window.setWindowTitle('JARVIS · Local command center');window.setMinimumSize(960,660)
        from PyQt6.QtWidgets import QApplication
        available=QApplication.primaryScreen().availableGeometry();window.resize(min(1320,available.width()-40),min(860,available.height()-60))
        layout=QVBoxLayout(self.root);layout.setContentsMargins(22,18,22,15);layout.setSpacing(16)
        header=QHBoxLayout();brand=label('JARVIS',23,TEXT,True);header.addWidget(brand);self.brain_badge=label('AI ASSISTANT',10,CYAN);header.addWidget(self.brain_badge);header.addStretch()
        self.nav={}
        for name,key in [('Dashboard','dashboard'),('Chat','chat'),('Modes','modes'),('Devices','devices'),('Settings','settings')]:
            btn=button(name,lambda checked=False,value=key:self.navigate(value));btn.setCheckable(True);self.nav[key]=btn;header.addWidget(btn)
        self.clock=label('',12,MUTED);header.addSpacing(14);header.addWidget(self.clock);layout.addLayout(header)
        body=QHBoxLayout();body.setSpacing(16);self.sidebar=QWidget();self.sidebar.setFixedWidth(215);side=QVBoxLayout(self.sidebar);side.setContentsMargins(0,0,0,0);side.setSpacing(14)
        identity,box=card('AI CONNECTION');self.brain_name=label('Connect AI',20,TEXT,True);box.addWidget(self.brain_name);self.brain_note=label('Local hearing, speech and memory',12,MUTED);box.addWidget(self.brain_note);box.addWidget(button('Connect cloud AI',self.openai_connection));side.addWidget(identity)
        health,box=card('SYSTEM');self.cpu=QProgressBar();self.cpu.setFormat('CPU  %p%');self.mem=QProgressBar();self.mem.setFormat('RAM  %p%');box.addWidget(self.cpu);box.addWidget(self.mem);self.memory_info=label('',12,MUTED);box.addWidget(self.memory_info);side.addWidget(health)
        mode,box=card('CURRENT MODE');self.mode_label=label('Assistant',20,TEXT,True);box.addWidget(self.mode_label);self.mode_note=label('Say “enable eye control”\nor “pair my iPad”.',12,MUTED);box.addWidget(self.mode_note);box.addWidget(button('Change mode',lambda:self.navigate('modes')));side.addWidget(mode)
        side.addStretch();self.privacy=label('LOCAL AI  ·  REMOTE ACCESS OFF',10,CYAN,True);side.addWidget(self.privacy);body.addWidget(self.sidebar)
        self.pages=QStackedWidget();body.addWidget(self.pages,1)
        dashboard=QWidget();dashboard_layout=QVBoxLayout(dashboard);dashboard_layout.setContentsMargins(0,0,0,0);dashboard_layout.setSpacing(10)
        old_hud=window.hud;old_hud.setParent(old);old_hud.hide()
        for timer in old_hud.findChildren(QTimer):timer.stop()
        import os
        from core.gestures import ROOT
        scene_available=any((ROOT/'assets'/name/'index.html').is_file() for name in ('echo-reference','echo-core'))
        if os.environ.get('JARVIS_OFFSCREEN_STATIC')=='1' or not scene_available:self.orb=Orb()
        else:
            from core.brahma_scene import Scene
            self.orb=Scene()
        window.hud=self.orb;window._hud_cam_stack.insertWidget(0,self.orb);window._hud_cam_stack.setCurrentWidget(self.orb)
        dashboard_layout.addWidget(window._center_split,1)
        operation,op=card('LIVE OPERATIONS');self.operation=label('Starting the local assistant…',12,MUTED);op.addWidget(self.operation);dashboard_layout.addWidget(operation)
        self.pages.addWidget(dashboard);self.modes_page=self.build_modes();self.pages.addWidget(self.modes_page);self.devices_page=self.build_devices();self.pages.addWidget(self.devices_page);self.settings_page=self.build_settings();self.pages.addWidget(self.settings_page)
        self.chat_card,chat_layout=card('CONVERSATION','Voice and typed requests share the same conversation.');self.chat_card.setMinimumWidth(280);self.chat_card.setMaximumWidth(365)
        old_log=window._log
        try:window._log_sig.disconnect(old_log.append_log)
        except (TypeError,RuntimeError):pass
        self.chat=ChatFeed(self);window._log=self.chat;window._log_sig.connect(self.chat.append_log);window._live_transcript_sig.connect(self.chat.live_transcript);chat_layout.addWidget(self.chat,1);body.addWidget(self.chat_card,1)
        layout.addLayout(body,1)
        command=QFrame();command.setObjectName('Glass');row=QHBoxLayout(command);row.setContentsMargins(12,10,12,10);row.setSpacing(10)
        attach=button('Attach',window._drop_zone._browse);row.addWidget(attach)
        window._input.setParent(command);window._input.setPlaceholderText('Ask JARVIS… or say “switch to gestures”');window._input.setMinimumHeight(44);window._input.setStyleSheet('');window._input.setAccessibleName('Command or question');row.addWidget(window._input,1)
        row.addWidget(button('Send',window._send,True));self.mic=button('Mic on',window._toggle_mute);row.addWidget(self.mic)
        self.talk=button('Hold to talk',lambda:None);self.talk.setToolTip('Hold while speaking, then release to send. This also turns the microphone on.')
        self.talk.pressed.connect(lambda:self.hold_to_talk(True));self.talk.released.connect(lambda:self.hold_to_talk(False));row.addWidget(self.talk)
        stop=button('Stop',self.stop_everything);stop.setObjectName('Stop');row.addWidget(stop);layout.addWidget(command)
        foot=QHBoxLayout();window._file_hint.setParent(self.root);window._file_hint.setStyleSheet('color:#bdbdbd;font-size:11px;');foot.addWidget(window._file_hint,1);clear=button('Clear file',self.clear_file);clear.setMinimumHeight(28);foot.addWidget(clear);self.motion=QCheckBox('Reduce motion');self.motion.toggled.connect(lambda value:setattr(self.orb,'reduced',value));foot.addWidget(self.motion);layout.addLayout(foot)
        for attr in ('_cam_preview','_clipboard_panel','_overlay'):
            item=getattr(window,attr,None)
            if item:item.setParent(self.root)
        if hasattr(self.orb,'motionPreference'):self.orb.motionPreference.connect(self.motion.setChecked)
        self.timer=QTimer(self.root);self.timer.timeout.connect(self.refresh);self.timer.start(500);self.navigate('dashboard');self.refresh()
        from core.local_capabilities import ProductivityStore
        from memory.local_database import database
        self.productivity=ProductivityStore(database())
        self.reminder_timer=QTimer(self.root);self.reminder_timer.timeout.connect(self.notify_due);self.reminder_timer.start(1000)
        QShortcut(QKeySequence('Ctrl+K'),window).activated.connect(window._input.setFocus)
        window._mode_sig.connect(self.mode_request)
    def drag_enter(self,event):
        if event.mimeData().hasUrls():event.acceptProposedAction()
    def drop(self,event):
        for url in event.mimeData().urls():
            if url.isLocalFile() and Path(url.toLocalFile()).is_file():self.window._drop_zone._set_file(url.toLocalFile());event.acceptProposedAction();break
    def clear_file(self):self.window._drop_zone.clear_file();self.window._file_hint.setText('No attachment · drop a file anywhere on this dashboard')
    def hold_to_talk(self,held):
        if held and self.window._muted:self.window._toggle_mute()
        self.window._ptt_hold(held)
        self.talk.setText('Listening… release' if held else 'Hold to talk')
        self.operation.setText('Speak now, then release Hold to talk.' if held else 'Recognizing your speech locally…')
    def scroll_page(self,content):
        scroll=QScrollArea();scroll.setWidgetResizable(True);scroll.setWidget(content);return scroll
    def build_modes(self):
        content=QWidget();self.mode_layout=QVBoxLayout(content);self.mode_layout.setContentsMargins(0,0,0,0);self.mode_layout.setSpacing(14)
        self.mode_layout.addWidget(label('One assistant. Different ways to interact.',25,TEXT,True));self.mode_layout.addWidget(label('Say a mode name, or choose one below. Camera and Windows input stay visible and controllable.',13,MUTED))
        grid=QGridLayout();grid.setSpacing(12)
        for i,(title,desc,mode) in enumerate([('Assistant','Voice, chat, files and local memory.','assistant'),('Eye control','Calibrated gaze pointer and optional dwell clicks.','eyes'),('Hand gestures','Pointer, pinch, scrolling and media controls.','gestures'),('Holo workspace','Two-hand interaction with notes and 3D objects.','holo')]):
            tile,box=card(title,desc);box.addWidget(button('Enter mode',lambda checked=False,value=mode:self.request({'mode':value,'action':'open'})));grid.addWidget(tile,i//2,i%2)
        self.mode_layout.addLayout(grid)
        self.pending_card,self.pending_box=card('LOCAL CAMERA PERMISSION');self.pending_note=label('',13);self.pending_box.addWidget(self.pending_note);self.pending_box.addWidget(button('Allow local camera for this mode',self.confirm,True));self.pending_box.addWidget(button('Cancel',self.cancel));self.pending_card.hide();self.mode_layout.addWidget(self.pending_card)
        self.mode_detail=QWidget();self.detail_layout=QVBoxLayout(self.mode_detail);self.detail_layout.setContentsMargins(0,0,0,0);self.mode_layout.addWidget(self.mode_detail);self.mode_layout.addStretch();return self.scroll_page(content)
    def build_devices(self):
        content=QWidget();box=QVBoxLayout(content);box.setContentsMargins(0,0,0,0);box.setSpacing(16);box.addWidget(label('Your devices, one private workspace.',25,TEXT,True))
        tile,inside=card('PAIR YOUR iPAD','Say “pair my iPad” to return here. Pairing uses a temporary code after private HTTPS access is configured.')
        self.device_status=label('Private remote access is currently off. Your iPad cannot reach the laptop from away until private HTTPS access is enabled.',14,MUTED);inside.addWidget(self.device_status);inside.addWidget(button('Show pairing code',self.window._open_remote));inside.addWidget(label('No public tunnel is enabled by changing modes. The PC must be awake and JARVIS running. iPad camera permission is granted on the iPad itself.',12,MUTED));box.addWidget(tile);box.addStretch();return self.scroll_page(content)
    def build_settings(self):
        content=QWidget();box=QVBoxLayout(content);box.setContentsMargins(0,0,0,0);box.setSpacing(14);box.addWidget(label('Make JARVIS yours.',25,TEXT,True))
        cloud,inside=card('AI CONNECTION','Gemini offers a limited free tier; OpenAI needs API credits. Your own key is required. Hearing, voice and cursor control stay local.');inside.addWidget(button('Connect / manage Gemini or OpenAI',self.openai_connection,True));box.addWidget(cloud)
        speech,inside=card('OFFLINE SPEECH','Windows voice uses Mark-LVI’s local system speech provider. Kokoro remains an optional offline British voice.')
        choice=QComboBox();choice.addItem('Windows native — Microsoft David','system_tts');choice.addItem('Kokoro — British George','kokoro')
        from memory.config_manager import get_pipeline
        choice.setCurrentIndex(max(0,choice.findData(get_pipeline().get('tts','system_tts'))))
        def switch_voice(index):
            from memory.config_manager import save_pipeline
            save_pipeline(tts=choice.itemData(index))
            if self.window.on_voice_change:self.window.on_voice_change()
        choice.activated.connect(switch_voice);inside.addWidget(choice);box.addWidget(speech)
        for name,desc,handler in [('Local memory','Inspect remembered conversations, documents and facts.',lambda:self.memory()),('Audio devices','Choose microphone and speakers.',self.window._open_audio_devices),('Voice and identity','Customize the assistant and its voice.',self.window._open_customize),('Speech providers','Manage on-device hearing and voice.',self.window._open_providers),('Plugins','Manage installed optional capabilities.',self.window._open_plugin_manager),('Listening controls','Wake phrase and push-to-talk settings.',lambda:self.controls())]:
            tile,inside=card(name,desc);inside.addWidget(button('Configure',handler));box.addWidget(tile)
        box.addStretch();return self.scroll_page(content)
    def memory(self):
        from core.database_panel import open_panel
        open_panel(self.window)
    def openai_connection(self):
        from core.openai_setup import open_dialog
        self._openai_dialog=open_dialog(self.window,self.window.on_voice_change)
    def controls(self):
        drawer=self.window._ctrl_drawer;drawer.setParent(self.root);self.window._position_ctrl_drawer();drawer.show();drawer.raise_()
    def navigate(self,key):
        index={'dashboard':0,'chat':0,'modes':1,'devices':2,'settings':3}.get(key,0);self.pages.setCurrentIndex(index)
        for name,item in self.nav.items():item.setChecked(name==key)
        self.chat_card.setVisible(key!='settings')
        if key=='chat':self.window._input.setFocus()
    def detail(self,mode):
        self.navigate('modes')
        while self.detail_layout.count():
            item=self.detail_layout.takeAt(0)
            if item.widget():item.widget().hide();item.widget().setParent(self.root)
        if mode=='eyes':
            if self.eye_panel is None:
                from core.eye_panel import EyePanel
                self.eye_panel=EyePanel(self.window);self.eye_panel.setWindowFlags(Qt.WindowType.Widget)
            panel=self.eye_panel
        else:
            if self.hand_panel is None:
                from core.gesture_panel import open_panel
                self.hand_panel=open_panel(self.window);self.hand_panel.setWindowFlags(Qt.WindowType.Widget)
            panel=self.hand_panel
        self.detail_layout.addWidget(panel);panel.show();return panel
    def request(self,spec):
        from core.gestures import service as hands
        from core.eye_control import service as eyes
        mode,action=spec['mode'],spec['action']
        if action=='confirm':return self.confirm()
        if action=='cancel':return self.cancel()
        self.mode_generation+=1
        self.pending=None;self.pending_card.hide()
        if mode=='modes':self.navigate('modes');return 'Modes are on screen. Choose assistant, eye control, gestures or Holo.'
        if mode=='devices':self.navigate('devices');return 'The iPad pairing page is open. Private HTTPS access must be configured before a pairing code can connect your iPad.'
        if action=='stop' or mode=='assistant':
            from core.holo_workspace import stop_camera
            stop_camera()
            hands.stop();eyes.stop();self.active_mode='assistant';self.pending=None;self.pending_card.hide();self.navigate('dashboard');return 'Camera controls stopped. Assistant mode is active.'
        if mode=='holo':
            from core.holo_workspace import open_workspace
            hands.stop();eyes.stop();open_workspace(self.window);self.active_mode='holo';return 'The separate local Holo workspace is open. Start its camera when ready.'
        panel=self.detail(mode)
        if action=='open':return ('Eye' if mode=='eyes' else 'Gesture')+' mode is open. Camera controls are on screen.'
        if action=='head':panel.setup_head();return 'Starting the local head-assisted cursor. Face the camera and move your head to steer; Ctrl+Alt+G stops.'
        if action=='calibrate':panel.calibration();return 'Follow the calibration dots on screen. Press Space to start.' if eyes.active else 'Start the eye camera first, then calibrate.'
        if action in ('pointer','dwell'):
            if mode=='gestures':
                try:hands.set_control(True);return 'Hand pointer enabled. Raise only your index finger to move; pinch to click. Open palm pauses.'
                except Exception as error:return str(error)
            try:eyes.pointer_mode='gaze';eyes.set_control(True,action=='dwell');return 'Eye pointer enabled.' if action=='pointer' else 'Eye pointer and dwell clicks enabled.'
            except Exception as error:return str(error)
        from memory.local_database import database
        self.pending={'mode':mode,'action':'enable','expires':time.monotonic()+60}
        if database().setting('camera_consent_'+mode,'0')!='1':
            self.pending_note.setText('Allow local '+('eye tracking' if mode=='eyes' else 'hand tracking')+' camera access? Video stays in memory on this laptop. '+('Finish calibration before enabling the eye cursor.' if mode=='eyes' else 'Confirming starts Windows pointer control. Point to move; pinch to click; Ctrl+Alt+G stops.')+' You can also say “confirm mode”.')
            self.pending_card.show();return 'Please confirm local camera access in the mode card, or say confirm mode.'
        return self.activate(mode)
    def confirm(self):
        if not self.pending:return 'There is no mode request waiting for confirmation.'
        if time.monotonic()>self.pending['expires']:
            self.cancel();return 'That camera request expired. Ask to enable the mode again.'
        from memory.local_database import database
        mode=self.pending['mode'];database().set_setting('camera_consent_'+mode,'1');self.pending=None;self.pending_card.hide();return self.activate(mode)
    def cancel(self):self.mode_generation+=1;self.pending=None;self.pending_card.hide();return 'Mode change cancelled.'
    def activate(self,mode):
        from core.gestures import service as hands
        from core.eye_control import service as eyes
        from core.holo_workspace import stop_camera
        self.mode_generation+=1;generation=self.mode_generation;self.pending=None;self.pending_card.hide()
        stop_camera();hands.stop();eyes.stop();panel=self.detail(mode)
        def start(attempt=0):
            if generation!=self.mode_generation:return
            if (hands.thread and hands.thread.is_alive()) or (eyes.thread and eyes.thread.is_alive()):
                if attempt<25:QTimer.singleShot(80,lambda:start(attempt+1));return
                self.operation.setText('The previous camera is still stopping. Try enabling the mode again.');return
            try:
                if mode=='eyes':eyes.start(panel.camera.currentData())
                else:
                    hands.arm('pc',True,panel.camera.currentData())
                    from core.gesture_preview import open_preview
                    open_preview(panel)
                self.active_mode=mode;self.operation.setText('Eye camera started. Click Calibrate eyes, finish the dots, then Enable eye pointer.' if mode=='eyes' else 'Hand cursor ON. Raise only your index finger to move. Pinch clicks. Ctrl+Alt+G stops.')
            except Exception as error:self.operation.setText(str(error));self.window._log_sig.emit('ERR: '+str(error))
        QTimer.singleShot(1700,start);return ('Eye' if mode=='eyes' else 'Gesture')+' mode selected. Starting the local camera in preview.'
    def mode_request(self,payload):
        spec,reply=payload
        try:reply(self.request(spec))
        except Exception as error:reply('Mode change failed: '+str(error))
    def stop_everything(self):
        self.request({'mode':'assistant','action':'stop'});self.window._do_interrupt()
    def notify_due(self):
        try:
            for item in self.productivity.due():
                text='Reminder: '+item['title'];self.window._log_sig.emit('JARVIS: '+text)
                self.window._content_sig.emit('REMINDER',text)
                from PyQt6.QtWidgets import QApplication
                QApplication.alert(self.window,10000);QApplication.beep()
        except Exception as error:self.operation.setText('Reminder check failed: '+str(error))
    def refresh(self):
        if self.pending and time.monotonic()>self.pending['expires']:self.cancel()
        self.clock.setText(datetime.now().strftime('%H:%M  ·  %d %b'));self.mic.setText('Mic off' if self.window._muted else 'Mic on')
        from core.cloud_config import active,load
        cloud=active();vendor='Gemini' if load().get('provider')=='gemini_cloud' else 'OpenAI'
        self.brain_name.setText(load().get('model','OpenAI') if cloud else 'AI not connected')
        self.brain_badge.setText(vendor.upper()+' CLOUD' if cloud else 'CONNECT CLOUD AI')
        self.brain_note.setText('AI requests and relevant memory go to '+vendor+'. Hearing, voice and storage stay on this PC.' if cloud else 'Connect Gemini or OpenAI for answers. No offline AI is installed.')
        self.privacy.setText((vendor.upper()+' CLOUD' if cloud else 'AI DISCONNECTED')+'  ·  REMOTE ACCESS OFF')
        from memory.config_manager import get_push_to_talk_enabled
        from core.hotkey import chord_label
        self.mic.setToolTip('Microphone muted' if self.window._muted else ('Hold '+chord_label()+' or Hold to talk to speak.' if get_push_to_talk_enabled() else 'Listening automatically. Hold to talk sends when released.'))
        from core.gestures import service as hands
        from core.eye_control import service as eyes
        state=eyes.snapshot()
        if state['active']:self.mode_label.setText('Head-assisted cursor' if state['pointer_mode']=='head' else 'Eye control');self.mode_note.setText('Pointer active' if state['control'] else 'Preview · pointer off')
        elif hands.mode!='off':self.mode_label.setText('Hand gestures');self.mode_note.setText('Windows input on' if hands.control else 'Preview · input off')
        else:self.mode_label.setText('Holo workspace' if self.active_mode=='holo' else 'Assistant');self.mode_note.setText('Say “show modes” to switch.')
        try:
            import psutil
            self.cpu.setValue(round(psutil.cpu_percent()));self.mem.setValue(round(psutil.virtual_memory().percent))
            from memory.local_database import database
            counts=database().stats();self.memory_info.setText(f"{counts['messages']} saved messages\n{counts['documents']} imported documents")
        except Exception:pass

def install(window):
    shell=UnifiedShell(window);window._unified=shell;return shell
