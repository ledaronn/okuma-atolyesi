"""belge/editor.py — Word benzeri belge editörü (Okuma Atölyesi).

Sayfa görünümü: Qt'nin sayfalama motoru (QTextDocument.setPageSize) belgeyi
gerçek sayfalara böler; kenar boşlukları kök çerçevenin kenar boşluğu olarak
HER sayfada uygulanır (ölçüldü). Görünüm gri zemine beyaz sayfaları, kenar
boşluğuna da üst/alt bilgiyi ve sayfa numarasını çizer. PDF ve yazdırma aynı
sayfa yerleşimini kullanır: ekranda ne görünüyorsa kâğıtta o.

Tam Word gücü (izlenen değişiklik, yorum, dipnot, içindekiler...) için
"LibreOffice'te aç". Word'de yazılmış bir dosyada editörün taşıyamadığı
içerik varsa özgün dosyanın ÜSTÜNE kaydedilmez (o içerik silinirdi): editör
Farklı kaydet'e yönlendirir ve LibreOffice'i önerir.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QMarginsF, QPointF, QRectF, QSizeF, Qt, QUrl
from PySide6.QtGui import (QAction, QBrush, QColor, QFont, QFontDatabase, QIcon, QImage, QKeySequence, QPageLayout,
                           QPageSize, QPainter, QPalette, QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextDocument, QTextFormat, QTextImageFormat, QTextLength, QTextListFormat,
                           QTextTableFormat)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFontComboBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox, QTabWidget, QTextEdit,
                               QToolBar, QVBoxLayout, QWidget)

from belge import docx_io
from belge.docx_io import MM_PX, SayfaAyari

SAYFA_ARASI = 24          # sayfalar arasindaki gri bosluk (px) — yalnizca gorunumde
KAGIT = {"A4": (210, 297), "A5": (148, 210), "Letter": (215.9, 279.4)}
KENAR = {"Normal (2,5 cm)": 25.0, "Dar (1,27 cm)": 12.7, "Geniş (3,8 cm)": 38.1}
STILLER = ["Normal", "Belge başlığı", "Başlık 1", "Başlık 2", "Başlık 3"]


def soffice_yolu() -> str | None:
    """Kurulu LibreOffice. Yalnızca bilinen kurulum yolları ve PATH; kullanıcı
    verisinden program yolu alınmaz."""
    for aday in (r"C:\Program Files\LibreOffice\program\soffice.exe",
                 r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"):
        if Path(aday).is_file():
            return aday
    return shutil.which("soffice") or shutil.which("libreoffice")


# --------------------------------------------------------------------------
# Sayfa gorunumu
# --------------------------------------------------------------------------
class SayfaGorunumu(QTextEdit):
    """Belgeyi sayfa sayfa gösterir. Belge sayfa boyutunda sayfalanır; araya
    görünür boşluk koymak yerine sayfa sınırları gri bir bantla çizilir (metin
    düzeni değişmez, PDF ile birebir aynı kalır)."""

    def __init__(self, ayar: SayfaAyari, parent=None):
        super().__init__(parent)
        self.ayar = ayar
        self.setAcceptRichText(True)
        self.setLineWrapMode(QTextEdit.FixedPixelWidth)
        # QTextEdit genislik degisince belgeyi yeniden yerlestirir ve sayfa
        # yuksekligini ATAR (sayfalama kapanir; olculdu: 60 paragraf tek
        # "sayfa"). Kaydirma cubugu hep acik: belirip kaybolmasi yeniden
        # yerlesim tetiklemesin; boyutlanmadan sonra sayfa boyutu yeniden konur.
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOn)
        # Sayfa her temada beyaz kagit, metin siyah murekkep (Word gibi): koyu
        # temada palet metni beyaz yapip beyaz sayfada gorunmez kiliyordu.
        for hedef in (self, self.viewport()):
            pal = hedef.palette()
            pal.setColor(QPalette.Base, QColor(0, 0, 0, 0))
            pal.setColor(QPalette.Text, QColor("#1a1a1a"))
            pal.setColor(QPalette.Highlight, QColor("#b5d3f3")); pal.setColor(QPalette.HighlightedText, QColor("#1a1a1a"))
            hedef.setPalette(pal)
        self.viewport().setAutoFillBackground(False)
        self.setStyleSheet("QTextEdit { background: #e6e3de; border: 0; color: #1a1a1a; }")

    def belge_ayarla(self, belge: QTextDocument) -> None:
        self.setDocument(belge)
        self.sayfa_uygula()

    def sayfa_uygula(self) -> None:
        a, d = self.ayar, self.document()
        d.setDocumentMargin(0)
        self.setLineWrapColumnOrWidth(round(a.genislik * MM_PX))
        f = d.rootFrame().frameFormat()
        f.setTopMargin(a.ust * MM_PX); f.setBottomMargin(a.alt * MM_PX)
        f.setLeftMargin(a.sol * MM_PX); f.setRightMargin(a.sag * MM_PX)
        d.rootFrame().setFrameFormat(f)
        self._ortala()
        self._sayfalama()
        self.viewport().update()

    def _sayfalama(self) -> None:
        """Sayfa boyutunu (yeniden) koy: QTextEdit'in yerlesimi yuksekligi atmis olabilir."""
        a = self.ayar
        boyut = QSizeF(round(a.genislik * MM_PX), a.yukseklik * MM_PX)
        if self.document().pageSize() != boyut:
            self.document().setPageSize(boyut)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._ortala()
        self._sayfalama()

    def setDocument(self, belge):
        super().setDocument(belge)
        self._sayfalama()

    def _ortala(self) -> None:
        g = int(self.ayar.genislik * MM_PX)
        bos = max(SAYFA_ARASI, (self.width() - g - 20) // 2)
        self.setViewportMargins(bos, SAYFA_ARASI, bos, SAYFA_ARASI)

    def sayfa_sayisi(self) -> int:
        return max(1, self.document().pageCount())

    def paintEvent(self, e):
        p = QPainter(self.viewport())
        a = self.ayar
        self._sayfalama()
        g, y = round(a.genislik * MM_PX), a.yukseklik * MM_PX
        kay = self.verticalScrollBar().value()
        p.fillRect(self.viewport().rect(), QColor("#ffffff"))      # viewport = sayfalar sutunu
        p.setPen(QColor("#9a958d"))
        kucuk = QFont(self.document().defaultFont()); kucuk.setPointSizeF(8.5)
        p.setFont(kucuk)
        for i in range(self.sayfa_sayisi()):
            ust = i * y - kay
            if ust > self.viewport().height() or ust + y < 0:
                continue
            if i:                                                   # sayfa siniri: gri bant
                p.fillRect(QRectF(0, ust - 3, g, 6), QColor("#d5d1ca"))
            if a.ust_bilgi:
                p.drawText(QRectF(a.sol * MM_PX, ust + 8, g - (a.sol + a.sag) * MM_PX, a.ust * MM_PX - 12),
                           Qt.AlignHCenter | Qt.AlignBottom, a.ust_bilgi)
            alt = self._alt_metin(i)
            if alt:
                p.drawText(QRectF(a.sol * MM_PX, ust + y - a.alt * MM_PX + 4, g - (a.sol + a.sag) * MM_PX,
                                  a.alt * MM_PX - 12), Qt.AlignHCenter | Qt.AlignTop, alt)
        p.end()
        super().paintEvent(e)

    def _alt_metin(self, i: int) -> str:
        a = self.ayar
        parca = [a.alt_bilgi] if a.alt_bilgi else []
        if a.sayfa_no:
            parca.append(str(i + 1))
        return "  ·  ".join(parca)


def sayfalari_bas(belge: QTextDocument, ayar: SayfaAyari, yazici: QPrinter) -> None:
    """Ekrandaki sayfa yerlesimiyle PDF/yazici. Belgenin kopyasi ayni sayfa
    boyutunda sayfalanir, her sayfa ayri cizilir; ust/alt bilgi eklenir."""
    yazici.setPageLayout(QPageLayout(QPageSize(QSizeF(ayar.genislik, ayar.yukseklik), QPageSize.Millimeter),
                                     QPageLayout.Landscape if ayar.yatay else QPageLayout.Portrait,
                                     QMarginsF(0, 0, 0, 0)))
    kopya = belge.clone()
    for ad in _resim_adlari(belge):                      # clone kaynaklari tasimaz
        kopya.addResource(QTextDocument.ImageResource, QUrl(ad), belge.resource(QTextDocument.ImageResource, QUrl(ad)))
    g, y = ayar.genislik * MM_PX, ayar.yukseklik * MM_PX
    kopya.setDocumentMargin(0)
    kopya.setPageSize(QSizeF(g, y))
    f = kopya.rootFrame().frameFormat()
    f.setTopMargin(ayar.ust * MM_PX); f.setBottomMargin(ayar.alt * MM_PX)
    f.setLeftMargin(ayar.sol * MM_PX); f.setRightMargin(ayar.sag * MM_PX)
    kopya.rootFrame().setFrameFormat(f)
    p = QPainter(yazici)
    olcek = yazici.resolution() / docx_io.EKRAN_DPI
    kucuk = QFont(belge.defaultFont()); kucuk.setPointSizeF(8.5)
    for i in range(max(1, kopya.pageCount())):
        if i:
            yazici.newPage()
        p.save()
        p.scale(olcek, olcek)
        p.translate(0, -i * y)
        kopya.drawContents(p, QRectF(0, i * y, g, y))
        p.restore()
        p.save(); p.scale(olcek, olcek); p.setFont(kucuk); p.setPen(QColor("#555555"))
        if ayar.ust_bilgi:
            p.drawText(QRectF(ayar.sol * MM_PX, 8, g - (ayar.sol + ayar.sag) * MM_PX, ayar.ust * MM_PX - 12),
                       Qt.AlignHCenter | Qt.AlignBottom, ayar.ust_bilgi)
        parca = ([ayar.alt_bilgi] if ayar.alt_bilgi else []) + ([str(i + 1)] if ayar.sayfa_no else [])
        if parca:
            p.drawText(QRectF(ayar.sol * MM_PX, y - ayar.alt * MM_PX + 4, g - (ayar.sol + ayar.sag) * MM_PX,
                              ayar.alt * MM_PX - 12), Qt.AlignHCenter | Qt.AlignTop, "  ·  ".join(parca))
        p.restore()
    p.end()


def _resim_adlari(belge: QTextDocument) -> set[str]:
    adlar = set()
    b = belge.begin()
    while b.isValid():
        it = b.begin()
        while not it.atEnd():
            f = it.fragment()
            if f.isValid() and f.charFormat().isImageFormat():
                adlar.add(f.charFormat().toImageFormat().name())
            it += 1
        b = b.next()
    return adlar


# --------------------------------------------------------------------------
# Diyaloglar
# --------------------------------------------------------------------------
class BulDegistir(QDialog):
    def __init__(self, editor: "BelgeEditoru"):
        super().__init__(editor)
        self.setWindowTitle("Bul ve değiştir")
        self.e = editor
        form = QFormLayout(self)
        self.bul = QLineEdit(); self.yeni = QLineEdit()
        self.harf = QCheckBox("Büyük/küçük harf duyarlı"); self.kelime = QCheckBox("Tam kelime")
        form.addRow("Bul:", self.bul); form.addRow("Değiştir:", self.yeni)
        form.addRow(self.harf); form.addRow(self.kelime)
        satir = QHBoxLayout()
        for ad, f in (("Sonrakini bul", self.sonraki), ("Değiştir", self.degistir), ("Tümünü değiştir", self.tumu)):
            b = QPushButton(ad); b.clicked.connect(f); satir.addWidget(b)
        form.addRow(satir)
        self.durum = QLabel(""); form.addRow(self.durum)

    def _bayrak(self):
        b = QTextDocument.FindFlag(0)
        if self.harf.isChecked():
            b |= QTextDocument.FindCaseSensitively
        if self.kelime.isChecked():
            b |= QTextDocument.FindWholeWords
        return b

    def sonraki(self) -> bool:
        metin = self.bul.text()
        if not metin:
            return False
        g = self.e.gorunum
        if g.find(metin, self._bayrak()):
            self.durum.setText("")
            return True
        g.moveCursor(QTextCursor.Start)                 # basa sar
        bulundu = g.find(metin, self._bayrak())
        self.durum.setText("" if bulundu else "Bulunamadı.")
        return bulundu

    def degistir(self) -> None:
        c = self.e.gorunum.textCursor()
        if c.hasSelection() and (c.selectedText() == self.bul.text() or
                                 (not self.harf.isChecked() and c.selectedText().lower() == self.bul.text().lower())):
            c.insertText(self.yeni.text())
        self.sonraki()

    def tumu(self) -> None:
        belge = self.e.gorunum.document()
        c = QTextCursor(belge); c.beginEditBlock()
        n = 0
        bul = belge.find(self.bul.text(), 0, self._bayrak())
        while not bul.isNull():
            bul.insertText(self.yeni.text()); n += 1
            bul = belge.find(self.bul.text(), bul.position(), self._bayrak())
        c.endEditBlock()
        self.durum.setText(f"{n} yer değiştirildi.")


class UstAltBilgi(QDialog):
    def __init__(self, ayar: SayfaAyari, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Üst ve alt bilgi")
        form = QFormLayout(self)
        self.ust = QLineEdit(ayar.ust_bilgi); self.alt = QLineEdit(ayar.alt_bilgi)
        self.no = QCheckBox("Alt bilgide sayfa numarası"); self.no.setChecked(ayar.sayfa_no)
        form.addRow("Üst bilgi:", self.ust); form.addRow("Alt bilgi:", self.alt); form.addRow(self.no)
        dug = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        dug.accepted.connect(self.accept); dug.rejected.connect(self.reject); form.addRow(dug)


class KenarBosluklari(QDialog):
    def __init__(self, ayar: SayfaAyari, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Özel kenar boşlukları (mm)")
        form = QFormLayout(self)
        self.alanlar = {}
        for ad, deger in (("ust", ayar.ust), ("alt", ayar.alt), ("sol", ayar.sol), ("sag", ayar.sag)):
            s = QDoubleSpinBox(); s.setRange(0, 100); s.setDecimals(1); s.setValue(deger)
            self.alanlar[ad] = s
            form.addRow({"ust": "Üst", "alt": "Alt", "sol": "Sol", "sag": "Sağ"}[ad] + ":", s)
        dug = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        dug.accepted.connect(self.accept); dug.rejected.connect(self.reject); form.addRow(dug)


# --------------------------------------------------------------------------
# Pencere
# --------------------------------------------------------------------------
class BelgeEditoru(QMainWindow):
    def __init__(self, yol: str | None = None):
        super().__init__()
        self.yol: Path | None = None
        self.kayipli = False             # ozgun dosyada editorun tasiyamadigi icerik var
        self.ozgun: Path | None = None
        self.ayar = SayfaAyari()
        self.gorunum = SayfaGorunumu(self.ayar)
        self.gorunum.belge_ayarla(self._yeni_belge())
        self.setCentralWidget(self._govde())
        self._serit()
        self._durum_cubugu()
        self.resize(1200, 860)
        self._baglan()
        if yol:
            self.ac(yol)
        self._baslik()

    # ---------------- iskelet ----------------
    def _govde(self) -> QWidget:
        w = QWidget(); v = QVBoxLayout(w); v.setContentsMargins(0, 0, 0, 0); v.setSpacing(0)
        self.serit = QTabWidget(); self.serit.setDocumentMode(True); self.serit.setMaximumHeight(92)
        v.addWidget(self.serit)
        self.uyari = QWidget(); u = QHBoxLayout(self.uyari); u.setContentsMargins(12, 6, 12, 6)
        self.uyari.setStyleSheet("background:#fff4d6; color:#5c4400;")
        self.uyari_metin = QLabel(); self.uyari_metin.setWordWrap(True)
        lo = QPushButton("LibreOffice'te aç"); lo.clicked.connect(self.libreoffice_ac)
        u.addWidget(self.uyari_metin, 1); u.addWidget(lo)
        self.uyari.hide()
        v.addWidget(self.uyari)
        v.addWidget(self.gorunum, 1)
        return w

    def _eylem(self, ad, f, kisayol=None, ipucu=None, denetlenir=False) -> QAction:
        a = QAction(ad, self)
        a.triggered.connect(f)
        if kisayol:
            a.setShortcut(QKeySequence(kisayol))
        if ipucu:
            a.setToolTip(ipucu)
        a.setCheckable(denetlenir)
        self.addAction(a)
        return a

    def _sekme(self, ad: str) -> QToolBar:
        t = QToolBar(ad); t.setMovable(False)
        t.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.serit.addTab(t, ad)
        return t

    def _serit(self) -> None:
        d = self._sekme("Dosya")
        for ad, f, k in (("Yeni", self.yeni, "Ctrl+N"), ("Aç…", self.ac_diyalog, "Ctrl+O"),
                         ("Kaydet", self.kaydet, "Ctrl+S"), ("Farklı kaydet…", self.farkli_kaydet, "Ctrl+Shift+S")):
            d.addAction(self._eylem(ad, f, k))
        d.addSeparator()
        d.addAction(self._eylem("PDF olarak dışa aktar…", self.pdf_aktar))
        d.addAction(self._eylem("Yazdır…", self.yazdir, "Ctrl+P"))
        d.addSeparator()
        d.addAction(self._eylem("LibreOffice'te aç", self.libreoffice_ac,
                                ipucu="Tam Word gücü: izlenen değişiklikler, yorumlar, dipnot, içindekiler…"))

        g = self._sekme("Giriş")
        g.addAction(self._eylem("Geri al", lambda: self.gorunum.undo(), "Ctrl+Z"))
        g.addAction(self._eylem("Yinele", lambda: self.gorunum.redo(), "Ctrl+Y"))
        g.addSeparator()
        self.stil = QComboBox(); self.stil.addItems(STILLER); self.stil.activated.connect(self.stil_uygula)
        g.addWidget(self.stil)
        self.yazi = QFontComboBox(); self.yazi.currentFontChanged.connect(lambda f: self._bicim(lambda c: c.setFontFamilies([f.family()])))
        g.addWidget(self.yazi)
        self.boyut = QComboBox(); self.boyut.setEditable(True)
        self.boyut.addItems([str(s) for s in (8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 36, 48, 72)])
        self.boyut.textActivated.connect(self._boyut_uygula)
        g.addWidget(self.boyut)
        self.kalin = self._eylem("K", self.kalin_yap, "Ctrl+B", "Kalın", True)
        self.italik = self._eylem("İ", self.italik_yap, "Ctrl+I", "İtalik", True)
        self.alti = self._eylem("A", self.alti_ciz, "Ctrl+U", "Altı çizili", True)
        self.ustu = self._eylem("Ü", self.ustu_ciz, None, "Üstü çizili", True)
        for a in (self.kalin, self.italik, self.alti, self.ustu):
            g.addAction(a)
        g.addAction(self._eylem("x²", lambda: self._simge(QTextCharFormat.AlignSuperScript), "Ctrl+Shift++", "Üst simge"))
        g.addAction(self._eylem("x₂", lambda: self._simge(QTextCharFormat.AlignSubScript), "Ctrl+=", "Alt simge"))
        g.addAction(self._eylem("Renk", self.renk_sec, None, "Yazı rengi"))
        g.addAction(self._eylem("Vurgu", self.vurgu_sec, None, "Vurgu rengi"))
        g.addAction(self._eylem("Temizle", self.bicimi_temizle, None, "Biçimi temizle"))
        g.addSeparator()
        for ad, hiza, k in (("Sola", Qt.AlignLeft, "Ctrl+L"), ("Ortala", Qt.AlignHCenter, "Ctrl+E"),
                            ("Sağa", Qt.AlignRight, "Ctrl+R"), ("İki yana", Qt.AlignJustify, "Ctrl+J")):
            g.addAction(self._eylem(ad, lambda _=False, h=hiza: self.gorunum.setAlignment(h), k))
        g.addSeparator()
        g.addAction(self._eylem("• Madde", lambda: self.liste(QTextListFormat.ListDisc)))
        g.addAction(self._eylem("1. Numara", lambda: self.liste(QTextListFormat.ListDecimal)))
        g.addAction(self._eylem("Girinti −", lambda: self.girinti(-1)))
        g.addAction(self._eylem("Girinti +", lambda: self.girinti(1)))
        self.aralik = QComboBox(); self.aralik.addItems(["1,0", "1,15", "1,5", "2,0"])
        self.aralik.setToolTip("Satır aralığı")
        self.aralik.activated.connect(lambda _: self.satir_araligi(float(self.aralik.currentText().replace(",", "."))))
        g.addWidget(self.aralik)
        g.addAction(self._eylem("Bul/Değiştir", self.bul_ac, "Ctrl+H"))
        self._eylem("Bul", self.bul_ac, "Ctrl+F")

        e = self._sekme("Ekle")
        e.addAction(self._eylem("Tablo…", self.tablo_ekle))
        e.addAction(self._eylem("Satır ekle", lambda: self._tablo_islem("satir")))
        e.addAction(self._eylem("Sütun ekle", lambda: self._tablo_islem("sutun")))
        e.addAction(self._eylem("Satırı sil", lambda: self._tablo_islem("satir_sil")))
        e.addAction(self._eylem("Sütunu sil", lambda: self._tablo_islem("sutun_sil")))
        e.addSeparator()
        e.addAction(self._eylem("Resim…", self.resim_ekle))
        e.addAction(self._eylem("Sayfa sonu", self.sayfa_sonu, "Ctrl+Return"))
        e.addSeparator()
        e.addAction(self._eylem("Üst/alt bilgi…", self.ust_alt_bilgi))
        self.no_eylem = self._eylem("Sayfa numarası", self.sayfa_no_degistir, None, None, True)
        e.addAction(self.no_eylem)

        z = self._sekme("Düzen")
        self.kenar = QComboBox(); self.kenar.addItems(list(KENAR) + ["Özel…"]); self.kenar.setToolTip("Kenar boşlukları")
        self.kenar.activated.connect(self.kenar_sec)
        z.addWidget(QLabel(" Kenar boşlukları ")); z.addWidget(self.kenar)
        self.kagit = QComboBox(); self.kagit.addItems(list(KAGIT)); self.kagit.activated.connect(self.kagit_sec)
        z.addWidget(QLabel(" Kâğıt ")); z.addWidget(self.kagit)
        z.addAction(self._eylem("Dikey / yatay", self.yon_degistir))

    def _durum_cubugu(self) -> None:
        self.durum = QLabel(); self.statusBar().addPermanentWidget(self.durum)

    def _baglan(self) -> None:
        """Gorunumun sinyalleri BIR KEZ; belgenin sinyali her yeni belgede (_belge_koy)."""
        g = self.gorunum
        g.currentCharFormatChanged.connect(self._bicim_goster)
        g.cursorPositionChanged.connect(self._konum_goster)
        g.textChanged.connect(self._sayac)
        self._belge_bagla()

    def _belge_bagla(self) -> None:
        self.gorunum.document().modificationChanged.connect(lambda _: self._baslik())

    # ---------------- belge ----------------
    def _yeni_belge(self) -> QTextDocument:
        b = QTextDocument()
        f = QFont("Calibri"); f.setPointSizeF(11)
        b.setDefaultFont(f)
        return b

    def _belge_koy(self, belge: QTextDocument, ayar: SayfaAyari) -> None:
        self.ayar = ayar
        self.gorunum.ayar = ayar
        self.gorunum.belge_ayarla(belge)
        self._belge_bagla()
        self.no_eylem.setChecked(ayar.sayfa_no)
        self._sayac(); self._baslik()

    def kaydedilsin_mi(self) -> bool:
        if not self.gorunum.document().isModified():
            return True
        c = QMessageBox.question(self, "Kaydedilmemiş değişiklikler", "Belgedeki değişiklikler kaydedilsin mi?",
                                 QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
        if c == QMessageBox.Save:
            return self.kaydet()
        return c == QMessageBox.Discard

    def yeni(self) -> None:
        if not self.kaydedilsin_mi():
            return
        self.yol = None; self.kayipli = False; self.ozgun = None; self.uyari.hide()
        self._belge_koy(self._yeni_belge(), SayfaAyari())

    def ac_diyalog(self) -> None:
        if not self.kaydedilsin_mi():
            return
        yol, _ = QFileDialog.getOpenFileName(self, "Belge aç", str(self.yol.parent if self.yol else Path.home()),
                                             "Word belgesi (*.docx)")
        if yol:
            self.ac(yol)

    def ac(self, yol) -> bool:
        yol = Path(yol)
        try:
            sonuc = docx_io.docx_oku(yol)
        except Exception as h:
            QMessageBox.warning(self, "Açılamadı", f"{yol.name} açılamadı:\n{h}\n\nLibreOffice'te açmayı deneyebilirsin.")
            return False
        self.yol = yol
        self._belge_koy(sonuc.belge, sonuc.sayfa)
        self.kayipli = bool(sonuc.uyarilar)
        self.ozgun = yol if self.kayipli else None
        if self.kayipli:
            self.uyari_metin.setText("Bu belgede editörün taşıyamadığı içerik var: " + ", ".join(sonuc.uyarilar)
                                     + ". Özgün dosyanın üstüne kaydedilmez (o içerik silinirdi); değişiklikleri "
                                       "Farklı kaydet ile yeni bir dosyaya kaydet ya da belgeyi LibreOffice'te düzenle.")
            self.uyari.show()
        else:
            self.uyari.hide()
        return True

    def kaydet(self) -> bool:
        if self.yol is None or (self.kayipli and self.ozgun is not None and self.yol == self.ozgun):
            return self.farkli_kaydet()
        return self._yaz(self.yol)

    def farkli_kaydet(self) -> bool:
        oneri = self.yol or (Path.home() / "Belge.docx")
        if self.kayipli and self.ozgun is not None and oneri == self.ozgun:
            oneri = oneri.with_name(oneri.stem + " (düzenlendi).docx")
        yol, _ = QFileDialog.getSaveFileName(self, "Farklı kaydet", str(oneri), "Word belgesi (*.docx)")
        if not yol:
            return False
        yol = Path(yol if yol.lower().endswith(".docx") else yol + ".docx")
        if self.kayipli and self.ozgun is not None and yol.resolve() == self.ozgun.resolve():
            QMessageBox.warning(self, "Özgün dosya korunuyor",
                                "Bu dosyadaki taşınamayan içerik silinirdi. Başka bir ad seç ya da LibreOffice'te düzenle.")
            return False
        return self._yaz(yol)

    def _yaz(self, yol: Path) -> bool:
        try:
            docx_io.docx_yaz(self.gorunum.document(), self.ayar, yol)
        except Exception as h:
            QMessageBox.warning(self, "Kaydedilemedi", f"{yol}\n{h}")
            return False
        self.yol = yol
        self.gorunum.document().setModified(False)
        self.statusBar().showMessage(f"Kaydedildi: {yol.name}", 4000)
        self._baslik()
        return True

    def pdf_aktar(self) -> None:
        oneri = (self.yol.with_suffix(".pdf") if self.yol else Path.home() / "Belge.pdf")
        yol, _ = QFileDialog.getSaveFileName(self, "PDF olarak dışa aktar", str(oneri), "PDF (*.pdf)")
        if not yol:
            return
        self.pdf_yaz(yol)
        self.statusBar().showMessage(f"PDF yazıldı: {Path(yol).name}", 4000)

    def pdf_yaz(self, yol) -> None:
        y = QPrinter(QPrinter.HighResolution)
        y.setOutputFormat(QPrinter.PdfFormat); y.setOutputFileName(str(yol))
        sayfalari_bas(self.gorunum.document(), self.ayar, y)

    def yazdir(self) -> None:
        y = QPrinter(QPrinter.HighResolution)
        if QPrintDialog(y, self).exec() == QDialog.Accepted:
            sayfalari_bas(self.gorunum.document(), self.ayar, y)

    def libreoffice_ac(self) -> None:
        """Tam Word gucu. Kayipli bir Word dosyasinda OZGUN dosya acilir
        (editordeki degisiklik henuz kaydedilmediyse once sorulur)."""
        so = soffice_yolu()
        if not so:
            QMessageBox.information(self, "LibreOffice bulunamadı",
                                    "LibreOffice kurulu değil. libreoffice.org'dan ücretsiz kurulabilir.")
            return
        if self.kayipli and self.ozgun:
            # Ozgun Word dosyasi KAYDETMEDEN acilir: tasinamayan icerik orada.
            hedef = self.ozgun
            if self.gorunum.document().isModified():
                self.statusBar().showMessage("LibreOffice özgün dosyayı açtı; editördeki kaydedilmemiş değişiklikler "
                                             "o dosyada yok.", 8000)
        else:
            if self.yol is None or self.gorunum.document().isModified():
                if not self.kaydet():
                    return
            hedef = self.yol
        subprocess.Popen([so, "--writer", str(hedef)], close_fds=True)

    # ---------------- bicim ----------------
    def _bicim(self, degistir) -> None:
        f = QTextCharFormat(); degistir(f)
        c = self.gorunum.textCursor()
        c.mergeCharFormat(f)
        self.gorunum.mergeCurrentCharFormat(f)

    def _boyut_uygula(self, metin: str) -> None:
        try:
            boyut = float(metin.replace(",", "."))
        except ValueError:
            return
        if 1 <= boyut <= 400:
            self._bicim(lambda f: f.setFontPointSize(boyut))

    def kalin_yap(self):
        self._bicim(lambda f: f.setFontWeight(QFont.Bold if self.kalin.isChecked() else QFont.Normal))

    def italik_yap(self):
        self._bicim(lambda f: f.setFontItalic(self.italik.isChecked()))

    def alti_ciz(self):
        self._bicim(lambda f: f.setFontUnderline(self.alti.isChecked()))

    def ustu_ciz(self):
        self._bicim(lambda f: f.setFontStrikeOut(self.ustu.isChecked()))

    def _simge(self, hiza):
        simdiki = self.gorunum.currentCharFormat().verticalAlignment()
        self._bicim(lambda f: f.setVerticalAlignment(QTextCharFormat.AlignNormal if simdiki == hiza else hiza))

    def renk_sec(self):
        r = QColorDialog.getColor(self.gorunum.textColor(), self, "Yazı rengi")
        if r.isValid():
            self._bicim(lambda f: f.setForeground(QBrush(r)))

    def vurgu_sec(self):
        r = QColorDialog.getColor(QColor("#ffff00"), self, "Vurgu rengi")
        if r.isValid():
            self._bicim(lambda f: f.setBackground(QBrush(QColor(docx_io.VURGU[docx_io.en_yakin_vurgu(r)]))))

    def bicimi_temizle(self):
        c = self.gorunum.textCursor()
        c.setCharFormat(QTextCharFormat())
        self.gorunum.setCurrentCharFormat(QTextCharFormat())

    def stil_uygula(self, i: int) -> None:
        c = self.gorunum.textCursor(); c.beginEditBlock()
        bf = c.blockFormat()
        bf.setProperty(QTextFormat.UserProperty + 1, None)
        if i == 0:
            bf.setHeadingLevel(0); cf = QTextCharFormat(); cf.setFontWeight(QFont.Normal); cf.setFontPointSize(
                self.gorunum.document().defaultFont().pointSizeF())
        elif i == 1:
            bf.setHeadingLevel(0); bf.setProperty(QTextFormat.UserProperty + 1, "baslik"); cf = docx_io.baslik_bicimi(0)
        else:
            bf.setHeadingLevel(i - 1); cf = docx_io.baslik_bicimi(i - 1)
        c.setBlockFormat(bf)
        blok = QTextCursor(c.block()); blok.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
        blok.mergeCharFormat(cf); c.mergeBlockCharFormat(cf)
        c.endEditBlock()
        self.gorunum.mergeCurrentCharFormat(cf)      # bos blokta da: yazilacak metin bu stilde

    def liste(self, stil) -> None:
        c = self.gorunum.textCursor()
        mevcut = c.currentList()
        if mevcut is not None and mevcut.format().style() == stil:        # ayni dugme: listeden cik
            mevcut.remove(c.block())
            bf = c.blockFormat(); bf.setIndent(0); bf.setObjectIndex(-1)    # liste bagi kalirsa blok geri eklenir
            c.setBlockFormat(bf)
            return
        f = QTextListFormat(); f.setStyle(stil); f.setIndent(1)
        c.createList(f)

    def girinti(self, yon: int) -> None:
        c = self.gorunum.textCursor()
        lst = c.currentList()
        if lst is not None:
            f = lst.format(); yeni = max(1, min(3, f.indent() + yon))
            alt = {QTextListFormat.ListDisc: QTextListFormat.ListCircle, QTextListFormat.ListDecimal: QTextListFormat.ListLowerAlpha}
            ust = {v: k for k, v in alt.items()}
            stil = f.style()
            stil = alt.get(stil, stil) if yeni > 1 else ust.get(stil, stil)
            nf = QTextListFormat(); nf.setStyle(stil); nf.setIndent(yeni)
            lst.remove(c.block()); bf = c.blockFormat(); bf.setIndent(0); bf.setObjectIndex(-1); c.setBlockFormat(bf)
            c.createList(nf)
            return
        bf = c.blockFormat(); bf.setLeftMargin(max(0.0, bf.leftMargin() + yon * 12.7 * MM_PX)); c.setBlockFormat(bf)

    def satir_araligi(self, oran: float) -> None:
        c = self.gorunum.textCursor()
        bf = c.blockFormat(); bf.setLineHeight(oran * 100, QTextBlockFormat.ProportionalHeight.value)
        c.mergeBlockFormat(bf)

    def tablo_ekle(self) -> None:
        dlg = QDialog(self); dlg.setWindowTitle("Tablo ekle"); form = QFormLayout(dlg)
        sat = QSpinBox(); sat.setRange(1, 200); sat.setValue(3)
        sut = QSpinBox(); sut.setRange(1, 30); sut.setValue(3)
        form.addRow("Satır:", sat); form.addRow("Sütun:", sut)
        dug = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        dug.accepted.connect(dlg.accept); dug.rejected.connect(dlg.reject); form.addRow(dug)
        if dlg.exec() != QDialog.Accepted:
            return
        tf = QTextTableFormat(); tf.setBorder(0.8); tf.setCellPadding(4); tf.setCellSpacing(0)
        tf.setBorderCollapse(True); tf.setWidth(QTextLength(QTextLength.PercentageLength, 100))
        self.gorunum.textCursor().insertTable(sat.value(), sut.value(), tf)

    def _tablo_islem(self, ne: str) -> None:
        c = self.gorunum.textCursor(); t = c.currentTable()
        if t is None:
            self.statusBar().showMessage("Önce imleci bir tablonun içine koy.", 3000)
            return
        h = t.cellAt(c)
        {"satir": lambda: t.insertRows(h.row() + 1, 1), "sutun": lambda: t.insertColumns(h.column() + 1, 1),
         "satir_sil": lambda: t.removeRows(h.row(), 1), "sutun_sil": lambda: t.removeColumns(h.column(), 1)}[ne]()

    def resim_ekle(self) -> None:
        yol, _ = QFileDialog.getOpenFileName(self, "Resim ekle", str(Path.home()), "Resim (*.png *.jpg *.jpeg *.bmp *.gif)")
        if not yol:
            return
        img = QImage(yol)
        if img.isNull():
            QMessageBox.warning(self, "Resim", "Resim okunamadı.")
            return
        sayi = len(_resim_adlari(self.gorunum.document())) + 1
        ad = f"belge://ekli{sayi}-{Path(yol).stem}"
        self.gorunum.document().addResource(QTextDocument.ImageResource, QUrl(ad), img)
        en = (self.ayar.genislik - self.ayar.sol - self.ayar.sag) * MM_PX
        f = QTextImageFormat(); f.setName(ad)
        oran = min(1.0, en / img.width())
        f.setWidth(img.width() * oran); f.setHeight(img.height() * oran)
        self.gorunum.textCursor().insertImage(f)

    def sayfa_sonu(self) -> None:
        c = self.gorunum.textCursor()
        bf = QTextBlockFormat(c.blockFormat()); bf.setPageBreakPolicy(QTextFormat.PageBreak_AlwaysBefore)
        c.insertBlock(bf)

    # ---------------- sayfa duzeni ----------------
    def _duzen_degisti(self) -> None:
        self.gorunum.sayfa_uygula()
        self.gorunum.document().setModified(True)
        self._sayac()

    def ust_alt_bilgi(self) -> None:
        d = UstAltBilgi(self.ayar, self)
        if d.exec() == QDialog.Accepted:
            self.ayar.ust_bilgi, self.ayar.alt_bilgi = d.ust.text(), d.alt.text()
            self.ayar.sayfa_no = d.no.isChecked(); self.no_eylem.setChecked(self.ayar.sayfa_no)
            self._duzen_degisti()

    def sayfa_no_degistir(self) -> None:
        self.ayar.sayfa_no = self.no_eylem.isChecked(); self._duzen_degisti()

    def kenar_sec(self, i: int) -> None:
        ad = self.kenar.itemText(i)
        if ad in KENAR:
            a = self.ayar; a.ust = a.alt = a.sol = a.sag = KENAR[ad]
        else:
            d = KenarBosluklari(self.ayar, self)
            if d.exec() != QDialog.Accepted:
                return
            for k, s in d.alanlar.items():
                setattr(self.ayar, k, s.value())
        self._duzen_degisti()

    def kagit_sec(self, i: int) -> None:
        g, y = KAGIT[self.kagit.itemText(i)]
        if self.ayar.yatay:
            g, y = y, g
        self.ayar.genislik, self.ayar.yukseklik = g, y
        self._duzen_degisti()

    def yon_degistir(self) -> None:
        self.ayar.dondur(); self._duzen_degisti()

    # ---------------- durum ----------------
    def bul_ac(self) -> None:
        if not hasattr(self, "_bul"):
            self._bul = BulDegistir(self)
        c = self.gorunum.textCursor()
        if c.hasSelection():
            self._bul.bul.setText(c.selectedText())
        self._bul.show(); self._bul.raise_(); self._bul.bul.setFocus()

    def _bicim_goster(self, f: QTextCharFormat) -> None:
        self.kalin.setChecked(f.fontWeight() >= QFont.Bold)
        self.italik.setChecked(f.fontItalic()); self.alti.setChecked(f.fontUnderline())
        self.ustu.setChecked(f.fontStrikeOut())
        if f.fontPointSize() > 0:
            self.boyut.setCurrentText(str(int(f.fontPointSize())) if f.fontPointSize().is_integer() else str(f.fontPointSize()))
        aile = (f.fontFamilies() or [self.gorunum.document().defaultFont().family()])[0]
        self.yazi.blockSignals(True); self.yazi.setCurrentFont(QFont(aile)); self.yazi.blockSignals(False)

    def _konum_goster(self) -> None:
        bf = self.gorunum.textCursor().blockFormat()
        seviye = bf.headingLevel()
        self.stil.setCurrentIndex(seviye + 1 if 1 <= seviye <= 3 else (1 if bf.property(QTextFormat.UserProperty + 1) == "baslik" else 0))
        self._sayac()

    def _sayac(self) -> None:
        metin = self.gorunum.document().toPlainText()
        kelime = len(metin.split())
        y = self.ayar.yukseklik * MM_PX
        r = self.gorunum.cursorRect()
        sayfa = int((r.top() + self.gorunum.verticalScrollBar().value()) // y) + 1
        self.durum.setText(f"Sayfa {min(sayfa, self.gorunum.sayfa_sayisi())} / {self.gorunum.sayfa_sayisi()}   ·   "
                           f"{kelime} kelime   ·   {len(metin)} karakter")

    def _baslik(self) -> None:
        ad = self.yol.name if self.yol else "Adsız belge"
        self.setWindowTitle(("* " if self.gorunum.document().isModified() else "") + f"{ad} — Okuma Atölyesi Belge")

    def closeEvent(self, e):
        if self.kaydedilsin_mi():
            e.accept()
        else:
            e.ignore()


def main(argv=None) -> int:
    argv = sys.argv if argv is None else argv
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName("Okuma Atölyesi Belge")
    ikon = Path(__file__).resolve().parent.parent / "okuma.ico"
    if ikon.exists():
        app.setWindowIcon(QIcon(str(ikon)))
    yol = next((a for a in argv[1:] if a.lower().endswith(".docx")), None)
    w = BelgeEditoru(yol)
    w.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
