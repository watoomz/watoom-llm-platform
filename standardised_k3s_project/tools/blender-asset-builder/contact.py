import sys
from pathlib import Path
from PIL import Image,ImageOps,ImageDraw
r=Path(sys.argv[1]);names=['front','side','top','three_quarter','rear','beauty'];out=Image.new('RGB',(900,640),'#e8e8e8');d=ImageDraw.Draw(out)
for i,n in enumerate(names):
 im=Image.open(r/'renders'/(n+'.png')).convert('RGB');im=ImageOps.contain(im,(300,290));x=(i%3)*300;y=(i//3)*320;out.paste(im,(x+(300-im.width)//2,y+22));d.text((x+10,y+4),n,fill='black')
out.save(r/'renders/contact.png');print('PASS contact')
