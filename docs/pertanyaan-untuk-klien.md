# Pertanyaan untuk Klien — Katalog Produk & Harga

Dokumen ini berisi semua hal yang **masih kami tebak sendiri** saat memasukkan
data katalog (`AS PER 11 August 2026 (1).xlsx`) dan price list Panel Glide
(`Price List Accent -Panelblinds-01 juni 2026.pdf`) ke dalam sistem. Mohon
konfirmasi dari klien sebelum data ini dianggap final, karena ini menentukan
harga yang akan muncul di setiap quotation.

---

## 1. Kategori produk mana pakai rumus yang mana?

Catatan rumus yang diberikan menyebut **ROLLER, WOOD, VERTIKAL, ROMAN,
ALUMINIUM**. Di sistem, kategori produknya adalah: Roller, Design Shades, All
Venetian, Curtain, Cellular Shade, Vertical Fabric. Kami memetakan sebagai
berikut, tapi ini **masih tebakan**:

- **Design Shades** (SHADOWLINE, DOLCE, SENSE) — kami anggap ini yang
  dimaksud "ROMAN" di rumus, jadi pakai rumus luas minimum 1m².
  **Benar begitu?**
- **Cellular Shade** (OPAQUE, SEMI OPAQUE) — tidak disebut di rumus manapun.
  Kami pakai rumus yang sama seperti Roller/Venetian (luas minimum 1m²) untuk
  sementara. **Apakah ini benar, atau Cellular Shade punya rumus sendiri?**

## 2. Rumus gorden (curtain) — lebar kain per produk

Rumus gorden butuh tahu **lebar gulungan kain** (140cm atau 280cm) untuk
setiap produk kain gorden, karena itu menentukan jumlah panel. Daftar kain
sheet "Curtain":

- ATLAS, DREAMLAND, ELARA, LIORA, LOVINA, LUMIA, ORION, PANDAWA, POSITANO,
  SERENE, SHEER, SHIMMER

**Untuk masing-masing dari 12 kain di atas, berapa lebar gulungan kainnya —
140cm atau 280cm?** (Saat ini semua kami set default 140cm sementara, belum
dikonfirmasi.)

## 3. Rumus pembulatan meter kain gorden

Contoh di catatan rumus:
- Kain 140cm: hasil 15,76m dibulatkan jadi **16m** (bulat ke meter penuh)
- Kain 280cm: hasil 8,08m dibulatkan jadi **8,5m** (bulat ke setengah meter)

Kami pakai aturan "selalu bulatkan ke atas ke kelipatan 0,5m" untuk kedua
kasus (hasilnya sama untuk dua contoh di atas secara kebetulan). **Apakah
aturan pembulatannya benar-benar selalu 0,5m, atau kain 140cm punya aturan
beda (bulat ke 1m penuh)?**

## 4. Price List Panel Glide 01 Juni 2026 — pencocokan nama opsi

Price list menyebut tiga tipe: **Classic, Sewless, Villa**. Di data yang
sudah diimpor dari FABRIC CHART, nama opsinya adalah **Plain, Sewless,
Plantation**. Kami asumsikan:

- Classic = Plain
- Villa = Plantation

**Apakah pencocokan ini benar?**

## 5. Kain yang disebut di price list tapi tidak ada di katalog produk

Tiga nama di price list Panel Glide tidak match dengan data produk yang
sudah ada:

- **Luxe (BO)** — tidak ada produk dengan nama ini sama sekali di katalog.
- **Luxe (T)** — tidak ada produk dengan nama ini sama sekali di katalog.
- **Harrington BO** — di katalog hanya ada "HARRINGTON" (tanpa embel-embel
  BO/TL). Apakah ini kain yang sama?

**Mohon konfirmasi:**
- Apakah Luxe (BO) dan Luxe (T) perlu ditambahkan sebagai produk baru? Jika
  ya, mohon info lengkap (kategori, warna yang tersedia, dimensi maksimum).
- Apakah "Harrington BO" di price list = "HARRINGTON" di katalog produk?

## 6. Linen (BO) dan Resene (BO) — data mekanisme hilang

Dua kain ini (**Linen (BO)** dan **Resene (BO)**) muncul di price list Panel
Glide dengan harga, tapi di database **tidak ada data mekanisme sama sekali**
untuk keduanya (harusnya ada data Roman/Roller/Panel Glide/Vertical dari
sheet FABRIC CHART, tapi untuk dua kain ini kosong total — kemungkinan bug
saat impor data lama, bukan masalah baru). Harga Panel Glide untuk kedua kain
ini **belum bisa dimasukkan** sampai ini diperbaiki.

**Tidak perlu dijawab oleh klien — ini catatan teknis internal kami,**
disebutkan di sini supaya tidak terlupa.

## 7. Harga dasar yang masih belum ada sama sekali

Price list 01 Juni 2026 hanya memberi harga untuk mekanisme **Panel Glide**.
Mekanisme lain pada kain yang sama (Roller, Roman, Vertical) **masih IDR 0**
dan produknya sengaja kami nonaktifkan sampai ada harga asli — supaya tidak
ada quotation yang keluar dengan harga Rp 0 secara tidak sengaja.

**Pertanyaan untuk klien: kapan price list untuk Roller, Roman/Design
Shades, All Venetian, Vertical Fabric, Cellular Shade, dan Curtain akan
tersedia?** Tanpa ini, 133 produk di katalog (dikurangi 21 yang sudah dapat
harga Panel Glide) masih belum bisa dijual lewat sistem.

## 8. Status stok yang tidak diketahui (167 warna)

Saat impor katalog awal, 167 varian warna di seluruh sheet tidak punya status
stok yang jelas (kolom warnanya tidak cocok dengan legenda status di sheet
manapun, atau sheetnya — Curtain dan Design Shades — tidak punya legenda
status sama sekali). Ini tercatat di sistem sebagai status `unknown`.

**Mohon klien mengecek ulang status stok (in stock / limited / out of
stock / discontinued) untuk warna-warna yang hilang statusnya ini.** Kami
bisa kirimkan daftar lengkapnya jika diperlukan.

---

*Dokumen ini dibuat otomatis berdasarkan data yang sudah diimpor ke sistem
Workweb per 23 Oktober. Mohon balasan per poin supaya kami bisa langsung
perbarui data.*
