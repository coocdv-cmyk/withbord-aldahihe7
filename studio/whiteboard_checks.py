"""Checks for drawing, colour timing, pen calibration and real media output."""
import json
import threading
import unittest
import cv2
import numpy as np
from PIL import Image,ImageDraw
from core import ROOT,validate_project,render_project,find_ffmpeg
from demo import project
from whiteboard import prepare,Pencil,camera_rect

class WhiteboardChecks(unittest.TestCase):
    def test_ink_before_colour_and_tip_on_revealed_path(self):
        im=Image.new('RGB',(400,220),'white');draw=ImageDraw.Draw(im)
        draw.rectangle((70,45,330,180),fill=(120,155,115),outline='black',width=4)
        timing,path,breaks=prepare(im,[(50,30,350,200)])
        self.assertGreater(float(timing[110,200]),.79)
        self.assertLess(float(timing[45,200]),.79)
        for fraction in (.1,.3,.6):
            point=path[round(fraction/.78*(len(path)-1))]
            self.assertLessEqual(float(timing[round(point[1]),round(point[0])]),fraction+.02)

    def test_pencil_tip_is_visible_and_camera_finishes_on_board(self):
        pencil=Pencil(1280)
        self.assertIsNotNone(pencil.image)
        x,y=pencil.anchor;patch=pencil.image[max(0,y-5):y+8,max(0,x-5):x+10]
        self.assertTrue(np.any((patch[:,:,:3].max(axis=2)<130)&(patch[:,:,3]>240)))
        self.assertEqual(camera_rect(3,4,1280,720,1),(0.,0.,2560.,1440.))

    def test_two_scene_export_exact_frames_and_camera_board(self):
        p=project();p['resolution']='720p';p['scenes']=p['scenes'][:2]
        p['scenes'][0]['duration']=2.125;p['scenes'][1]['duration']=2.25
        job={};render_project(p,job,threading.Event())
        folder=__import__('pathlib').Path(job['folder']);cap=cv2.VideoCapture(str(folder/'video.mp4'))
        self.assertEqual(cap.get(cv2.CAP_PROP_FRAME_COUNT),105)
        cap.set(cv2.CAP_PROP_POS_FRAMES,104);ok,last=cap.read();cap.release();self.assertTrue(ok)
        # The wide final view must retain ink on both top tiles, not erase the previous scene.
        self.assertGreater(int((last[:360,:640].min(axis=2)<100).sum()),100)
        self.assertGreater(int((last[:360,640:].min(axis=2)<100).sum()),100)
        report=json.loads((folder/'render-report.json').read_text())
        self.assertTrue(report['hand']);self.assertTrue(report['camera'])
        self.assertTrue((folder/'captions.srt').exists())

    def test_validation_rejects_invalid_options(self):
        p=project();p['hand']='yes'
        with self.assertRaises(ValueError):validate_project(p)
        p=project();p['scenes'][0]['labels']={'0':'x'*100}
        with self.assertRaises(ValueError):validate_project(p)

if __name__=='__main__':unittest.main(verbosity=2)
