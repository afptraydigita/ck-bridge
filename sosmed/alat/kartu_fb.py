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
    """Kaki: HANYA kredit foto di kanan bawah. Teks "cekricek.id" kiri dan "Kisah lengkapnya di situs"
    dihapus atas koreksi AFP 16 Okt 2026 (18.36) — logo di atas sudah cukup."""
    y = H - 70
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
    _badan(d, o, 240, K.PUTIH, K.ORANYE, K.ABU)
    _kaki(d, o, (150, 168, 184), (60, 78, 96))
    return K.butir(im, 5)


def kertas(o):
    """Terang: kertas krem, judul serif biru malam, aksen oranye. Untuk topik ringan, kuliner, perjalanan."""
    im = Image.new("RGB", (W, H), K.KRIM)
    d = ImageDraw.Draw(im, "RGBA")
    d.rectangle([0, 0, W, 10], fill=K.ORANYE)
    lg = K.wordmark(58, "gelap"); im.paste(lg, (TEPI - 6, 64), lg)
    _badan(d, o, 250, K.MALAM, (200, 96, 0), (88, 100, 112))
    _kaki(d, o, (120, 130, 140), (205, 198, 186))
    return K.butir(im, 3)


def kutipan(o):
    """Kutipan tokoh: tanda kutip serif raksasa oranye, kalimat serif miring, nama di bawah."""
    im = K.gradasi(W, H, (14, 36, 52), K.MALAM)
    d = ImageDraw.Draw(im, "RGBA")
    lg = K.wordmark(58, "putih"); im.paste(lg, (TEPI - 6, 56), lg)
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


def _tanpa_titik(teks):
    """Judul dan kail tanpa tanda titik di ujung (koreksi AFP 16 Okt 2026). Tanda tanya/seru dibiarkan."""
    teks = teks.strip()
    while teks.endswith(".") or teks.endswith(".*"):
        teks = teks[:-2] + "*" if teks.endswith(".*") else teks[:-1]
    return teks


def buat(o, keluar):
    for k in ("judul", "kail"):
        if o.get(k) and o.get("templat") != "kutipan":
            o[k] = _tanpa_titik(o[k])
    t = o.get("templat") or ("foto" if o.get("foto") else "malam")
    im = TEMPLAT[t](o)
    im.save(keluar, "PNG", optimize=True)
    return keluar




def sampul(o):
    """Pola yang terbukti tinggi impresinya: foto sebidang besar, satu kalimat kail besar di panel
    terang di bawah foto (kontras atau pertanyaan). Tanpa label; kail bukan judul artikel."""
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
    # label seri di atas panel DIHAPUS (koreksi AFP 16 Okt 2026, 18.36): nama seri hanya di caption
    d.rounded_rectangle([PX, py, PX + PW, py + ph], 22, fill=(255, 255, 255, 246))
    d.rectangle([PX, py + 26, PX + 8, py + ph - 26], fill=K.ORANYE)
    K.tulis(d, b, ft, PX + 48, py + 46, lh, K.MALAM, (214, 104, 0), ft2)
    # kaki: hanya kredit foto di kanan bawah (koreksi AFP 16 Okt 2026, 18.36)
    if o.get("kredit"):
        fk = K.font("light", 19)
        d.text((W - TEPI - d.textlength(o["kredit"], font=fk), H - 60), o["kredit"], font=fk, fill=(150, 168, 184))
    return K.butir(im, 3)


TEMPLAT["sampul"] = sampul




def tiktok(o):
    """Tiruan persis kartu TikTok @cekricekid (rujukan AFP 16 Okt 2026, 20.49: "tiru persis, kecuali logo"):
    foto penuh melebur ke biru malam; garis tipis di kiri judul+deskripsi; judul Poppins tebal putih dengan
    kata sorot oranye; deskripsi Poppins reguler putih; empat titik; pil toska "www.cekricek.id" dengan ikon
    lup (kaca pembesar) dalam lingkaran oranye; garis kiri oranye rata huruf. Dipakai untuk TikTok, Facebook, dan Instagram (frame 1080x1350, 4:5).
    Ruas: foto, fokus, judul (*sorot*), ringkas, kredit (opsional, kecil di kanan bawah)."""
    im = Image.new("RGB", (W, H), K.MALAM)
    FH = 900
    f = K.hangatkan(K.foto_pas(o["foto"], W, FH, o.get("fokus", 0.5)), 1.03)
    im.paste(f, (0, 0))
    K.gradasi_atas(im, 140, K.MALAM, 120)
    K.gradasi_bawah(im, 420, FH - 420, K.MALAM, kurva=1.25, puncak=255)
    d = ImageDraw.Draw(im, "RGBA")
    lg = K.wordmark(60, "putih"); im.paste(lg, (TEPI - 6, 56), lg)
    X = 112                      # teks mulai di sini; garis tipis di X-30
    maxw = W - X - TEPI + 10
    toks = K.tokens(o["judul"])
    ft, ft2, b, sz = K.pas(d, toks, maxw, 3, 66, 48, "sans", "extrabold" if K._cari("Poppins-ExtraBold.ttf") else "bold", None)
    ft2 = ft
    lh = int(sz * 1.12)
    fr = K.font("regular", 29)
    rb = K.bungkus_teks(d, o.get("ringkas", ""), fr, maxw)
    if len(rb) > 5:
        print("PERINGATAN: ringkas terpotong, lebih dari 5 baris", file=sys.stderr); rb = rb[:5]
    lhr = 40
    tinggi = len(b) * lh + 22 + len(rb) * lhr
    y0 = H - 262 - tinggi
    # garis tipis kiri (putih keabuan) sepanjang judul + deskripsi
    y = K.tulis(d, b, ft, X, y0, lh, K.PUTIH, K.ORANYE, ft2)
    yy = y + 22
    for s_ in rb:
        d.text((X, yy), s_, font=fr, fill=K.PUTIH); yy += lhr
    # garis kiri: warna sama dengan sorot judul (oranye/kuning), rata dengan puncak huruf judul
    # dan dasar huruf baris terakhir deskripsi (koreksi AFP 16 Okt 2026, 21.00)
    atas_huruf = y0 + ft.getbbox("H")[1]
    terakhir = rb[-1] if rb else b[-1]
    f_ter = fr if rb else ft
    bawah_huruf = (yy - lhr if rb else y - lh) + f_ter.getbbox("H")[3]  # garis dasar huruf (tanpa ekor p/g)
    d.rectangle([X - 30, atas_huruf, X - 26, bawah_huruf], fill=K.ORANYE)
    # empat titik
    cy = H - 212; r = 7; jar = 26; cx0 = W // 2 - 1.5 * jar
    for k in range(4):
        d.ellipse([cx0 + k * jar - r, cy - r, cx0 + k * jar + r, cy + r], fill=K.PUTIH)
    # pil toska www.cekricek.id + ikon hati dalam lingkaran oranye
    TOSKA = (23, 196, 200)
    fp = K.font("bold", 30)
    teks = "www.cekricek.id"
    tw = d.textlength(teks, font=fp)
    ph = 86; pw = int(tw + 64 + 86)
    px = (W - pw) // 2; py = H - 180
    d.rounded_rectangle([px, py, px + pw, py + ph], ph // 2, fill=TOSKA)
    d.text((px + 34, py + (ph - 36) // 2), teks, font=fp, fill=K.PUTIH)
    ccx = px + pw - 52; ccy = py + ph // 2; cr = 29
    d.ellipse([ccx - cr, ccy - cr, ccx + cr, ccy + cr], fill=K.ORANYE)
    _lup(d, ccx, ccy, 11, K.PUTIH)
    if o.get("kredit"):
        fk = K.font("light", 18)
        d.text((W - TEPI - d.textlength(o["kredit"], font=fk), H - 48), o["kredit"], font=fk, fill=(150, 168, 184))
    return im


def _lup(d, cx, cy, r, warna):
    """Ikon kaca pembesar (lup, lambang pencarian): cincin + gagang miring ke kanan bawah."""
    ox, oy = cx - 3, cy - 3
    d.ellipse([ox - r, oy - r, ox + r, oy + r], outline=warna, width=5)
    d.line([(ox + r * 0.72, oy + r * 0.72), (cx + 11, cy + 11)], fill=warna, width=6)


TEMPLAT["tiktok"] = tiktok


if __name__ == "__main__":
    o = json.load(open(sys.argv[1], encoding="utf-8"))
    print(buat(o, sys.argv[2]))
