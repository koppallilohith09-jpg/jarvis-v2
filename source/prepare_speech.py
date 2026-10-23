"""Explicit setup download for offline Whisper; never imported at runtime."""
from pathlib import Path
from huggingface_hub import HfApi,snapshot_download
ROOT=Path(__file__).resolve().parent
repo='Systran/faster-whisper-base'
revision=HfApi().model_info(repo).sha
snapshot_download(repo,revision=revision,local_dir=str(ROOT/'models/whisper-base'),allow_patterns=['config.json','model.bin','tokenizer.json','vocabulary.*','preprocessor_config.json'])
(ROOT/'models/whisper-base/UPSTREAM_REVISION.txt').write_text(repo+'\n'+revision+'\n')
print('Offline speech model ready:',revision)
