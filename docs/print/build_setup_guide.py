# Builds the printed setup guide (docs/print/LayerHound-setup-guide.pdf) from setup-guide.html.
#
#   python docs/print/build_setup_guide.py        (from the project folder; see README.md here)
#
# Fills in the QR codes, then prints the page to a letter-size PDF with Chrome (through Playwright).
# Every QR code points at a fixed address, so the printed guide never goes out of date with a release.
from pathlib import Path
import sys
import segno
from playwright.sync_api import sync_playwright

HERE=Path(__file__).resolve().parent
OUT=HERE/'LayerHound-setup-guide.pdf'
QR={
 'QR_DASHBOARD':'http://layerhound.local',
 'QR_GUIDE':'https://github.com/TeamTacticalRC/LayerHound/blob/main/docs/GUIDE.md',
}

def qr_svg(url):
 # Plain black squares with the standard quiet zone; medium error correction survives a smudge
 return segno.make(url,error='m',micro=False).svg_inline(scale=1,border=4,dark='#000',light='#fff',omitsize=True)

def main():
 html=(HERE/'setup-guide.html').read_text()
 for key,url in QR.items(): html=html.replace('{{'+key+'}}',qr_svg(url))
 if '{{' in html: sys.exit('setup-guide.html has a placeholder the build script does not fill')
 page_file=HERE/'.setup-guide.built.html'; page_file.write_text(html)
 try:
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True); pg=b.new_page()
   pg.goto(page_file.as_uri()); pg.wait_for_load_state('networkidle')
   # The guide is one page: stop if anything spills onto a second one
   overflow=pg.evaluate("(()=>{const p=document.querySelector('.page');return p.scrollHeight>p.clientHeight+1})()")
   if overflow: sys.exit('The guide no longer fits on one page; shorten the text')
   pg.pdf(path=str(OUT),format='Letter',print_background=True,margin={'top':'0','right':'0','bottom':'0','left':'0'})
   if len(sys.argv)>1: pg.set_viewport_size({'width':816,'height':1056}); pg.screenshot(path=sys.argv[1],full_page=True)
   b.close()
 finally: page_file.unlink(missing_ok=True)
 print(f'wrote {OUT.relative_to(HERE.parent.parent)}')

if __name__=='__main__': main()
