"""Keep server output redacted; credentials remain process-local and never written."""
import json,os,re,subprocess
from pathlib import Path
from urllib.parse import urlsplit
root=Path(__file__).resolve().parent
os.umask(0o077)
values=[]
for line in Path('/workspace/competition/secrets/deepseek.env').read_text().splitlines():
    if '=' in line and not line.lstrip().startswith('#'):
        values.append(line.split('=',1)[1].strip().strip('"\''))
for value in json.loads(Path('/workspace/competition/m3-demo-env/runtime/test-environment.json').read_text()).values():
    value=str(value)
    if '://' in value:
        password=urlsplit(value).password
        if password:values.append(password)
for value in json.loads(os.environ['DRILL_PRIVATE_JSON']).values():
    if '://' in str(value):
        password=urlsplit(str(value)).password
        if password:values.append(password)
process=subprocess.Popen([str(root/'start.sh')],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
root.joinpath('runtime','server.pid').write_text(str(process.pid)+'\n')
with root.joinpath('runtime','server.log').open('w') as log:
    for line in process.stdout:
        if '://' in line:continue
        for value in values:
            if len(value)>6:line=line.replace(value,'<redacted>')
        line=re.sub(r'sk-[A-Za-z0-9_-]+','<redacted>',line)
        log.write(line);log.flush();print(line,end='',flush=True)
raise SystemExit(process.wait())
