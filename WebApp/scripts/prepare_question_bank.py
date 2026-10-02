from pathlib import Path
import json,re,urllib.request,pdfplumber
from PIL import Image
root=Path(__file__).resolve().parents[1]
pdf_path=root/'docs/600-cau-hoi-thi-ly-thuyet-lai-xe_hoclaixehcm.vn.pdf'
out=root/'docs/imports'; (out/'question-images').mkdir(exist_ok=True)
url='https://xaydungchinhsach.chinhphu.vn/60-cau-hoi-ve-xu-ly-tinh-huong-mat-an-toan-giao-thong-nghiem-trong-119250513145731021.htm'
raw=urllib.request.urlopen(url,timeout=30).read()
import gzip
html=(gzip.decompress(raw) if raw[:2]==b'\x1f\x8b' else raw).decode('utf-8')
critical=sorted(set(int(n) for n in re.findall(r'<h4[^>]*>\s*Câu\s+(\d+)\.',html)))
assert len(critical)==60, len(critical)
(out/'critical-source.json').write_text(json.dumps({'source':url,'numbers':critical},ensure_ascii=False,indent=2),encoding='utf-8')
questions=[]; current=None; option=None; regions=[]
with pdfplumber.open(pdf_path) as pdf:
 for page_no,page in enumerate(pdf.pages,1):
  words=page.extract_words(); lines=page.extract_text_lines()
  under=[r for r in page.rects if r['height']<=3 and r['width']>3 and r.get('non_stroking_color') in (0,0.0,(0,),(0,0,0))]+[r for r in page.lines if r['height']<2 and r['width']>3]
  starts=[]
  for line in lines:
   text=line['text'].strip(); heading=re.match(r'^Câu\s*(\d+)[.:]',text)
   if heading:
    n=int(heading[1]); current={'externalId':f'Q{n:03}','number':n,'text':text[heading.end():].strip(),'chapter':next(i+1 for i,e in enumerate([180,205,263,300,485,600]) if n<=e),'_options':{},'answerCandidates':[],'correctAnswer':None,'critical':n in critical,'source':pdf_path.name,'criticalSource':url,'sourcePages':[page_no],'reviewed':False,'needsReview':True,'imageRequired':False,'_first_option':{}}
    questions.append(current); option=None; starts.append((line['top'],current))
   if current is None or text.startswith('CHƯƠNG') or re.fullmatch(r'\d+',text): continue
   if page_no not in current['sourcePages']: current['sourcePages'].append(page_no)
   ws=[w for w in words if abs(w['top']-line['top'])<3 and w['bottom']<=line['bottom']+2]
   labels=[i for i,w in enumerate(ws) if re.fullmatch(r'[1-4]\.',w['text']) and (i==0 or w['x0']-ws[i-1]['x1']>20)]
   if labels and labels[0]==0:
    current['_first_option'].setdefault(page_no,line['top'])
    for part,idx in enumerate(labels):
     num=int(ws[idx]['text'][0])-1; end=labels[part+1] if part+1<len(labels) else len(ws)
     assert num not in current['_options'], (current['number'],num)
     current['_options'][num]=' '.join(w['text'] for w in ws[idx+1:end]); option=num
     left=ws[idx]['x0']; right=ws[end-1]['x1']
     if any(-4<=r['top']-line['bottom']<=3 and min(r['x1'],right)-max(r['x0'],left)>3 for r in under): current['answerCandidates'].append(num)
   elif not heading:
    if option is None: current['text']+=' '+text
    else:
     current['_options'][option]+=' '+text
     if any(-4<=r['top']-line['bottom']<=3 and r['x1']>line['x0'] and r['x0']<line['x1'] for r in under): current['answerCandidates'].append(option)
  # A question can continue onto the following page before the first heading.
  if starts and starts[0][0]>55 and len(questions)>len(starts):
   previous=questions[-len(starts)-1]; starts.insert(0,(0,previous))
  for index,(top,q) in enumerate(starts):
   bottom=starts[index+1][0] if index+1<len(starts) else page.height-30
   images=[im for im in page.images if im['top']>=top and im['bottom']<=bottom+1]
   if not images: continue
   image_top=min(im['top'] for im in images); image_bottom=max(im['bottom'] for im in images)
   # Include figure captions but stop before option text (and its underlined answers).
   first=q['_first_option'].get(page_no)
   if first and first>image_bottom: image_bottom=first-3
   else: image_bottom=min(image_bottom+16,bottom-2)
   box=(max(0,min(im['x0'] for im in images)-5),image_top,max(im['x1'] for im in images)+5,image_bottom)
   picture=page.crop(box).to_image(resolution=120).original.convert('RGB')
   path=out/'question-images'/f"{q['externalId']}-p{page_no}.png"; picture.save(path)
   q.setdefault('imageFiles',[]).append(path.name); q['imageRequired']=True
for q in questions:
 opts=q.pop('_options'); q.pop('_first_option'); assert sorted(opts)==list(range(len(opts))),q['number']; q['options']=[opts[i] for i in range(len(opts))]
 candidates=sorted(set(q['answerCandidates'])); q['answerCandidates']=candidates
 if len(candidates)==1: q['correctAnswer']=candidates[0]
assert [q['number'] for q in questions]==list(range(1,601))
assert all(2<=len(q['options'])<=4 for q in questions)
# Source page 46 visually verified: the first option of Q204 is underlined.
questions[203]['correctAnswer']=0
print('ambiguous',[(q['number'],q['answerCandidates']) for q in questions if q['correctAnswer'] is None])
assert questions[300]['options']==['Biển 1.','Biển 2.','Biển 1 và biển 3.','Cả ba biển.']
assert questions[300]['correctAnswer']==0 and questions[301]['correctAnswer']==3 and questions[351]['correctAnswer']==0
(out/'questions-draft.json').write_text(json.dumps(questions,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'questions':len(questions),'answers':sum(q['correctAnswer'] is not None for q in questions),'critical':sum(q['critical'] for q in questions),'images':sum(q['imageRequired'] for q in questions),'unresolved':[q['number'] for q in questions if q['correctAnswer'] is None]},ensure_ascii=False))


import runpy
runpy.run_path(str(root/'scripts/pack_question_images.py'))
