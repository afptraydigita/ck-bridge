#!/usr/bin/env python3
"""Reels Cekricek.id — video vertikal 1080x1920, 24 fps: teks bergerak di atas foto artikel
(atau latar biru malam bila tanpa foto) + musik bebas hak cipta.

Pakai:
  python3 reels_teks.py naskah.json keluar.mp4
naskah.json:
  {"rubrik": "Rona", "gaya": "feature",            # feature = serif Lora, berita = Poppins
   "judul": "Orang Rimba di Jambi Sudah Mengenal *Satu Tuhan* Sebelum Berislam",   # layar penutup
   "foto": "foto/279173.webp", "fokus": 0.5, "kredit": "Foto: .../Wikimedia Commons",  # foto bawaan
   "adegan": [                                     # tiap adegan BOLEH punya foto sendiri (ketentuan AFP 16 Okt 2026:
      {"jenis": "kail",    "teks": "...", "detik": 5, "foto": "foto/a.webp", "fokus": 0.4, "kredit": "Foto: ..."},
      {"jenis": "fakta",   "teks": "...", "sorot": "Alah Ta'ala", "foto": "foto/b.webp", "kredit": "Foto: ..."},
      {"jenis": "kutipan", "teks": "...", "oleh": "Temenggung Pemubar"},
      {"jenis": "angka",   "teks": "2", "sub": "nabi yang dikenal Orang Rimba"},
      {"jenis": "penutup", "teks": "Selengkapnya di cekricek.id"}
   ],
   "musik": "aset/musik/namafile.mp3"   # WAJIB dari Facebook Sound Collection (aturan AFP 16 Okt 2026); kosong = tanpa audio
  }
Durasi tiap adegan dihitung dari panjang teks (3,5–7,5 detik) bila "detik" tidak diisi.
Teks muncul baris demi baris, selalu terbaca tanpa suara.

KETENTUAN DESAIN AFP 16 Okt 2026 (18.59), mengikat:
  1. kredit foto di PALING BAWAH frame, sebelah kanan;
  2. teks TIDAK di tengah frame — ditempatkan di sepertiga bawah supaya foto tetap bisa dinikmati;
  3. foto BUKAN cuma satu: beberapa foto bergantian per adegan, tiap foto wajib bersesuaian dengan narasi adegannya;
  4. isi dan desain wajib menarik penonton.
"""
import json, os, shutil, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageChops
import ckfb as K

W, H, FPS = 1080, 1920, 24
TEPI = 84
AMAN_ATAS = 290       # ruang untuk nama Halaman di aplikasi
AMAN_BAWAH = 540      # ruang untuk caption dan tombol di aplikasi


def _durasi(a):
    if a.get("detik"):
        return float(a["detik"])
    n = len(a.get("teks", "").split())
    return max(3.5, min(7.5, 2.4 + n * 0.3))


def _ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


# ------------------------------------------------------------- latar
_LATAR = {}


def _latar_foto(path, fokus):
    if (path, fokus) not in _LATAR:
        penuh = K.foto_pas(path, W, H, fokus)
        # lebih terang daripada versi lama (0.62): foto harus bisa dinikmati (ketentuan AFP 16 Okt 2026)
        _LATAR[(path, fokus)] = K.vignette(K.hangatkan(penuh, 1.05), 0.35)
    return _LATAR[(path, fokus)]


def _latar_malam():
    if "malam" not in _LATAR:
        im = K.gradasi(W, H, K.MALAM, (16, 40, 62))
        glow = Image.new("RGB", (W, H), (0, 0, 0))
        ImageDraw.Draw(glow).ellipse([W - 700, -500, W + 400, 600], fill=(100, 48, 0))
        glow = glow.filter(K.ImageFilter.GaussianBlur(220))
        _LATAR["malam"] = ImageChops.add(im, glow)
    return _LATAR["malam"]


def _foto_adegan(a, naskah):
    """Foto adegan: milik adegan sendiri bila ada, kalau tidak foto bawaan naskah."""
    foto = a.get("foto") or naskah.get("foto")
    fokus = a.get("fokus", naskah.get("fokus", 0.5)) if a.get("foto") else naskah.get("fokus", 0.5)
    kredit = a.get("kredit") if a.get("foto") else naskah.get("kredit")
    if a.get("foto") and not a.get("kredit"):
        kredit = naskah.get("kredit")
    return foto, fokus, kredit


def _frame_dasar(t_global, total, naskah, a=None, u_adegan=0.0, sebelumnya=None):
    """Latar satu frame. Ken Burns berjalan per adegan (u_adegan 0..1); 0,5 detik pertama adegan
    melebur dari foto adegan sebelumnya (sebelumnya = gambar latar terakhir adegan lalu)."""
    foto, fokus, kredit = _foto_adegan(a or {}, naskah)
    if foto:
        arah = (0.5, 0.35) if (a or {}).get("jenis") == "kail" else (0.5, 0.5)
        im = K.ken_burns(_latar_foto(foto, fokus), u_adegan, 1.10, arah)
    else:
        im = K.ken_burns(_latar_malam(), u_adegan, 1.04)
    if sebelumnya is not None and u_adegan * (a or {}).get("_dur", 1) < 0.5:
        campur = _ease(u_adegan * (a or {}).get("_dur", 1) / 0.5)
        im = Image.blend(sebelumnya, im, campur)
    latar_bersih = im.copy()
    # gradasi hanya sepertiga bawah (tempat teks) + tipis di atas untuk logo; tengah frame dibiarkan bersih
    K.gradasi_bawah(im, 900, H - 900, K.MALAM, kurva=0.5, puncak=238)
    K.gradasi_atas(im, 240, K.MALAM, 150)
    d = ImageDraw.Draw(im, "RGBA")
    lg = K.wordmark(54, "putih")
    im.paste(lg, (TEPI - 4, AMAN_ATAS - 130), lg)
    # label rubrik DIHAPUS (koreksi AFP 16 Okt 2026, 18.37: berlaku untuk semua konten FB dan IG)
    u = t_global / max(1e-6, total)
    d.rectangle([TEPI, AMAN_ATAS - 44, W - TEPI, AMAN_ATAS - 41], fill=(255, 255, 255, 50))
    d.rectangle([TEPI, AMAN_ATAS - 44, TEPI + (W - 2 * TEPI) * u, AMAN_ATAS - 41], fill=K.ORANYE)
    if foto and kredit:
        # ketentuan AFP 16 Okt 2026: kredit di PALING BAWAH frame, sebelah kanan
        fk = K.font("light", 19)
        d.text((W - TEPI - d.textlength(kredit, font=fk), H - 50), kredit, font=fk, fill=(200, 210, 220, 210))
    im._latar_bersih = latar_bersih
    return im


# ------------------------------------------------------------- adegan
def _toks(a):
    teks = a["teks"]
    if a.get("sorot") and a["sorot"] in teks:
        teks = teks.replace(a["sorot"], "*" + a["sorot"] + "*", 1)
    return K.tokens(teks)


def _gambar_adegan(a, u, im, naskah):
    """u 0..1 = kemajuan adegan. Baris muncul satu per satu (0,18 s per baris), semua memudar di ujung."""
    d = ImageDraw.Draw(im, "RGBA")
    gaya = naskah.get("gaya", "feature")
    jenis = a.get("jenis", "fakta")
    dur = a["_dur"]
    t = u * dur
    fade_out = _ease((dur - t) / 0.5)
    maxw = W - 2 * TEPI
    # ketentuan AFP 16 Okt 2026: teks di sepertiga bawah, bukan tengah frame; batas bawah di atas zona UI aplikasi
    atas, bawah = H - AMAN_BAWAH - 40 - 700, H - AMAN_BAWAH - 40

    if jenis == "angka":
        fa = K.serif("bold", 320) if gaya == "feature" else K.font("bold", 300)
        masuk = _ease(t / 0.6)
        al = int(255 * min(masuk, fade_out))
        tw = d.textlength(a["teks"], font=fa)
        fs = K.font("medium", 44)
        nsub = len(K.bungkus_teks(d, a.get("sub", ""), fs, maxw - 80))
        y = bawah - 400 - nsub * 58 - 20 + int(30 * (1 - masuk))
        d.text((TEPI, y), a["teks"], font=fa, fill=K.ORANYE + (al,))
        al2 = int(255 * min(_ease((t - 0.5) / 0.6), fade_out))
        yy = y + 400
        for s in K.bungkus_teks(d, a.get("sub", ""), fs, maxw - 80):
            d.text((TEPI, yy), s, font=fs, fill=K.PUTIH + (al2,)); yy += 58
        return

    if jenis == "penutup":
        toks = K.tokens(naskah.get("judul", ""))
        if gaya == "feature":
            ft, ft2, b, sz = K.pas(d, toks, maxw, 5, 70, 44, "serif", "bold", "bolditalic")
        else:
            ft, ft2, b, sz = K.pas(d, toks, maxw, 5, 66, 42, "sans", "bold", None)
        lh = int(sz * 1.18)
        masuk = _ease(t / 0.6)
        al = int(255 * min(masuk, fade_out))
        tinggi = len(b) * lh + 150
        y = bawah - tinggi + int(30 * (1 - masuk))
        d.rectangle([TEPI, y - 30, TEPI + 72, y - 24], fill=K.ORANYE + (al,))
        K.tulis(d, b, ft, TEPI, y, lh, K.PUTIH, K.ORANYE, ft2, alpha=al)
        y += len(b) * lh + 44
        al2 = int(255 * min(_ease((t - 0.6) / 0.5), fade_out))
        fb = K.font("bold", 32)
        teks = a.get("teks", "Selengkapnya di cekricek.id")
        tw = d.textlength(teks, font=fb)
        d.rounded_rectangle([TEPI, y, TEPI + tw + 72, y + 82], 41, fill=K.ORANYE + (al2,))
        d.text((TEPI + 36, y + 20), teks, font=fb, fill=K.MALAM + (al2,))
        return

    toks = _toks(a)
    if gaya == "feature":
        besar = 84 if jenis == "kail" else 66
        w, w2 = ("italic", "bolditalic") if jenis == "kutipan" else ("bold", "bolditalic")
        ft, ft2, b, sz = K.pas(d, toks, maxw, 7, besar, 44, "serif", w, w2)
        lh = int(sz * 1.2)
    else:
        besar = 80 if jenis == "kail" else 64
        ft, ft2, b, sz = K.pas(d, toks, maxw, 7, besar, 42, "sans", "bold", None)
        lh = int(sz * 1.22)
    ekstra = 120 if jenis == "kutipan" else 0
    tinggi = len(b) * lh + ekstra + (60 if a.get("oleh") else 0)
    y = max(atas, bawah - tinggi)
    if jenis == "kutipan":
        fq = K.serif("bold", 220)
        al = int(255 * min(_ease(t / 0.4), fade_out))
        d.text((TEPI - 10, y - 60), "“", font=fq, fill=K.ORANYE + (al,))
        y += ekstra
    elif jenis == "kail":
        al = int(255 * min(_ease(t / 0.4), fade_out))
        d.rectangle([TEPI, y - 34, TEPI + 72, y - 28], fill=K.ORANYE + (al,))
    spasi = d.textlength(" ", font=ft)
    for i, baris in enumerate(b):
        masuk = _ease((t - 0.15 - i * 0.18) / 0.45)
        if masuk <= 0:
            continue
        al = int(255 * min(masuk, fade_out))
        geser = int(22 * (1 - masuk))
        cx = TEPI
        for kata, s, wd in baris:
            warna = (K.KUNING if jenis == "kutipan" else K.ORANYE) if s else K.PUTIH
            d.text((cx, y + i * lh + geser), kata, font=(ft2 if (s and ft2) else ft), fill=warna + (al,))
            cx += wd + spasi
    if a.get("oleh"):
        al = int(255 * min(_ease((t - 0.3 - len(b) * 0.18) / 0.5), fade_out))
        fo = K.font("regular", 32)
        d.text((TEPI, y + len(b) * lh + 26), "— " + a["oleh"], font=fo, fill=K.ABU + (al,))


# ------------------------------------------------------------- musik
def musik_sintetis(detik, keluar, sr=44100):
    """Pad instrumental lembut buatan sendiri (bebas hak cipta): empat akor bergantian tiap 4 detik,
    nada rendah, volume kecil. Lapisan supaya Reels tidak sunyi, bukan pengganti musik sungguhan."""
    t = np.linspace(0, detik, int(sr * detik), endpoint=False)
    akor = [[220.0, 261.63, 329.63], [174.61, 220.0, 261.63], [196.0, 246.94, 293.66], [164.81, 196.0, 246.94]]
    sinyal = np.zeros_like(t)
    panjang = 4.0
    for i, ta in enumerate(np.arange(0, detik, panjang)):
        n = akor[i % 4]
        mask = (t >= ta) & (t < ta + panjang)
        tt = t[mask] - ta
        env = np.minimum(1, tt / 0.9) * np.minimum(1, (panjang - tt) / 1.3)
        suara = np.zeros_like(tt)
        for f in n:
            suara += 0.5 * np.sin(2 * np.pi * f * tt) + 0.16 * np.sin(2 * np.pi * f * 2 * tt + 0.3) \
                     + 0.10 * np.sin(2 * np.pi * (f * 1.004) * tt)
        sinyal[mask] += suara * env
    sinyal *= (1 + 0.02 * np.sin(2 * np.pi * 0.25 * t))
    sinyal *= np.minimum(1, t / 1.5) * np.minimum(1, (detik - t) / 2.5)
    sinyal /= max(1e-6, np.abs(sinyal).max())
    sinyal *= 0.2
    raw = keluar + ".pcm"
    (sinyal * 32767).astype(np.int16).tofile(raw)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "s16le", "-ar", str(sr), "-ac", "1", "-i", raw,
                    "-af", "lowpass=f=1800", keluar], check=True)
    os.remove(raw)
    return keluar


# ------------------------------------------------------------- rakit
def buat(naskah, keluar):
    adegan = list(naskah["adegan"])
    for f in [naskah.get("foto")] + [a.get("foto") for a in adegan]:
        if f and not os.path.exists(f):
            raise SystemExit(f"foto tidak ditemukan: {f}")
    foto_unik = {a.get("foto") or naskah.get("foto") for a in adegan} - {None}
    if len(foto_unik) < 2 and len(adegan) > 2:
        sys.stderr.write("PERINGATAN: hanya satu foto untuk seluruh Reels; ketentuan AFP 16 Okt 2026 minta beberapa foto bergantian yang sesuai narasi.\n")
    for a in adegan:
        a["_dur"] = _durasi(a)
    total = sum(a["_dur"] for a in adegan)
    tmp = tempfile.mkdtemp(prefix="reels_")
    n, t_mulai = 0, 0.0
    sebelumnya = None
    for a in adegan:
        nf = int(round(a["_dur"] * FPS))
        terakhir = None
        for i in range(nf):
            ua = i / max(1, nf - 1)
            im = _frame_dasar(t_mulai + i / FPS, total, naskah, a, ua, sebelumnya)
            terakhir = im._latar_bersih
            _gambar_adegan(a, ua, im, naskah)
            im.save(os.path.join(tmp, f"{n:05d}.jpg"), quality=92)
            n += 1
        sebelumnya = terakhir
        t_mulai += a["_dur"]
    # ATURAN AFP 16 Okt 2026 (tidak boleh dilanggar): audio Reels HANYA dari Facebook Sound Collection
    # (facebook.com/sound/collection), berkas di aset/musik/ dengan catatan di aset/musik/LISENSI.txt.
    # Pad sintetis tidak dipakai lagi; tanpa berkas musik yang sah, Reels dibuat TANPA audio.
    musik = naskah.get("musik")
    if musik and os.path.exists(musik):
        audio, af = musik, ["-af", f"afade=t=in:d=1,afade=t=out:st={max(0, total - 2.5)}:d=2.5,volume=0.5"]
    else:
        sys.stderr.write("PERINGATAN: tidak ada berkas musik Sound Collection; Reels dirender TANPA audio.\n")
        audio, af = os.path.join(tmp, "senyap.wav"), []
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo",
                        "-t", f"{total:.2f}", audio], check=True)
    cmd = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(tmp, "%05d.jpg"),
           "-i", audio, *af, "-t", f"{total:.2f}", "-shortest",
           "-vf", "noise=alls=3:allf=t",
           "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high", "-crf", "24", "-preset", "slow", "-r", str(FPS),
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", keluar]
    subprocess.run(cmd, check=True)
    shutil.rmtree(tmp, ignore_errors=True)
    return keluar, total, n


if __name__ == "__main__":
    naskah = json.load(open(sys.argv[1], encoding="utf-8"))
    k, total, n = buat(naskah, sys.argv[2])
    print(f"{k}  {total:.1f} detik  {n} frame")
