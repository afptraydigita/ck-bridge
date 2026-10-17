#!/usr/bin/env python3
"""Reels Cekricek.id dengan SUARA NEWS ANCHOR (rekaman suara AFP) — 1080x1920, 30 fps.

Permintaan AFP 17 Okt 2026: Reels tidak sekadar ketikan tulisan, tetapi dibacakan news anchor.
Suara = rekaman AFP sendiri (WhatsApp/HP). Alat ini:
  1. membersihkan tiap rekaman (potong hening awal/akhir, buang dengung rendah, rapikan dinamika);
  2. bila satu rekaman berisi PENGULANGAN (salah baca lalu diulang), ruas "potong" [[mulai, akhir], ...] dipakai
     untuk menyimpan potongan yang benar saja (detik, menurut transkrip kata);
  3. mentranskrip kata per kata (whisper.cpp) lalu MENYELARASKAN dengan naskah resmi, supaya teks layar
     selalu ejaan naskah (bukan salah dengar mesin) dan muncul tepat saat kata diucapkan (gaya karaoke);
  4. menyusun foto bergantian per bagian (Ken Burns tajam, silang 0,4 detik), kartu angka, logo,
     indikator suara, kredit foto di paling bawah kanan, dan kartu penutup;
  5. musik WAJIB dari Facebook Sound Collection (aset/musik/), diredam di bawah suara (ducking).

Pakai:  python3 reels_anchor.py naskah.json keluar.mp4 [--model ggml-small-q5_1.bin]
naskah.json:
 {"judul": "Anak Muda Suku *Duano* di Jambi Malu Memakai Bahasa Leluhurnya",
  "kicker": "Bahasa Duano · Jambi", "rubrik": "Rona",
  "musik": "../aset/musik/fall.m4a", "jeda": 0.35,
  "bagian": [
    {"audio": "r4.mp4", "teks": "Di pesisir Jambi, ...", "foto": "a.jpg", "fokus": [0.5, 0.5],
     "kredit": "Foto: X/Wikimedia Commons (CC BY-SA 4.0)", "zoom": 1.10,
     "potong": [[0.0, 3.2], [5.1, 9.0]],                                   # opsional
     "angka": [{"teks": "178", "sub": "dari 200 kata dasar sudah berubah", "tempat": "Sabak", "mulai_kata": 12}]},
    ...
    {"audio": "r6.mp4", "teks": "Kisah lengkapnya, baca di cekricek.id.", "penutup": true, "foto": ...}
  ]}
"""
import difflib, json, os, re, subprocess, sys, tempfile, shutil
from multiprocessing import Pool
import numpy as np
from PIL import Image, ImageDraw, ImageFilter
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ckfb as K

W, H, FPS = 1080, 1920, 30
SR = 48000
TEPI = 84
AMAN_ATAS = 290
AMAN_BAWAH = 540
SKALA = 1.25


def _ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def sh(*a):
    subprocess.run(a, check=True)


# ------------------------------------------------------------------ audio
def bersihkan(src, dst, potong=None):
    """Rekaman -> wav mono 48 kHz bersih. potong = daftar [mulai, akhir] (detik pada rekaman asli)."""
    tmp = dst + ".mentah.wav"
    sh("ffmpeg", "-y", "-loglevel", "error", "-i", src, "-ac", "1", "-ar", str(SR), tmp)
    if potong:
        parts = []
        for i, (a, b) in enumerate(potong):
            p = f"{dst}.p{i}.wav"
            sh("ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-ss", f"{a}", "-to", f"{b}",
               "-af", "afade=t=in:d=0.02,areverse,afade=t=in:d=0.04,areverse", p)
            parts.append(p)
        lst = dst + ".lst"
        open(lst, "w").write("".join(f"file '{os.path.abspath(p)}'\n" for p in parts))
        sh("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, tmp + "2.wav")
        os.replace(tmp + "2.wav", tmp)
    af = ("silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05,"
          "areverse,silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.12,areverse,"
          "highpass=f=75,lowpass=f=15000,"
          "equalizer=f=220:t=q:w=1.2:g=-1.5,equalizer=f=3500:t=q:w=1.0:g=2,"
          "acompressor=threshold=-20dB:ratio=2.5:attack=8:release=120:makeup=2,"
          "afade=t=in:d=0.03")
    sh("ffmpeg", "-y", "-loglevel", "error", "-i", tmp, "-af", af, "-ar", str(SR), dst)
    os.remove(tmp)
    return float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                          "-of", "csv=p=0", dst]).decode())


_MODEL = None


def transkrip(wav, model):
    global _MODEL
    from pywhispercpp.model import Model
    if _MODEL is None:
        _MODEL = Model(model, n_threads=os.cpu_count() or 4, print_progress=False, print_realtime=False)
    w16 = wav + ".16k.wav"
    sh("ffmpeg", "-y", "-loglevel", "error", "-i", wav, "-ar", "16000", w16)
    segs = _MODEL.transcribe(w16, language="id", token_timestamps=True, max_len=1, split_on_word=True)
    out = [(s.t0 / 100, s.t1 / 100, s.text.strip()) for s in segs if s.text.strip()]
    os.remove(w16)
    return out


def _norm(k):
    k = k.lower()
    k = re.sub(r"[^a-z0-9]", "", k)
    return k


_ANGKA = {"0": "nol", "1": "satu", "2": "dua", "3": "tiga", "4": "empat", "5": "lima", "6": "enam", "7": "tujuh",
          "8": "delapan", "9": "sembilan", "10": "sepuluh"}


def selaraskan(naskah_kata, asr):
    """Beri waktu [mulai, akhir] tiap kata naskah, dari kata ASR yang cocok; sisanya diinterpolasi."""
    a = [_norm(k) for k in naskah_kata]
    b = [_norm(_ANGKA.get(k, k)) for _, _, k in asr]
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    t = [None] * len(a)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for k in range(i2 - i1):
                t[i1 + k] = [asr[j1 + k][0], asr[j1 + k][1]]
        elif tag == "replace":
            # sebar rentang waktu kata ASR ke kata naskah secara proporsional
            t0, t1 = asr[j1][0], asr[j2 - 1][1]
            n = i2 - i1
            for k in range(n):
                t[i1 + k] = [t0 + (t1 - t0) * k / n, t0 + (t1 - t0) * (k + 1) / n]
    akhir = asr[-1][1] if asr else 1.0
    for i in range(len(t)):
        if t[i] is None:
            prev = t[i - 1][1] if i > 0 and t[i - 1] else 0.0
            j = i
            while j < len(t) and t[j] is None:
                j += 1
            nxt = t[j][0] if j < len(t) else akhir
            n = j - i
            for k in range(n):
                t[i + k] = [prev + (nxt - prev) * k / n, prev + (nxt - prev) * (k + 1) / n]
    for i in range(1, len(t)):  # monoton
        t[i][0] = max(t[i][0], t[i - 1][0])
    return t


def rms_amplop(wav):
    x = subprocess.check_output(["ffmpeg", "-loglevel", "error", "-i", wav, "-f", "s16le", "-ac", "1",
                                 "-ar", str(SR), "-"])
    s = np.frombuffer(x, np.int16).astype(np.float32) / 32768
    hop = SR // FPS
    n = len(s) // hop
    r = np.sqrt(np.mean(s[:n * hop].reshape(n, hop) ** 2, axis=1) + 1e-9)
    return np.clip((20 * np.log10(r) + 50) / 40, 0, 1)


# ------------------------------------------------------------------ gambar
_LATAR = {}


def latar(path, fokus):
    key = (path, tuple(fokus))
    if key not in _LATAR:
        im = Image.open(path).convert("RGB")
        tw, th = int(W * SKALA), int(H * SKALA)
        r = max(tw / im.size[0], th / im.size[1])
        if r > 1.0:
            sys.stderr.write(f"PERINGATAN: {path} {im.size} diperbesar {r:.2f}x — cari foto lebih besar.\n")
        im = im.resize((max(tw, round(im.size[0] * r)), max(th, round(im.size[1] * r))), Image.LANCZOS)
        x = int((im.size[0] - tw) * fokus[0]); y = int((im.size[1] - th) * fokus[1])
        im = im.crop((x, y, x + tw, y + th)).filter(ImageFilter.UnsharpMask(1.2, 40, 2))
        _LATAR[key] = K.vignette(K.hangatkan(im, 1.04), 0.30)
    return _LATAR[key]


def kb(im, u, zoom=1.10, arah=(0.5, 0.5)):
    w, h = im.size
    s = (w / W) / (1 + (zoom - 1) * u)
    cw, ch = W * s, H * s
    x0 = (w - cw) * arah[0]; y0 = (h - ch) * arah[1]
    return im.resize((W, H), Image.LANCZOS, box=(x0, y0, x0 + cw, y0 + ch))


_LAPIS = {}


def lapis_tetap():
    """Gradasi atas+bawah sekali hitung (RGBA)."""
    if "g" not in _LAPIS:
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        for y in range(520):
            d.line([(0, y), (W, y)], fill=K.MALAM + (int(185 * (1 - y / 520) ** 1.4),))
        top = 760
        for y in range(top, H):
            t = (y - top) / (H - top)
            d.line([(0, y), (W, y)], fill=K.MALAM + (int(235 * t ** 1.15),))
        _LAPIS["g"] = ov
        _LAPIS["logo"] = K.wordmark(54, "putih")
    return _LAPIS["g"], _LAPIS["logo"]


def potong_baris(kata, waktu, d, ft, maxw, maks_baris=2):
    """Pecah kata menjadi potongan teks layar (maks 2 baris), utamakan putus di tanda baca."""
    chunks, kini = [], []
    spasi = d.textlength(" ", font=ft)

    def muat(ks):
        baris, lebar = 1, 0
        for k in ks:
            w = d.textlength(k, font=ft)
            if lebar and lebar + spasi + w > maxw:
                baris += 1; lebar = w
            else:
                lebar += (spasi if lebar else 0) + w
        return baris <= maks_baris

    for i, k in enumerate(kata):
        if kini and not muat([kata[j] for j in kini] + [k]):
            # mundur ke tanda baca terakhir bila ada
            cut = None
            for m in range(len(kini) - 1, 0, -1):
                if re.search(r"[,.:;!?]$", kata[kini[m - 1]]):
                    cut = m; break
            if cut and cut >= len(kini) // 2:
                chunks.append(kini[:cut]); kini = kini[cut:]
            else:
                chunks.append(kini); kini = []
        kini.append(i)
        if re.search(r"[.!?]$", k) and len(kini) >= 3:
            chunks.append(kini); kini = []
    if kini:
        chunks.append(kini)
    return chunks


def susun_garis_waktu(naskah, kerja, model):
    t = 0.0
    jeda = naskah.get("jeda", 0.35)
    bag = naskah["bagian"]
    voice_list = []
    for i, b in enumerate(bag):
        wav = os.path.join(kerja, f"v{i}.wav")
        dur = bersihkan(b["audio"], wav, b.get("potong"))
        asr = transkrip(wav, model)
        kata = b["teks"].split()
        waktu = selaraskan(kata, asr)
        b.update(_wav=wav, _dur=dur, _mulai=t, _kata=kata, _waktu=[[t + a, t + c] for a, c in waktu], _asr=asr)
        voice_list.append(wav)
        t += dur + (jeda if i < len(bag) - 1 else 0)
    return t


def gambar_frame(args):
    fi, naskah, total_video, amplop, kerja = args
    t = fi / FPS
    bag = naskah["bagian"]
    # bagian aktif (visual)
    idx = 0
    for i, b in enumerate(bag):
        if t >= b["_mulai"] - 0.2:
            idx = i
    b = bag[idx]
    nxt_start = bag[idx + 1]["_mulai"] - 0.2 if idx + 1 < len(bag) else total_video
    s0 = b["_mulai"] - 0.2 if idx > 0 else 0.0
    u = (t - s0) / max(0.1, nxt_start - s0)
    im = kb(latar(b["foto"], b.get("fokus", [0.5, 0.5])), u, b.get("zoom", 1.10), tuple(b.get("arah", [0.5, 0.5])))
    if idx > 0 and t < b["_mulai"] + 0.2:  # silang 0,4 detik
        p = bag[idx - 1]
        ps = p["_mulai"] - 0.2 if idx - 1 > 0 else 0.0
        up = (t - ps) / max(0.1, b["_mulai"] - 0.2 - ps)
        prev = kb(latar(p["foto"], p.get("fokus", [0.5, 0.5])), min(up, 1.0), p.get("zoom", 1.10), tuple(p.get("arah", [0.5, 0.5])))
        im = Image.blend(prev, im, _ease((t - (b["_mulai"] - 0.2)) / 0.4))
    g, logo = lapis_tetap()
    im = im.convert("RGBA")
    im.alpha_composite(g)
    d = ImageDraw.Draw(im, "RGBA")

    # --- kepala: logo + indikator suara + kicker
    y0 = AMAN_ATAS - 150
    im.alpha_composite(logo, (TEPI, y0))
    lx = TEPI + logo.size[0] + 26
    a = amplop[min(fi, len(amplop) - 1)] if len(amplop) else 0
    for k, f in enumerate((0.55, 1.0, 0.75, 0.9)):
        hh = 8 + int(38 * a * f * (0.75 + 0.25 * np.sin(fi * 0.9 + k * 1.7)))
        cy = y0 + 27
        d.rounded_rectangle([lx + k * 13, cy - hh // 2, lx + k * 13 + 7, cy + hh // 2], 3, fill=K.ORANYE + (235,))
    fk = K.font("bold", 26)
    kick = " ".join(naskah.get("kicker", "").upper())
    d.text((TEPI, y0 + 78), kick, font=fk, fill=K.PUTIH + (215,))
    d.rectangle([TEPI, y0 + 122, TEPI + 64, y0 + 127], fill=K.ORANYE + (255,))

    bawah = H - AMAN_BAWAH - 30
    maxw = W - 2 * TEPI - 40

    # --- kartu angka
    for ag in b.get("angka", []):
        ts = b["_waktu"][ag.get("mulai_kata", 0)][0] - 0.15
        te = b["_mulai"] + b["_dur"] + 0.25
        if ts <= t <= te:
            m = _ease((t - ts) / 0.5); al = int(255 * min(m, _ease((te - t) / 0.3)))
            fa = K.font("extrabold", 250)
            ya = 610 + int(40 * (1 - m))
            # panel gelap di belakang kartu angka supaya terbaca di atas langit/foto terang
            fs0 = K.font("medium", 42)
            nsub = len(K.bungkus_teks(d, ag.get("sub", ""), fs0, maxw))
            d.rounded_rectangle([TEPI - 34, ya + 40, W - TEPI + 34, ya + 300 + nsub * 54 + 30], 28,
                                fill=K.MALAM + (int(al * 0.66),))
            d.text((TEPI - 8, ya), ag["teks"], font=fa, fill=K.ORANYE + (al,))
            wa = d.textlength(ag["teks"], font=fa)
            if ag.get("tempat"):
                K_lbl = K.font("bold", 30)
                tx = " ".join(ag["tempat"].upper())
                tw = d.textlength(tx, font=K_lbl)
                d.rounded_rectangle([TEPI + wa + 24, ya + 92, TEPI + wa + 24 + tw + 40, ya + 152], 30, fill=K.PUTIH + (al,))
                d.text((TEPI + wa + 44, ya + 101), tx, font=K_lbl, fill=K.MALAM + (al,))
            fs = K.font("medium", 42)
            yy = ya + 300
            for s in K.bungkus_teks(d, ag.get("sub", ""), fs, maxw):
                d.text((TEPI, yy), s, font=fs, fill=K.PUTIH + (al,)); yy += 54

    # --- teks layar karaoke
    if not b.get("penutup"):
        ft = K.font("bold", 64)
        lh = 82
        kata, waktu = b["_kata"], b["_waktu"]
        chunks = b.setdefault("_chunks", potong_baris(kata, waktu, d, ft, maxw))
        aktif = None
        for ci, ch in enumerate(chunks):
            cs = waktu[ch[0]][0] - 0.12
            ce = waktu[chunks[ci + 1][0]][0] - 0.12 if ci + 1 < len(chunks) else b["_mulai"] + b["_dur"] + 0.3
            if cs <= t < ce:
                aktif = (ch, cs, ce)
        if aktif:
            ch, cs, ce = aktif
            baris = K.bungkus(d, [(kata[i], False) for i in ch], ft, maxw)
            y = bawah - len(baris) * lh
            m = _ease((t - cs) / 0.25)
            k = 0
            spasi = d.textlength(" ", font=ft)
            for bi, br in enumerate(baris):
                cx = TEPI
                for (kt, _, w) in br:
                    i = ch[k]; k += 1
                    ws, we = waktu[i]
                    if t >= we:
                        warna, al = K.PUTIH, 255
                    elif t >= ws - 0.05:
                        warna, al = K.ORANYE, 255
                    else:
                        warna, al = K.PUTIH, 120
                    al = int(al * m)
                    yy = y + bi * lh + int(14 * (1 - m))
                    d.text((cx + 3, yy + 4), kt, font=ft, fill=(0, 0, 0, int(al * 0.55)))
                    d.text((cx, yy), kt, font=ft, fill=warna + (al,))
                    cx += w + spasi
    else:
        ts = b["_mulai"] - 0.1
        m = _ease((t - ts) / 0.6)
        al = int(255 * m)
        toks = K.tokens(naskah.get("judul", ""))
        ftj, ftj2, br, sz = K.pas(d, toks, maxw, 5, 70, 46, "serif", "bold", "bolditalic")
        lh = int(sz * 1.2)
        y = bawah - 120 - len(br) * lh + int(30 * (1 - m))
        d.rectangle([TEPI, y - 34, TEPI + 72, y - 28], fill=K.ORANYE + (al,))
        K.tulis(d, br, ftj, TEPI, y, lh, K.PUTIH, K.ORANYE, ftj2, alpha=al)
        al2 = int(255 * _ease((t - ts - 0.5) / 0.5))
        fb = K.font("bold", 34)
        teks = "Kisah lengkapnya di cekricek.id"
        tw = d.textlength(teks, font=fb)
        yb = y + len(br) * lh + 34
        d.rounded_rectangle([TEPI, yb, TEPI + tw + 76, yb + 84], 42, fill=K.ORANYE + (al2,))
        d.text((TEPI + 38, yb + 20), teks, font=fb, fill=K.MALAM + (al2,))

    # --- kredit foto: paling bawah, kanan (ketentuan AFP 16 Okt 2026)
    if b.get("kredit"):
        fc = K.font("regular", 22)
        tw = d.textlength(b["kredit"], font=fc)
        d.text((W - 40 - tw, H - 52), b["kredit"], font=fc, fill=K.PUTIH + (190,))
    im.convert("RGB").save(os.path.join(kerja, "f", f"{fi:05d}.jpg"), quality=97, subsampling=0)
    return fi


def buat(naskah, keluar, model):
    musik = naskah.get("musik")
    if not (musik and os.path.exists(musik)):
        sys.exit("GALAT: Reels wajib beraudio musik Sound Collection (ketetapan AFP 17 Okt 2026).")
    kerja = tempfile.mkdtemp(prefix="anchor_")
    os.makedirs(os.path.join(kerja, "f"))
    akhir_suara = susun_garis_waktu(naskah, kerja, model)
    ekor = naskah.get("ekor", 2.2)
    total = akhir_suara + ekor
    # suara utuh: tiap bagian ditempatkan pada _mulai
    ins, flt = [], []
    for i, b in enumerate(naskah["bagian"]):
        ins += ["-i", b["_wav"]]
        ms = int(round(b["_mulai"] * 1000))
        flt.append(f"[{i}:a]adelay={ms}|{ms}[d{i}]")
    n = len(naskah["bagian"])
    suara = os.path.join(kerja, "suara.wav")
    flt.append("".join(f"[d{i}]" for i in range(n)) + f"amix=inputs={n}:normalize=0,"
               f"loudnorm=I=-16:TP=-1.5:LRA=9,aresample={SR},apad=whole_dur={total:.3f}[o]")
    sh("ffmpeg", "-y", "-loglevel", "error", *ins, "-filter_complex", ";".join(flt), "-map", "[o]", "-ac", "1", suara)
    amplop = rms_amplop(suara)
    # transkrip + penyelarasan disimpan untuk diperiksa redaksi
    json.dump([{"teks": b["teks"], "asr": " ".join(k for _, _, k in b["_asr"]),
                "kata": [[k, round(w[0], 2), round(w[1], 2)] for k, w in zip(b["_kata"], b["_waktu"])]}
               for b in naskah["bagian"]], open(keluar + ".selaras.json", "w"), ensure_ascii=False, indent=1)
    nf = int(round(total * FPS))
    with Pool(os.cpu_count() or 4) as p:
        for _ in p.imap_unordered(gambar_frame, [(i, naskah, total, amplop, kerja) for i in range(nf)], chunksize=8):
            pass
    vol = naskah.get("musik_volume", 0.16)
    fc = (f"[1:a]aformat=sample_rates={SR}:channel_layouts=stereo,asplit=2[v][vk];"
          f"[2:a]aformat=sample_rates={SR}:channel_layouts=stereo,atrim=0:{total:.3f},asetpts=PTS-STARTPTS,volume={vol},"
          f"afade=t=in:d=1.2,afade=t=out:st={total - 2.0:.3f}:d=2.0[m];"
          f"[m][vk]sidechaincompress=threshold=0.03:ratio=6:attack=40:release=500[md];"
          f"[v][md]amix=inputs=2:normalize=0,alimiter=limit=0.95[a]")
    sh("ffmpeg", "-y", "-loglevel", "error", "-framerate", str(FPS), "-i", os.path.join(kerja, "f", "%05d.jpg"),
       "-i", suara, "-stream_loop", "-1", "-i", musik, "-filter_complex", fc, "-map", "0:v", "-map", "[a]",
       "-t", f"{total:.3f}", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-profile:v", "high", "-crf", "17",
       "-preset", "slow", "-tune", "film", "-maxrate", "16M", "-bufsize", "32M", "-r", str(FPS),
       "-c:a", "aac", "-b:a", "192k", "-ar", str(SR), "-movflags", "+faststart", keluar)
    shutil.rmtree(kerja, ignore_errors=True)
    return total, nf


if __name__ == "__main__":
    model = "ggml-small-q5_1.bin"
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]
    naskah = json.load(open(sys.argv[1], encoding="utf-8"))
    total, nf = buat(naskah, sys.argv[2], model)
    print(f"{sys.argv[2]}  {total:.1f} detik  {nf} frame")
