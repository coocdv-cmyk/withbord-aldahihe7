"""Behavior checks: preserve the script, exact frame budget, formats, validation."""
import json
import threading
import time
import unittest
import cv2
from core import *

SCRIPT='الادخار يبدأ بخطوة صغيرة كل يوم. حدد جزءا من دخلك لصندوق الطوارئ. الاستثمار يحتاج فهم المخاطر وتنويع الخيارات. تطوير المهارات يزيد فرص النجاح.'

class Checks(unittest.TestCase):
    def project(self):
        return plan({'script':SCRIPT,'duration':5.375,'scene_length':5,'domain':'finance','resolution':'720p'})

    def test_preserve_script_and_time(self):
        p=plan({'script':SCRIPT,'duration':61.375,'scene_length':10})
        self.assertEqual(' '.join(s['text'] for s in p['scenes']),SCRIPT)
        self.assertAlmostEqual(sum(s['duration'] for s in p['scenes']),61.375)
        self.assertTrue(all(s['assets'] for s in p['scenes']))

    def test_formats_and_arabic_search(self):
        self.assertGreater(len(catalog()),2000)
        self.assertTrue(any(r['id']=='brain' for r in search_assets('عقل')))
        for resolution,size in [('720p',(1280,720)),('1080p',(1920,1080)),('vertical',(1080,1920))]:
            p=self.project();p['resolution']=resolution;p['scenes'][0]['assets']=['brain','heart','book-open','target','coins','house']
            im,regions=compose(p,0)
            self.assertEqual(im.size,size)
            self.assertEqual(len(regions),7)
        p['scenes'][0]['placements']={'0':{'x':float('nan')}}
        with self.assertRaises(ValueError): validate_project(p)

    def test_export_frame_budget_and_no_audio(self):
        p=self.project();p['scenes']=p['scenes']*3
        for s in p['scenes']:s['duration']=1.125
        job={};start=time.monotonic();render_project(p,job,threading.Event())
        out=Path(job['folder'])/'video.mp4'
        cap=cv2.VideoCapture(str(out))
        self.assertTrue(cap.isOpened())
        self.assertEqual(int(cap.get(cv2.CAP_PROP_FRAME_COUNT)),81)
        self.assertEqual(cap.get(cv2.CAP_PROP_FPS),24)
        cap.release()
        probe=Path(find_ffmpeg()).with_name('ffprobe.exe')
        result=subprocess.run([str(probe),'-v','error','-show_entries','stream=codec_type,width,height','-of','json',str(out)],capture_output=True,check=True)
        streams=json.loads(result.stdout)['streams']
        self.assertEqual(len(streams),1)
        self.assertEqual(streams[0]['codec_type'],'video')
        (DATA/'verification.json').write_text(json.dumps({'video':str(out),'render_seconds':round(time.monotonic()-start,2),
                 'duration':3.375,'frames':81,'assets':len(catalog())},indent=2),encoding='utf-8')

if __name__=='__main__':unittest.main(verbosity=2)
