"""Sentetik test PDF'leri: yoğun metinli kitap (200 s) ve seyrek slayt (120 s)."""
import pymupdf, random
from pathlib import Path
HERE = Path(__file__).resolve().parent
random.seed(7)
WORDS="psikoloji davranış bilişsel kuram deney gözlem değişken hipotez örneklem korelasyon bağımlı bağımsız ölçek güvenilirlik geçerlik anlamlılık dağılım ortalama sapma analiz bulgu tartışma sonuç öneri terapi aile sistem bağlanma şema duygu düzenleme".split()
def para(n): return ' '.join(random.choice(WORDS) for _ in range(n)).capitalize()+'.'
# Kitap: A4, ~520 kelime/sayfa, iki paragraf blok + başlık
doc=pymupdf.open()
for i in range(200):
    p=doc.new_page(width=595,height=842)
    p.insert_text((60,70),f"Bölüm {i//12+1} · {i+1}",fontsize=9,fontname='helv',color=(.4,.4,.4))
    text='\n\n'.join(para(85) for _ in range(6))
    p.insert_textbox(pymupdf.Rect(60,95,535,790),text,fontsize=10.5,fontname='tiro',lineheight=1.35)
    p.insert_text((290,815),str(i+1),fontsize=9,fontname='helv')
doc.save(str(HERE/'kitap_200.pdf'),garbage=3,deflate=True); doc.close()
# Slayt: 16:9, başlık + 3 madde + renkli şerit
doc=pymupdf.open()
for i in range(120):
    p=doc.new_page(width=960,height=540)
    p.draw_rect(pymupdf.Rect(0,0,960,80),color=None,fill=(.16,.31,.26))
    p.insert_text((40,52),f"{i+1}. {para(4)[:-1]}",fontsize=26,fontname='hebo',color=(1,1,1))
    for k in range(3): p.insert_text((70,160+k*70),"• "+para(9),fontsize=18,fontname='helv')
    p.insert_text((900,520),str(i+1),fontsize=11,fontname='helv')
doc.save(str(HERE/'slayt_120.pdf'),garbage=3,deflate=True); doc.close()
for f in ('kitap_200.pdf','slayt_120.pdf'):
    d=pymupdf.open(HERE/f); print(f,len(d),'sayfa', d[3].rect, len(d[3].get_text('words')),'kelime/s4')
