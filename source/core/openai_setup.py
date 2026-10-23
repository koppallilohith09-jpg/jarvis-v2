"""Masked OpenAI connection form. The key never enters chat or logs."""
import hashlib,threading
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QDialog,QVBoxLayout,QLabel,QLineEdit,QPushButton,QApplication,QComboBox,QCheckBox
from core import cloud_config
from providers.llm_openai_cloud import OpenAICloud,DEFAULT_MODEL
from providers.llm_gemini_cloud import GeminiCloud,DEFAULT_MODEL as GEMINI_MODEL

class ConnectionDialog(QDialog):
    tested=pyqtSignal(bool,str,str)
    models_checked=pyqtSignal(object,str)
    def __init__(self,parent=None,on_change=None):
        super().__init__(parent);self.on_change=on_change;self.setWindowTitle('JARVIS — AI connection');self.resize(610,590)
        self.setStyleSheet('QWidget{background:#111;color:#eee;font:14px "Segoe UI";} QLineEdit{padding:10px;border:1px solid #777;} QPushButton{padding:12px;border:1px solid #999;background:#292929;}')
        layout=QVBoxLayout(self)
        text=QLabel('Connect JARVIS AI\nGemini or OpenAI handles answers. Messages, selected file text and relevant memory go to that provider. Hearing, voice, cameras and storage stay on your PC. No offline AI model is installed.');text.setWordWrap(True);layout.addWidget(text)
        cfg=cloud_config.load()
        self.provider=QComboBox();self.provider.addItem('Gemini — Google AI Studio free tier available','gemini_cloud');self.provider.addItem('OpenAI — API credits required','openai_cloud');self.provider.setCurrentIndex(max(0,self.provider.findData(cfg.get('provider','openai_cloud' if cfg.get('api_key') else 'gemini_cloud'))));layout.addWidget(self.provider)
        link=QLabel('<a style="color:white" href="https://aistudio.google.com/apikey">Get a Gemini key</a> · <a style="color:white" href="https://platform.openai.com/api-keys">Get an OpenAI key</a>');link.setOpenExternalLinks(True);layout.addWidget(link)
        billing=QLabel('For Gemini without extra fees, use a free-tier AI Studio project without paid billing. Quotas apply. JARVIS cannot verify your project billing tier. <a style="color:white" href="https://platform.openai.com/settings/organization/billing/overview">OpenAI credits/billing</a>');billing.setWordWrap(True);billing.setOpenExternalLinks(True);layout.addWidget(billing)
        layout.addWidget(QLabel('API key — saved using Windows credential protection'))
        self.key=QLineEdit();self.key.setEchoMode(QLineEdit.EchoMode.Password);self.key.setText(cfg.get('api_key',''));self.key.setPlaceholderText('Paste your API key here');layout.addWidget(self.key)
        layout.addWidget(QLabel('AI model'))
        self.model=QLineEdit(cfg.get('model') or (GEMINI_MODEL if self.provider.currentData()=='gemini_cloud' else DEFAULT_MODEL));layout.addWidget(self.model)
        self.models_button=QPushButton('Check available Gemini models');self.models_button.clicked.connect(self.check_models);layout.addWidget(self.models_button)
        self.google_consent=QCheckBox('I understand Google may use free-tier prompts/replies to improve its products.');self.google_consent.setVisible(self.provider.currentData()=='gemini_cloud');layout.addWidget(self.google_consent)
        self.status=QLabel('Cloud AI is connected.' if cloud_config.active() else 'Not connected. Your key stays out of the ZIP and chat.');self.status.setWordWrap(True);layout.addWidget(self.status)
        self.connect_button=QPushButton('Test & connect selected AI');self.connect_button.clicked.connect(self.connect);layout.addWidget(self.connect_button)
        self.disconnect_button=QPushButton('Disconnect AI');self.disconnect_button.clicked.connect(self.disconnect);layout.addWidget(self.disconnect_button)
        self.tested.connect(self.finish_test)
        self.models_checked.connect(self.show_models)
        self.provider.currentIndexChanged.connect(self.provider_changed)
    def provider_changed(self):
        cfg=cloud_config.load();pid=self.provider.currentData();same=cfg.get('provider','openai_cloud')==pid
        self.key.setText(cfg.get('api_key','') if same else '');self.model.setText(cfg.get('model') if same and cfg.get('model') else (GEMINI_MODEL if pid=='gemini_cloud' else DEFAULT_MODEL));self.google_consent.setVisible(pid=='gemini_cloud');self.google_consent.setChecked(False)
        self.status.setText('Enter your own key, select a model, then connect. There is no offline AI fallback.')
        self.models_button.setVisible(pid=='gemini_cloud')
    def check_models(self):
        if self.provider.currentData()!='gemini_cloud':return
        key=self.key.text().strip()
        if not key:self.status.setText('Enter your Gemini key first.');return
        if not self.google_consent.isChecked():self.status.setText('Read and accept the Google data-use notice first.');return
        fingerprint=self.fingerprint();self.models_button.setEnabled(False);self.status.setText('Checking Google model access. This does not generate a reply…')
        def worker():
            try:result=GeminiCloud({'cloud_enabled':True,'api_key':key,'model':GEMINI_MODEL}).list_models()
            except Exception as error:result=str(error).replace(key,'[redacted]')
            self.models_checked.emit(result,fingerprint)
        threading.Thread(target=worker,daemon=True,name='gemini-model-check').start()
    def show_models(self,result,fingerprint):
        self.models_button.setEnabled(True)
        if fingerprint!=self.fingerprint():self.status.setText('Settings changed. Check models again.');return
        if isinstance(result,str):self.status.setText(result);return
        if not result:self.status.setText('No compatible Gemini text models were returned for this key.');return
        from PyQt6.QtWidgets import QInputDialog
        ordered=([GEMINI_MODEL] if GEMINI_MODEL in result else [])+[name for name in result if name!=GEMINI_MODEL]
        chosen,ok=QInputDialog.getItem(self,'Available Gemini models','Model access does not guarantee free quota. Use a free-tier project without paid billing.',ordered,0,False)
        if ok:self.model.setText(chosen);self.status.setText('Model selected. Click Test & connect selected AI.')
    def fingerprint(self):return hashlib.sha256((self.provider.currentData()+'\0'+self.key.text().strip()+'\0'+self.model.text().strip()).encode()).hexdigest()
    def connect(self):
        key=self.key.text().strip();model=self.model.text().strip()
        if not key:self.status.setText('Enter the API key in the field above.');return
        if self.provider.currentData()=='gemini_cloud' and not self.google_consent.isChecked():self.status.setText('Read and accept the Google free-tier data-use notice before connecting.');return
        cfg={'api_key':key,'model':model,'cloud_enabled':True};fingerprint=self.fingerprint()
        provider=GeminiCloud if self.provider.currentData()=='gemini_cloud' else OpenAICloud
        self.connect_button.setEnabled(False);self.disconnect_button.setEnabled(False);self.status.setText('Checking Gemini key/model access (no generated reply)…' if self.provider.currentData()=='gemini_cloud' else 'Testing OpenAI with a short billed request…')
        def worker():
            try:
                _,answer=provider(cfg).probe();self.tested.emit(True,str(answer)[:160],fingerprint)
            except Exception as error:self.tested.emit(False,str(error).replace(key,'[redacted]')[:300],fingerprint)
        threading.Thread(target=worker,daemon=True,name='openai-connection-test').start()
    def finish_test(self,ok,message,fingerprint):
        self.connect_button.setEnabled(True);self.disconnect_button.setEnabled(True)
        if fingerprint!=self.fingerprint():self.status.setText('Settings changed during the test. Test again before connecting.');return
        if not ok:self.status.setText(message);return
        try:
            if self.provider.currentData()=='gemini_cloud' and not self.google_consent.isChecked():self.status.setText('Data-use consent changed. Test again before connecting.');return
            cloud_config.save({'enabled':True,'provider':self.provider.currentData(),'api_key':self.key.text().strip(),'model':self.model.text().strip()})
            from providers import registry
            registry.reset()
            self.status.setText('Selected AI connected. '+message)
            if self.on_change:self.on_change()
        except Exception as error:self.status.setText('Connection could not be saved: '+str(error)[:160])
    def disconnect(self):
        cloud_config.disable()
        from providers import registry
        registry.reset();self.status.setText('AI disconnected. No offline model or automatic fallback is installed. Reconnect to receive AI answers.')
        if self.on_change:self.on_change()

def open_dialog(parent=None,on_change=None):
    dialog=ConnectionDialog(parent,on_change);dialog.show();dialog.raise_();dialog.activateWindow();return dialog

if __name__=='__main__':
    import sys
    from core.local_privacy import install_network_guard
    install_network_guard();app=QApplication([sys.argv[0]]);dialog=open_dialog();app.exec()
