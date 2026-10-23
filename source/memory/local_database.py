"""Persistent local SQLite memory. Only selected files and JARVIS activity."""
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import threading
import time
import uuid

def data_dir():
    return Path(os.environ.get('JARVIS_DATA_DIR') or Path(os.environ.get('LOCALAPPDATA',str(Path.home())))/'JARVISLocal/data')

def words(query):
    stop={'what','which','does','this','that','about','please','tell','have','with','from','your','remember','file','analyse','analyze','summarize','summarise','the','and','you','for','can','are','was','how','did','say','said'}
    return [word for word in re.findall(r'\w+',query.casefold()) if len(word)>2 and word not in stop][:12]

class LocalDatabase:
    def __init__(self,path=None):
        self.path=Path(path) if path else data_dir()/'jarvis.sqlite3'
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as connection:
            connection.executescript('''
              PRAGMA journal_mode=WAL;
              CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY,created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS messages(id INTEGER PRIMARY KEY,session TEXT,role TEXT NOT NULL,body TEXT NOT NULL,created REAL NOT NULL);
              CREATE INDEX IF NOT EXISTS messages_session ON messages(session,id);
              CREATE TABLE IF NOT EXISTS documents(id INTEGER PRIMARY KEY,path TEXT NOT NULL,title TEXT NOT NULL,sha TEXT NOT NULL UNIQUE,body TEXT NOT NULL,created REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS facts(name TEXT PRIMARY KEY,value TEXT NOT NULL,updated REAL NOT NULL);
              CREATE TABLE IF NOT EXISTS settings(name TEXT PRIMARY KEY,value TEXT NOT NULL);
            ''')
            try:
                connection.execute('CREATE VIRTUAL TABLE IF NOT EXISTS search_index USING fts5(kind UNINDEXED, item_id UNINDEXED, body)')
                self.fts=True
            except sqlite3.OperationalError:self.fts=False
    @contextmanager
    def connect(self):
        connection=sqlite3.connect(self.path,timeout=10)
        connection.row_factory=sqlite3.Row
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback();raise
        finally:connection.close()
    def session(self):
        value=uuid.uuid4().hex
        with self.connect() as c:c.execute('INSERT INTO sessions VALUES (?,?)',(value,time.time()))
        return value
    def setting(self,name,default=''):
        with self.connect() as c:row=c.execute('SELECT value FROM settings WHERE name=?',(name,)).fetchone()
        return row['value'] if row else default
    def set_setting(self,name,value):
        with self.connect() as c:c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',(name,str(value)))
    def add_message(self,session,role,body):
        if self.setting('remember','1')!='1' or not str(body).strip():return
        with self.connect() as c:
            c.execute('INSERT OR IGNORE INTO sessions VALUES (?,?)',(session,time.time()))
            row=c.execute('INSERT INTO messages(session,role,body,created) VALUES (?,?,?,?)',(session,role,str(body),time.time()))
            if self.fts:c.execute('INSERT INTO search_index(kind,item_id,body) VALUES (?,?,?)',('message',str(row.lastrowid),str(body)))
        if role=='user':self.learn_explicit(body)
    def learn_explicit(self,text):
        for field,pattern in [('name',r'\bmy name is\s+([^.!?\n]{1,80})'),('location',r'\bi live in\s+([^.!?\n]{1,120})')]:
            match=re.search(pattern,text,re.I)
            if match:self.set_fact(field,match.group(1).strip())
        match=re.match(r'\s*(?:please\s+)?remember(?:\s+that)?\s+(.+)',text,re.I|re.S)
        if match:
            value=match.group(1).strip();self.set_fact('note_'+hashlib.sha256(value.encode()).hexdigest()[:12],value)
    def set_fact(self,name,value):
        with self.connect() as c:c.execute('INSERT OR REPLACE INTO facts VALUES (?,?,?)',(str(name),str(value),time.time()))
    def facts(self):
        with self.connect() as c:return [dict(row) for row in c.execute('SELECT * FROM facts ORDER BY updated DESC')]
    def recent(self,limit=12):
        with self.connect() as c:rows=list(c.execute("SELECT * FROM messages WHERE role IN ('user','assistant') ORDER BY id DESC LIMIT ?",(limit,)))
        return [dict(row) for row in reversed(rows)]
    def import_document(self,path):
        path=Path(path).resolve()
        if not path.is_file():raise ValueError('The selected file is unavailable. Select it again.')
        if path.suffix.lower() not in ('.txt','.md','.log','.rst','.csv','.json','.py','.js','.ts'):
            raise ValueError('This direct offline reader supports text files. Use the file tool for other formats.')
        if path.stat().st_size>10*1024*1024:raise ValueError('This file exceeds the 10 MB local text import limit.')
        blob=path.read_bytes();digest=hashlib.sha256(blob).hexdigest()
        for encoding in (('utf-16','utf-8-sig','cp1252') if blob.startswith((b'\xff\xfe',b'\xfe\xff')) else ('utf-8-sig','cp1252')):
            try:body=blob.decode(encoding);break
            except UnicodeError:continue
        else:raise ValueError('Unable to decode this text file.')
        if not body.strip():raise ValueError('The selected text file is empty.')
        with self.connect() as c:
            row=c.execute('SELECT id FROM documents WHERE sha=?',(digest,)).fetchone()
            if row:return int(row['id'])
            inserted=c.execute('INSERT INTO documents(path,title,sha,body,created) VALUES (?,?,?,?,?)',(str(path),path.name,digest,body,time.time()))
            document_id=inserted.lastrowid
            if self.fts:
                for offset in range(0,len(body),2500):c.execute('INSERT INTO search_index(kind,item_id,body) VALUES (?,?,?)',('document',str(document_id),body[offset:offset+2800]))
        return document_id
    def document(self,document_id):
        with self.connect() as c:row=c.execute('SELECT * FROM documents WHERE id=?',(document_id,)).fetchone()
        return dict(row) if row else None
    def documents(self,limit=30):
        with self.connect() as c:return [dict(row) for row in c.execute('SELECT id,title,body,created FROM documents ORDER BY id DESC LIMIT ?',(limit,))]
    def search(self,query,limit=8,kind=None,item_id=None):
        terms=words(query)
        with self.connect() as c:
            if self.fts and terms:
                sql='SELECT kind,item_id,body FROM search_index WHERE search_index MATCH ?';args=[' OR '.join('"'+word+'"' for word in terms)]
                if kind:sql+=' AND kind=?';args.append(kind)
                if item_id is not None:sql+=' AND item_id=?';args.append(str(item_id))
                sql+=' ORDER BY rank LIMIT ?';args.append(limit)
                return [dict(row) for row in c.execute(sql,args)]
            if kind=='document' and item_id is not None:
                row=c.execute('SELECT body FROM documents WHERE id=?',(item_id,)).fetchone()
                return [{'kind':'document','item_id':str(item_id),'body':row['body'][:6000]}] if row else []
            rows=c.execute('SELECT id,body FROM messages WHERE body LIKE ? ORDER BY id DESC LIMIT ?',('%'+(terms[0] if terms else query)+'%',limit))
            return [{'kind':'message','item_id':str(row['id']),'body':row['body']} for row in rows]
    def context(self,query):
        facts='\n'.join(row['name']+': '+row['value'] for row in self.facts())[:1200]
        recalled='\n'.join(row['body'][:650] for row in self.search(query,4))[:2400]
        return (facts+'\n'+recalled).strip()
    def stats(self):
        with self.connect() as c:return {name:c.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ('sessions','messages','documents','facts')}
    def clear(self):
        with self.connect() as c:
            for table in ('messages','documents','facts','sessions'):c.execute('DELETE FROM '+table)
            if self.fts:c.execute('DELETE FROM search_index')
            c.execute("INSERT OR REPLACE INTO settings VALUES ('memory_epoch',?)",(str(time.time()),))

_database=None
_lock=threading.Lock()
def database():
    global _database
    with _lock:
        if _database is None:_database=LocalDatabase()
        return _database
