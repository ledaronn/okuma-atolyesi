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

from PySide6.QtCore import QMarginsF, QPointF, QRectF, QSize, QSizeF, Qt, QUrl
from PySide6.QtGui import (QAction, QActionGroup, QBrush, QColor, QFont, QFontDatabase, QIcon, QImage, QKeySequence, QPageLayout,
                           QPageSize, QPainter, QPalette, QTextBlockFormat, QTextCharFormat, QTextCursor,
                           QTextDocument, QTextFormat, QTextImageFormat, QTextLength, QTextListFormat,
                           QTextTableFormat)
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import (QApplication, QCheckBox, QColorDialog, QComboBox, QDialog, QDialogButtonBox,
                               QDoubleSpinBox, QFileDialog, QFontComboBox, QFormLayout, QGridLayout, QHBoxLayout, QLabel,
                               QLineEdit, QMainWindow, QMessageBox, QPushButton, QSpinBox, QTabWidget, QTextEdit,
                               QSizePolicy, QToolBar, QToolButton, QVBoxLayout, QWidget)

from belge import docx_io
from belge.docx_io import MM_PX, SayfaAyari
from belge.ikonlar import ikon
from ceviri import t as _t

SAYFA_ARASI = 24          # sayfalar arasindaki gri bosluk (px) — yalnizca gorunumde
KAGIT = {"A4": (210, 297), "A5": (148, 210), "Letter": (215.9, 279.4)}
KENAR = {"Normal (2,5 cm)": 25.0, "Dar (1,27 cm)": 12.7, "Geniş (3,8 cm)": 38.1}
# Serit: okuyucuyla ayni renk dili (sicak kagit zemin, koyu yesil murekkep).
SERIT_STILI = """
QMainWindow { background: #efece5; }
QTabWidget#serit::pane { border: 0; border-top: 1px solid #d9d4c7; border-bottom: 1px solid #d9d4c7; background: #fbfaf7; }
QTabWidget#serit > QTabBar { background: #efece5; }
QTabWidget#serit > QTabBar::tab { background: transparent; color: #4a5a52; border: 0; padding: 7px 18px 6px 18px;
    margin: 4px 1px 0 1px; font-size: 13px; }
QTabWidget#serit > QTabBar::tab:hover:!selected { color: #1f2d26; background: #e4e0d6; border-radius: 6px; }
QTabWidget#serit > QTabBar::tab:selected { color: #1f2d26; background: #fbfaf7; font-weight: 600;
    border: 1px solid #d9d4c7; border-bottom: 2px solid #2f433a; border-top-left-radius: 6px; border-top-right-radius: 6px; }
QWidget#seritSayfa { background: #fbfaf7; }
QWidget#grup { border-right: 1px solid #e3ded3; }
QWidget#seritSayfa QLabel { color: #1f2d26; }
QWidget#seritSayfa QLabel#grupAdi { color: #8a867c; font-size: 11px; }
QToolButton { color: #1f2d26; border: 1px solid transparent; border-radius: 5px; padding: 2px 3px; background: transparent; }
QToolButton#buyuk { padding: 2px 4px 4px 4px; font-size: 12px; }
QToolButton:hover { background: #e7eee8; border-color: #cddbd1; }
QToolButton:pressed { background: #cfe0d4; }
QToolButton:checked { background: #d6e5da; border-color: #9fbaa7; }
QComboBox, QFontComboBox { background: #ffffff; color: #1f2d26; border: 1px solid #d3cec2; border-radius: 4px;
    padding: 2px 6px; min-height: 20px; }
QComboBox:hover, QFontComboBox:hover { border-color: #9fbaa7; }
QAbstractItemView { background: #ffffff; color: #1f2d26; selection-background-color: #d6e5da; selection-color: #1f2d26; }
QToolTip { background: #fbfaf7; color: #1f2d26; border: 1px solid #d3cec2; padding: 4px 6px; }
QMenu { background: #fbfaf7; color: #1f2d26; border: 1px solid #d3cec2; }
QMenu::item:selected { background: #d6e5da; }
QStatusBar { background: #efece5; color: #5b5a55; border-top: 1px solid #d9d4c7; }
QStatusBar QLabel { color: #5b5a55; padding: 0 8px; }
"""

STILLER = ["Normal", _t("Belge başlığı"), _t("Başlık 1"), _t("Başlık 2"), _t("Başlık 3")]


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
        self.setWindowTitle(_t("Bul ve değiştir"))
        self.e = editor
        form = QFormLayout(self)
        self.bul = QLineEdit(); self.yeni = QLineEdit()
        self.harf = QCheckBox(_t("Büyük/küçük harf duyarlı")); self.kelime = QCheckBox(_t("Tam kelime"))
        form.addRow(_t("Bul:"), self.bul); form.addRow(_t("Değiştir:"), self.yeni)
        form.addRow(self.harf); form.addRow(self.kelime)
        satir = QHBoxLayout()
        for ad, f in ((_t("Sonrakini bul"), self.sonraki), (_t("Değiştir"), self.degistir), (_t("Tümünü değiştir"), self.tumu)):
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
        self.durum.setText("" if bulundu else _t("Bulunamadı."))
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
        self.durum.setText(_t("{n} yer değiştirildi.", n=n))


class UstAltBilgi(QDialog):
    def __init__(self, ayar: SayfaAyari, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("Üst ve alt bilgi"))
        form = QFormLayout(self)
        self.ust = QLineEdit(ayar.ust_bilgi); self.alt = QLineEdit(ayar.alt_bilgi)
        self.no = QCheckBox(_t("Alt bilgide sayfa numarası")); self.no.setChecked(ayar.sayfa_no)
        form.addRow(_t("Üst bilgi:"), self.ust); form.addRow(_t("Alt bilgi:"), self.alt); form.addRow(self.no)
        dug = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        dug.accepted.connect(self.accept); dug.rejected.connect(self.reject); form.addRow(dug)


class KenarBosluklari(QDialog):
    def __init__(self, ayar: SayfaAyari, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_t("Özel kenar boşlukları (mm)"))
        form = QFormLayout(self)
        self.alanlar = {}
        for ad, deger in (("ust", ayar.ust), ("alt", ayar.alt), ("sol", ayar.sol), ("sag", ayar.sag)):
            s = QDoubleSpinBox(); s.setRange(0, 100); s.setDecimals(1); s.setValue(deger)
            self.alanlar[ad] = s
            form.addRow({"ust": _t("Üst"), "alt": _t("Alt"), "sol": _t("Sol"), "sag": _t("Sağ")}[ad] + ":", s)
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
        self.serit = QTabWidget(); self.serit.setObjectName("serit"); self.serit.setDocumentMode(True)
        self.serit.setFixedHeight(132)
        v.addWidget(self.serit)
        self.uyari = QWidget(); u = QHBoxLayout(self.uyari); u.setContentsMargins(12, 6, 12, 6)
        self.uyari.setStyleSheet("background:#fff4d6; color:#5c4400;")
        self.uyari_metin = QLabel(); self.uyari_metin.setWordWrap(True)
        lo = QPushButton(ikon("libreoffice"), _t("LibreOffice'te aç")); lo.clicked.connect(self.libreoffice_ac)
        u.addWidget(self.uyari_metin, 1); u.addWidget(lo)
        self.uyari.hide()
        v.addWidget(self.uyari)
        v.addWidget(self.gorunum, 1)
        return w

    def _eylem(self, ad, f, kisayol=None, ipucu=None, denetlenir=False, simge=None) -> QAction:
        a = QAction(ad, self)
        a.triggered.connect(f)
        if simge:
            a.setIcon(ikon(simge) if isinstance(simge, str) else simge)
        if kisayol:
            a.setShortcut(QKeySequence(kisayol))
        # Ipucu kisayolu da gosterir (Word gibi): "Kalin (Ctrl+B)"
        metin = (ipucu or ad).replace("…", "")
        if kisayol:
            metin += f"  ({QKeySequence(kisayol).toString(QKeySequence.NativeText)})"
        a.setToolTip(metin)
        a.setCheckable(denetlenir)
        self.addAction(a)
        return a

    # ---------------- serit (Word benzeri: sekme > grup > dugme) ----------------
    def _sekme(self, ad: str) -> QHBoxLayout:
        sayfa = QWidget(); sayfa.setObjectName("seritSayfa")
        h = QHBoxLayout(sayfa); h.setContentsMargins(6, 4, 6, 2); h.setSpacing(0)
        self.serit.addTab(sayfa, ad)
        return h

    def _grup(self, sekme: QHBoxLayout, ad: str) -> QGridLayout:
        """Adli grup: icerik ustte, grup adi altta, sagda ince ayrac."""
        kutu = QWidget(); kutu.setObjectName("grup")
        v = QVBoxLayout(kutu); v.setContentsMargins(6, 0, 8, 0); v.setSpacing(2)
        icerik = QGridLayout(); icerik.setContentsMargins(0, 0, 0, 0); icerik.setHorizontalSpacing(2); icerik.setVerticalSpacing(3)
        v.addLayout(icerik, 1)
        etiket = QLabel(ad); etiket.setObjectName("grupAdi"); etiket.setAlignment(Qt.AlignCenter)
        v.addWidget(etiket)
        sekme.addWidget(kutu)
        return icerik

    def _buyuk(self, eylem: QAction) -> QToolButton:
        """Ikon ustte, metin altta (Word'deki buyuk dugme)."""
        b = QToolButton(); b.setDefaultAction(eylem); b.setObjectName("buyuk")
        b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon); b.setIconSize(QSize(32, 32))
        b.setMinimumWidth(58); b.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        return b

    def _kucuk(self, eylem: QAction, metinli=False) -> QToolButton:
        b = QToolButton(); b.setDefaultAction(eylem); b.setIconSize(QSize(20, 20)); b.setAutoRaise(True)
        b.setToolButtonStyle(Qt.ToolButtonTextBesideIcon if metinli else Qt.ToolButtonIconOnly)
        return b

    def _serit(self) -> None:
        dil_harf = {"K": _t("K"), "İ": _t("İ"), "A": _t("A"), "Ü": _t("Ü")}

        # ---- Dosya ----
        d = self._sekme(_t("Dosya"))
        g = self._grup(d, _t("Belge"))
        for i, (ad, f, k, s) in enumerate(((_t("Yeni"), self.yeni, "Ctrl+N", "yeni"),
                                           (_t("Aç…"), self.ac_diyalog, "Ctrl+O", "ac"),
                                           (_t("Kaydet"), self.kaydet, "Ctrl+S", "kaydet"),
                                           (_t("Farklı kaydet…"), self.farkli_kaydet, "Ctrl+Shift+S", "farkli_kaydet"))):
            g.addWidget(self._buyuk(self._eylem(ad, f, k, simge=s)), 0, i)
        g = self._grup(d, _t("Paylaş"))
        g.addWidget(self._buyuk(self._eylem(_t("PDF olarak dışa aktar…"), self.pdf_aktar, simge="pdf")), 0, 0)
        g.addWidget(self._buyuk(self._eylem(_t("Yazdır…"), self.yazdir, "Ctrl+P", simge="yazdir")), 0, 1)
        g = self._grup(d, "LibreOffice")
        g.addWidget(self._buyuk(self._eylem(_t("LibreOffice'te aç"), self.libreoffice_ac, simge="libreoffice",
                                            ipucu=_t("Tam Word gücü: izlenen değişiklikler, yorumlar, dipnot, içindekiler…"))), 0, 0)
        d.addStretch(1)

        # ---- Giris ----
        h = self._sekme(_t("Giriş"))
        g = self._grup(h, _t("Pano"))
        g.addWidget(self._buyuk(self._eylem(_t("Yapıştır"), lambda: self.gorunum.paste(), simge="yapistir")), 0, 0, 2, 1)
        g.addWidget(self._kucuk(self._eylem(_t("Kes"), lambda: self.gorunum.cut(), simge="kes"), True), 0, 1)
        g.addWidget(self._kucuk(self._eylem(_t("Kopyala"), lambda: self.gorunum.copy(), simge="kopyala"), True), 1, 1)

        g = self._grup(h, _t("Yazı tipi"))
        self.yazi = QFontComboBox(); self.yazi.setFixedWidth(170)
        self.yazi.currentFontChanged.connect(lambda f: self._bicim(lambda c: c.setFontFamilies([f.family()])))
        self.boyut = QComboBox(); self.boyut.setEditable(True); self.boyut.setFixedWidth(58)
        self.boyut.addItems([str(s) for s in (8, 9, 10, 11, 12, 14, 16, 18, 20, 24, 28, 36, 48, 72)])
        self.boyut.textActivated.connect(self._boyut_uygula); self.boyut.setToolTip(_t("Yazı boyutu"))
        satir1 = QHBoxLayout(); satir1.setSpacing(3); satir1.addWidget(self.yazi); satir1.addWidget(self.boyut); satir1.addStretch(1)
        g.addLayout(satir1, 0, 0)
        self.kalin = self._eylem(_t("Kalın"), self.kalin_yap, "Ctrl+B", None, True, ikon("kalin", harf=dil_harf["K"]))
        self.italik = self._eylem(_t("İtalik"), self.italik_yap, "Ctrl+I", None, True, ikon("italik", harf=dil_harf["İ"]))
        self.alti = self._eylem(_t("Altı çizili"), self.alti_ciz, "Ctrl+U", None, True, ikon("alti_ciz", harf=dil_harf["A"]))
        self.ustu = self._eylem(_t("Üstü çizili"), self.ustu_ciz, None, None, True, ikon("ustu_ciz", harf=dil_harf["Ü"]))
        self.renk_eylem = self._eylem(_t("Yazı rengi"), self.renk_sec, simge=ikon("yazi_rengi", "#c00000"))
        self.vurgu_eylem = self._eylem(_t("Vurgu rengi"), self.vurgu_sec, simge=ikon("vurgu", "#ffe84d"))
        satir2 = QHBoxLayout(); satir2.setSpacing(1)
        for a in (self.kalin, self.italik, self.alti, self.ustu,
                  self._eylem(_t("Üst simge"), lambda: self._simge(QTextCharFormat.AlignSuperScript), "Ctrl+Shift++", simge="ust_simge"),
                  self._eylem(_t("Alt simge"), lambda: self._simge(QTextCharFormat.AlignSubScript), "Ctrl+=", simge="alt_simge"),
                  self.renk_eylem, self.vurgu_eylem,
                  self._eylem(_t("Biçimi temizle"), self.bicimi_temizle, simge="bicimi_temizle")):
            satir2.addWidget(self._kucuk(a))
        satir2.addStretch(1)
        g.addLayout(satir2, 1, 0)

        g = self._grup(h, _t("Paragraf"))
        p1 = QHBoxLayout(); p1.setSpacing(1)
        for ad, f, s in ((_t("Madde işaretleri"), lambda: self.liste(QTextListFormat.ListDisc), "madde"),
                         (_t("Numaralandırma"), lambda: self.liste(QTextListFormat.ListDecimal), "numara"),
                         (_t("Girintiyi azalt"), lambda: self.girinti(-1), "girinti_azalt"),
                         (_t("Girintiyi artır"), lambda: self.girinti(1), "girinti_artir")):
            p1.addWidget(self._kucuk(self._eylem(ad, f, simge=s)))
        self.aralik = QComboBox(); self.aralik.addItems([_t("1,0"), _t("1,15"), _t("1,5"), _t("2,0")])
        self.aralik.setToolTip(_t("Satır aralığı")); self.aralik.setFixedWidth(62)
        self.aralik.activated.connect(lambda _: self.satir_araligi(float(self.aralik.currentText().replace(",", "."))))
        aralik_ikon = QLabel(); aralik_ikon.setPixmap(ikon("satir_araligi").pixmap(20, 20)); aralik_ikon.setToolTip(_t("Satır aralığı"))
        p1.addSpacing(4); p1.addWidget(aralik_ikon); p1.addWidget(self.aralik); p1.addStretch(1)
        g.addLayout(p1, 0, 0)
        p2 = QHBoxLayout(); p2.setSpacing(1)
        self.hizalar = QActionGroup(self); self.hizalar.setExclusive(True); self.hiza_eylem = {}
        for ad, hiza, k, s in ((_t("Sola hizala"), Qt.AlignLeft, "Ctrl+L", "sola"), (_t("Ortala"), Qt.AlignHCenter, "Ctrl+E", "ortala"),
                               (_t("Sağa hizala"), Qt.AlignRight, "Ctrl+R", "saga"), (_t("İki yana yasla"), Qt.AlignJustify, "Ctrl+J", "iki_yana")):
            a = self._eylem(ad, lambda _=False, h=hiza: self.gorunum.setAlignment(h), k, None, True, s)
            self.hizalar.addAction(a); self.hiza_eylem[int(hiza)] = a; p2.addWidget(self._kucuk(a))
        p2.addStretch(1)
        g.addLayout(p2, 1, 0)

        g = self._grup(h, _t("Stiller"))
        self.stil = QComboBox(); self.stil.addItems(STILLER); self.stil.setMinimumWidth(150)
        self.stil.activated.connect(self.stil_uygula); self.stil.setToolTip(_t("Paragraf stili"))
        stil_ikon = QLabel(); stil_ikon.setPixmap(ikon("stil").pixmap(28, 28))
        g.addWidget(stil_ikon, 0, 0, Qt.AlignCenter); g.addWidget(self.stil, 1, 0)

        g = self._grup(h, _t("Düzenleme"))
        g.addWidget(self._kucuk(self._eylem(_t("Bul"), self.bul_ac, "Ctrl+F", simge="bul"), True), 0, 0)
        g.addWidget(self._kucuk(self._eylem(_t("Değiştir"), self.bul_ac, "Ctrl+H", simge="degistir"), True), 1, 0)
        h.addStretch(1)

        # ---- Ekle ----
        e = self._sekme(_t("Ekle"))
        g = self._grup(e, _t("Tablo"))
        g.addWidget(self._buyuk(self._eylem(_t("Tablo…"), self.tablo_ekle, simge="tablo")), 0, 0, 2, 1)
        g.addWidget(self._kucuk(self._eylem(_t("Satır ekle"), lambda: self._tablo_islem("satir"), simge="satir_ekle"), True), 0, 1)
        g.addWidget(self._kucuk(self._eylem(_t("Sütun ekle"), lambda: self._tablo_islem("sutun"), simge="sutun_ekle"), True), 1, 1)
        g.addWidget(self._kucuk(self._eylem(_t("Satırı sil"), lambda: self._tablo_islem("satir_sil"), simge="satir_sil"), True), 0, 2)
        g.addWidget(self._kucuk(self._eylem(_t("Sütunu sil"), lambda: self._tablo_islem("sutun_sil"), simge="sutun_sil"), True), 1, 2)
        g = self._grup(e, _t("Çizimler"))
        g.addWidget(self._buyuk(self._eylem(_t("Resim…"), self.resim_ekle, simge="resim")), 0, 0)
        g = self._grup(e, _t("Sayfalar"))
        g.addWidget(self._buyuk(self._eylem(_t("Sayfa sonu"), self.sayfa_sonu, "Ctrl+Return", simge="sayfa_sonu")), 0, 0)
        g = self._grup(e, _t("Üst ve alt bilgi"))
        g.addWidget(self._buyuk(self._eylem(_t("Üst/alt bilgi…"), self.ust_alt_bilgi, simge="ust_alt_bilgi")), 0, 0)
        self.no_eylem = self._eylem(_t("Sayfa numarası"), self.sayfa_no_degistir, None, None, True, "sayfa_no")
        g.addWidget(self._buyuk(self.no_eylem), 0, 1)
        e.addStretch(1)

        # ---- Duzen ----
        z = self._sekme(_t("Düzen"))
        g = self._grup(z, _t("Sayfa yapısı"))
        self.kenar = QComboBox(); self.kenar.addItems([_t(k) for k in KENAR] + [_t("Özel…")]); self.kenar.setToolTip(_t("Kenar boşlukları"))
        self.kenar.activated.connect(self.kenar_sec)
        self.kagit = QComboBox(); self.kagit.addItems(list(KAGIT)); self.kagit.activated.connect(self.kagit_sec)
        self.kagit.setToolTip(_t("Kâğıt boyutu"))
        for sat, (s, metin, kutu) in enumerate((("kenar_bosluklari", _t("Kenar boşlukları"), self.kenar),
                                                 ("kagit", _t("Kâğıt boyutu"), self.kagit))):
            simge = QLabel(); simge.setPixmap(ikon(s).pixmap(20, 20))
            g.addWidget(simge, sat, 0); g.addWidget(QLabel(metin), sat, 1); g.addWidget(kutu, sat, 2)
        g.addWidget(self._buyuk(self._eylem(_t("Dikey / yatay"), self.yon_degistir, simge="yon")), 0, 3, 2, 1)
        z.addStretch(1)

        # ---- Hizli erisim: sekmelerin sagi (Kaydet, Geri al, Yinele) ----
        hizli = QWidget(); hz = QHBoxLayout(hizli); hz.setContentsMargins(0, 2, 8, 0); hz.setSpacing(0)
        for a in (self._eylem(_t("Kaydet"), self.kaydet, None, None, False, "kaydet"),
                  self._eylem(_t("Geri al"), lambda: self.gorunum.undo(), "Ctrl+Z", simge="geri_al"),
                  self._eylem(_t("Yinele"), lambda: self.gorunum.redo(), "Ctrl+Y", simge="yinele")):
            b = self._kucuk(a); b.setIconSize(QSize(18, 18)); hz.addWidget(b)
        self.serit.setCornerWidget(hizli, Qt.TopRightCorner)
        self.serit.setCurrentIndex(1)                  # Word gibi Giris sekmesiyle acilir
        self.setStyleSheet(SERIT_STILI)

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
        c = QMessageBox.question(self, _t("Kaydedilmemiş değişiklikler"), _t("Belgedeki değişiklikler kaydedilsin mi?"),
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
        yol, _ = QFileDialog.getOpenFileName(self, _t("Belge aç"), str(self.yol.parent if self.yol else Path.home()),
                                             _t("Word belgesi (*.docx)"))
        if yol:
            self.ac(yol)

    def ac(self, yol) -> bool:
        yol = Path(yol)
        try:
            sonuc = docx_io.docx_oku(yol)
        except Exception as h:
            QMessageBox.warning(self, _t("Açılamadı"), _t("{ad} açılamadı:\n{hata}\n\nLibreOffice'te açmayı deneyebilirsin.", ad=yol.name, hata=h))
            return False
        self.yol = yol
        self._belge_koy(sonuc.belge, sonuc.sayfa)
        self.kayipli = bool(sonuc.uyarilar)
        self.ozgun = yol if self.kayipli else None
        if self.kayipli:
            self.uyari_metin.setText(_t("Bu belgede editörün taşıyamadığı içerik var: ") + ", ".join(sonuc.uyarilar)
                                     + _t(". Özgün dosyanın üstüne kaydedilmez (o içerik silinirdi); değişiklikleri "
                                       "Farklı kaydet ile yeni bir dosyaya kaydet ya da belgeyi LibreOffice'te düzenle."))
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
            oneri = oneri.with_name(oneri.stem + _t(" (düzenlendi)") + ".docx")
        yol, _ = QFileDialog.getSaveFileName(self, _t("Farklı kaydet"), str(oneri), _t("Word belgesi (*.docx)"))
        if not yol:
            return False
        yol = Path(yol if yol.lower().endswith(".docx") else yol + ".docx")
        if self.kayipli and self.ozgun is not None and yol.resolve() == self.ozgun.resolve():
            QMessageBox.warning(self, _t("Özgün dosya korunuyor"),
                                _t("Bu dosyadaki taşınamayan içerik silinirdi. Başka bir ad seç ya da LibreOffice'te düzenle."))
            return False
        return self._yaz(yol)

    def _yaz(self, yol: Path) -> bool:
        try:
            docx_io.docx_yaz(self.gorunum.document(), self.ayar, yol)
        except Exception as h:
            QMessageBox.warning(self, _t("Kaydedilemedi"), f"{yol}\n{h}")
            return False
        self.yol = yol
        self.gorunum.document().setModified(False)
        self.statusBar().showMessage(_t("Kaydedildi: {ad}", ad=yol.name), 4000)
        self._baslik()
        return True

    def pdf_aktar(self) -> None:
        oneri = (self.yol.with_suffix(".pdf") if self.yol else Path.home() / "Belge.pdf")
        yol, _ = QFileDialog.getSaveFileName(self, _t("PDF olarak dışa aktar"), str(oneri), _t("PDF (*.pdf)"))
        if not yol:
            return
        self.pdf_yaz(yol)
        self.statusBar().showMessage(_t("PDF yazıldı: {ad}", ad=Path(yol).name), 4000)

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
            QMessageBox.information(self, _t("LibreOffice bulunamadı"),
                                    _t("LibreOffice kurulu değil. libreoffice.org'dan ücretsiz kurulabilir."))
            return
        if self.kayipli and self.ozgun:
            # Ozgun Word dosyasi KAYDETMEDEN acilir: tasinamayan icerik orada.
            hedef = self.ozgun
            if self.gorunum.document().isModified():
                self.statusBar().showMessage(_t("LibreOffice özgün dosyayı açtı; editördeki kaydedilmemiş değişiklikler "
                                             "o dosyada yok."), 8000)
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
        r = QColorDialog.getColor(self.gorunum.textColor(), self, _t("Yazı rengi"))
        if r.isValid():
            self._bicim(lambda f: f.setForeground(QBrush(r)))
            self.renk_eylem.setIcon(ikon("yazi_rengi", r.name()))

    def vurgu_sec(self):
        r = QColorDialog.getColor(QColor("#ffff00"), self, _t("Vurgu rengi"))
        if r.isValid():
            renk = QColor(docx_io.VURGU[docx_io.en_yakin_vurgu(r)])
            self._bicim(lambda f: f.setBackground(QBrush(renk)))
            self.vurgu_eylem.setIcon(ikon("vurgu", renk.name()))

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
        dlg = QDialog(self); dlg.setWindowTitle(_t("Tablo ekle")); form = QFormLayout(dlg)
        sat = QSpinBox(); sat.setRange(1, 200); sat.setValue(3)
        sut = QSpinBox(); sut.setRange(1, 30); sut.setValue(3)
        form.addRow(_t("Satır:"), sat); form.addRow(_t("Sütun:"), sut)
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
            self.statusBar().showMessage(_t("Önce imleci bir tablonun içine koy."), 3000)
            return
        h = t.cellAt(c)
        {"satir": lambda: t.insertRows(h.row() + 1, 1), "sutun": lambda: t.insertColumns(h.column() + 1, 1),
         "satir_sil": lambda: t.removeRows(h.row(), 1), "sutun_sil": lambda: t.removeColumns(h.column(), 1)}[ne]()

    def resim_ekle(self) -> None:
        yol, _ = QFileDialog.getOpenFileName(self, _t("Resim ekle"), str(Path.home()), _t("Resim (*.png *.jpg *.jpeg *.bmp *.gif)"))
        if not yol:
            return
        img = QImage(yol)
        if img.isNull():
            QMessageBox.warning(self, _t("Resim"), _t("Resim okunamadı."))
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
        adlar = list(KENAR)              # gosterilen ad cevrilmis olabilir: sira ile eslenir
        if i < len(adlar):
            a = self.ayar; a.ust = a.alt = a.sol = a.sag = KENAR[adlar[i]]
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
        hiza = int(bf.alignment() & (Qt.AlignLeft | Qt.AlignHCenter | Qt.AlignRight | Qt.AlignJustify)) or int(Qt.AlignLeft)
        a = self.hiza_eylem.get(hiza)
        if a is not None:
            a.setChecked(True)
        seviye = bf.headingLevel()
        self.stil.setCurrentIndex(seviye + 1 if 1 <= seviye <= 3 else (1 if bf.property(QTextFormat.UserProperty + 1) == "baslik" else 0))
        self._sayac()

    def _sayac(self) -> None:
        metin = self.gorunum.document().toPlainText()
        kelime = len(metin.split())
        y = self.ayar.yukseklik * MM_PX
        r = self.gorunum.cursorRect()
        sayfa = int((r.top() + self.gorunum.verticalScrollBar().value()) // y) + 1
        self.durum.setText(_t("Sayfa {sayfa} / {toplam}   ·   {kelime} kelime   ·   {karakter} karakter",
                              sayfa=min(sayfa, self.gorunum.sayfa_sayisi()), toplam=self.gorunum.sayfa_sayisi(),
                              kelime=kelime, karakter=len(metin)))

    def _baslik(self) -> None:
        ad = self.yol.name if self.yol else _t("Adsız belge")
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
