# ZaminTahlil MVP

ZaminTahlil GeoJSON dala konturi bo‘yicha Sentinel-2 L2A ning eng yangi beshta haqiqiy
kuzatuvini qayta ishlaydigan FastAPI web-ilova. Tahlil faqat beshta qat’iy ruxsat etilgan
indeksdan foydalanadi: `NDVI`, `NDMI`, `NDRE`, `EVI`, `BSI`.

## Asosiy imkoniyatlar

- WGS84 GeoJSON `Polygon` validatsiyasi, geometriya hash’i va geodezik maydon;
- Sentinel Hub OAuth, Catalog va Process API orqali oxirgi 5 tasvir hamda tanlangan sanadan
  hozirgacha tarixiy metrikalarni yuklash;
- 10 m grid, reflektansga bilinear va SCL/dataMask qatlamiga nearest-neighbor resampling;
- RGB, QA va beshta indeksning qat’iy `[-1, 1]` heatmaplari;
- Esri fon xaritasidagi tasvir ko‘ruvchi, ko‘k dala chegarasi va A/B swipe solishtiruvi;
- beshta indeks uchun yillik va ixtiyoriy boshlanish sanali dinamika line graph’i;
- qizil, sariq va yashil guruhlarga bo‘lingan AI tavsiyasi, har guruhda 0–3 band;
- oxirgi 10 ta foydalanuvchi chat xabari faqat browser `sessionStorage` ida.

## O‘rnatish va ishga tushirish

Python 3.12+ kerak.

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp .env.example .env
.venv/bin/uvicorn app.main:app --reload
```

So‘ng `http://127.0.0.1:8000` ni oching. Frontend Leaflet, Chart.js va Esri tilelari,
backend esa Sentinel Hub va OpenAI uchun internetga ulanishi kerak.

## Environment variablelar

```dotenv
SENTINEL_HUB_CLIENT_ID=
SENTINEL_HUB_CLIENT_SECRET=
OPENAI_API_KEY=
DATABASE_PATH=./data/zamintahlil.sqlite3
ARTIFACT_DIR=./data/artifacts
CLOUD_FREE_THRESHOLD=20
SENTINEL_TIMEOUT_SECONDS=45
OPENAI_TIMEOUT_SECONDS=45
OPENAI_PRIMARY_MODEL=gpt-5.4-nano
OPENAI_FALLBACK_MODEL=gpt-5.4-mini
```

Sentinel Hub/CDSE OAuth client ID va secret hamda OpenAI kaliti faqat server `.env`
faylida saqlanadi. Ular frontendga yoki loglarga chiqarilmaydi.

## Ma’lumot va hisoblash oqimi

Oddiy tahlil Catalog natijasini acquisition vaqti bo‘yicha kamayish tartibida so‘rab, eng yangi
beshtasini oladi. Yillik dinamika panelidagi boshlanish sanasi va `Hozirgacha yuklash` tugmasi esa
shu sanadan joriy kungacha Catalog sahifalarini ketma-ket olib, faqat yangi product/revisionlarni
qayta ishlaydi. Tarixiy kuzatuvlar uchun grafikni quradigan `.npy` indeks qiymatlari saqlanadi;
og‘ir PNG tasvirlar va tasvir ko‘ruvchi esa avvalgidek faqat eng yangi beshta acquisition bilan
cheklanadi.

Faqat quyidagi formulalar ishlatiladi:

- NDVI: `(B8 - B4) / (B8 + B4)`;
- NDMI: `(B8 - B11) / (B8 + B11)`;
- NDRE: `(B8A - B5) / (B8A + B5)`;
- EVI: `2.5 * (B8 - B4) / (B8 + 6*B4 - 7.5*B2 + 1)`;
- BSI: `((B11 + B4) - (B8 + B2)) / ((B11 + B4) + (B8 + B2))`.

Indeks piksel qiymatlari `.npy` ichki cache’da saqlanadi. `min`, `mean`, `median`, `max`
SQLite schema’sida yo‘q, acquisition API’sida qaytmaydi va frontendda ko‘rsatilmaydi. Bu to‘rtta
statistika faqat yangi acquisition sabab AI tavsiyasi yaratiladigan paytda hisoblanadi.

Yillik dinamika endpointi har acquisition/indeks uchun yagona grafik qiymatini qaytaradi. API’da
`min/mean/median/max` variantlari yoki agregat query parametri yo‘q; `null` bulut/no-data sifatida
grafik uzilishi bo‘lib qoladi. Tarixiy yuklash idempotent: avval qayta ishlangan acquisition
takroriy so‘rovda Sentinel Process API’dan yana yuklanmaydi.

## AI tavsiyasi

Asosiy model `gpt-5.4-nano`, retrydan keyingi fallback `gpt-5.4-mini`. Structured output:

- `red`: qilinishi shart bo‘lgan ishlar;
- `yellow`: chorasi ko‘rilishi kerak bo‘lgan ishlar;
- `green`: yaxshi jarayonlar.

Har bir ro‘yxat 0–3 banddan iborat. AI’ga faqat dala metadata’si, yangi acquisition metadata’si
va beshta indeksning oxirgi besh kuzatuvi uchun ayni paytda hisoblangan statistikalar yuboriladi.

## Artifact va schema

PNG va `.npy` fayllar `ARTIFACT_DIR` ostida field/product/revision/render-version bo‘yicha
joylashadi. Joriy render versiyasi `v2-top5-fixed-grid-gamma22`. SQLite schema versiyasi `2`;
startup migratsiyasi eski `index_stats` jadvalini olib tashlaydi va structured advice ustunini
qo‘shadi. Tasvir endpointi faqat SQLite’da ro‘yxatlangan joriy render versiyadagi qatlamni beradi.

Eski/orphan PNG fayllarni avval dry-run bilan ko‘ring, keyin tekshirib o‘chiring:

```bash
.venv/bin/python scripts/cleanup_artifacts.py
.venv/bin/python scripts/cleanup_artifacts.py --apply
```

## API

- `POST /api/fields`, `GET /api/fields`, `GET /api/fields/{id}`;
- `POST /api/fields/{id}/analyze` (`latest` yoki `latest_cloud_free`);
- `GET /api/fields/{id}/acquisitions`;
- `GET /api/fields/{id}/annual-metrics?year=2026`;
- `POST /api/fields/{id}/historical-metrics` (`{"from_date":"2025-01-01"}`);
- `GET /api/fields/{id}/historical-metrics?from_date=2025-01-01`;
- `GET /api/fields/{id}/acquisitions/{acquisition_id}/artifacts`;
- `GET /api/fields/{id}/acquisitions/{acquisition_id}/images/{layer}`;
- `GET /api/fields/{id}/recommendation`;
- `POST /api/fields/{id}/chat`.

Interaktiv schema: `http://127.0.0.1:8000/docs`.

## Tekshiruvlar

```bash
.venv/bin/ruff check --no-cache app tests
.venv/bin/ruff format --check --no-cache app tests
.venv/bin/mypy --cache-dir /tmp/zamintahlil-mypy-cache app
.venv/bin/pytest -q -p no:cacheprovider
node --check app/static/app.js
```

Unit/integration testlar top-5 tasvir retention’i, tarixiy Catalog pagination’i va metric cache’i,
on-demand AI statistikasi, structured advice, annual endpoint, geometriya, render va xavfsiz
artifact endpointlarini qamrab oladi. Haqiqiy Sentinel Hub/OpenAI credentials va browser smoke
testi kalitlarsiz bajarilmaydi.
