#!/usr/bin/env python3
"""Bounded actual OCR/PDF, media, x86 decoding and DOS execution acceptance."""
import json, os, pathlib, shutil, subprocess, tempfile
import capstone, pefile, numpy, PyPDF2
from PIL import Image, ImageDraw, ImageFont
def run(args, **kw):
    return subprocess.check_output(args, timeout=60, stderr=subprocess.STDOUT, **kw).decode(errors="replace")
for tool in ["pdftotext","pdftoppm","tesseract","dosbox","identify","convert","ffmpeg","ffprobe","exiftool","r2","xxd","hexdump","objdump","gdb"]:
    assert shutil.which(tool), tool
with tempfile.TemporaryDirectory(prefix="engineering-") as temp:
    root=pathlib.Path(temp)
    image=Image.new("RGB",(1000,200),"white")
    draw=ImageDraw.Draw(image)
    font=ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",52)
    draw.text((25,50),"ENGINEERING 12345",font=font,fill="black")
    image.save(root/"ocr.png")
    image.save(root/"manual.pdf","PDF")
    assert len(PyPDF2.PdfReader(str(root/"manual.pdf")).pages)==1
    run(["pdftotext",str(root/"manual.pdf"),str(root/"text.txt")])
    run(["pdftoppm","-singlefile","-scale-to","1200","-png",str(root/"manual.pdf"),str(root/"page")])
    assert "ENGINEERING" in run(["tesseract",str(root/"page.png"),"stdout","--psm","6"])
    assert "1000x200" in run(["identify",str(root/"ocr.png")])
    run(["convert",str(root/"ocr.png"),"-resize","50%",str(root/"small.png")])
    assert Image.open(root/"small.png").size==(500,100)
    run(["exiftool","-ImageWidth",str(root/"ocr.png")])
    run(["ffmpeg","-v","error","-f","lavfi","-i","color=c=red:s=64x64:d=0.2","-c:v","mpeg4",str(root/"sample.mp4")])
    assert "mpeg4" in run(["ffprobe","-v","error","-show_entries","stream=codec_name",str(root/"sample.mp4")])
    code=bytes.fromhex("b82a00c3")
    decoder=capstone.Cs(capstone.CS_ARCH_X86,capstone.CS_MODE_16)
    assert list(decoder.disasm(code,0x100))[0].mnemonic=="mov"
    (root/"code.bin").write_bytes(code)
    assert "mov" in run(["r2","-q","-a","x86","-b","16","-c","pd 2;q",str(root/"code.bin")])
    assert numpy.array([1,2,3]).sum()==6
    # DOS COM: print marker with int21/09 then exit int21/4c.
    (root/"PROBE.COM").write_bytes(bytes.fromhex("ba0c01b409cd21b8004ccd21")+b"DOS_RUNTIME_PASS\r\n$")
    config=root/"dosbox.conf"
    config.write_text("[sdl]\nfullscreen=false\noutput=surface\n[dosbox]\nmemsize=16\n[cpu]\ncycles=fixed 10000\n[mixer]\nnosound=true\n")
    env=dict(os.environ,HOME=temp,SDL_AUDIODRIVER="dummy")
    run(["xvfb-run","-a","dosbox","-conf",str(config),"-c","mount c "+temp,"-c","c:","-c","PROBE.COM > RESULT.TXT","-c","exit"],env=env)
    assert "DOS_RUNTIME_PASS" in (root/"RESULT.TXT").read_text()
print(json.dumps({"status":"PASS","checks":["pdf-raster","ocr","image-resize","media","metadata","16bit-disassembly","dos-runtime","python-imports"]}))
