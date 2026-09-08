# ZaminTahlil — Raqamli Qishloq Xo‘jaligi Monitoringi va Agro-AI Platformasi

**ZaminTahlil** — O‘zbekiston qishloq xo‘jaligi maydonlarini sun’iy yo‘ldosh tasvirlari ($Sentinel-2$ L2A), agrometeorologik ma’lumotlar (Open-Meteo), Mashinali O‘rganish ($ML$) hosildorlik bashorati va Agronomik $RAG$ (Retrieval-Augmented Generation) sun’iy intellekti orqali kompleks tahlil qiluvchi zamonaviy veb-platforma.

---

## 📋 Mundarija

1. [Tizim Talablari](#tizim-talablari)
2. [O‘rnatish va Virtual Muhit](#ornatish-va-virtual-muhit)
3. [Environment (.env) Sozlamalari](#environment-env-sozlamalari)
4. [Dasturni Ishga Tushirish](#dasturni-ishga-tushirish)
5. [Agronomiya Kitoblarini RAG Bazasiga Kiritish](#agronomiya-kitoblarini-rag-bazasiga-kiritish)
6. [Hosildorlikni Bashorat Qilish (ML Models)](#hosildorlikni-bashorat-qilish-ml-models)
7. [Avtomatlashtirilgan Testlarni Ishga Tushirish](#avtomatlashtirilgan-testlarni-ishga-tushirish)
8. [Loyiha Jildlar Tuzilmasi](#loyiha-jildlar-tuzilmasi)

---

## ⚙️ Tizim Talablari

- **Python**: 3.12 yoki undan yuqori versiya
- **Operatsion tizim**: Windows 10/11, Linux (Ubuntu 22.04+) yoki macOS
- **Paket menejeri**: `pip`
- **Internet aloqasi**: Sentinel Hub CDSE API, Open-Meteo ob-havo xizmati va OpenAI API bilan ishlash uchun

---

## 🚀 O‘rnatish va Virtual Muhit

### 1. Loyihani yuklab olish va papkaga o'tish
```bash
cd ZaminTahlil
```

### 2. Python virtual muhitini (venv) yaratish va faollashtirish

**Windows (PowerShell):**
```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

**Windows (CMD):**
```cmd
python -m venv venv
.\venv\Scripts\activate.bat
```

**Linux / macOS:**
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Barcha kerakli kutubxonalarni o‘rnatish
```bash
pip install --upgrade pip
pip install -r requirements.txt
```

---

## 🔑 Environment (.env) Sozlamalari

Loyiha ildiz katalogida `.env` faylini yarating (yoki `.env.example` dan nusxa oling):

```dotenv
# Ish rejimi: demo (Swagger /docs ochiq) yoki prod (xavfsiz, hujjatlar yopiq)
APP_ENV=demo

# Sentinel Hub / Copernicus Data Space Ecosystem (CDSE) OAuth ma'lumotlari
SENTINEL_HUB_CLIENT_ID=sizning_sentinel_client_id
SENTINEL_HUB_CLIENT_SECRET=sizning_sentinel_client_secret
SENTINEL_PROXY=

# OpenAI API Kaliti (AI tavsiyalari va RAG chat uchun)
OPENAI_API_KEY=sk-sizning_openai_api_kalitingiz

# Ma'lumotlar bazasi va fayllar yo'li
DATABASE_PATH=./data/zamintahlil.sqlite3
ARTIFACT_DIR=./data/artifacts
MODELS_DIR=./models

# Tahlil va AI parametrlari
CLOUD_FREE_THRESHOLD=20
SENTINEL_TIMEOUT_SECONDS=45
OPENAI_TIMEOUT_SECONDS=45
OPENAI_PRIMARY_MODEL=gpt-5.4-nano
OPENAI_FALLBACK_MODEL=gpt-5.4-mini

# RAG Semantik qidiruv sozlamalari
RAG_SIMILARITY_THRESHOLD=0.50
RAG_MODEL_NAME=BAAI/bge-small-en-v1.5

# Prod rejim uchun CORS (vergul bilan ajratilgan domenlar)
CORS_ORIGINS=
```

---

## ▶️ Dasturni Ishga Tushirish

FastAPI serverini Uvicorn orqali ishga tushiring:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Brauzer orqali oching:
- **Asosiy boshqaruv paneli**: `http://127.0.0.1:8000/`
- **Interaktiv API Swagger hujjatlari** (faqat `APP_ENV=demo` rejimida): `http://127.0.0.1:8000/docs`
- **ReDoc hujjatlari**: `http://127.0.0.1:8000/redoc`

---

## 📚 Agronomiya Kitoblarini RAG Bazasiga Kiritish (Offline Developer Workflow)

Server (VM) resurslari va operativ xotirasini tejash maqsadida og‘ir PDF qayta ishlash serverdan butunlay chiqarilgan. Barcha kitoblar dasturchining kompyuterida lokal tarzda vektorlashtiriladi va ixcham `data/rag_seed.json` orqali Gitga tushadi.

### 1. Dasturchi kompyuterida kitoblarni indekslash:
1. Yangi agronomik PDF darsliklarni `data/books/` katalogiga joylashtiring.
2. Indekslash va bilimlar grafini yaratish skriptini yurgizing:
   ```bash
   python scripts/ingest_books.py
   ```
3. Yaratilgan 768-o‘lchamli embeddinglar, matn bo‘laklari va bilimlar grafi `data/rag_seed.json` hamda `data/graph/` ga eksport qilinadi.
4. Ushbu fayllarni Git orqali serverga (VM) yuborasiz (katta hajmli PDF fayllar `.gitignore` da xavfsiz qoladi).

### 2. Veb-interfeys orqali foydalanuvchi nazorati:
- Serverda foydalanuvchi qo‘lda fayl yuklashi yoki o‘chirib yuborishi talab etilmaydi.
- Interfeysdagi **"⚙️ Kitoblar"** tugmasi orqali agronomlar mavjud kitoblardan qaysilari sun’iy intellekt qidiruvida ishtirok etishini shunchaki **Yoqish (ON)** yoki **O‘chirish (OFF)** orqali boshqaradi.

---

## 🌾 Hosildorlikni Bashorat Qilish (ML Models)

Loyihada paxta va kuzgi bug‘doy uchun oldindan o‘qitilgan Machine Learning modellari mavjud (`models/` jildida):
- `CatBoost`
- `LightGBM`
- `XGBoost`
- `RandomForest`
- `GradientBoosting`

### Ishlash tartibi va Natijalar:
1. Xaritada dala belgilang yoki saqlangan dalani tanlang.
2. **"Hosilni bashorat qilish"** bo‘limiga o‘ting.
3. Ekin turini (`Paxta` yoki `Kuzgi Bug'doy`) va istalgan ML modelini tanlang.
4. **"Hosilni hisoblash"** tugmasini bosing. Tizim avtomatik ravishda:
   - Dala koordinatalari bo‘yicha Open-Meteo & NASA POWER API dan real kunlik ob-havo va tuproq namligini oladi;
   - Sentinel-2 va Sentinel-1 oylik spektral ko‘rsatkichlarini integratsiya qiladi;
   - 122 ta ML parametrlar matritsasini tuzadi va 1 gektar hosilini ($t/ga$), umumiy hosilni ($tonna$), ishonchlilik oralig‘ini chiqarib beradi;
   - **Bashorat Manbalari Shaffofligi (`data_sources`)**: Hisoblashda qaysi axborot oqimidan qancha hajmda foydalanilganini ko‘rsatadi (Sentinel-2 tasvirlari soni, ob-havo o‘lchovlari kunlari soni, 3 qatlamli tuproq namligi, Sentinel-1 radar o‘lchovlari);
   - Eng muhim 10 ta ta’sir omilini ($Top\ Features$) va interaktiv fenologiya grafigi (`Chart.js`) hamda oylik batafsil jadvalni taqdim etadi.

---

## 🛰️ Sun’iy Yo‘ldosh Monitoringi va Yillik Dinamika

- **1 Kunda Faqat 1 ta Eng Kam Bulutli Tasvir**: Sentinel-2 yo‘ldoshining kesishuvchi orbitalari (swaths) bitta dala bo‘yicha bir kunda bir nechta tasvir keltirganda, tizim avtomatik ravishda bulutlilik darajasi (`cloud_coverage`) eng kam bo‘lgan 1 ta eng sifatli tasvirni tanlaydi. Dropdownda va tahlillarda bir xil sanalar takrorlanmaydi.
- **Yillik Vaqt O‘qi Zamonaviy Dizayni**: Yillik va tarixiy dinamika grafigida X o‘qi gorizontal (`maxRotation: 0`), avtomatik oraliqlash (`autoSkip: true, maxTicksLimit: 12`) va ixcham `DD MMM` (masalan: `3 Yan`, `15 Yan`, `4 Fev`) formatida aks etadi. Pastki matn kesilib ketmaydi, hover paytida tooltipda to‘liq kalendar sana ko‘rinadi.

---

## 🧪 Avtomatlashtirilgan Testlarni Ishga Tushirish

Barcha unit va integratsion testlarni (jami 69 ta test) tekshirish:

```bash
python -m pytest
```

Qisqa rejimda natijani ko‘rish:
```bash
python -m pytest -q
```

---

## 📁 Loyiha Jildlar Tuzilmasi

```text
ZaminTahlil/
├── app/                        # Asosiy ilova kodi
│   ├── deps.py                 # Dependency Injection va app.state initsializatsiyasi
│   ├── main.py                 # FastAPI asosiy kirish nuqtasi va middlewarelar
│   ├── routers/                # Modulli marshrutizatorlar
│   │   ├── fields.py           # Dala yaratish, ro'yxat va GeoJSON amallari
│   │   ├── analysis.py         # Sentinel-2 tahlillari, artefaktlar va yillik dinamika
│   │   ├── chat.py             # Agro-AI muloqoti, xulosalar va xabarlar tarixi
│   │   ├── rag_routes.py       # RAG kitoblari, faollik toggle va boshqaruv
│   │   └── yield_routes.py     # ML hosildorlik bashorati va manbalar tahlili
│   ├── ai.py                   # OpenAI chat va umumlashtirish (Summary) mantiqi
│   ├── analysis.py             # Sentinel-2 multispektral tahlil xizmati
│   ├── config.py               # Pydantic Settings konfiguratsiyasi
│   ├── constants.py            # Indekslar, qatlamlar va tizim konstantalari
│   ├── db.py                   # SQLite jadvallar sxemasi (Schema v7, WAL, keshlar)
│   ├── geometry.py             # GeoJSON polygon validatsiyasi va maydon hisobi
│   ├── indices.py              # NDVI, NDMI, NDRE, EVI, BSI formulalari
│   ├── language.py             # O‘zbek, rus, ingliz tillarini avtomatik aniqlash
│   ├── rag.py                  # In-memory matrisa keshi, BM25, MMR va 4-RAG dvigateli
│   ├── rag_graph.py            # Agronomik bilimlar grafi (Graph RAG BFS)
│   ├── rendering.py            # PNG tasvirlarni rangli render qilish
│   ├── repository.py           # Ma'lumotlar bazasi CRUD amallari
│   ├── schemas.py              # Pydantic v2 so'rov va javob modellari
│   ├── security.py             # Xavfsizlik sarlavhalari, rate limiter va log maskalash
│   ├── sentinel.py             # Copernicus CDSE / Sentinel Hub mijozi (Daily dedup)
│   ├── timeutils.py            # UTC vaqt konvertatsiyalari
│   ├── weather.py              # Open-Meteo & NASA POWER ob-havo integratsiyasi
│   ├── yield_service.py        # ML hosildorlik inferensiyasi (LRU model keshi)
│   └── static/                 # Frontend aktivlari
│       ├── app.js              # Xarita, tahlil, hosildorlik va chat boshqaruvi
│       ├── i18n.js             # 4 tilda mahalliylashtirish (uz-latn, uz-cyrl, ru, en)
│       ├── index.html          # Asosiy interfeys sahifasi
│       ├── logo.png            # Platforma logotipi
│       └── styles.css          # Zamonaviy dizayn uslublari
├── data/                       # Ma'lumotlar va precomputed RAG
│   ├── rag_seed.json           # 100% precomputed RAG ko'chma seed fayli
│   ├── graph/                  # Ekstraksiya qilingan agronomik bilimlar grafi
│   └── books/                  # Lokal kitoblar (PDF fayllar gitignore qilingan)
├── models/                     # O'qitilgan ML modellar (.joblib)
├── scripts/                    # Yordamchi CLI skriptlar
│   ├── cleanup_artifacts.py    # Eskirgan tasvirlarni tozalash
│   └── ingest_books.py         # Offline developer RAG ingestion va export
├── tests/                      # Pytest avtomatlashtirilgan testlari (69 ta test, 100% pass)
├── AGENTS.md                   # Agentlar va ishlab chiquvchilar uchun qoidalar
├── pyproject.toml              # Loyiha metadata va pytest sozlamalari
├── requirements.txt            # Minimal toza bog'liqliklar ro'yxati
├── ABOUT.md                    # To'liq arxitektura va ilmiy-texnik hujjat
└── README.md                   # Ishga tushirish qo'llanmasi
