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

## 📚 Agronomiya Kitoblarini RAG Bazasiga Kiritish

Foydalanuvchi istalgan agronomik PDF qo‘llanma yoki darsliklarni bilimlar bazasiga kiritishi mumkin. Kiritilgan kitoblar avtomatik bo‘laklarga bo‘linadi va lokal `fastembed` modeli orqali vektorlashtiriladi.

### 1-usul: CLI Terminal orqali (Tavsiya etiladi)
```bash
python scripts/ingest_book.py "C:\kitoblar\paxtachilik_qollanmasi.pdf" --name "Paxtachilik amaliy qo'llanmasi"
```

### 2-usul: Veb-interfeys orqali
1. Brauzerda `http://127.0.0.1:8000` ga kiring.
2. Yuqori o‘ng burchakdagi **"📚 Agronom Kutubxonasi"** tugmasini bosing.
3. PDF faylning to‘liq manzilini kiriting va **"Kitobni kiritish va embedding hisoblash"** tugmasini bosing.

> [!NOTE]
> Chat orqali savol berilganda, qidiruv jarayoni, topilgan kitob sahifalari va moslik ballari (`Score`) to‘g‘ridan-to‘g‘ri server terminalida rangli ko‘rinishda aks etadi.

---

## 🌾 Hosildorlikni Bashorat Qilish (ML Models)

Loyihada paxta va kuzgi bug‘doy uchun oldindan o‘qitilgan Machine Learning modellari mavjud (`models/` jildida):
- `CatBoost`
- `LightGBM`
- `XGBoost`
- `RandomForest`
- `GradientBoosting`

### Ishlash tartibi:
1. Xaritada dala belgilang yoki saqlangan dalani tanlang.
2. **"Hosilni bashorat qilish"** bo‘limiga o‘ting.
3. Ekin turini (`Paxta` yoki `Kuzgi Bug'doy`) va istalgan ML modelini tanlang.
4. **"Hosilni hisoblash"** tugmasini bosing. Tizim avtomatik ravishda:
   - Dala koordinatalari bo‘yicha Open-Meteo API dan real kunlik ob-havo va tuproq namligi ma’lumotlarini oladi;
   - Sentinel-2 va Sentinel-1 oylik spektral ko‘rsatkichlarini integratsiya qiladi;
   - 122 ta ML parametrlar matritsasini tuzadi va 1 gektar hosilini ($t/ga$), umumiy hosilni ($tonna$), ishonchlilik oralig‘ini hamda eng ta’sirchan omillarni ($Top\ Features$) chiqarib beradi.

---

## 🧪 Avtomatlashtirilgan Testlarni Ishga Tushirish

Barcha unit va integratsion testlarni (jami 56 ta test) tekshirish:

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
│   ├── ai.py                   # OpenAI chat va umumlashtirish (Summary) mantiqi
│   ├── analysis.py             # Sentinel-2 tahlil xizmati
│   ├── config.py               # Pydantic Settings konfiguratsiyasi
│   ├── constants.py            # Indekslar, qatlamlar va tizim konstantalari
│   ├── db.py                   # SQLite jadvallar sxemasi (v4)
│   ├── geometry.py             # GeoJSON polygon validatsiyasi va maydon hisobi
│   ├── indices.py              # NDVI, NDMI, NDRE, EVI, BSI formulalari
│   ├── language.py             # O‘zbek, rus, ingliz tillarini avtomatik aniqlash
│   ├── main.py                 # FastAPI marshrutlari va ilova fabrikasi
│   ├── rag.py                  # PDF o'qish, fastembed embedding va semantik qidiruv
│   ├── rendering.py            # PNG tasvirlarni rangli render qilish
│   ├── repository.py           # Ma'lumotlar bazasi CRUD amallari
│   ├── schemas.py              # Pydantic so'rov va javob modellari
│   ├── security.py             # Xavfsizlik sarlavhalari va loglarni maskalash
│   ├── sentinel.py             # Copernicus CDSE / Sentinel Hub mijozi
│   ├── timeutils.py            # UTC vaqt konvertatsiyalari
│   ├── weather.py              # Open-Meteo ob-havo API integratsiyasi
│   ├── yield_service.py        # ML hosildorlik inferensiyasi va fenologiya
│   └── static/                 # Frontend aktivlari
│       ├── app.js              # Xarita, tahlil, hosildorlik va chat boshqaruvi
│       ├── i18n.js             # 4 tilda mahalliylashtirish (uz-latn, uz-cyrl, ru, en)
│       ├── index.html          # Asosiy interfeys sahifasi
│       ├── logo.png            # Platforma logotipi
│       └── styles.css          # Zamonaviy dizayn uslublari
├── models/                     # O'qitilgan ML modellar (.joblib)
├── scripts/                    # Yordamchi CLI skriptlar
│   ├── cleanup_artifacts.py    # Eskirgan tasvirlarni tozalash
│   └── ingest_book.py          # Agronomiya kitoblarini kiritish
├── tests/                      # Pytest avtomatlashtirilgan testlari (56 ta test)
├── AGENTS.md                   # Agentlar va ishlab chiquvchilar uchun qoidalar
├── pyproject.toml              # Loyiha metadata va pytest sozlamalari
├── requirements.txt            # Python bog'liqliklari ro'yxati
└── README.md                   # Ishga tushirish qo'llanmasi
```
