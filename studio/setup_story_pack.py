"""Register locally saved project illustrations without downloading at run time."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent
ASSETS={
 'well':('بئر حجري بحبل ودلو','religion','بئر جب دلو حبل حجارة','hidden'),
 'elder':('رجل مسن من الخلف يحمل قماشًا','religion','يعقوب اب انتظار اباه ابيه حزن قميص','hidden'),
 'boy':('صبي بملابس قديمة من الخلف','religion','يوسف صبي غلام حلم رؤيا','hidden'),
 'shirt':('قميص تاريخي بتفاصيل القماش','religion','قميص ثوب ملابس قماش','none'),
 'shirt-marked':('قميص بأثر أحمر رمزي','religion','قميص الدم كذب ثوب احمر','none'),
 'shirt-torn':('قميص ممزق من الظهر','religion','قميص ممزق دبر ظهر شهد','none'),
 'caravan':('قافلة بجملين وتاجر من الخلف','religion','قافلة قافله جمال تجارة مصر سفر','hidden'),
 'business':('شخص يدير المال على مكتبه','finance','مال اقتصاد عمل شركة اعمال ادخار استثمار ميزانية نقود','visible'),
 'mind':('شخص يتأمل مع فقاعة أفكار','psychology','نفس مشاعر عقل قلق تفكير حياة علاقات','visible'),
 'learning':('طالبة تقرأ وتكتب على مكتب','growth','تعلم تعليم تطوير قراءة دراسة مهارات كتاب','visible'),
}

def install():
    path=ROOT/'library/catalog.json'
    records=json.loads(path.read_text(encoding='utf-8'))
    for key,(name,domain,tags,faces) in ASSETS.items():
        aid='story-'+key
        if not (ROOT/'library'/f'{aid}.png').exists():continue
        record={'id':aid,'name':name,'file':f'{aid}.png','tags':tags.split(),
            'domain':domain,'kind':'illustration','style':'classic-story-sage-ochre',
            'source':'Project artwork generated using OpenAI built-in image generation',
            'license':'Generated project asset; provider terms apply','review_status':'approved',
            'faces':faces,'compositor':'strict alpha matte; original file retained',
            'notes':'Raster illustration. Drawing paths are computed approximations, not original vector strokes.'}
        records=[r for r in records if r['id']!=aid];records.append(record)
    path.write_text(json.dumps(records,ensure_ascii=False),encoding='utf-8')
    print('Registered story artwork',len(ASSETS))

if __name__=='__main__':install()
