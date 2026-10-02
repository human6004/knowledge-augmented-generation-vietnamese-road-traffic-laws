from pathlib import Path
from PIL import Image
import json,zipfile,hashlib
root=Path(__file__).resolve().parents[1]; out=root/'docs/imports'
rows=json.loads((out/'questions-draft.json').read_text(encoding='utf-8'))
files=[]
for q in rows:
 if not q.get('imageFiles'): continue
 images=[Image.open(out/'question-images'/name).convert('RGB') for name in q['imageFiles']]
 picture=Image.new('RGB',(max(im.width for im in images),sum(im.height for im in images)),'white'); y=0
 for image in images: picture.paste(image,(0,y)); y+=image.height
 assert max(picture.size)<=4096
 target=out/'question-images'/f"{q['externalId']}.png"; picture.quantize(colors=256,dither=Image.Dither.NONE).save(target,optimize=True); files.append(target)
# Archives are deliberately split before the server's 20 MB upload ceiling.
parts=[]; group=[]; size=0
for file in files:
 if size+file.stat().st_size>18*1024*1024 and group: parts.append(group); group=[]; size=0
 group.append(file); size+=file.stat().st_size
if group: parts.append(group)
archives=[]
for number,group in enumerate(parts,1):
 name='question-images.zip' if len(parts)==1 else f'question-images-{number}.zip'; archives.append(name)
 with zipfile.ZipFile(out/name,'w',zipfile.ZIP_DEFLATED) as archive:
  for file in group: archive.write(file,file.name)
 assert (out/name).stat().st_size<=20*1024*1024
pdf=root/'docs/600-cau-hoi-thi-ly-thuyet-lai-xe_hoclaixehcm.vn.pdf'
(out/'question-audit.json').write_text(json.dumps({'pdfSha256':hashlib.sha256(pdf.read_bytes()).hexdigest(),'source':pdf.name,'criticalSource':json.loads((out/'critical-source.json').read_text(encoding='utf-8'))['source'],'questions':len(rows),'answers':sum(q['correctAnswer'] is not None for q in rows),'critical':sum(q['critical'] for q in rows),'images':len(files),'archives':archives,'manualChecks':{'204':{'page':46,'correctAnswer':0},'301':{'page':69,'correctAnswer':0},'302':{'page':69,'correctAnswer':3},'352':{'page':86,'correctAnswer':0}},'publication':'draft; explicit administrator approval required'},ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'archives':archives,'bytes':sum((out/name).stat().st_size for name in archives),'images':len(files)}))
