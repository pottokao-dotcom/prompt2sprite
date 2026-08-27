import json, urllib.request, time, os, shutil, copy
WF=json.load(open('/home/pottokao/photo_masters2_local2.0/workflows/zimage_base2_turbo8_gx10_nvfp4all.json'))
OUT='/home/pottokao/zimage_sprites'; os.makedirs(OUT,exist_ok=True)
COMFY_OUT='/home/pottokao/ComfyUI/output'
POS='{s}, pixel art, 16-bit SNES sprite, single game asset, centered, front view, flat bright colors, hard edges, crisp clean pixels on a grid, limited palette, plain solid white background'
NEG='blurry, anti-aliasing, smooth gradient, soft shading, 3d render, realistic, photo, depth of field, noise, jpeg artifacts, text, letters, watermark, multiple objects, cluttered background, drop shadow'
JOBS=[
 ('A_coin_512','a shiny gold coin with a star',512,''),
 ('A_fireball_512','a flaming fireball projectile pointing up',512,''),
 ('A_rabbit_512','a cute jazz white rabbit with black sunglasses holding a golden saxophone',512,''),
 ('B_coin_256','a shiny gold coin with a star',256,''),
 ('B_coin_128','a shiny gold coin with a star',128,''),
 ('B_coin_64','a shiny gold coin with a star',64,''),
 ('D_mint_512','a round red and white peppermint candy',512,''),
 ('D_lolli_512','a purple spiral lollipop on a stick',512,''),
 ('D_gummy_512','a green gummy bear',512,''),
 ('D_choco_512','a chocolate bar with square segments',512,''),
 ('D_donut_512','a pink frosted donut with sprinkles',512,''),
 ('D_orange_512','an orange citrus slice',512,''),
 ('C_mint_soft_512','a round red and white peppermint candy',512,', using only bubblegum pink, purple, teal, lemon yellow, cream and white colors'),
]
def submit(wf):
    r=urllib.request.Request('http://localhost:8188/prompt',json.dumps({'prompt':wf}).encode(),{'Content-Type':'application/json'})
    return json.loads(urllib.request.urlopen(r,timeout=30).read())['prompt_id']
def wait(pid,timeout=180):
    t=time.time()
    while time.time()-t<timeout:
        h=json.loads(urllib.request.urlopen('http://localhost:8188/history/'+pid,timeout=15).read())
        if pid in h and h[pid].get('outputs'):
            for n,o in h[pid]['outputs'].items():
                if 'images' in o: return o['images'][0]
        time.sleep(1.5)
    return None
man={}
for i,(lab,subj,px,extra) in enumerate(JOBS):
    wf=copy.deepcopy(WF)
    wf['84:66']['inputs']['user_prompt']=POS.format(s=subj)+extra
    wf['79']['inputs']['width']=px; wf['79']['inputs']['height']=px
    import_seed=1000+i
    for sn in ('81','81b'):
        ip=wf.get(sn,{}).get('inputs',{})
        if 'seed' in ip: ip['seed']=import_seed
        if 'noise_seed' in ip: ip['noise_seed']=import_seed
    print('submit',lab,px,flush=True)
    try:
        pid=submit(wf); img=wait(pid)
        if img:
            src=os.path.join(COMFY_OUT,img.get('subfolder',''),img['filename']); dst=os.path.join(OUT,lab+'.png')
            shutil.copy(src,dst); man[lab]=lab+'.png'; print('  ok',lab,'->',img['filename'],flush=True)
        else: print('  TIMEOUT',lab,flush=True)
    except Exception as e: print('  ERR',lab,str(e)[:120],flush=True)
json.dump(man,open(os.path.join(OUT,'manifest.json'),'w'),indent=2)
print('DONE',len(man),'images ->',OUT)
