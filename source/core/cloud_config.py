"""Per-Windows-user OpenAI connection; never packaged in the portable app."""
from memory.local_database import data_dir
from core.secure_config import loads,dumps

def path():return data_dir().parent/'openai-connection.json'
def load():
    try:return loads(path().read_text(encoding='utf-8'))
    except (OSError,ValueError):return {}
def save(values):
    target=path();target.parent.mkdir(parents=True,exist_ok=True)
    temporary=target.with_suffix('.tmp');temporary.write_text(dumps(values,indent=2),encoding='utf-8');temporary.replace(target)
def active():
    cfg=load();return cfg.get('enabled') is True and bool(cfg.get('api_key'))

def provider_id():return load().get('provider','openai_cloud') if active() else ''
def disable():
    cfg=load();cfg['enabled']=False;save(cfg)
