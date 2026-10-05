"""ac.pyw — dosya ilişkilendirmesinin çağırdığı başlatıcı (konsol penceresi yok).

    pythonw ac.pyw belge.docx   -> belge editörü
    pythonw ac.pyw kitap.pdf    -> okuyucu (kitaplığa ekler — aynı dosya zaten
                                   varsa onu açar — ve açık pencereye iletir)
"""
import os
import sys
from pathlib import Path

KOK = Path(__file__).resolve().parent
sys.path.insert(0, str(KOK))
os.chdir(KOK)                       # app.py veri klasörünü ve veri_yolu.txt'yi buradan bulur

yol = next((a for a in sys.argv[1:] if not a.startswith("-")), "")
if yol.lower().endswith(".docx"):
    from belge.editor import main
    sys.exit(main([sys.argv[0], yol]))
import app
sys.argv = [sys.argv[0]] + ([yol] if yol else [])
sys.exit(app.main())
