"""Render the models' unedited SVGs with the production stroke engine."""
import sys,json
from pathlib import Path
BASE=Path(__file__).resolve().parent
sys.path.insert(0,str(BASE))
import audit
from engine.strokes import scan_svg
from engine.render.canvas import Whiteboard,DocCursor
from engine.render.director import clip_strokes
for p in (BASE/'results').glob('*/08_svg.json'):
    rec=json.loads(p.read_text(encoding='utf-8'))
    if rec.get('parsed',{}).get('svg'):
        dest=p.parent/'assets'/'08_ship_original_response.svg'
        dest.parent.mkdir(exist_ok=True)
        dest.write_text(rec['parsed']['svg'],encoding='utf-8')
for p in (BASE/'results').glob('*/assets/*.svg'):
    try:
        doc=scan_svg(p)
        wb=Whiteboard(800,500)
        cur=DocCursor(clip_strokes(doc,[60,60,680,380]))
        wb.paint(cur.advance(1.0))
        wb.rgb.save(p.with_suffix('.preview.png'))
        print(p)
    except Exception as e: print(type(e).__name__,str(e))
