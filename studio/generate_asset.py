"""Runs in .venv-gen, separate from the editor. Uses already downloaded weights."""
import json
import os
import sys
from pathlib import Path
import torch
from diffusers import AutoPipelineForText2Image, DPMSolverMultistepScheduler

root=Path(__file__).resolve().parent
sys.path.insert(0,str(root.parent/'gen'))
from imglib import clean_to_white

def main():
    request=Path(sys.argv[1])
    data=json.loads(request.read_text(encoding='utf-8'))
    torch.set_num_threads(max(1,min(8,os.cpu_count() or 4)))
    options=dict(torch_dtype=torch.float32,local_files_only=True,safety_checker=None,requires_safety_checker=False)
    model='stable-diffusion-v1-5/stable-diffusion-v1-5'
    try:
        pipe=AutoPipelineForText2Image.from_pretrained(model,variant='fp16',**options)
    except OSError:
        pipe=AutoPipelineForText2Image.from_pretrained(model,**options)
    pipe.scheduler=DPMSolverMultistepScheduler.from_config(pipe.scheduler.config)
    pipe.set_progress_bar_config(disable=True)
    styles={
        'line':'minimal line icon, consistent thick dark outlines, no color fill',
        'flat':'simple flat vector clipart, thick black outline, teal and blue flat color fills',
        'doodle':'simple hand drawn doodle, bold black marker outline, minimal teal accents',
    }
    prompt=data['prompt']+', '+styles[data['style']]+', isolated single object, pure white background, no text'
    negative='watermark, signature, text, letters, photo, realistic, 3d, shading, shadow, gradient, scenery, room, complex, blurry'
    image=pipe(prompt=prompt,negative_prompt=negative,num_inference_steps=data['steps'],
               guidance_scale=data['guidance'],width=512,height=512,clip_skip=2,
               generator=torch.Generator('cpu').manual_seed(data['seed'])).images[0]
    image.save(request.with_suffix('.raw.png'))
    cleaned,_,_=clean_to_white(image)
    cleaned.save(request.with_suffix('.png'))

if __name__=='__main__': main()
