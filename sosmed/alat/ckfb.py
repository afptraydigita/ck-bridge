#!/usr/bin/env python3
"""Pustaka bersama kartu dan Reels Facebook Cekricek.id.

Karakter visual (ketetapan 15 Okt 2026): editorial hangat. Latar biru malam, aksen oranye merek,
judul feature (Rona/Nuansa/Sains) berhuruf serif Lora, judul berita berhuruf Poppins.
Foto alami dengan vignette halus dan butir film tipis. Logo resmi dari aset/.

Berjalan di peti kerja Claude maupun di komputer AFP (Linux VM Cowork).
"""
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import os, re, random

TEAL   = (0, 192, 204)
ORANYE = (252, 144, 0)
KUNING = (252, 192, 12)
GELAP  = (13, 26, 38)
MALAM  = (9, 18, 28)
PUTIH  = (255, 255, 255)
ABU    = (190, 205, 218)
KRIM   = (246, 241, 232)

_ASET = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "aset")
_FONT_DIRS = [os.path.join(_ASET, "font"), "/usr/share/fonts/truetype/google-fonts", os.path.expanduser("~/.fonts")]
_SANS = {"bold": "Poppins-Bold.ttf", "medium": "Poppins-Medium.ttf", "regular": "Poppins-Regular.ttf",
         "light": "Poppins-Light.ttf", "italic": "Poppins-Italic.ttf"}
_SERIF = {"bold": ("Lora-Variable.ttf", "Bold"), "semibold": ("Lora-Variable.ttf", "SemiBold"),
          "regular": ("Lora-Variable.ttf", "Regular"), "italic": ("Lora-Italic-Variable.ttf", "Italic"),
          "bolditalic": ("Lora-Italic-Variable.ttf", "Bold Italic")}
_LOGO = {"putih": os.path.join(_ASET, "logo-cekricek-putih.png"),
         "gelap": os.path.join(_ASET, "logo-cekricek-gelap.png"),
         "tanda": os.path.join(_ASET, "logo-cekricek-tanda.png")}


def _cari(nama):
    for d in _FONT_DIRS:
        p = os.path.join(d, nama)
        if os.path.exists(p):
            return p
    return None


def font(w, size):
    """Poppins (sans)."""
    p = _cari(_SANS[w])
    return ImageFont.truetype(p, size) if p else ImageFont.load_default(size)


def serif(w, size):
    """Lora (serif) untuk judul feature. Jatuh ke Poppins bila Lora tidak ada."""
    nama, var = _SERIF[w]
    p = _cari(nama)
    if not p:
        return font("bold" if "bold" in w else "regular", size)
    f = ImageFont.truetype(p, size)
    try:
        f.set_variation_by_name(var)
    except Exception:
        pass
    return f


def wordmark(tinggi, varian="putih"):
    p = _LOGO.get(varian)
    if p and os.path.exists(p):
        im = Image.open(p).convert("RGBA")
        r = tinggi / im.size[1]
        return im.resize((int(im.size[0] * r), tinggi), Image.LANCZOS)
    ft = font("bold", int(tinggi * 0.92))
    tmp = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
    w1 = tmp.textlength("Cekricek", font=ft); w2 = tmp.textlength(".id", font=ft)
    im = Image.new("RGBA", (int(w1 + w2) + 4, int(tinggi * 1.3)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.text((0, 0), "Cekricek", font=ft, fill=PUTIH if varian == "putih" else GELAP)
    d.text((w1, 0), ".id", font=ft, fill=ORANYE)
    return im


# ------------------------------------------------------------------ teks
def tokens(teks):
    """'kata *disorot dua* kata' -> [(kata, disorot)]"""
    out, sorot = [], False
    for kata in teks.split():
        n = kata
        if n.startswith("*"):
            sorot = True; n = n[1:]
        akhir = "*" in n
        if akhir:
            n = n.replace("*", "")
        out.append((n, sorot))
        if akhir:
            sorot = False
    return out


def bungkus(d, toks, ft, maxw, ft2=None):
    """ft2 = font untuk kata disorot (mis. italic) bila berbeda."""
    baris, kini, lebar = [], [], 0
    spasi = d.textlength(" ", font=ft)
    for kata, s in toks:
        w = d.textlength(kata, font=(ft2 if (s and ft2) else ft))
        if kini and lebar + spasi + w > maxw:
            baris.append(kini); kini, lebar = [], 0
        kini.append((kata, s, w))
        lebar += (spasi if len(kini) > 1 else 0) + w
    if kini:
        baris.append(kini)
    return baris


def pas(d, toks, maxw, maxbaris, besar, kecil, keluarga="sans", w="bold", w2=None):
    """Turunkan ukuran sampai muat. keluarga 'sans' atau 'serif'; w2 = varian kata disorot."""
    mk = font if keluarga == "sans" else serif
    for size in range(besar, kecil - 1, -2):
        ft = mk(w, size); ft2 = mk(w2, size) if w2 else None
        b = bungkus(d, toks, ft, maxw, ft2)
        if len(b) <= maxbaris:
            return ft, ft2, b, size
    ft = mk(w, kecil); ft2 = mk(w2, kecil) if w2 else None
    return ft, ft2, bungkus(d, toks, ft, maxw, ft2), kecil


def tulis(d, baris, ft, x, y, lh, biasa, sorot, ft2=None, rata="kiri", maxw=None, alpha=255, maks_baris=None):
    spasi = d.textlength(" ", font=ft)
    for i, b in enumerate(baris):
        if maks_baris is not None and i >= maks_baris:
            break
        lebar = sum(w for _, _, w in b) + spasi * (len(b) - 1)
        cx = x if rata == "kiri" else x + (maxw - lebar) / 2
        for kata, s, w in b:
            warna = sorot if s else biasa
            d.text((cx, y), kata, font=(ft2 if (s and ft2) else ft), fill=warna + (alpha,))
            cx += w + spasi
        y += lh
    return y


def bungkus_teks(d, teks, ft, maxw):
    """Bungkus kalimat biasa berdasarkan lebar piksel, bukan jumlah karakter."""
    baris, kini = [], ""
    for kata in teks.split():
        uji = (kini + " " + kata).strip()
        if kini and d.textlength(uji, font=ft) > maxw:
            baris.append(kini); kini = kata
        else:
            kini = uji
    if kini:
        baris.append(kini)
    return baris


def bersih(teks):
    teks = re.sub(r"<[^>]+>", "", teks)
    for a, b in {"&#8217;": "’", "&#8216;": "‘", "&#8220;": "“", "&#8221;": "”",
                 "&#8212;": "—", "&#8211;": "–", "&amp;": "&", "&nbsp;": " "}.items():
        teks = teks.replace(a, b)
    return teks.strip()


# ------------------------------------------------------------------ latar dan foto
def gradasi(w, h, atas=GELAP, bawah=(22, 48, 70)):
    im = Image.new("RGB", (w, h), atas)
    d = ImageDraw.Draw(im)
    for y in range(h):
        t = y / max(1, h - 1)
        d.line([(0, y), (w, y)], fill=tuple(int(atas[i] + (bawah[i] - atas[i]) * t) for i in range(3)))
    return im


def butir(im, kuat=6, benih=7):
    """Butir film tipis supaya bidang warna rata tidak terasa plastik."""
    import numpy as np
    rng = np.random.default_rng(benih)
    a = np.asarray(im.convert("RGB")).astype("int16")
    n = rng.integers(-kuat, kuat + 1, size=a.shape[:2], dtype="int16")[..., None]
    return Image.fromarray(np.clip(a + n, 0, 255).astype("uint8"))


def vignette(im, kuat=0.45):
    w, h = im.size
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.ellipse([-w * 0.25, -h * 0.25, w * 1.25, h * 1.25], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(int(min(w, h) * 0.25)))
    gelap = Image.new("RGB", (w, h), (0, 0, 0))
    hasil = Image.composite(im, gelap, mask)
    return Image.blend(im, hasil, kuat)


def foto_pas(path, tw, th, fokus=0.5):
    """Krop 'cover' ke tw x th. fokus 0..1 = titik potong vertikal (0 atas, 1 bawah)."""
    im = Image.open(path).convert("RGB")
    r = max(tw / im.size[0], th / im.size[1])
    im = im.resize((max(tw, int(round(im.size[0] * r))), max(th, int(round(im.size[1] * r)))), Image.LANCZOS)
    x = (im.size[0] - tw) // 2
    y = int((im.size[1] - th) * fokus)
    return im.crop((x, y, x + tw, y + th))


def ken_burns(im, u, zoom=1.08, arah=(0.5, 0.5)):
    """Perbesar perlahan: u 0..1 -> skala 1..zoom; arah = titik pusat pembesaran."""
    w, h = im.size
    s = 1 + (zoom - 1) * u
    big = im.resize((int(w * s), int(h * s)), Image.BILINEAR)
    x = int((big.size[0] - w) * arah[0]); y = int((big.size[1] - h) * arah[1])
    return big.crop((x, y, x + w, y + h))


def gelapkan(im, faktor=0.45):
    return ImageEnhance.Brightness(im).enhance(faktor)


def hangatkan(im, faktor=1.08):
    """Sedikit menghangatkan foto supaya senada dengan oranye merek."""
    r, g, b = im.split()
    r = r.point(lambda v: min(255, int(v * faktor)))
    b = b.point(lambda v: int(v * (2 - faktor)))
    return Image.merge("RGB", (r, g, b))


def kabur(im, radius=28):
    return im.filter(ImageFilter.GaussianBlur(radius))


def gradasi_bawah(im, tinggi, dari, warna, kurva=1.4, puncak=255):
    """Gradasi transparan -> warna di bagian bawah area, dimulai pada baris `dari`."""
    w = im.size[0]
    ov = Image.new("RGBA", (w, tinggi), warna + (0,))
    d = ImageDraw.Draw(ov)
    for i in range(tinggi):
        t = i / max(1, tinggi - 1)
        d.line([(0, i), (w, i)], fill=warna + (int(puncak * (t ** kurva)),))
    potongan = im.crop((0, dari, w, dari + tinggi)).convert("RGBA")
    im.paste(Image.alpha_composite(potongan, ov).convert("RGB"), (0, dari))
    return im


def gradasi_atas(im, tinggi, warna, puncak=170):
    w = im.size[0]
    ov = Image.new("RGBA", (w, tinggi), warna + (0,))
    d = ImageDraw.Draw(ov)
    for i in range(tinggi):
        t = 1 - i / max(1, tinggi - 1)
        d.line([(0, i), (w, i)], fill=warna + (int(puncak * (t ** 1.3)),))
    potongan = im.crop((0, 0, w, tinggi)).convert("RGBA")
    im.paste(Image.alpha_composite(potongan, ov).convert("RGB"), (0, 0))
    return im


def label(d, x, y, teks, bg, fg, ukuran=21):
    """Pil rubrik kecil, huruf kapital berjarak."""
    ft = font("bold", ukuran)
    t = " ".join(teks.upper())  # jarak antarhuruf
    tw = d.textlength(t, font=ft)
    d.rounded_rectangle([x, y, x + tw + 36, y + ukuran * 2], ukuran, fill=bg)
    d.text((x + 18, y + ukuran * 0.42), t, font=ft, fill=fg)
    return tw + 36
