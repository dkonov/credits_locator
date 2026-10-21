#!/usr/bin/env python3
"""Convert v0.3 credits_raw.json to tracked lines and conservative role/person pairs."""
import argparse, json, re
from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
from statistics import median

def norm(s): return re.sub(r'[^a-zа-яё0-9]','',s.lower())
def center(l):
    b=l['bbox'];return ((b[0]+b[2])/2,(b[1]+b[3])/2)

def motion(frames):
    speeds=[]
    for a,b in zip(frames,frames[1:]):
        dt=b['time_sec']-a['time_sec']
        if dt<=0 or dt>2.1:continue
        amap=defaultdict(list)
        for l in a['lines']:
            if len(norm(l['text']))>=8:amap[norm(l['text'])].append(center(l)[1])
        for l in b['lines']:
            positions=amap.get(norm(l['text']),[])
            if len(positions)==1:
                v=(center(l)[1]-positions[0])/dt
                if -.25<v<-.005:speeds.append(v)
    return median(speeds) if speeds else None

def reconstruct(frames,min_observations=2,max_position_gap=.023):
    frames=sorted(frames,key=lambda f:f['time_sec'])
    if not frames:return [],None
    speed=motion(frames)
    if speed is None:return [],None
    t0=frames[0]['time_sec'];tracks=[]
    for f in frames:
        t=f['time_sec']
        for line in f['lines']:
            txt=line['text'].strip()
            if len(norm(txt))<3:continue
            x,y=center(line); anchor=y-speed*(t-t0)
            side='left' if x<.50 else 'right'
            candidates=[]
            for track in tracks:
                if track['side']!=side or abs(track['anchor']-anchor)>max_position_gap:continue
                similarity=SequenceMatcher(None,norm(txt),norm(track['best_text'])).ratio()
                if similarity<.48:continue
                candidates.append((abs(track['anchor']-anchor)-.009*similarity,track))
            if candidates:
                track=min(candidates,key=lambda x:x[0])[1]
                if t in track['times']:continue
                n=track['observations']
                track['anchor']=(track['anchor']*n+anchor)/(n+1)
                track['times'].append(t);track['observations']+=1
                if line['confidence']>track['confidence'] or (line['confidence']==track['confidence'] and len(txt)>len(track['best_text'])):
                    track['best_text']=txt;track['confidence']=line['confidence']
                track['variants'][txt]+=1
            else:
                tracks.append({'side':side,'anchor':anchor,'best_text':txt,'confidence':line['confidence'],
                  'observations':1,'times':[t],'variants':defaultdict(int,{txt:1})})
    result=[]
    for tr in sorted(tracks,key=lambda x:x['anchor']):
        if tr['observations']<min_observations:continue
        result.append({'id':f'line_{len(result)+1:04}','text':tr['best_text'],'side':tr['side'],
          'scroll_y':round(tr['anchor'],5),'observations':tr['observations'],'confidence':tr['confidence'],
          'first_seen_sec':min(tr['times']),'last_seen_sec':max(tr['times']),
          'variants':dict(tr['variants'])})
    return result,speed

def structure(tracks):
    tracks=sorted(tracks,key=lambda x:x['scroll_y'])
    role_re=re.compile(r'(автор сценария|режисс[её]р|продюсер|оператор|художник|постановщик|звукорежисс|гафф?ер|осветител|фокус.пуллер|механик|монтаж|цветокоррекц|консультант|конультант|скрипт|администратор|хелпер)',re.I)
    plural=re.compile(r'^(продюсеры|осветители|хелперы)',re.I)
    left=[x for x in tracks if x['side']=='left']
    right=[x for x in tracks if x['side']=='right']
    roles=[x for x in left if role_re.search(x['text'])]
    thanks=next((x for x in left if 'отдельная благодарность' in x['text'].lower()),None)
    credits=[];review=[]
    for person in right:
        y=person['scroll_y']
        if thanks and y>thanks['scroll_y']:
            credits.append({'role':'Отдельная благодарность','person':person['text'],
                'kind':'thanks','evidence':[thanks['id'],person['id']],'needs_review':False})
            continue
        nearest=min(left,key=lambda l:abs(l['scroll_y']-y),default=None)
        if nearest and abs(nearest['scroll_y']-y)<=.020:
            label=nearest['text']
            if label.lower().startswith(('в ролях','над фильмом')):
                review.append({'name':person['text'],'reason':'matched heading','evidence':[person['id'],nearest['id']]})
                continue
            kind='role' if nearest in roles else 'character'
            credits.append({'role':label,'person':person['text'],'kind':kind,
                'evidence':[nearest['id'],person['id']],'needs_review':False})
            continue
        preceding=[l for l in left if l['scroll_y']<y]
        last=preceding[-1] if preceding else None
        if last and y-last['scroll_y']<=.095 and plural.search(last['text']):
            credits.append({'role':last['text'],'person':person['text'],'kind':'group_continuation',
               'evidence':[last['id'],person['id']],'needs_review':False})
        else:
            review.append({'name':person['text'],'reason':'no reliable role aligned; OCR might have missed label',
               'evidence':[person['id']]})
    if thanks:
        for l in left:
            if l['scroll_y']>thanks['scroll_y'] and not l['text'].lower().startswith(('гкб','отдельная')):
                if not role_re.search(l['text']):
                    credits.append({'role':'Отдельная благодарность','person':l['text'],
                        'kind':'thanks','evidence':[thanks['id'],l['id']],'needs_review':False})
    used={id for c in credits for id in c['evidence']}
    for l in roles:
        if l['id'] not in used:
            review.append({'role':l['text'],'reason':'role without matched name','evidence':[l['id']]})
    return credits,review

def run(source,destination,min_observations=2):
    raw=json.loads(Path(source).read_text(encoding='utf8'))
    obj={'video':raw.get('video'),'method':'scroll-motion track alignment v0.4','intervals':[]}
    for interval in raw['intervals']:
        lines,speed=reconstruct(interval['frames'],min_observations)
        credits,review=structure(lines)
        obj['intervals'].append({'boundary_estimate':interval.get('boundary_estimate'),
           'vertical_speed_per_second':round(speed,5) if speed is not None else None,
           'tracked_lines':lines,'credits':credits,'review':review})
    Path(destination).parent.mkdir(parents=True,exist_ok=True)
    Path(destination).write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8')
    print('Saved',destination,'credits',sum(len(x['credits']) for x in obj['intervals']))
    return obj

if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--input',required=True,type=Path)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--min-observations',type=int,default=2)
    a=p.parse_args();run(a.input,a.output,a.min_observations)
