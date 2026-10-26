# Job Spy Multi-Portal Expansion Analysis

> **Metodologi & batas kepercayaan**
>
> Analisis ini dibuat dari pembacaan langsung source code yang terpasang di repo ini
> (`jobspy/.venv/Lib/site-packages/jobspy/`, `src/`, `jobspy/main.py`) ditambah probing
> HTTP terbatas terhadap endpoint publik JobStreet dan Glints.
>
> Setiap temuan diberi label:
>
> | Label | Arti |
> |---|---|
> | **CONFIRMED** | Terbukti dari source code / hasil probe yang saya jalankan sendiri |
> | **LIKELY** | Konsisten dengan bukti, tapi ada jalur alternatif yang belum dieliminasi |
> | **HYPOTHESIS** | Dugaan beralasan, belum ada bukti langsung |
> | **NEEDS RUNTIME TEST** | Hanya bisa dipastikan dengan eksekusi dari VPS produksi |
>
> **Batas penting pada probe jaringan:** semua request HTTP dalam dokumen ini berasal dari
> infrastruktur fetch saya, **bukan dari VPS Anda**, tanpa header browser lengkap dan dari
> rentang IP datacenter. Status `403` yang saya terima **tidak boleh dibaca sebagai
> "portal memblokir scraper"** — bisa jadi hanya reputasi IP/User-Agent saya. Semua hasil
> probe wajib diulang dari VPS sebelum dijadikan dasar keputusan (lihat §8.4).

---

## 1. Executive Summary

**Pertanyaan inti:** bisakah JobStreet, Glints, dan portal sejenis ditambahkan memakai
mekanisme fetch/scraping yang sama seperti 7 portal yang sudah didukung?

**Jawaban singkat: secara arsitektur ya, tapi ada satu penghalang struktural yang harus
diputuskan lebih dulu — dan penghalang itu bukan soal scraping, melainkan soal
_di mana kode scraper baru boleh hidup_.**

Lima temuan yang menentukan:

1. **Abstraksi adapter yang Anda gambarkan sudah ada dan sudah matang.** `jobspy.model.Scraper`
   adalah ABC dengan satu method abstrak `scrape(ScraperInput) -> JobResponse`. Pipeline
   `Portal → Adapter → Parser → Normalizer → Common Schema → MCP` bukan sesuatu yang perlu
   dirancang — itu **persis** bentuk yang sudah dipakai 8 scraper existing. **(CONFIRMED)**

2. **Tapi repo ini tidak memiliki source jobspy.** `jobspy/requirements.txt` hanya berisi
   `python-jobspy==1.1.82`; paketnya di-*install dari PyPI*. Tidak ada satu pun file scraper
   di dalam version control repo ini. **Tidak ada tempat untuk menaruh scraper baru
   tanpa mengubah strategi dependency.** **(CONFIRMED)**

3. **Opsi "plugin bersih" — daftarkan scraper baru lewat monkey-patch — tidak mungkin.**
   `SCRAPER_MAPPING` adalah variabel **lokal di dalam fungsi** `scrape_jobs()`
   (`jobspy/__init__.py:58`), bukan konstanta modul, jadi tidak bisa di-patch dari luar.
   `Site` juga Enum tertutup. Jalur ini mati. **(CONFIRMED — lihat §7.2)**

4. **Rekomendasi: pola _sidecar_, bukan fork.** Tulis scraper Indonesia sebagai modul
   terpisah di repo ini yang **meng-import** `jobspy.model` dan `jobspy.util` (reuse penuh),
   lalu gabungkan hasilnya di `main.py`. Risiko terhadap 7 portal existing = **nol**, karena
   paket upstream tidak disentuh sama sekali dan tetap bisa di-`pip install -U`. **(§9)**

5. **Framework ini tidak punya kemampuan render JavaScript sama sekali** — tidak ada
   Playwright/Selenium/Puppeteer di dependency manapun. Digabung dengan batas memori
   **256MB** yang Anda set di server (lihat analisa resource sebelumnya), menambah headless
   browser praktis **tidak mungkin**. Portal apa pun yang wajib JS-rendered otomatis
   di luar jangkauan. **(CONFIRMED)**

**Kelayakan per portal:**

| Portal | Mekanisme yang dibutuhkan | Template terdekat | Kelayakan |
|---|---|---|---|
| **JobStreet ID** | GraphQL POST ke `id.jobstreet.com/graphql` | `glassdoor/` (Apollo GraphQL) | **LIKELY layak** — endpoint merespons, schema perlu direverse |
| **Glints** | GraphQL POST ke `glints.com/api/graphql` | `glassdoor/` | **NEEDS RUNTIME TEST** — probe saya diblokir di edge |
| **BDJobs** | — sudah ada di paket terpasang | — | **Sudah didukung, tapi belum di-expose ke MCP** (§7.1) |

**Temuan bonus:** paket yang terpasang **sudah** berisi scraper `bdjobs` lengkap dengan
`Site.BDJOBS`, tapi MCP layer ini tidak pernah mengizinkannya — daftar `validSites` di
[searchParamsSchema.js:31-39](../src/schemas/searchParamsSchema.js#L31-L39) hanya memuat 7
nama. Mengaktifkannya adalah perubahan beberapa baris, dan sekaligus jadi **latihan
end-to-end paling murah** untuk membuktikan jalur "tambah portal" sebelum menulis
scraper baru dari nol. **(CONFIRMED)**

---

## 2. Existing Architecture Analysis

### 2.1 Rantai eksekusi aktual

```
MCP Client
   │  tool: search_jobs
   ▼
src/tools/search-jobs.js        ← Zod validate + concurrency gate (cap 1)
   │  spawn(python, ['main.py', '--site_name', ...])
   ▼
jobspy/main.py                  ← argparse → scrape_jobs(...) → JSON ke stdout
   │
   ▼
jobspy/.venv/.../jobspy/__init__.py::scrape_jobs()
   │  ThreadPoolExecutor fan-out per site
   ▼
Scraper subclass (.scrape())    ← Indeed / LinkedIn / Glassdoor / ... / BDJobs
   │  → JobResponse(jobs=[JobPost, ...])
   ▼
normalisasi inline (__init__.py:130-198) → pandas DataFrame → desired_order
```

### 2.2 Lapisan dan kepemilikannya

| Lapisan | Lokasi | Di version control repo ini? | Boleh diubah? |
|---|---|---|---|
| MCP tool + schema | `src/` | ✅ Ya | ✅ Bebas |
| CLI bridge | `jobspy/main.py` | ✅ Ya | ✅ Bebas |
| Orkestrator `scrape_jobs` | `.venv/.../jobspy/__init__.py` | ❌ **Tidak** | ⚠️ Hilang saat reinstall |
| Model & util | `.venv/.../jobspy/model.py`, `util.py` | ❌ **Tidak** | ⚠️ Hilang saat reinstall |
| Scraper per portal | `.venv/.../jobspy/<site>/` | ❌ **Tidak** | ⚠️ Hilang saat reinstall |

**Ini temuan paling penting dari seluruh analisis.** Tiga lapisan bawah adalah artefak
`pip install`, bukan kode Anda. Setiap perubahan di sana akan lenyap pada rebuild image
berikutnya, karena [Dockerfile:35](../Dockerfile#L35) menjalankan
`uv pip install -r jobspy/requirements.txt` dari awal di setiap build. **(CONFIRMED)**

### 2.3 Interface adapter yang sudah ada

`jobspy/model.py:325-335`:

```python
class Scraper(ABC):
    def __init__(self, site: Site, proxies=None, ca_cert=None, user_agent=None):
        self.site = site
        self.proxies = proxies
        self.ca_cert = ca_cert
        self.user_agent = user_agent

    @abstractmethod
    def scrape(self, scraper_input: ScraperInput) -> JobResponse: ...
```

Kontraknya sangat kecil: **satu input model, satu output model**. Inilah yang membuat
penambahan portal secara teknis murah — beban sesungguhnya ada di reverse-engineering
portal, bukan di integrasi. **(CONFIRMED)**

### 2.4 Common schema

`JobPost` (`model.py:239-281`) adalah pydantic `BaseModel` dengan hampir semua field
`Optional`. Hanya **tiga** field wajib: `title`, `company_name`, `job_url`. Portal baru
yang hanya bisa memberi judul + perusahaan + URL tetap valid secara skema.

Field portal-specific sudah punya presedennya: blok `# Naukri specific` (`model.py:275-281`)
menambahkan `skills`, `experience_range`, `company_rating`, dst. **Pola "tambah field
opsional untuk satu portal" sudah diterima arsitektur ini.** **(CONFIRMED)**

---

## 3. Current Portal Integration Pattern

### 3.1 Taksonomi 8 portal terpasang

Dibaca langsung dari source tiap scraper:

| Portal | Jenis sumber | HTTP client | Auth / token | Parser | Paginasi | LOC |
|---|---|---|---|---|---|---|
| `indeed` | **API GraphQL** `apis.indeed.com/graphql` | `create_session(is_tls=False)` | header statis | JSON | cursor | 260 |
| `linkedin` | **HTML server-rendered** | session + retry | — | BeautifulSoup | offset 25/hal | 339 |
| `glassdoor` | **API GraphQL (Apollo)** | `requests.post` | **CSRF token di-scrape dari HTML** + `fallback_token` | JSON | cursor | 322 |
| `google` | **Endpoint internal** `/async/callback:550` | session | — | regex + JSON | token | 202 |
| `zip_recruiter` | API JSON | session | — | JSON | offset | 219 |
| `bayt` | **HTML polos** | `is_tls=False, has_retry=True` | — | BeautifulSoup | `?page=N` | 145 |
| `naukri` | **REST JSON** `/jobapi/v3/search` | session, `clear_cookies=True` | header konstanta | JSON | `pageNo` | 300 |
| `bdjobs` | **HTML (ASP klasik)** | session | header konstanta | BeautifulSoup | page | 353 |

**Kesimpulan taksonomi (CONFIRMED):**

- Rentang kompleksitas 145–353 LOC. **Portal termurah (`bayt`) hanya 145 baris.**
- **Tidak satu pun memakai headless browser.** Semua adalah HTTP request + parse.
- Tiga varian sumber sudah tercakup: **API resmi/publik-tanpa-key**, **endpoint internal
  front-end**, dan **HTML server-rendered**. Yang **belum pernah** ditangani framework ini:
  **halaman yang benar-benar JavaScript-rendered** dan **portal berautentikasi**.
- **Glassdoor adalah template paling berharga untuk kasus Anda**, karena ia satu-satunya
  yang menyelesaikan pola *"GraphQL + token dinamis yang harus diambil dulu dari halaman HTML"* —
  persis bentuk yang kemungkinan besar dibutuhkan JobStreet dan Glints.

### 3.2 Struktur direktori baku per portal

Setiap scraper non-trivial memakai layout tiga file yang sama:

```
jobspy/<portal>/
├── __init__.py    ← class <Portal>(Scraper), orkestrasi + paginasi
├── constant.py    ← headers, query template GraphQL, param default
└── util.py        ← parser kecil: parse_location, parse_date, is_job_remote, parse_job_type
```

Ini konvensi yang konsisten dan sebaiknya **diikuti persis** untuk portal baru. **(CONFIRMED)**

### 3.3 Anti-bot yang sudah tersedia gratis

`util.py:89-132` menyediakan `create_session(is_tls=True)` yang mengembalikan `TLSRotating`
— subclass `tls_client.Session` dengan `random_tls_extension_order=True`. Artinya
**kemampuan menyamarkan TLS/JA3 fingerprint sudah terpasang di dependency**
(`tls_client==1.0.1`, terverifikasi ada di venv).

Ini penting: banyak blokir Cloudflare bekerja di level TLS fingerprint, bukan User-Agent.
Portal yang menolak `requests` polos sering **lolos** dengan `is_tls=True`. Jadi kegagalan
probe awal bukan vonis akhir. **(CONFIRMED tersedia; efektivitas per portal = NEEDS RUNTIME TEST)**

### 3.4 Normalisasi & common schema

Setelah semua scraper selesai, `scrape_jobs()` menjalankan loop normalisasi
(`__init__.py:130-198`) yang menyeragamkan `location`, `job_type`, `compensation`,
`emails`, `skills`, lalu:

```python
for column in desired_order:
    if column not in jobs_df.columns:
        jobs_df[column] = None      # field yang tak diisi portal → None
jobs_df = jobs_df[desired_order]    # ⚠️ filter keras
```

**Dua konsekuensi yang harus dipegang saat menambah portal:**

1. **Aman:** portal baru tidak wajib mengisi semua kolom — yang kosong otomatis jadi `None`.
   Inilah alasan penambahan portal **tidak merusak** portal existing. **(CONFIRMED)**
2. **Jebakan:** baris `jobs_df = jobs_df[desired_order]` adalah **allow-list keras**. Field
   baru yang Anda tambahkan ke `JobPost` tapi **lupa** didaftarkan di `desired_order`
   (`util.py:318-354`) akan **hilang diam-diam tanpa error**. **(CONFIRMED)**

---

## 4. JobStreet Feasibility

### 4.1 Status platform

JobStreet Indonesia sudah bermigrasi ke tumpukan SEEK. Terverifikasi lewat probe:

| Probe | Hasil | Interpretasi |
|---|---|---|
| `GET www.jobstreet.co.id/api/chalice-search/v4/search?...` | **308 Permanent Redirect** → `id.jobstreet.com/api/chalice-search/v4/search` | Domain lama masih hidup, hanya redirect. **Perhatian: header `Location` tidak membawa query string** — client harus menembak host baru langsung. **(CONFIRMED)** |
| `GET id.jobstreet.com/api/chalice-search/v4/search?siteKey=ID-Main&keywords=...` | **404 Not Found** | Path `chalice-search` legacy **tidak** melayani permintaan ini apa adanya. **(CONFIRMED)** |
| `GET id.jobstreet.com/graphql` | **400 Bad Request** | Bukan 404, bukan 403. Ini **respons khas GraphQL server yang menerima GET tanpa parameter `query`**. **(CONFIRMED status; LIKELY interpretasi)** |
| `GET id.jobstreet.com/` (homepage) | **403 Forbidden** | Rute HTML diblokir untuk fetcher saya |
| `GET id.jobstreet.com/id/jobs?keywords=...` | **403 Forbidden** | Idem |

### 4.2 Pembacaan bukti

Perbandingan status inilah yang informatif, bukan status individualnya:

- Rute **HTML** → `403`
- Rute **API** (`/graphql`, `/api/chalice-search/...`) → `400` dan `404`

Karena `400`/`404` berarti request **berhasil menembus edge** dan dijawab oleh aplikasi di
belakangnya, sementara `403` dihentikan di edge, maka:

> **LIKELY:** proteksi bot JobStreet dipasang di rute HTML, dan **rute API relatif lebih
> longgar**. Untuk arsitektur jobspy yang murni HTTP+JSON, ini kabar baik.

**Namun — dan ini penting — `403` pada homepage membuat saya tidak bisa menyimpulkan
apa pun tentang postur anti-bot JobStreet secara umum.** Homepage publik yang menolak saya
adalah tanda bahwa **IP/UA saya** yang ditolak, bukan bahwa portal memusuhi semua klien
otomatis. Sumber pihak ketiga menyebut endpoint pencarian JobStreet dapat diakses tanpa
API key; saya **tidak bisa memverifikasi** klaim itu dari sini. **(NEEDS RUNTIME TEST)**

### 4.3 Mekanisme yang dibutuhkan

| Aspek | Penilaian |
|---|---|
| Jenis sumber | GraphQL POST (Apollo) — **bukan** API resmi, melainkan endpoint front-end **(LIKELY)** |
| Autentikasi | Kemungkinan tanpa login, tapi mungkin butuh header korelasi (`x-seek-site`, `seek-request-brand`, dsb.) **(HYPOTHESIS)** |
| JS rendering | **Tidak perlu**, jika jalur GraphQL dipakai **(LIKELY)** |
| CAPTCHA | Tidak terdeteksi pada rute API **(HYPOTHESIS)** |
| Template internal | **`jobspy/glassdoor/`** — sudah menyelesaikan pola GraphQL + token + `query_template` di `constant.py` |
| Dependency baru | **Tidak ada.** Cukup `requests` + `json` yang sudah terpasang **(CONFIRMED)** |
| Country enum | `Country.INDONESIA = ("indonesia", "id")` **sudah ada** di `model.py:94` — tidak perlu ubah enum **(CONFIRMED)** |

### 4.4 Yang belum bisa dipastikan tanpa runtime testing

1. Nama operasi GraphQL dan bentuk `variables` (kandidat: `SearchJobs`, `jobs`, `searchJobs`).
2. Apakah introspection diaktifkan (kalau ya, reverse-engineering jadi jauh lebih cepat).
3. Header wajib yang ditolak jika absen.
4. Ambang rate limit dan apakah IP VPS Indonesia diperlakukan berbeda dari IP datacenter asing.
5. Apakah `chalice-search` masih hidup dengan kombinasi parameter yang benar (404 saya bisa
   berarti "path mati" **atau** "parameter salah" — dua hal berbeda yang belum terpisahkan).

**Verdict JobStreet: LIKELY layak dengan effort sedang.** Estimasi 250–350 LOC mengikuti
pola `glassdoor`, ditambah 1–2 hari reverse-engineering payload GraphQL lewat DevTools.

---

## 5. Glints Feasibility

### 5.1 Hasil probe

| Probe | Hasil |
|---|---|
| `GET glints.com/api/graphql` | **403 Forbidden** |
| `GET glints.com/id` (homepage) | **403 Forbidden** |
| `GET glints.com/api/v2/job/search?...` | **403 Forbidden** |

### 5.2 Pembacaan bukti — dan mengapa hasilnya inkonklusif

Berbeda dari JobStreet, **semua** rute Glints — termasuk homepage publik biasa — menolak
fetcher saya dengan status yang sama. Ini justru **melemahkan**, bukan menguatkan,
kesimpulan tentang anti-bot:

> Kalau homepage publik pun `403`, maka yang diblokir hampir pasti **klien saya**
> (IP datacenter + UA non-browser), bukan **jalur API**-nya. Saya tidak mendapat sinyal
> pembeda apa pun antara rute HTML dan rute API seperti pada JobStreet.

**Konsekuensi jujur: saya tidak bisa menyatakan Glints layak maupun tidak layak.**
Yang bisa saya nyatakan hanya: *dengan klien polos dari IP datacenter asing, Glints
tidak dapat diakses sama sekali.* **(CONFIRMED, tapi sempit)**

### 5.3 Yang diketahui dari sumber lain

Laporan pihak ketiga menyebut Glints mengekspos GraphQL tanpa autentikasi di `/api/graphql`
dengan schema tidak terdokumentasi (hasil reverse-engineering), mencakup pasar
ID/SG/MY/VN/TW. Ini **konsisten** dengan Glints sebagai aplikasi Next.js, tapi
**tidak terverifikasi olehku**. **(HYPOTHESIS)**

### 5.4 Dua jalur kandidat

| Jalur | Deskripsi | Prasyarat |
|---|---|---|
| **A. GraphQL** | POST `/api/graphql` dengan query hasil reverse-engineer | Harus bisa menembus edge dari IP VPS |
| **B. `__NEXT_DATA__`** | Ambil HTML halaman pencarian, ekstrak blob JSON `<script id="__NEXT_DATA__">` | Idem, plus halaman harus SSR (bukan client-only) |

Jalur B layak dipertimbangkan sebagai cadangan karena **BeautifulSoup + `json` sudah
tersedia**, dan pola "regex/parse blob JSON dari HTML" sudah dipakai scraper `google`
(`google/util.py`) maupun pengambilan CSRF Glassdoor (`glassdoor/__init__.py:152-162`).
Tidak butuh dependency baru. **(CONFIRMED soal ketersediaan tooling)**

### 5.5 Faktor pembeda paling menentukan

**Lokasi IP.** Glints, JobStreet ID, dan portal lokal lain melayani trafik Indonesia.
VPS Anda — jika berada di Indonesia atau Singapura — punya profil reputasi yang sangat
berbeda dari IP fetcher saya. Ini bukan detail kecil: **ini kemungkinan besar satu-satunya
variabel yang memisahkan "tidak bisa diakses" dari "bisa diakses".**

**Verdict Glints: NEEDS RUNTIME TEST.** Jangan alokasikan effort implementasi sebelum
langkah §8.4 dijalankan dari VPS. Biaya tes itu ~10 menit; biaya salah tebak = berhari-hari.

---

## 6. Reusable Architecture

Pipeline yang Anda usulkan sudah terimplementasi. Berikut pemetaannya ke kode nyata,
beserta **apa yang bisa dipakai ulang apa adanya** vs **apa yang wajib ditulis per portal**.

```
Job Portal
   ↓
Adapter / Fetcher   ──→ REUSE: create_session() — tls_client, proxy rotation, retry
   ↓                    TULIS : base_url, params/payload, headers, paginasi, delay
Parser              ──→ REUSE: BeautifulSoup, json, regex, markdown_converter()
   ↓                    TULIS : selector/JSONPath, parse_date, parse_location
Normalizer          ──→ REUSE: extract_salary, currency_parser, extract_emails_from_text,
   ↓                           extract_job_type, get_enum_from_job_type
Common Job Schema   ──→ REUSE: JobPost, Location, Compensation, JobResponse (pydantic)
   ↓                    TULIS : (hanya) field opsional khas portal + entri desired_order
MCP Server          ──→ REUSE: seluruhnya. TULIS: 1 nama site di validSites
```

### 6.1 Komponen reusable (0 baris kode baru)

| Komponen | Lokasi | Fungsi |
|---|---|---|
| `create_session()` | `util.py:106-132` | Session dengan TLS spoofing, rotasi proxy, retry/backoff, `clear_cookies` |
| `TLSRotating` / `RequestsRotating` | `util.py:55-103` | Implementasi rotasi proxy per-request |
| `create_logger()` | `util.py:19-29` | Logger ber-namespace `JobSpy:<Portal>`, otomatis patuh `--verbose` |
| `markdown_converter()` | `util.py:154-158` | HTML deskripsi → Markdown |
| `extract_salary()` | `util.py:202-269` | Parsing rentang gaji dari teks bebas |
| `currency_parser()` | `util.py:179-193` | Normalisasi format angka mata uang |
| `extract_emails_from_text()` | `util.py:161-165` | Ekstraksi email dari deskripsi |
| `extract_job_type()` | `util.py:272-288` | Deteksi fulltime/parttime/contract dari deskripsi |
| `JobPost`, `Location`, `Compensation`, `JobResponse`, `ScraperInput` | `model.py` | Skema bersama |
| `Country` enum | `model.py:60-178` | `INDONESIA` sudah ada |
| Fan-out multi-site | `__init__.py:119-126` | `ThreadPoolExecutor` paralel antar portal |
| Seluruh MCP layer | `src/` | Tool, schema, SSE, queue |

### 6.2 Komponen wajib portal-specific

| Komponen | Kenapa tidak bisa digeneralisasi |
|---|---|
| Endpoint + pembangunan request | Tiap portal beda total: query param vs GraphQL payload |
| `constant.py` (headers / query template) | Header wajib bersifat unik per portal |
| Bootstrap token | Glassdoor scrape CSRF; portal lain mungkin butuh cookie/build-id |
| Parsing respons → `JobPost` | Struktur data sepenuhnya berbeda |
| Strategi paginasi | `?page=N` vs `pageNo` vs cursor vs offset |
| Parsing tanggal | "2 hari lalu" vs ISO vs epoch |
| Parsing lokasi → `Location` | Format alamat lokal |
| `delay` / `band_delay` | Toleransi rate limit tiap portal berbeda |

### 6.3 Perbaikan reusability yang layak dilakukan lebih dulu

Dua titik di kode existing menghambat penambahan portal, dan keduanya murah diperbaiki:

**(a) Daftar site di-hardcode 4× dalam satu file.** Di
[searchParamsSchema.js](../src/schemas/searchParamsSchema.js) nama portal muncul di
baris 9 (describe), 14 (describe), 31-39 (`validSites`), dan 44 (pesan error) — empat
tempat yang harus disinkronkan manual. **Ekstrak jadi satu konstanta `SUPPORTED_SITES`**
lalu turunkan keempatnya dari sana. **(CONFIRMED — sumber bug sinkronisasi)**

**(b) Loop normalisasi tidak bisa dipakai ulang.** Blok `__init__.py:130-198` yang
mengubah `JobPost` → baris DataFrame ada **inline di dalam** `scrape_jobs()`. Pendekatan
sidecar (§9) tidak bisa memanggilnya, jadi harus menduplikasi subsetnya. Ini **biaya nyata**
dari pendekatan sidecar yang harus diterima secara sadar. **(CONFIRMED)**

---

## 7. Required Code Changes

### 7.1 Perubahan minimum untuk mengaktifkan portal yang sudah ada (`bdjobs`)

Ini bukan hipotesis — scraper `bdjobs` **sudah terpasang** (`Site.BDJOBS` di `model.py:295`,
`BDJobs` terdaftar di `SCRAPER_MAPPING` `__init__.py:66`, 353 baris di `bdjobs/__init__.py`).
Yang hilang hanya izin di lapisan MCP:

| File | Perubahan |
|---|---|
| [src/schemas/searchParamsSchema.js:31-39](../src/schemas/searchParamsSchema.js#L31-L39) | Tambah `'bdjobs'` ke `validSites` |
| [src/schemas/searchParamsSchema.js:9,14,44](../src/schemas/searchParamsSchema.js#L9) | Perbarui teks `describe` + pesan error |
| [jobspy/main.py:11](../jobspy/main.py#L11) | Perbarui help text (`--site_name` tidak divalidasi, jadi ini kosmetik) |

**Total: satu file, ~4 baris.** Ini membuktikan bahwa **biaya integrasi portal baru ke MCP
memang sangat kecil** — dan sekaligus mengonfirmasi bahwa seluruh beban ada di penulisan
scraper. Jadikan ini langkah pertama untuk memvalidasi jalur end-to-end. **(CONFIRMED)**

### 7.2 Tiga opsi penempatan scraper baru

#### Opsi A — Fork & vendor `python-jobspy` ke repo

Salin source paket ke `jobspy/vendor/jobspy/`, hapus `python-jobspy` dari `requirements.txt`.

| | |
|---|---|
| ✅ | Akses penuh; persis mengikuti arsitektur upstream; `SCRAPER_MAPPING` bisa diedit langsung |
| ❌ | Anda mewarisi maintenance **seluruh** paket (3.098 LOC, 8 scraper) |
| ❌ | Kehilangan perbaikan upstream — dan scraper portal besar **rutin rusak** karena situs berubah |
| ❌ | Beban terbesar justru di portal yang **tidak** Anda pedulikan (Indeed/LinkedIn/Glassdoor) |

#### Opsi B — Plugin via monkey-patch — **TIDAK MUNGKIN**

Ide: daftarkan scraper baru ke `SCRAPER_MAPPING` dari luar tanpa menyentuh paket.

**Terbukti tidak bisa (CONFIRMED), dua penghalang independen:**

1. `SCRAPER_MAPPING` **bukan** konstanta modul. Ia dibangun ulang sebagai **variabel lokal
   setiap kali `scrape_jobs()` dipanggil** (`__init__.py:58-67`). Tidak ada referensi yang
   bisa dipegang dan dimodifikasi dari luar.
2. `Site` adalah `enum.Enum` tertutup (`model.py:287-295`). Menambah member saat runtime
   tidak didukung; dan seandainya berhasil, `SCRAPER_MAPPING[site]` tetap `KeyError`
   karena dict-nya dibangun dari literal.

**Jalur ini gugur. Jangan dikejar.**

#### Opsi C — Sidecar di `main.py` — **REKOMENDASI**

Tulis scraper Indonesia sebagai paket terpisah **di dalam repo ini**, yang meng-*import*
`jobspy.model` dan `jobspy.util` (reuse penuh via import biasa, bukan modifikasi), lalu
gabungkan hasilnya di `main.py`.

```
jobspy/
├── main.py                 ← orkestrator: panggil scrape_jobs() + scraper lokal, lalu merge
├── requirements.txt        ← python-jobspy==1.1.82 TIDAK BERUBAH
└── portals/                ← BARU, milik Anda, masuk version control
    ├── __init__.py         ← LOCAL_SCRAPERS = {"jobstreet": JobStreet, "glints": Glints}
    ├── base.py             ← helper bersama: JobPost[] → DataFrame(desired_order)
    ├── jobstreet/
    │   ├── __init__.py     ← class JobStreet(Scraper)   ← import dari jobspy.model
    │   ├── constant.py
    │   └── util.py
    └── glints/
        └── ...
```

| | |
|---|---|
| ✅ | **Risiko ke 7 portal existing = nol.** Paket upstream tidak disentuh sama sekali |
| ✅ | `pip install -U python-jobspy` tetap jalan; perbaikan upstream tetap masuk |
| ✅ | Kode Anda masuk version control dan bertahan lintas rebuild image |
| ✅ | Reuse penuh `Scraper`, `JobPost`, `create_session`, `util.*` lewat import biasa |
| ✅ | Bisa dikembangkan/diuji portal per portal tanpa menyentuh yang lain |
| ⚠️ | Harus menduplikasi subset loop normalisasi (§6.3b) — **biaya nyata, ±60 baris** |
| ⚠️ | Terikat pada API internal `jobspy.model`/`jobspy.util`; **pin versi ketat wajib** |

Catatan tentang pin versi: `requirements.txt` sudah memakai `==1.1.82` (bukan `>=`), jadi
proteksinya sudah benar. Pertahankan, dan perlakukan upgrade `python-jobspy` sebagai
perubahan yang butuh pengujian. **(CONFIRMED)**

### 7.3 Rincian perubahan untuk Opsi C

| # | File | Sifat | Perubahan |
|---|---|---|---|
| 1 | `jobspy/portals/<portal>/*` | **Baru** | Scraper: `__init__.py` + `constant.py` + `util.py` |
| 2 | `jobspy/portals/base.py` | **Baru** | `jobposts_to_df(jobs, site)` — normalisasi + `desired_order` |
| 3 | `jobspy/main.py` | Ubah | Pisahkan `--site_name` jadi site upstream vs lokal; jalankan keduanya; `pd.concat` |
| 4 | `src/schemas/searchParamsSchema.js` | Ubah | `SUPPORTED_SITES` + tambah nama portal baru |
| 5 | `Dockerfile` | Ubah | `COPY --chown=bun:bun jobspy/portals ./jobspy/portals` — **wajib**; baris 40 saat ini hanya menyalin `main.py` |
| 6 | `README.md` | Ubah | Dokumentasi daftar portal |
| 7 | `tests/` | **Baru** | Fixture respons + tes parser offline (lihat §8.5) |

**Item #5 adalah jebakan yang mudah terlewat.** [Dockerfile:40](../Dockerfile#L40) saat ini
berbunyi `COPY --chown=bun:bun jobspy/main.py ./jobspy/main.py` — **hanya satu file**.
Direktori `portals/` tidak akan ikut masuk image, dan kegagalannya baru muncul saat runtime
di VPS sebagai `ModuleNotFoundError`. **(CONFIRMED)**

### 7.4 Dampak terhadap MCP tool & output schema

| Aspek | Dampak |
|---|---|
| Nama tool `search_jobs` | **Tidak berubah** |
| Parameter tool | **Tidak ada parameter baru** — cukup nilai baru pada `siteNames` |
| Struktur output `{count, jobs[]}` | **Tidak berubah** |
| Field pada objek job | **Additive-only** — field baru `null` untuk portal lain (`__init__.py:208-210`) |
| Kompatibilitas klien lama | **Aman**, selama tidak ada field yang dihapus/di-rename |
| `countryIndeed` | Tidak relevan untuk portal lokal, tapi tetap divalidasi `Country.from_string()` — `"indonesia"` valid |

**Aturan tunggal agar tidak merusak apa pun: hanya tambah, jangan ubah, jangan hapus.**
Setiap field baru harus (a) `Optional` di `JobPost` **dan** (b) terdaftar di `desired_order`
— melewatkan (b) membuat field hilang tanpa error (§3.4). **(CONFIRMED)**

---

## 8. Risks & Limitations

### 8.1 Risiko teknis

| Risiko | Bukti / dasar | Dampak | Mitigasi | Prioritas |
|---|---|---|---|---|
| **Perubahan struktur situs** | Scraper portal besar rutin rusak; Glassdoor bahkan menyimpan `fallback_token` sebagai penanda kerapuhan | Portal berhenti berfungsi tanpa peringatan | Tes parser berbasis fixture + alerting saat hasil 0 | **High** |
| **Schema GraphQL tak terdokumentasi** | JobStreet & Glints keduanya reverse-engineered | Query pecah saat FE portal di-deploy ulang | Simpan query di `constant.py`, jangan sebar di kode | **High** |
| **IP blocking / rate limit** | Semua trafik keluar dari **satu IP VPS**; probe saya `403` dari IP datacenter | Blokir permanen bisa mematikan portal existing juga | `delay`/`band_delay` seperti scraper lain; dukungan `--proxies` sudah ada | **High** |
| **Tidak ada kemampuan JS rendering** | Tak ada Playwright/Selenium di dependency mana pun **(CONFIRMED)** | Portal JS-only mustahil didukung | Verifikasi jalur non-JS **sebelum** implementasi | **High** |
| **Memori: fan-out `ThreadPoolExecutor` tanpa batas** | `__init__.py:119` — `ThreadPoolExecutor()` tanpa `max_workers`; default `min(32, cpu+4)` | Makin banyak portal dipilih sekaligus → makin banyak scraper paralel → **OOM di cap 256MB** | Set `max_workers` eksplisit; batasi jumlah site per request | **High** |
| **`desired_order` membuang field diam-diam** | `__init__.py:213` **(CONFIRMED)** | Data hilang tanpa error | Checklist: tiap field baru wajib masuk `desired_order` | **Medium** |
| **Terikat API internal `jobspy.*`** | Sidecar meng-import `model`/`util` yang bukan API publik | Upgrade upstream bisa mematahkan sidecar | Pin `==1.1.82` (sudah ✅); uji saat upgrade | **Medium** |
| **`__all__` salah di upstream** | `__init__.py:224` → `__all__ = ["BDJobs"]`, menutupi `scrape_jobs` | `from jobspy import *` tidak mengekspor `scrape_jobs` | `main.py:6` sudah pakai import eksplisit — **aman**, tapi jangan pernah pakai wildcard | **Low** |

### 8.2 Risiko non-teknis

| Risiko | Catatan |
|---|---|
| **Terms of Service** | JobStreet/SEEK dan Glints umumnya melarang pengambilan data otomatis di ToS. Ini keputusan bisnis/legal, di luar wewenang analisis teknis — **tapi harus diputuskan sadar, bukan diabaikan.** |
| **Data pribadi** | Listing bisa memuat nama recruiter/email (`extract_emails_from_text` memang mengekstraknya). Pertimbangkan implikasi UU PDP. |
| **Beban ke portal** | Hormati `robots.txt` dan pertahankan delay; ini juga melindungi IP VPS Anda sendiri. |

### 8.3 Batasan analisis ini

- Tidak ada satu pun request yang dijalankan **dari VPS Anda**. Semua status HTTP di §4-§5
  berasal dari infrastruktur lain dengan profil IP dan header berbeda.
- Tidak ada POST GraphQL yang benar-benar dieksekusi (tool fetch saya hanya GET), sehingga
  **keberadaan endpoint** teruji tapi **kegunaannya** tidak.
- Struktur respons JobStreet/Glints belum pernah saya lihat langsung — semua pernyataan
  soal bentuk data adalah HYPOTHESIS.

### 8.4 Checklist validasi runtime dari VPS — **jalankan ini lebih dulu**

Semua perintah dijalankan **dari dalam container di VPS** (`docker exec -it job-spy-mcp-1 sh`),
supaya IP, DNS, dan TLS stack-nya sama persis dengan kondisi produksi.

```sh
# A. Apakah rute HTML JobStreet bisa diakses dari IP VPS?
curl -s -o /dev/null -w "%{http_code}\n" \
  -A "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36" \
  "https://id.jobstreet.com/id/jobs?keywords=software+engineer"

# B. Apakah endpoint GraphQL JobStreet menerima POST?  (400 = hidup, 403 = diblokir)
curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://id.jobstreet.com/graphql" \
  -H "content-type: application/json" -d '{"query":"{__typename}"}'

# C. Apakah introspection terbuka?  (kalau ya, reverse-engineering jadi hitungan menit)
curl -s -X POST "https://id.jobstreet.com/graphql" \
  -H "content-type: application/json" \
  -d '{"query":"{__schema{queryType{name}}}"}' | head -c 500

# D. Glints — homepage dulu, untuk memisahkan blokir-IP dari blokir-API
curl -s -o /dev/null -w "%{http_code}\n" -A "Mozilla/5.0 ..." "https://glints.com/id"

# E. Glints GraphQL
curl -s -o /dev/null -w "%{http_code}\n" -X POST "https://glints.com/api/graphql" \
  -H "content-type: application/json" -d '{"query":"{__typename}"}'

# F. Apakah halaman Glints server-rendered? (cari blob __NEXT_DATA__)
curl -s -A "Mozilla/5.0 ..." "https://glints.com/id/opportunities/jobs/explore?keyword=engineer" \
  | grep -o '__NEXT_DATA__' | head -1

# G. Uji tls_client — sering lolos di tempat curl/requests ditolak
python - <<'PY'
import tls_client
s = tls_client.Session(random_tls_extension_order=True)
for url in ["https://id.jobstreet.com/", "https://glints.com/id"]:
    try:
        print(url, s.get(url).status_code)
    except Exception as e:
        print(url, "ERR", e)
PY
```

**Aturan keputusan:**

| Hasil | Tindakan |
|---|---|
| B/E mengembalikan `200` atau `400` | Endpoint hidup → lanjut reverse-engineer payload lewat DevTools |
| C mengembalikan schema | **Jalur tercepat** — generate query langsung dari introspection |
| A/D `403` tapi G `200` | Masalahnya TLS fingerprint → pakai `create_session(is_tls=True)` |
| A/D/G semuanya `403` | Butuh proxy residensial Indonesia, atau portal itu **tidak layak dikejar** |
| F menemukan `__NEXT_DATA__` | Jalur cadangan Glints terbuka tanpa GraphQL |

### 8.5 Cara menambah portal tanpa merusak portal existing

1. **Isolasi direktori** — kode portal baru tidak pernah menyentuh file portal lain.
2. **Additive-only pada schema** — field baru `Optional` + wajib masuk `desired_order`.
3. **Fail soft** — bungkus scraper baru dengan `try/except` di level orkestrasi. Kegagalan
   JobStreet **tidak boleh** menggagalkan hasil Indeed di request yang sama. (Perhatikan:
   `scrape_jobs()` upstream **tidak** melakukan ini — `future.result()` di `__init__.py:125`
   akan mem-propagate exception; sidecar Anda justru berkesempatan lebih baik di sini.)
4. **Tes parser offline** — simpan respons asli sebagai fixture, uji parser tanpa jaringan.
   Ini satu-satunya cara mendeteksi kerusakan portal secara deterministik. Repo sudah punya
   `tests/` (berisi `jobSchema.test.js`, `api.http`) dan skrip `bun test` — pondasinya ada.
5. **Feature flag** — env var seperti `ENABLE_LOCAL_PORTALS=0` agar portal baru bisa
   dimatikan di produksi tanpa redeploy image.
6. **Batasi `max_workers`** — lihat §8.1; ini langsung menyangkut cap memori 256MB.

---

## 9. Recommended Implementation

### 9.1 Arsitektur final

```
                        MCP Client
                            │
                   src/tools/search-jobs.js
                     (Zod + queue cap 1)
                            │
                    jobspy/main.py  ← ORKESTRATOR
                            │
              ┌─────────────┴─────────────┐
              │                           │
   jobspy.scrape_jobs()          jobspy/portals/  ← MILIK ANDA
   (paket PyPI, TAK DISENTUH)    LOCAL_SCRAPERS
              │                           │
   indeed / linkedin / glassdoor   jobstreet / glints
   google / zip / bayt / naukri            │
   / bdjobs                                │
              │                    import: Scraper, JobPost,
              │                    create_session, util.*
              └─────────────┬─────────────┘
                            │
                 base.jobposts_to_df()
                  → desired_order → pd.concat
                            │
                    JSON {count, jobs[]}
```

Kuncinya: **panah import hanya satu arah** — kode Anda bergantung pada paket upstream,
paket upstream tidak tahu-menahu soal kode Anda. Itulah yang membuat risiko regresi nol.

### 9.2 Urutan eksekusi

| Tahap | Aksi | Output | Effort |
|---|---|---|---|
| **0** | Jalankan checklist §8.4 dari VPS | Keputusan go/no-go per portal, berbasis data | ~1 jam |
| **1** | Aktifkan `bdjobs` (§7.1) + ekstrak `SUPPORTED_SITES` (§6.3a) | Jalur "tambah portal" terbukti end-to-end, tanpa scraper baru | ~1 jam |
| **2** | Buat kerangka `jobspy/portals/` + `base.py` + update `Dockerfile` (§7.3 #5) | Fondasi sidecar; uji dengan scraper dummy | ~4 jam |
| **3** | Implementasi **JobStreet** (template `glassdoor`) | Portal Indonesia pertama | 2–3 hari |
| **4** | Fixture + tes parser offline JobStreet | Deteksi kerusakan otomatis | ~4 jam |
| **5** | Implementasi **Glints** — **hanya jika tahap 0 lolos** | Portal kedua | 2–4 hari |
| **6** | `max_workers` + feature flag + dokumentasi | Siap produksi di cap 256MB | ~4 jam |

**Tahap 0 dan 1 harus mendahului sisanya.** Tahap 0 mencegah membangun sesuatu yang
ternyata tidak bisa diakses dari VPS; tahap 1 memberi kepastian bahwa lapisan MCP-nya
sudah benar sebelum ada variabel scraper baru yang bisa disalahkan.

### 9.3 Kerangka scraper baru

```python
# jobspy/portals/jobstreet/__init__.py
from __future__ import annotations
import json
from jobspy.model import (
    Scraper, ScraperInput, Site, JobPost, JobResponse, Location, Country,
)
from jobspy.util import create_session, create_logger, markdown_converter

from .constant import headers, search_query
from .util import parse_date, parse_location

log = create_logger("JobStreet")


class JobStreet(Scraper):
    base_url = "https://id.jobstreet.com"
    graphql_url = f"{base_url}/graphql"
    delay = 2
    band_delay = 3

    def __init__(self, proxies=None, ca_cert=None, user_agent=None):
        # Site enum upstream tidak punya JOBSTREET; pakai placeholder dan
        # timpa nilainya saat normalisasi di base.jobposts_to_df(site="jobstreet")
        super().__init__(Site.BAYT, proxies=proxies, ca_cert=ca_cert)
        self.session = create_session(
            proxies=proxies, ca_cert=ca_cert, is_tls=True, has_retry=True
        )
        self.session.headers.update(headers)

    def scrape(self, scraper_input: ScraperInput) -> JobResponse:
        jobs: list[JobPost] = []
        page = 1
        while len(jobs) < scraper_input.results_wanted:
            payload = {
                "query": search_query,
                "variables": {
                    "keywords": scraper_input.search_term,
                    "location": scraper_input.location,
                    "page": page,
                },
            }
            res = self.session.post(self.graphql_url, json=payload)
            if res.status_code not in range(200, 400):
                log.error(f"JobStreet API {res.status_code}")
                break
            batch = self._parse(res.json())
            if not batch:
                break
            jobs.extend(batch)
            page += 1
        return JobResponse(jobs=jobs[: scraper_input.results_wanted])
```

**Catatan jujur soal `Site` enum:** karena `Site` tertutup (§7.2 Opsi B), sidecar tidak bisa
menambah `Site.JOBSTREET`. Dua jalan keluar realistis:

| Pendekatan | Konsekuensi |
|---|---|
| Pakai member `Site` mana pun sebagai placeholder, lalu **set kolom `site` secara eksplisit** di `base.jobposts_to_df()` | Sederhana, tidak menyentuh upstream. Nilai `self.site` di dalam scraper jadi menyesatkan — beri komentar jelas |
| Definisikan enum lokal `LocalSite` di `portals/__init__.py`, dan longgarkan tipe di sidecar | Lebih bersih secara semantik, tapi `Scraper.__init__` tetap minta `Site` |

Saya condong ke yang pertama: lebih sedikit bagian bergerak, dan kolom `site` di output
akhir tetap benar karena diisi eksplisit — yang justru **satu-satunya** yang dilihat klien MCP.

### 9.4 Titik penggabungan di `main.py`

```python
UPSTREAM_SITES = {"indeed","linkedin","zip_recruiter","glassdoor",
                  "google","bayt","naukri","bdjobs"}

requested  = [s.strip() for s in args.site_name.split(",")]
upstream   = [s for s in requested if s in UPSTREAM_SITES]
local      = [s for s in requested if s in LOCAL_SCRAPERS]
unknown    = [s for s in requested if s not in UPSTREAM_SITES and s not in LOCAL_SCRAPERS]
if unknown:
    print(f"warning: unknown sites ignored: {unknown}", file=sys.stderr)

frames = []
if upstream:
    frames.append(scrape_jobs(site_name=upstream, ...))

for name in local:                      # fail-soft — lihat §8.5 poin 3
    try:
        scraper = LOCAL_SCRAPERS[name](proxies=proxies, ca_cert=args.ca_cert)
        resp = scraper.scrape(build_scraper_input(args))
        frames.append(jobposts_to_df(resp.jobs, site=name))
    except Exception as e:
        print(f"warning: {name} scraper failed: {e}", file=sys.stderr)

jobs = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
```

Perhatikan `try/except` per portal lokal: **kegagalan JobStreet tidak boleh menghapus hasil
Indeed.** Ini justru memperbaiki perilaku upstream, yang mem-propagate exception apa pun
dari `future.result()` (`__init__.py:125`).

Sisa `main.py` — `snake_to_camel`, `to_json(orient="records")`, pembungkus `{"count":...}` —
**tidak perlu diubah sama sekali**, karena semua frame sudah diseragamkan ke `desired_order`
sebelum di-`concat`.

---

## 10. Conclusion

**Bisakah portal baru ditambahkan dengan mekanisme fetch/scraping yang sama? Ya.**
Abstraksinya sudah ada, matang, dan terbukti dipakai 8 portal dengan karakteristik yang
sangat berbeda — dari HTML ASP klasik (`bdjobs`) sampai Apollo GraphQL bertoken
(`glassdoor`). Pipeline `Adapter → Parser → Normalizer → Common Schema → MCP` yang Anda
usulkan **tidak perlu dirancang; ia sudah menjadi bentuk kode ini.**

**Yang perlu diputuskan bukan soal scraping, melainkan soal penempatan kode.** Repo ini
tidak memuat source jobspy — ia hanya mem-`pip install` paketnya. Opsi "plugin bersih"
lewat monkey-patch sudah saya buktikan **tidak mungkin** (`SCRAPER_MAPPING` adalah variabel
lokal di dalam fungsi; `Site` adalah Enum tertutup). Tersisa fork atau sidecar, dan
**sidecar jelas lebih baik**: risiko terhadap 7 portal existing nol, upstream tetap bisa
di-upgrade, dan kode Anda masuk version control. Harganya satu: ±60 baris duplikasi
normalisasi. Itu harga yang murah.

**Soal JobStreet dan Glints, saya harus memisahkan apa yang saya tahu dari apa yang saya duga.**

Yang **terbukti**: `id.jobstreet.com/graphql` menjawab `400` — bukan `404`, bukan `403` —
pada GET tanpa parameter, pola khas GraphQL server yang hidup; sementara rute HTML-nya
`403`. Perbedaan status antara rute API dan rute HTML itulah sinyal yang berguna, dan
condong menguntungkan arsitektur HTTP-murni jobspy.

Yang **tidak** bisa saya klaim: apa pun tentang Glints. Homepage publiknya pun menolak
fetcher saya dengan `403` yang sama, jadi saya tidak punya sinyal pembeda sama sekali —
kemungkinan besar yang ditolak adalah IP datacenter saya, bukan aktivitas otomatisnya.
Menyebut Glints "diproteksi anti-bot" berdasarkan data ini akan menjadi kesimpulan yang
melampaui buktinya.

Karena itu **langkah pertama bukan menulis kode, melainkan menjalankan §8.4 dari VPS.**
Sepuluh menit `curl` dari IP yang benar akan menentukan apakah tahap 3 dan 5 layak
dikerjakan sama sekali. Variabel yang paling menentukan bukan kecanggihan scraper,
melainkan **dari IP mana request itu berasal.**

Satu langkah yang layak dikerjakan **tanpa menunggu apa pun**: aktifkan `bdjobs`. Scraper
353 baris itu sudah terpasang dan berfungsi di container Anda, hanya diblokir oleh daftar
`validSites` yang belum diperbarui. Empat baris perubahan, satu portal bertambah — dan
sekaligus membuktikan seluruh jalur "tambah portal" bekerja sebelum ada scraper baru
yang bisa dijadikan kambing hitam.

**Peringatan terakhir yang tidak boleh hilang:** framework ini tidak punya kemampuan render
JavaScript, dan container Anda dibatasi 256MB. Menambahkan headless browser akan melanggar
kedua batas itu sekaligus. Jadi kriteria kelayakan portal mana pun ke depan menjadi sangat
sederhana — **jika datanya tidak bisa diambil lewat HTTP request biasa, portal itu berada
di luar jangkauan arsitektur ini, dan tidak ada jumlah kode yang bisa mengubahnya tanpa
mengubah dulu batas memorinya.**
