#!/usr/bin/env python3
"""Kartu Facebook Cekricek.id — 1080x1350 (4:5), karakter editorial hangat.

Pakai:
  python3 kartu_fb.py masukan.json keluar.png
masukan.json:
  {"rubrik": "Rona",
   "judul": "Orang Rimba di Jambi *Sudah Mengenal Satu Tuhan* Sebelum Berislam",
   "ring": "satu kalimat fakta dari artikel",
   "templat": "foto|malam|kertas|kutipan",
   "foto": "foto/279173.webp", "fokus": 0.5, "kredit": "Foto: .../Wikimedia Commons",
   "gaya": "feature|berita",      # feature = judul serif Lora; berita = Poppins
   "oleh": "Temenggung Pemubar"   # hanya templat kutipan
  }
Tanda * mengapit kata yang disorot (feature: miring oranye; berita: teal tebal).
"""
import json, sys
from PIL import Image, ImageDraw, ImageChops
import ckfb as K

W, H = 1080, 1350
TEPI = 72


def _judul(d, o, maxw, maxbaris, besar, kecil):
    gaya = o.get("gaya", "feature")
    toks = K.tokens(o["judul"])
    if gaya == "feature":
        ft, ft2, b, sz = K.pas(d, toks, maxw, maxbaris, besar, kecil, "serif", "bold", "bolditalic")
        lh = int(sz * 1.16)
    else:
        ft, ft2, b, sz = K.pas(d, toks, maxw, maxbaris, besar, kecil, "sans", "bold", None)
        lh = int(sz * 1.2)
    return ft, ft2, b, lh


def _kaki(d, o, warna_teks, warna_garis):
    """Kaki: cekricek.id di kiri; kredit foto di kanan, sejajar (koreksi AFP 16 Okt 2026).
    Teks "Kisah lengkapnya di situs" dihapus atas koreksi AFP 16 Okt 2026."""
    y = H - 70
    d.line([(TEPI, y), (W - TEPI, y)], fill=warna_garis, width=1)
    ft = K.font("medium", 22)
    d.text((TEPI, y + 20), "c e k r i c e k . i d", font=ft, fill=warna_teks)
    if o.get("kredit"):
        fk = K.font("light", 19)
        d.text((W - TEPI - d.textlength(o["kredit"], font=fk), y + 22), o["kredit"], font=fk, fill=warna_teks)


def _badan(d, o, y_atas, warna_judul, warna_sorot, warna_ring, maxbaris=6, besar=92):
    ft, ft2, b, lh = _judul(d, o, W - 2 * TEPI, maxbaris, besar, 46)
    ring = o.get("ring", "")
    fr = K.font("regular", 28)
    rb = K.bungkus_teks(d, ring, fr, W - 2 * TEPI - 50) if ring else []
    tinggi = 46 + len(b) * lh + (30 + len(rb) * 40 if rb else 0)
    y0 = y_atas + max(0, (H - 110 - y_atas - tinggi) // 2)
    d.rectangle([TEPI, y0, TEPI + 72, y0 + 6], fill=K.ORANYE)
    y = K.tulis(d, b, ft, TEPI, y0 + 42, lh, warna_judul, warna_sorot, ft2)
    if rb:
        yy = y + 26
        for s in rb:
            d.text((TEPI, yy), s, font=fr, fill=warna_ring); yy += 40


def foto(o):
    """Foto penuh di bagian atas, melebur ke biru malam; judul serif besar di bawah."""
    FH = 760
    im = Image.new("RGB", (W, H), K.MALAM)
    f = K.vignette(K.hangatkan(K.foto_pas(o["foto"], W, FH, o.get("fokus", 0.5)), 1.05), 0.35)
    im.paste(f, (0, 0))
    K.gradasi_bawah(im, 320, FH - 320, K.MALAM, kurva=1.6)
    K.gradasi_atas(im, 170, K.MALAM, 150)
    d = ImageDraw.Draw(im, "RGBA")
    lg = K.wordmark(58, "putih"); im.paste(lg, (TEPI - 6, 56), lg)
    if o.get("rubrik"):
        K.label(d, W - TEPI - 150, 62, o["rubrik"], K.ORANYE, K.MALAM)
    _badan(d, o, FH - 200, K.PUTIH, K.ORANYE, K.ABU, maxbaris=5, besar=80)
    _kaki(d, o, (150, 168, 184), (60, 78, 96))
    return K.butir(im, 4)


def malam(o):
    """Tanpa foto: biru malam bergradasi dengan cahaya oranye samar, judul serif besar."""
    im = K.gradasi(W, H, K.MALAM, (18, 44, 66))
    glow = Image.new("RGB", (W, H), (0, 0, 0))
    ImageDraw.Draw(glow).ellipse([W - 520, -380, W + 260, 380], fill=(110, 52, 0))
    glow = glow.filter(K.ImageFilter.GaussianBlur(170))
    im = ImageChops.add(im, glow)
    d = ImageDraw.Draw(im, "RGBA")
    lg = K.wordmark(58, "putih"); im.paste(lg, (TEPI - 6, 56), lg)
    if o.get("rubrik"):
        K.label(d, TEPI, 150, o["rubrik"], K.ORANYE, K.MALAM)
    _badan(d, o, 240, K.PUTIH, K.ORANYE, K.ABU)
    _kaki(d, o, (150, 168, 184), (60, 78, 96))
    return K.butir(im, 5)


def kertas(o):
    """Terang: kertas krem, judul serif biru malam, aksen oranye. Untuk topik ringan, kuliner, perjalanan."""
    im = Image.new("RGB", (W, H), K.KRIM)
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle([0, 0, W, 10], fill=K.ORANYE)
    lg = K.wordmark(58, "gelap"); im.paste(lg, (TEPI - 6, 64), lg)
    if o.get("rubrik"):
        K.label(d, TEPI, 158, o["rubrik"], K.MALAM, K.KRIM)
    _badan(d, o, 250, K.MALAM, (200, 96, 0), (88, 100, 112))
    _kaki(d, o, (120, 130, 140), (205, 198, 186))
    return K.butir(im, 3)


def kutipan(o):
    """Kutipan tokoh: tanda kutip serif raksasa oranye, kalimat serif miring, nama di bawah."""
    im = K.gradasi(W, H, (14, 36, 52), K.MALAM)
    d = ImageDraw.Draw(im, "RGBA")
    lg = K.wordmark(58, "putih"); im.paste(lg, (TEPI - 6, 56), lg)
    if o.get("rubrik"):
        K.label(d, TEPI, 150, o["rubrik"], K.ORANYE, K.MALAM)
    fq = K.serif("bold", 260)
    d.text((TEPI - 12, 190), "“", font=fq, fill=K.ORANYE + (235,))
    toks = K.tokens(o["judul"])
    ft, ft2, b, sz = K.pas(d, toks, W - 2 * TEPI, 7, 72, 44, "serif", "italic", "bolditalic")
    lh = int(sz * 1.2)
    oleh = o.get("oleh", o.get("ring", ""))
    fo = K.font("medium", 27)
    ob = K.bungkus_teks(d, oleh, fo, W - 2 * TEPI - 80) if oleh else []
    tinggi = len(b) * lh + (44 + len(ob) * 38 if ob else 0)
    y0 = 430 + max(0, (H - 110 - 430 - tinggi) // 2)
    y = K.tulis(d, b, ft, TEPI, y0, lh, K.PUTIH, K.KUNING, ft2)
    if ob:
        d.rectangle([TEPI, y + 22, TEPI + 56, y + 26], fill=K.ORANYE)
        yy = y + 44
        for s in ob:
            d.text((TEPI, yy), s, font=fo, fill=K.ABU); yy += 38
    _kaki(d, o, (150, 168, 184), (60, 78, 96))
    return K.butir(im, 4)


TEMPLAT = {"foto": foto, "malam": malam, "kertas": kertas, "kutipan": kutipan}


def buat(o, keluar):
    t = o.get("templat") or ("foto" if o.get("foto") else "malam")
    im = TEMPLAT[t](o)
    im.save(keluar, "PNG", optimize=True)
    return keluar




def sampul(o):
    """Pola yang terbukti tinggi impresinya: foto sebidang besar, satu kalimat kail besar di panel
    terang di bawah foto (kontras atau pertanyaan), label kecil di atas panel. Kail bukan judul artikel."""
    FH = 900
    im = Image.new("RGB", (W, H), K.MALAM)
    f = K.vignette(K.hangatkan(K.foto_pas(o["foto"], W, FH, o.get("fokus", 0.5)), 1.04), 0.3)
    im.paste(f, (0, 0))
    K.gradasi_atas(im, 180, K.MALAM, 160)
    K.gradasi_bawah(im, 260, FH - 260, K.MALAM, kurva=1.5, puncak=200)
    d = ImageDraw.Draw(im, "RGBA")
    lg = K.wordmark(56, "putih"); im.paste(lg, (TEPI - 6, 52), lg)
    # panel kail
    PX, PW = 44, W - 88
    toks = K.tokens(o["kail"])
    ft, ft2, b, sz = K.pas(d, toks, PW - 96, 4, 76, 46, "sans", "bold", None)
    lh = int(sz * 1.14)
    ph = len(b) * lh + 96
    py = min(FH - 120, H - 96 - ph - 20)
    py = max(py, H - 110 - ph - 10) if py + ph > H - 110 else py
    # label di atas panel
    lab = o.get("label") or o.get("rubrik", "")
    if lab:
        fl = K.serif("bolditalic", 34)
        tw = d.textlength(lab, font=fl)
        d.rounded_rectangle([PX, py - 64, PX + tw + 44, py + 10], 10, fill=(246, 241, 232, 235))
        d.text((PX + 22, py - 56), lab, font=fl, fill=(60, 52, 44))
    d.rounded_rectangle([PX, py, PX + PW, py + ph], 22, fill=(255, 255, 255, 246))
    d.rectangle([PX, py + 26, PX + 8, py + ph - 26], fill=K.ORANYE)
    K.tulis(d, b, ft, PX + 48, py + 46, lh, K.MALAM, (214, 104, 0), ft2)
    # kaki di bidang gelap: cekricek.id kiri, kredit foto kanan sejajar (koreksi AFP 16 Okt 2026)
    ftk = K.font("medium", 22)
    d.text((TEPI, H - 62), "c e k r i c e k . i d", font=ftk, fill=(150, 168, 184))
    if o.get("kredit"):
        fk = K.font("light", 19)
        d.text((W - TEPI - d.textlength(o["kredit"], font=fk), H - 60), o["kredit"], font=fk, fill=(150, 168, 184))
    return K.butir(im, 3)


TEMPLAT["sampul"] = sampul


if __name__ == "__main__":
    o = json.load(open(sys.argv[1], encoding="utf-8"))
    print(buat(o, sys.argv[2]))
