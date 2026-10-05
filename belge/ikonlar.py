"""belge/ikonlar.py — belge editörünün ikonları, kodla çizilir (dosya yok).

Her ikon 24×24'lük bir tuvalde vektör olarak çizilir ve birkaç boyutta
QIcon'a eklenir: her ekran ölçeğinde keskin görünür. Renk dili okuyucuyla
aynı (koyu yeşil mürekkep). Devre dışı görünümü Qt kendisi üretir.

    ikon("kaydet")                  # sabit ikon
    ikon("yazi_rengi", "#c00000")   # renk çubuğu olan ikon
    ikon("kalin", harf="B")         # harf ikonları dile göre (K/B, İ/I…)
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF

MUREKKEP = QColor("#2f433a")
VURGU = QColor("#3c78dc")
KIRMIZI = QColor("#c0392b")
YESIL = QColor("#2e8b57")
KAGIT = QColor("#ffffff")
BOYUTLAR = (16, 20, 24, 32, 40, 48, 64)


def _kalem(p: QPainter, renk=MUREKKEP, kalinlik=1.6, kesik=False) -> None:
    k = QPen(QColor(renk), kalinlik, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
    if kesik:
        k.setStyle(Qt.DashLine); k.setDashPattern([2, 1.6])
    p.setPen(k); p.setBrush(Qt.NoBrush)


def _cizgi(p, x1, y1, x2, y2):
    p.drawLine(QPointF(x1, y1), QPointF(x2, y2))


def _sayfa(p, x=5, y=2.5, g=14, y2=19, kivrik=True):
    """Kıvrık köşeli sayfa."""
    yol = QPainterPath()
    yol.moveTo(x, y); yol.lineTo(x + g - 4, y); yol.lineTo(x + g, y + 4); yol.lineTo(x + g, y + y2); yol.lineTo(x, y + y2)
    yol.closeSubpath()
    p.setBrush(KAGIT); p.drawPath(yol); p.setBrush(Qt.NoBrush)
    if kivrik:
        _cizgi(p, x + g - 4, y, x + g - 4, y + 4); _cizgi(p, x + g - 4, y + 4, x + g, y + 4)


def _harf(p, metin, rect=QRectF(2, 1, 20, 18), boyut=15, kalin=True, italik=False, renk=MUREKKEP, aile="Segoe UI"):
    f = QFont(aile); f.setPixelSize(boyut); f.setBold(kalin); f.setItalic(italik)
    p.setFont(f); p.setPen(QColor(renk)); p.drawText(rect, Qt.AlignCenter, metin)


def _cubuk(p, renk, y=19.5):
    p.setPen(Qt.NoPen); p.setBrush(QColor(renk)); p.drawRoundedRect(QRectF(3.5, y, 17, 3.2), 1, 1); p.setBrush(Qt.NoBrush)


def _satirlar(p, hizalar, y0=5, adim=4.5, x0=4, x1=20):
    for i, (a, b) in enumerate(hizalar):
        y = y0 + i * adim
        _cizgi(p, x0 + a, y, x1 - b, y)


def _ok_ucu(p, x, y, yon):
    """Küçük dolu üçgen (yon: 'sag','sol','yukari','asagi')."""
    d = {"sag": [(x, y - 2.6), (x + 3.2, y), (x, y + 2.6)], "sol": [(x, y - 2.6), (x - 3.2, y), (x, y + 2.6)],
         "yukari": [(x - 2.6, y), (x, y - 3.2), (x + 2.6, y)], "asagi": [(x - 2.6, y), (x, y + 3.2), (x + 2.6, y)]}[yon]
    p.setBrush(p.pen().color()); p.drawPolygon(QPolygonF([QPointF(a, b) for a, b in d])); p.setBrush(Qt.NoBrush)


# ---------------------------------------------------------------- çizimler
def yeni(p, **_):
    _kalem(p); _sayfa(p)
    _kalem(p, YESIL, 2); _cizgi(p, 17, 15, 17, 22); _cizgi(p, 13.5, 18.5, 20.5, 18.5)


def ac(p, **_):
    _kalem(p)
    yol = QPainterPath(); yol.moveTo(2.5, 6); yol.lineTo(9, 6); yol.lineTo(11, 8); yol.lineTo(20, 8); yol.lineTo(20, 10)
    p.drawPath(yol)
    on = QPainterPath(); on.moveTo(2.5, 6); on.lineTo(2.5, 19.5); on.lineTo(18.5, 19.5); on.lineTo(21.5, 11); on.lineTo(6, 11)
    on.lineTo(2.5, 19.5)
    p.setBrush(QColor("#f3e3b5")); p.drawPath(on)


def kaydet(p, **_):
    _kalem(p)
    yol = QPainterPath(); yol.moveTo(3.5, 3.5); yol.lineTo(17, 3.5); yol.lineTo(20.5, 7); yol.lineTo(20.5, 20.5); yol.lineTo(3.5, 20.5)
    yol.closeSubpath(); p.setBrush(QColor("#dbe7f6")); p.drawPath(yol); p.setBrush(KAGIT)
    p.drawRect(QRectF(7, 3.5, 9, 5.5)); p.drawRect(QRectF(6.5, 13, 11, 7.5))
    _cizgi(p, 8.5, 16, 15.5, 16)


def farkli_kaydet(p, **_):
    p.save(); p.scale(.85, .85); kaydet(p); p.restore()
    _kalem(p, KIRMIZI, 2.2); _cizgi(p, 14, 22, 22, 14)
    _kalem(p, MUREKKEP, 1); _cizgi(p, 13, 23, 14, 22)


def pdf(p, **_):
    _kalem(p); _sayfa(p)
    p.setPen(Qt.NoPen); p.setBrush(KIRMIZI); p.drawRoundedRect(QRectF(2, 12, 15, 7.5), 1.2, 1.2)
    _harf(p, "PDF", QRectF(2, 12, 15, 7.5), 6.5, True, False, KAGIT)


def yazdir(p, **_):
    _kalem(p)
    p.setBrush(KAGIT); p.drawRect(QRectF(7, 3, 10, 6))
    p.setBrush(QColor("#dfe6e1")); p.drawRoundedRect(QRectF(3, 9, 18, 8), 2, 2)
    p.setBrush(KAGIT); p.drawRect(QRectF(7, 14, 10, 7))
    _cizgi(p, 9, 17, 15, 17); _cizgi(p, 9, 19, 13.5, 19)


def libreoffice(p, **_):
    _kalem(p); _sayfa(p, 3, 4, 13, 17)
    _kalem(p, VURGU, 1.9)
    _cizgi(p, 12, 12, 21, 3); _cizgi(p, 15.5, 3, 21, 3); _cizgi(p, 21, 3, 21, 8.5)


def geri_al(p, **_):
    _kalem(p, MUREKKEP, 2)
    yol = QPainterPath(); yol.moveTo(5, 10); yol.cubicTo(9, 5, 18, 5, 19.5, 12); yol.cubicTo(20.5, 16, 17, 19, 13, 19)
    p.drawPath(yol)
    _cizgi(p, 5, 10, 5, 4.5); _cizgi(p, 5, 10, 10.5, 10)


def yinele(p, **_):
    p.save(); p.translate(24, 0); p.scale(-1, 1); geri_al(p); p.restore()


def kes(p, **_):
    _kalem(p, MUREKKEP, 1.7)
    p.drawEllipse(QPointF(7, 17.5), 3, 3); p.drawEllipse(QPointF(17, 17.5), 3, 3)
    _cizgi(p, 9, 15, 16.5, 3.5); _cizgi(p, 15, 15, 7.5, 3.5)


def kopyala(p, **_):
    _kalem(p)
    p.setBrush(KAGIT); p.drawRoundedRect(QRectF(4, 3, 11, 14), 1.5, 1.5)
    p.setBrush(KAGIT); p.drawRoundedRect(QRectF(9, 7.5, 11, 14), 1.5, 1.5)
    _cizgi(p, 11.5, 12, 17.5, 12); _cizgi(p, 11.5, 15, 17.5, 15); _cizgi(p, 11.5, 18, 15.5, 18)


def yapistir(p, **_):
    _kalem(p)
    p.setBrush(QColor("#e9d9b8")); p.drawRoundedRect(QRectF(3.5, 4.5, 14, 17), 2, 2)
    p.setBrush(QColor("#c9d3cd")); p.drawRoundedRect(QRectF(7, 2.5, 7, 4), 1.2, 1.2)
    p.setBrush(KAGIT); p.drawRect(QRectF(10, 10, 11, 12))
    _cizgi(p, 12.5, 14, 18.5, 14); _cizgi(p, 12.5, 17, 18.5, 17); _cizgi(p, 12.5, 20, 16, 20)


def kalin(p, harf="B", **_):
    _harf(p, harf, QRectF(2, 1, 20, 22), 18, True, False, MUREKKEP, "Georgia")


def italik(p, harf="I", **_):
    _harf(p, harf, QRectF(2, 1, 20, 22), 18, True, True, MUREKKEP, "Georgia")


def alti_ciz(p, harf="U", **_):
    _harf(p, harf, QRectF(2, -1, 20, 20), 16, True, False, MUREKKEP, "Georgia")
    _kalem(p, MUREKKEP, 1.8); _cizgi(p, 6, 20.5, 18, 20.5)


def ustu_ciz(p, harf="S", **_):
    _harf(p, harf, QRectF(2, 1, 20, 22), 17, True, False, MUREKKEP, "Georgia")
    _kalem(p, KIRMIZI, 1.6); _cizgi(p, 4.5, 12.5, 19.5, 12.5)


def ust_simge(p, **_):
    _harf(p, "x", QRectF(1, 5, 15, 18), 15, False)
    _harf(p, "2", QRectF(13, 1, 9, 10), 9, True, False, VURGU)


def alt_simge(p, **_):
    _harf(p, "x", QRectF(1, 1, 15, 18), 15, False)
    _harf(p, "2", QRectF(13, 13, 9, 10), 9, True, False, VURGU)


def yazi_rengi(p, renk="#c00000", **_):
    _harf(p, "A", QRectF(2, -1, 20, 20), 15, True)
    _cubuk(p, renk)


def vurgu(p, renk="#ffff00", **_):
    p.save(); p.translate(12, 10); p.rotate(40)
    _kalem(p, MUREKKEP, 1.4); p.setBrush(QColor("#f7f2e1")); p.drawRoundedRect(QRectF(-3, -8, 6, 11), 1, 1)
    yol = QPainterPath(); yol.moveTo(-3, 3); yol.lineTo(3, 3); yol.lineTo(1.5, 7); yol.lineTo(-1.5, 7); yol.closeSubpath()
    p.setBrush(QColor(renk).darker(115)); p.drawPath(yol); p.restore()
    _cubuk(p, renk)


def bicimi_temizle(p, **_):
    _harf(p, "A", QRectF(0, -1, 17, 19), 14, True)
    _kalem(p, KIRMIZI, 2); _cizgi(p, 14, 13, 21, 20); _cizgi(p, 21, 13, 14, 20)


def sola(p, **_):
    _kalem(p, MUREKKEP, 1.8); _satirlar(p, [(0, 0), (0, 6), (0, 0), (0, 5)])


def ortala(p, **_):
    _kalem(p, MUREKKEP, 1.8); _satirlar(p, [(0, 0), (3, 3), (0, 0), (2.5, 2.5)])


def saga(p, **_):
    _kalem(p, MUREKKEP, 1.8); _satirlar(p, [(0, 0), (6, 0), (0, 0), (5, 0)])


def iki_yana(p, **_):
    _kalem(p, MUREKKEP, 1.8); _satirlar(p, [(0, 0), (0, 0), (0, 0), (0, 0)])


def madde(p, **_):
    p.setPen(Qt.NoPen); p.setBrush(MUREKKEP)
    for y in (6, 12, 18):
        p.drawEllipse(QPointF(5, y), 1.7, 1.7)
    _kalem(p, MUREKKEP, 1.7)
    for y in (6, 12, 18):
        _cizgi(p, 9, y, 21, y)


def numara(p, **_):
    for i, y in enumerate((6, 12, 18)):
        _harf(p, str(i + 1), QRectF(1, y - 4.5, 7, 9), 7.5, True)
    _kalem(p, MUREKKEP, 1.7)
    for y in (6, 12, 18):
        _cizgi(p, 9, y, 21, y)


def girinti_artir(p, **_):
    _kalem(p, MUREKKEP, 1.7)
    for y, x in ((4.5, 3), (9, 11), (13.5, 11), (18, 3)):
        _cizgi(p, x, y, 21, y)
    _kalem(p, VURGU, 1.7); _cizgi(p, 3, 11.25, 6.5, 11.25); _ok_ucu(p, 6.5, 11.25, "sag")


def girinti_azalt(p, **_):
    _kalem(p, MUREKKEP, 1.7)
    for y, x in ((4.5, 3), (9, 11), (13.5, 11), (18, 3)):
        _cizgi(p, x, y, 21, y)
    _kalem(p, VURGU, 1.7); _cizgi(p, 4, 11.25, 8, 11.25); _ok_ucu(p, 4, 11.25, "sol")


def satir_araligi(p, **_):
    _kalem(p, MUREKKEP, 1.7)
    for y in (5, 10, 15, 20):
        _cizgi(p, 10, y, 21, y)
    _kalem(p, VURGU, 1.5); _cizgi(p, 5, 6, 5, 19); _ok_ucu(p, 5, 6, "yukari"); _ok_ucu(p, 5, 19, "asagi")


def bul(p, **_):
    _kalem(p, MUREKKEP, 2); p.drawEllipse(QPointF(10, 10), 6, 6)
    _kalem(p, MUREKKEP, 2.8); _cizgi(p, 14.5, 14.5, 20.5, 20.5)


def degistir(p, **_):
    _harf(p, "a", QRectF(1, 0, 10, 12), 10, True)
    _harf(p, "b", QRectF(12, 11, 11, 12), 10, True, False, VURGU)
    _kalem(p, MUREKKEP, 1.5)
    yol = QPainterPath(); yol.moveTo(5, 14); yol.cubicTo(5, 19, 8, 20, 11, 20); p.drawPath(yol); _ok_ucu(p, 11, 20, "sag")
    yol = QPainterPath(); yol.moveTo(19, 10); yol.cubicTo(19, 5, 16, 4, 13, 4); p.drawPath(yol); _ok_ucu(p, 13, 4, "sol")


def tablo(p, **_):
    _kalem(p, MUREKKEP, 1.4)
    p.setBrush(KAGIT); p.drawRect(QRectF(3, 4, 18, 16))
    p.setPen(Qt.NoPen); p.setBrush(QColor("#b9cfc0")); p.drawRect(QRectF(3.7, 4.7, 16.6, 4.6))
    _kalem(p, MUREKKEP, 1.4); p.drawRect(QRectF(3, 4, 18, 16))
    for y in (9.3, 14.6):
        _cizgi(p, 3, y, 21, y)
    for x in (9, 15):
        _cizgi(p, x, 4, x, 20)


def _tablo_kucuk(p):
    p.save(); p.scale(.7, .7); tablo(p); p.restore()


def _arti(p, x, y):
    _kalem(p, YESIL, 2.2); _cizgi(p, x, y - 4, x, y + 4); _cizgi(p, x - 4, y, x + 4, y)


def _carpi(p, x, y):
    _kalem(p, KIRMIZI, 2.2); _cizgi(p, x - 3.5, y - 3.5, x + 3.5, y + 3.5); _cizgi(p, x + 3.5, y - 3.5, x - 3.5, y + 3.5)


def satir_ekle(p, **_):        # arti tablonun ALTINDA: yeni satir
    _tablo_kucuk(p); _arti(p, 8.5, 19)


def sutun_ekle(p, **_):        # arti tablonun SAGINDA: yeni sutun
    _tablo_kucuk(p); _arti(p, 19.5, 8.5)


def satir_sil(p, **_):
    _tablo_kucuk(p); _carpi(p, 8.5, 19.5)


def sutun_sil(p, **_):
    _tablo_kucuk(p); _carpi(p, 19.5, 8.5)


def resim(p, **_):
    _kalem(p, MUREKKEP, 1.5)
    p.setBrush(QColor("#e4eef7")); p.drawRoundedRect(QRectF(2.5, 4, 19, 16), 2, 2)
    p.setPen(Qt.NoPen); p.setBrush(QColor("#e8b23a")); p.drawEllipse(QPointF(16, 8.5), 2, 2)
    yol = QPainterPath(); yol.moveTo(3, 19.5); yol.lineTo(9, 11); yol.lineTo(13, 16); yol.lineTo(15.5, 13.5); yol.lineTo(21, 19.5)
    yol.closeSubpath(); p.setBrush(QColor("#5f9a74")); p.drawPath(yol)


def sayfa_sonu(p, **_):
    _kalem(p, MUREKKEP, 1.5)
    p.setBrush(KAGIT); p.drawRect(QRectF(5, 1.5, 14, 7.5)); p.drawRect(QRectF(5, 15, 14, 7.5))
    _kalem(p, VURGU, 1.5, kesik=True); _cizgi(p, 2, 12, 22, 12)


def ust_alt_bilgi(p, **_):
    _kalem(p, MUREKKEP, 1.5); _sayfa(p, 4.5, 2, 15, 20, False)
    p.setPen(Qt.NoPen); p.setBrush(VURGU); p.drawRect(QRectF(6.5, 4, 11, 2.6)); p.drawRect(QRectF(6.5, 17.5, 11, 2.6))
    _kalem(p, MUREKKEP, 1.1)
    for y in (9.5, 12, 14.5):
        _cizgi(p, 7, y, 17, y)


def sayfa_no(p, **_):
    _kalem(p, MUREKKEP, 1.5); _sayfa(p, 4.5, 2, 15, 20, False)
    _kalem(p, MUREKKEP, 1.1)
    for y in (6, 8.5, 11):
        _cizgi(p, 7, y, 17, y)
    p.setPen(Qt.NoPen); p.setBrush(VURGU); p.drawEllipse(QPointF(12, 17.5), 3.4, 3.4)
    _harf(p, "1", QRectF(8.6, 14.1, 6.8, 6.8), 6, True, False, KAGIT)


def kenar_bosluklari(p, **_):
    _kalem(p, MUREKKEP, 1.5); _sayfa(p, 4, 2, 16, 20, False)
    _kalem(p, VURGU, 1.2, kesik=True); p.drawRect(QRectF(7, 5, 10, 14))


def yon(p, **_):
    _kalem(p, MUREKKEP, 1.4)
    p.setBrush(KAGIT); p.drawRect(QRectF(2.5, 3, 9, 12)); p.drawRect(QRectF(9, 11, 12.5, 9))
    _kalem(p, VURGU, 1.5)
    yol = QPainterPath(); yol.moveTo(14, 3.5); yol.cubicTo(18, 3.5, 20, 5, 20, 8.5); p.drawPath(yol); _ok_ucu(p, 20, 8.5, "asagi")


def kagit(p, **_):
    _kalem(p, MUREKKEP, 1.4)
    p.setBrush(QColor("#eef0ec")); p.drawRect(QRectF(7, 2, 13, 17))
    p.setBrush(KAGIT); p.drawRect(QRectF(4, 5, 13, 17))
    _harf(p, "A4", QRectF(4, 8, 13, 10), 6.5, True)


def stil(p, **_):
    _harf(p, "A", QRectF(1, 2, 13, 19), 16, True)
    _harf(p, "a", QRectF(11, 7, 11, 14), 11, False, False, VURGU)


CIZIMLER = {ad: f for ad, f in dict(globals()).items()
            if callable(f) and getattr(f, "__module__", "") == __name__ and not ad.startswith("_")}


def ikon(ad: str, renk: str | None = None, harf: str | None = None) -> QIcon:
    ciz = CIZIMLER[ad]
    ek = {k: v for k, v in (("renk", renk), ("harf", harf)) if v}
    sonuc = QIcon()
    for boyut in BOYUTLAR:
        pm = QPixmap(boyut, boyut); pm.fill(Qt.transparent)
        p = QPainter(pm); p.setRenderHint(QPainter.Antialiasing); p.setRenderHint(QPainter.TextAntialiasing)
        p.scale(boyut / 24, boyut / 24)
        ciz(p, **ek)
        p.end()
        sonuc.addPixmap(pm)
    return sonuc
