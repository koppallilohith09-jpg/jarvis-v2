"""Launch Windows executables, shortcuts or registered app IDs; no typing."""
from functools import lru_cache
import os
from pathlib import Path
import re
import shutil
import subprocess

def key(name):return re.sub(r'[^a-z0-9]','',name.casefold().removesuffix('.exe'))

@lru_cache(maxsize=1)
def index():
    result={}
    def add(name,target):result.setdefault(key(name),target)
    roots=[Path(os.environ.get('APPDATA',''))/'Microsoft/Windows/Start Menu/Programs',Path(os.environ.get('PROGRAMDATA','C:/ProgramData'))/'Microsoft/Windows/Start Menu/Programs']
    for root in roots:
        if root.is_dir():
            for path in root.rglob('*.lnk'):add(path.stem,('shortcut',str(path)))
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER,winreg.HKEY_LOCAL_MACHINE):
            for access in (winreg.KEY_READ|winreg.KEY_WOW64_64KEY,winreg.KEY_READ|winreg.KEY_WOW64_32KEY):
                try:
                    with winreg.OpenKey(hive,r'Software\Microsoft\Windows\CurrentVersion\App Paths',0,access) as registry:
                        for i in range(winreg.QueryInfoKey(registry)[0]):
                            name=winreg.EnumKey(registry,i)
                            try:
                                with winreg.OpenKey(registry,name) as entry:
                                    target=str(winreg.QueryValue(entry,None)).strip('"')
                                    if Path(target).is_file():add(name,('exe',target))
                            except OSError:pass
                except OSError:pass
    except ImportError:pass
    return result

def _start(target):
    if target[0]=='shortcut':os.startfile(target[1])
    elif target[0]=='store':subprocess.Popen(['explorer.exe','shell:AppsFolder\\'+target[1]],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    else:subprocess.Popen([target[1]],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return True

def launch(name):
    name=name.strip()
    if not name or any(c in name for c in ('\n','\r',';','|','&','<','>')):return False
    if name.casefold() in ('ms-settings:','spotify:','steam:'):
        os.startfile(name);return True
    path=shutil.which(name)
    if path and Path(path).suffix.casefold()=='.exe':return _start(('exe',path))
    target=index().get(key(name))
    if target:return _start(target)
    try:
        import json
        data=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command','Get-StartApps | ConvertTo-Json -Compress'],capture_output=True,text=True,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
        apps=json.loads(data.stdout or '[]');apps=apps if isinstance(apps,list) else [apps]
        for app in apps:
            if isinstance(app,dict) and app.get('AppID'):index().setdefault(key(app.get('Name','')),('store',app['AppID']))
        match=index().get(key(name))
        if match:return _start(match)
    except (OSError,ValueError,subprocess.SubprocessError):pass
    return False
