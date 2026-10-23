"""Inspect, search, pause and clear persistent local memory."""
def open_panel(parent):
    from PyQt6.QtWidgets import QDialog,QVBoxLayout,QLabel,QLineEdit,QPushButton,QTextEdit,QCheckBox,QMessageBox
    from memory.local_database import database
    store=database();dialog=QDialog(parent);dialog.setWindowTitle('JARVIS — Local database');dialog.resize(760,620)
    layout=QVBoxLayout(dialog);info=QLabel('Stored on this laptop: '+str(store.path));info.setWordWrap(True);layout.addWidget(info)
    stats=QLabel();layout.addWidget(stats)
    remember=QCheckBox('Remember JARVIS conversations');remember.setChecked(store.setting('remember','1')=='1')
    remember.toggled.connect(lambda checked:store.set_setting('remember','1' if checked else '0'));layout.addWidget(remember)
    query=QLineEdit();query.setPlaceholderText('Search remembered conversations and selected documents');layout.addWidget(query)
    output=QTextEdit();output.setReadOnly(True);layout.addWidget(output)
    def refresh():
        counts=store.stats();stats.setText(' · '.join(f'{name}: {value}' for name,value in counts.items()))
        if query.text().strip():rows=store.search(query.text(),20)
        else:rows=[{'kind':row['role'],'body':row['body']} for row in store.recent(30)]
        facts='\n'.join(row['name']+': '+row['value'] for row in store.facts())
        output.setPlainText(('Remembered facts:\n'+facts+'\n\n' if facts else '')+'\n\n'.join('['+row['kind']+']\n'+row['body'] for row in rows))
    search=QPushButton('Search / refresh');search.clicked.connect(refresh);query.returnPressed.connect(refresh);layout.addWidget(search)
    clear=QPushButton('Delete all local conversation and document memory')
    def erase():
        if QMessageBox.question(dialog,'Delete memory','Permanently delete JARVIS conversation history, imported text and remembered facts from this local database?')==QMessageBox.StandardButton.Yes:store.clear();refresh()
    clear.clicked.connect(erase);layout.addWidget(clear);refresh();dialog.show();parent._database_dialog=dialog;return dialog
