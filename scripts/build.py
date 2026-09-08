"""Only explicit public files may enter the deployment artifact."""
import json
import shutil
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PUBLIC_FILES=['index.html','styles.css','app.js','modules/domain.js','modules/vault.js','modules/agent-tools.js','modules/sources.js','modules/collector.js','data/jobs.json','data/latest-run.json']
def build():
    destination=ROOT/'dist'
    if destination.is_symlink():raise ValueError('dist cannot be a symlink')
    if destination.exists():shutil.rmtree(destination)
    for name in PUBLIC_FILES:
        source=ROOT/'web'/name
        if not source.exists():
            if name=='data/latest-run.json':continue
            raise ValueError(f'Missing public file: {name}')
        if source.is_symlink() or not source.resolve().is_relative_to((ROOT/'web').resolve()):raise ValueError('Public files must stay inside web')
        target=destination/name;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target)
    (destination/'.nojekyll').touch()
    data=json.loads((destination/'data/jobs.json').read_text())
    print(f'Public build: {len(PUBLIC_FILES)} allowlisted files, {len(data["jobs"])} public jobs')
if __name__=='__main__':build()
