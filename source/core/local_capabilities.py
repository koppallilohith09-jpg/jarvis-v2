"""Local implementations of the requested Brahma productivity capabilities.

No reference bootstrap, cloud completion, arbitrary shell, or generated-code execution.
"""
import asyncio,csv,io,json,math,os,re,time,uuid
from datetime import datetime,timedelta,timezone
from pathlib import Path
from xml.sax.saxutils import escape

def normalize(text):
    value=re.sub(r'^(?:hey\s+)?jarvis[,\s:]+','',str(text).strip(),flags=re.I)
    return re.sub(r'^(?:(?:can|could|would) you\s+)?(?:please\s+)?','',value,flags=re.I).strip().rstrip('.!?')

def parse(text):
    if not isinstance(text,str):return None
    text=normalize(text);lower=text.casefold()
    if lower in ('run system diagnostics','system diagnostics','check my laptop','check system health','show system status'):
        return {'feature':'diagnostics','action':'status'}
    if lower in ('what is using my ram','show memory usage','show ram usage','show top processes'):
        return {'feature':'diagnostics','action':'processes'}
    if lower in ('daily briefing','give me my daily briefing','give me a daily briefing','morning briefing','show my day'):
        return {'feature':'briefing'}
    if lower in ('show my calendar','show my schedule','list reminders','show reminders','show upcoming events'):
        return {'feature':'calendar','action':'list'}
    if lower in ('export my calendar','export calendar'):
        return {'feature':'calendar','action':'export'}
    if lower in ('list routines','show routines','list protocols'):
        return {'feature':'routine','action':'list'}
    if lower in ('show local models','list local models','local model status'):
        return {'feature':'models'}
    if lower in ('open my outputs','open generated files','open my generated files'):
        return {'feature':'outputs'}
    match=re.fullmatch(r'(?:read|summari[sz]e|explain|translate) (?:my |the )?clipboard(?: (?:to|in) (.{1,50}))?',text,re.I)
    if match:return {'feature':'clipboard','request':text,'read':lower.startswith('read ')}
    match=re.fullmatch(r'remind me in (\d+(?:\.\d+)?) (seconds?|minutes?|hours?|days?) to (.{1,500})',text,re.I)
    if match:
        n,unit,title=match.groups();scale={'s':1,'m':60,'h':3600,'d':86400}[unit[0].lower()]
        return {'feature':'calendar','action':'add','title':title,'delay':float(n)*scale,'duration':0}
    match=re.fullmatch(r'remind me to (.{1,500}) in (\d+(?:\.\d+)?) (seconds?|minutes?|hours?|days?)',text,re.I)
    if match:return parse('remind me in '+match[2]+' '+match[3]+' to '+match[1])
    match=re.fullmatch(r'(?:schedule|add to my calendar) (.{1,200}?) on (\d{4}-\d{2}-\d{2}) at (\d{1,2}:\d{2})(?: for (\d+) minutes?)?',text,re.I)
    if match:
        title,day,clock,duration=match.groups()
        return {'feature':'calendar','action':'add','title':title,'when':day+'T'+clock,'duration':int(duration or 30)}
    match=re.fullmatch(r'(?:cancel|delete) (?:reminder|event) ([a-f0-9]{8})',lower)
    if match:return {'feature':'calendar','action':'cancel','id':match[1]}
    match=re.fullmatch(r'save (?:routine|protocol) ([\w -]{1,50}):\s*(.+)',text,re.I|re.S)
    if match:return {'feature':'routine','action':'save','name':match[1].strip(),'steps':[s.strip() for s in match[2].split(';') if s.strip()]}
    match=re.fullmatch(r'(run|delete) (?:routine|protocol) ([\w -]{1,50})',text,re.I)
    if match:return {'feature':'routine','action':match[1].lower(),'name':match[2].strip()}
    match=re.fullmatch(r'(?:create|make|write|generate|build|draft|i need|i want|give me)(?: me)?(?: an?| the)? (word document|word doc|docx|pdf|presentation|powerpoint|ppt|slide deck|spreadsheet|excel workbook|excel sheet)(?:\s+(?:about|on|for|with))?\s*:?\s*(.*)',text,re.I|re.S)
    if match:
        kind,topic=match.groups();kind=kind.lower()
        fmt='docx' if kind in ('word document','word doc','docx') else 'pdf' if kind=='pdf' else 'xlsx' if kind in ('spreadsheet','excel workbook','excel sheet') else 'pptx'
        return {'feature':'document','format':fmt,'topic':topic.strip()}
    return None

class ProductivityStore:
    def __init__(self,db):
        self.db=db
        with db.connect() as c:c.executescript('''
            CREATE TABLE IF NOT EXISTS appointments(id TEXT PRIMARY KEY,title TEXT NOT NULL,due REAL NOT NULL,duration INTEGER NOT NULL,notified INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS routines(name TEXT PRIMARY KEY,steps TEXT NOT NULL);
        ''')
    def add(self,title,due,duration=0):
        now=time.time();due=float(due);duration=int(duration)
        if not math.isfinite(due) or due<=now or due>now+366*86400:raise ValueError('Choose a future time within one year.')
        if not 0<=duration<=1440:raise ValueError('Event duration must be from 0 to 1440 minutes.')
        title=str(title).strip()
        if not 1<=len(title)<=500:raise ValueError('Use a title of 1 to 500 characters.')
        item=uuid.uuid4().hex[:8]
        with self.db.connect() as c:c.execute('INSERT INTO appointments(id,title,due,duration) VALUES (?,?,?,?)',(item,title,due,duration))
        return item
    def events(self,upcoming=True):
        with self.db.connect() as c:return [dict(r) for r in c.execute('SELECT * FROM appointments '+('WHERE due>=? OR notified=0 ' if upcoming else '')+'ORDER BY due LIMIT 200',((time.time()-86400,) if upcoming else ()))]
    def due(self,now=None):
        # Claim atomically, so two app windows cannot notify the same reminder.
        with self.db.connect() as c:
            c.execute('BEGIN IMMEDIATE');items=[dict(r) for r in c.execute('SELECT * FROM appointments WHERE due<=? AND notified=0 ORDER BY due LIMIT 20',(time.time() if now is None else now,))]
            c.executemany('UPDATE appointments SET notified=1 WHERE id=?',[(r['id'],) for r in items]);return items
    def cancel(self,item):
        with self.db.connect() as c:return c.execute('DELETE FROM appointments WHERE id=?',(str(item),)).rowcount>0
    def routines(self):
        with self.db.connect() as c:return {r['name']:json.loads(r['steps']) for r in c.execute('SELECT * FROM routines ORDER BY name')}
    def save_routine(self,name,steps):
        from core.quick_commands import parse as quick
        if not re.fullmatch(r'[\w -]{1,50}',name):raise ValueError('Use a routine name of 1 to 50 letters, digits or spaces.')
        if not 1<=len(steps)<=10:raise ValueError('A routine needs 1 to 10 steps.')
        if any(not (p:=quick(step)) or 'reply' in p or p['name'] not in ('browser_control','open_app') for step in steps):
            raise ValueError('Saved routines currently support explicit app and website opens only. Separate them with semicolons.')
        key=name.casefold()
        with self.db.connect() as c:
            if c.execute('SELECT 1 FROM routines WHERE name=?',(key,)).fetchone():raise ValueError('That routine exists. Delete it explicitly or use a new name.')
            c.execute('INSERT INTO routines VALUES (?,?)',(key,json.dumps(steps)))
    def delete_routine(self,name):
        with self.db.connect() as c:return c.execute('DELETE FROM routines WHERE name=?',(name.casefold(),)).rowcount>0

def output_dir():
    from memory.local_database import data_dir
    folder=data_dir().parent/'outputs';folder.mkdir(parents=True,exist_ok=True);return folder

def new_output(title,suffix):
    safe=re.sub(r'[^\w -]','',str(title))[:65].strip().replace(' ','_') or 'JARVIS'
    return output_dir()/(safe+'_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:6]+suffix)

def export_calendar(items):
    def esc(value):return str(value).replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
    def stamp(value):return datetime.fromtimestamp(value,timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//JARVIS Local//Calendar//EN']
    for item in items:
        lines+=['BEGIN:VEVENT','UID:'+item['id']+'@jarvis.local','DTSTAMP:'+stamp(time.time()),'DTSTART:'+stamp(item['due']),'DTEND:'+stamp(item['due']+max(1,item['duration'])*60),'SUMMARY:'+esc(item['title']),'END:VEVENT']
    lines+=['END:VCALENDAR'];folded=[]
    for line in lines:
        chunk=''
        for char in line:
            if len((chunk+char).encode('utf-8'))>73:folded.append(chunk);chunk=' '
            chunk+=char
        folded.append(chunk)
    path=new_output('Calendar','.ics');path.write_bytes(('\r\n'.join(folded)+'\r\n').encode('utf-8'));return path

def diagnostic_report(action='status'):
    import psutil
    ram=psutil.virtual_memory();battery=psutil.sensors_battery()
    lines=[f'CPU: {psutil.cpu_percent(interval=.2)}% ({psutil.cpu_count()} logical cores)',f'RAM: {ram.percent}% used; {ram.available/1024**3:.1f} GB available of {ram.total/1024**3:.1f} GB',f'Uptime: {(time.time()-psutil.boot_time())/3600:.1f} hours']
    if battery:lines.append(f'Battery: {battery.percent}%'+(' · charging/plugged in' if battery.power_plugged else ' · on battery'))
    for disk in psutil.disk_partitions():
        try:
            usage=psutil.disk_usage(disk.mountpoint);lines.append(f'{disk.device}: {usage.free/1024**3:.1f} GB free of {usage.total/1024**3:.1f} GB')
        except (PermissionError,OSError):pass
    if action=='processes':
        processes=[]
        for process in psutil.process_iter(['name','pid','memory_info']):
            try:processes.append((process.info['memory_info'].rss,process.info['name'],process.pid))
            except (psutil.Error,AttributeError):pass
        lines.append('Top RAM users:')
        lines.extend(f'{name} (PID {pid}): {size/1024**2:.0f} MB' for size,name,pid in sorted(processes,reverse=True)[:8])
    return '\n'.join(lines)

def explicit_table(topic):
    match=re.fullmatch(r'columns\s+(.+?)\s+and rows\s+(.+)',topic.strip(),re.I|re.S)
    if not match:return None
    headers=[s.strip() for s in re.split(r',|\band\b',match[1]) if s.strip()]
    if not 2<=len(headers)<=10:return None
    rows=[]
    for text in re.split(r';|\band\b',match[2]):
        values=next(csv.reader([text.strip()])) if ',' in text else text.strip().rsplit(None,len(headers)-1)
        if len(values)!=len(headers):return None
        rows.append([s.strip() for s in values])
    output=io.StringIO();writer=csv.writer(output);writer.writerow(headers);writer.writerows(rows);return output.getvalue()

async def completion(llm,instruction,content,progress=None):
    chunks=[]
    emitted=0
    async for event in llm.chat([{'role':'system','content':instruction},{'role':'user','content':content}],None):
        if event.get('text'):
            chunks.append(event['text'])
            if progress and len(''.join(chunks))-emitted>=160:
                draft=''.join(chunks);progress('LOCAL DRAFT · GENERATING',draft);emitted=len(draft)
    result=''.join(chunks).strip()
    if not result:raise RuntimeError('The local model returned no content. No document was created.')
    return result

def write_document(fmt,title,content):
    """Save real editable files; unique paths prevent overwriting existing work."""
    path=new_output(title,'.'+fmt)
    lines=content.splitlines()
    try:
        if fmt=='docx':
            from docx import Document
            from docx.shared import Pt
            doc=Document();doc.styles['Normal'].font.name='Calibri';doc.styles['Normal'].font.size=Pt(11);doc.add_heading(title,0)
            for line in lines:
                if line.startswith('#'):doc.add_heading(line.lstrip('# ').strip(),min(3,len(line)-len(line.lstrip('#'))))
                elif line.strip():doc.add_paragraph(line)
            doc.save(path)
        elif fmt=='pdf':
            from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer
            from reportlab.lib.styles import getSampleStyleSheet
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            font=Path('C:/Windows/Fonts/arial.ttf');styles=getSampleStyleSheet()
            if font.exists():
                if 'JARVISArial' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(TTFont('JARVISArial',str(font)))
                for style in styles.byName.values():style.fontName='JARVISArial'
            story=[Paragraph(escape(title),styles['Title']),Spacer(1,16)]
            for line in lines:
                story.extend([Paragraph(escape(line.lstrip('# ')),styles['Heading2'] if line.startswith('#') else styles['BodyText']),Spacer(1,7)])
            SimpleDocTemplate(str(path),title=title).build(story)
        elif fmt=='pptx':
            from pptx import Presentation
            from pptx.util import Pt
            deck=Presentation();sections=re.split(r'(?m)^#{1,3}\s+',content)
            slide=deck.slides.add_slide(deck.slide_layouts[0]);slide.shapes.title.text=title;slide.placeholders[1].text='Created locally with JARVIS'
            for section in sections:
                rows=[r.strip().lstrip('-* ') for r in section.splitlines() if r.strip()]
                if not rows:continue
                for offset in range(0,max(1,len(rows)-1),5):
                    slide=deck.slides.add_slide(deck.slide_layouts[1]);slide.shapes.title.text=rows[0][:110]
                    tf=slide.placeholders[1].text_frame;tf.clear()
                    for i,line in enumerate(rows[1+offset:1+offset+5]):
                        para=tf.paragraphs[0] if i==0 else tf.add_paragraph();para.text=line;para.font.size=Pt(20)
            deck.save(path)
        elif fmt=='xlsx':
            from openpyxl import Workbook
            from openpyxl.styles import Font,PatternFill
            clean=re.sub(r'^```(?:csv)?\s*|\s*```$','',content.strip(),flags=re.I)
            rows=list(csv.reader(io.StringIO(clean)))
            if not rows or len(rows[0])<2:raise ValueError('The model did not return a usable CSV table. Ask for explicit column names.')
            book=Workbook();sheet=book.active;sheet.title='Data';sheet.freeze_panes='A2'
            for row in rows[:1000]:
                sheet.append([float(v) if re.fullmatch(r'-?\d+\.\d+',v.strip()) else int(v) if re.fullmatch(r'-?\d+',v.strip()) else v for v in row[:30]])
            for row in sheet:
                for cell in row:
                    if isinstance(cell.value,str):cell.data_type='s'
            for cell in sheet[1]:cell.font=Font(bold=True,color='FFFFFF');cell.fill=PatternFill('solid',fgColor='222222')
            for column in sheet.columns:sheet.column_dimensions[column[0].column_letter].width=min(55,max(15,max(len(str(c.value or '')) for c in column)+2))
            sheet.auto_filter.ref=sheet.dimensions;book.save(path)
        else:raise ValueError('Unsupported output format.')
    except Exception:
        path.unlink(missing_ok=True);raise
    return path

async def run(plan,llm,db,progress=None):
    feature=plan['feature'];store=ProductivityStore(db)
    if feature=='document':
        if not plan['topic']:return 'What should the document contain? Example: create a Word document about my weekly study plan.'
        fmt=plan['format'];instruction='Draft a useful document in at most 250 words from the request. Use Markdown headings. Do not claim to have saved anything. Do not invent personal facts, citations or live statistics.'
        if fmt=='pptx':instruction+=' Use 4 to 6 sections, each starting with a # slide title and 3 short bullet points.'
        if fmt=='xlsx':instruction='Return only a valid CSV table with a header row, at least 2 columns, and up to 30 rows matching the request. Use blank cells for unknown personal values. No Markdown or formulas.'
        content=explicit_table(plan['topic']) if fmt=='xlsx' else None
        if content is None:
            content=await completion(llm,instruction,plan['topic'],progress)
            if fmt=='xlsx':
                rows=list(csv.reader(io.StringIO(content)))
                data=[tuple(row) for row in rows[1:] if row]
                if len(data)>3 and len(set(data))<len(data)*.75:raise ValueError('The model repeated rows. No file was saved. Provide explicit columns and rows for an exact table.')
        title=plan['topic'][:90].strip();path=await asyncio.to_thread(write_document,fmt,title,content)
        return f'Created {fmt.upper()} locally:\n{path}\nSay “open my outputs” to open the folder. Review AI-generated content before using it.'
    if feature=='diagnostics':return await asyncio.to_thread(diagnostic_report,plan.get('action','status'))
    if feature=='models':return 'No offline AI models are installed. Connect Gemini or OpenAI in Settings > AI connection.'
    if feature in ('calendar','briefing'):
        action=plan.get('action','list')
        if action=='add':
            due=time.time()+plan['delay'] if 'delay' in plan else datetime.fromisoformat(plan['when']).astimezone().timestamp()
            item=store.add(plan['title'],due,plan.get('duration',30))
            return f"Saved {item}: {plan['title']} — {datetime.fromtimestamp(due).astimezone():%d %b %Y, %H:%M %Z}. JARVIS must be running and the laptop awake to notify you; missed reminders appear next time it runs."
        if action=='cancel':return 'Reminder/event cancelled.' if store.cancel(plan['id']) else 'No event with that ID exists.'
        items=store.events()
        if action=='export':return 'Calendar exported locally:\n'+str(export_calendar(items))
        if feature=='briefing':
            today=datetime.now().date();items=[item for item in items if datetime.fromtimestamp(item['due']).date()==today]
        text='\n'.join(f"{r['id']} · {datetime.fromtimestamp(r['due']):%d %b %H:%M} · {r['title']}" for r in items) or 'No scheduled events.'
        if feature=='briefing':text=f"Today is {datetime.now():%A, %d %B %Y}.\n"+text+'\n'+await asyncio.to_thread(diagnostic_report)+'\nThis local briefing includes your saved agenda and laptop status. Online news, email and weather are not connected.'
        return text
    if feature=='routine':
        action=plan['action'];name=plan.get('name','').casefold()
        if action=='save':store.save_routine(name,plan['steps']);return 'Saved routine '+name+'. Say “run routine '+name+'” to start it.'
        if action=='delete':return 'Routine deleted.' if store.delete_routine(name) else 'No routine with that name exists.'
        routines=store.routines()
        if action=='list':return '\n'.join(name+': '+'; '.join(steps) for name,steps in routines.items()) or 'No saved routines. Example: save routine study: open Notepad; open YouTube'
        if name not in routines:return 'No routine with that name exists.'
        from core.quick_commands import parse as quick
        from actions.open_app import open_app
        from actions.browser_control import browser_control
        results=[]
        for command in routines[name]:
            spec=quick(command)
            if not spec or 'reply' in spec or spec['name'] not in ('browser_control','open_app'):raise ValueError('Invalid stored routine; delete it and create it again.')
            handler=browser_control if spec['name']=='browser_control' else open_app
            results.append(str(await asyncio.to_thread(handler,spec['args'])))
            await asyncio.sleep(0)
        return '\n'.join(results)
    raise ValueError('Unknown local feature.')

def tool(parameters,player=None):
    plan=parse(parameters.get('command',''))
    if not plan:return 'Use a supported explicit request: create a Word document/PDF/presentation/spreadsheet about a topic; remind me in N minutes to TASK; show my schedule; schedule TITLE on YYYY-MM-DD at HH:MM; export my calendar; system diagnostics; daily briefing; read/summarize my clipboard; list local models; save/run/list/delete routine NAME.'
    from memory.local_database import database
    from core.secure_config import loads
    from core.gestures import ROOT
    from providers import registry
    from memory.config_manager import get_pipeline,get_provider_config
    provider=get_pipeline().get('llm','cloud_setup')
    llm=registry.build(provider,get_provider_config(provider))
    result=asyncio.run(run(plan,llm,database()))
    if player:player.show_content('Local '+plan['feature'].title(),result)
    return result
