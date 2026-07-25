# ZaminTahlil MVP

ZaminTahlil GeoJSON dala konturi bo‘yicha Sentinel-2 L2A ning eng yangi beshta haqiqiy
kuzatuvini qayta ishlaydigan FastAPI web-ilova. Tahlil faqat beshta qat’iy ruxsat etilgan
indeksdan foydalanadi: `NDVI`, `NDMI`, `NDRE`, `EVI`, `BSI`.

## Asosiy imkoniyatlar

- WGS84 GeoJSON `Polygon` validatsiyasi, geometriya hash’i va geodezik maydon;
- Sentinel Hub OAuth, Catalog va Process API orqali oxirgi 5 tasvir hamda tanlangan sanadan
  hozirgacha tarixiy metrikalarni yuklash;
- 10 m grid, reflektansga bilinear va SCL/dataMask qatlamiga nearest-neighbor resampling;
  qayta ishlatiladigan HTTP klient (keep-alive), OAuth token keshi va rasterlarning
  parallel yuklanishi (3 gacha) orqali tezlashtirilgan;
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
# Ish rejimi: demo (standart) yoki prod
APP_ENV=demo
SENTINEL_HUB_CLIENT_ID=
SENTINEL_HUB_CLIENT_SECRET=
# Agar identity.dataspace.copernicus.eu bloklangan bo'lsa, HTTP proksi manzili (ixtiyoriy)
# Masalan: SENTINEL_PROXY=http://127.0.0.1:8080
SENTINEL_PROXY=
OPENAI_API_KEY=
DATABASE_PATH=./data/zamintahlil.sqlite3
ARTIFACT_DIR=./data/artifacts
CLOUD_FREE_THRESHOLD=20
SENTINEL_TIMEOUT_SECONDS=45
OPENAI_TIMEOUT_SECONDS=45
OPENAI_PRIMARY_MODEL=gpt-5.4-nano
OPENAI_FALLBACK_MODEL=gpt-5.4-mini
# Prod rejimi uchun ruxsat etilgan CORS kelib chiqish manzalari (vergul bilan)
CORS_ORIGINS=
```

Sentinel Hub/CDSE OAuth client ID va secret hamda OpenAI kaliti faqat server `.env`
faylida saqlanadi. Ular frontendga yoki loglarga chiqarilmaydi.

`APP_ENV=demo` (standart) — to‘liq debug rejim: Swagger `/docs`, `/redoc` va
`/openapi.json` yoqilgan, CORS `*` fallback bilan, xato javoblari batafsil. `APP_ENV=prod`
esa API hujjatlarini o‘chiradi (404), umumiy `*` CORS’ni rad etadi va faqat `CORS_ORIGINS`
ro‘yxatidagi manzillarni qabul qiladi (bo‘sh ro‘yxat = barcha cross-origin so‘rovlar
rad etiladi), xato detalini loglarga yo‘naltirib foydalanuvchiga umumiy xabar ko‘rsatadi.
Prod rejimda, shuningdek, loglardagi maxfiy qiymatlar (Bearer tokenlar, `sk-...` kalitlar,
secret/parollar va sozlangan kalitlar) `***` bilan maskalanadi.

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

Indeks piksel qiymatlari `.npy` ichki cache’da saqlanadi. `mean`, `min`, `median`, `max`
hamda `layer_valid_pixel_count` har bir artifact uchun SQLite schema’sida saqlanadi,
`GET /api/fields/{id}/acquisitions/{acquisition_id}/artifacts` javobida (`ArtifactOut`) qaytadi
va sun’iy yo‘ldosh tasviri ko‘ruvchisining meta panelida ko‘rsatiladi. Meta panel barcha
foydalanuvchiga ahamiyatli backend maydonlarni — qatlam, sana, bulut, mahsulot ID
(`product_id`), yaroqli piksel soni (`valid_pixel_count`), qayta ishlangan sana, indeks
qatlamlari uchun o‘rtacha/mediana/min–max va qatlam yaroqli piksellari, tasvir o‘lchami,
render versiyasi va (borsa) qayta ishlash xatosini — ko‘rsatadi. Yangi acquisition sabab AI
tavsiyasi yaratiladigan paytda ham ayni statistikalar hisoblanadi.

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

## AI suhbat (chat) tili

`POST /api/fields/{id}/chat` so‘rovda ixtiyoriy `language` maydoni (`uz-latn`, `uz-cyrl`, `ru`
yoki `en`) bilan keladi; frontend har bir chat so‘rovga `language: i18n.current` qo‘shadi.
Javob tili quyidagi ustuvarlik bo‘yicha aniqlanadi:

1. foydalanuvchi xabaridagi **to‘g‘ridan-to‘g‘ri til so‘rovi** (masalan, “Explain NDVI in
   English.”, “O‘zbek tilida tushuntiring.”) — LLM system prompt’dagi istisno bandi orqali
   bajaradi;
2. oxirgi foydalanuvchi xabarining **avtomatik aniqlangan tili** — `app/language.py` dagi sof
   Python `detect_language(text)` (tashqi kutubxonasiz): o‘zbek lotin/amerikalik alifbodagi
   lotin stop-so‘zlari, ў қ ғ ҳ kabi o‘zbek kiril harflari va umumiy kiril uchun `ru`;
3. frontend tomonidan tanlangan til.

Til ma’lum bo‘lsa, chat system prompt’iga “Javob tili: ...” direktivasi qo‘shiladi.
Misol: frontend o‘zbek + “Explain NDVI in English.” → inglizcha javob; frontend ingliz +
“Объясни индекс NDVI.” → ruscha javob; frontend rus + “O‘zbek tilida tushuntiring.” →
o‘zbekcha javob.

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

Interaktiv schema: `http://127.0.0.1:8000/docs` (faqat `APP_ENV=demo` rejimida; prod’da 404).

## Ish rejimi va xavfsizlik (APP_ENV)

`app/main.py` endi factory `create_app(settings: Settings | None = None) -> FastAPI` orqali
yaratiladi (modul darajasidagi `app = create_app()` uvicorn uchun o‘zgarmaydi). Rejim `.env`
dagi `APP_ENV` orqali tanlanadi.

- **Demo (`APP_ENV=demo`, standart)** — Swagger `/docs`, `/redoc`, `/openapi.json` yoqilgan;
  CORS `*` fallback bilan ishlaydi; 502 xato javoblari batafsil `str(exc)` ko‘rsatadi;
  to‘liq debug qobiliyati saqlanadi.
- **Prod (`APP_ENV=prod`)** — API hujjatlari o‘chirilgan (404); umumiy catch-all istisno
  handler `{"detail": "Ichki server xatosi"}` (500) qaytaradi, haqiqiy xato esa loglarga
  yoziladi; Sentinel/AI 502 javoblari umumiy o‘zbekcha detail (“Sun’iy yo‘ldosh xizmatida
  xatolik” / “AI xizmatida xatolik”) beradi, detal faqat loglarda; CORS faqat `CORS_ORIGINS`
  ro‘yxatidagi manzillarni qabul qiladi (`*` ishlatilmaydi, bo‘sh ro‘yxat = barcha
  cross-origin so‘rovlar rad etiladi).

Har bir javobga (har ikki rejimda) `app/security.py` dagi `SecurityHeadersMiddleware`
(pure ASGI) quyidagi xavfsizlik sarlavhalarini qo‘shadi: `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`,
`Permissions-Policy: camera=(), microphone=(), geolocation=()`. HTTPS so‘rovlar uchun
(scheme=https yoki `x-forwarded-proto: https`) qo‘shimcha `Strict-Transport-Security:
max-age=31536000; includeSubDomains` qo‘shiladi.

Prod rejimida `configure_logging(settings)` root logger handlerlariga
`SensitiveDataFilter` ulanadi: u Bearer tokenlar, `sk-...` kalitlar, `key=value` ko‘rinishidagi
secretlar (client_secret, api_key, token, password, authorization, cookie va h.k.) hamda
sozlangan maxfiy qiymatlarni (OpenAI kaliti, Sentinel client id/secret) `***` bilan maskalaydi.

## Tekshiruvlar

```bash
.venv/bin/ruff check --no-cache app tests
.venv/bin/ruff format --check --no-cache app tests
.venv/bin/mypy --cache-dir /tmp/zamintahlil-mypy-cache app
.venv/bin/pytest -q -p no:cacheprovider
node --check app/static/app.js
```

Unit/integration testlar top-5 tasvir retention’i, tarixiy Catalog pagination’i va metric cache’i,
on-demand AI statistikasi, structured advice, annual endpoint, geometriya, render, xavfsiz
artifact endpointlari, `APP_ENV=prod` xavfsizligi (hujjatlar o‘chirilgan, security headers/HSTS,
CORS cheklovi, umumiy 500, loglarni maskalash) hamda chat tili avtomatik aniqlash va
direktiv ustuvorligini qamrab oladi — jami 43 test yashil. Haqiqiy Sentinel Hub/OpenAI
credentials va browser smoke testi kalitlarsiz bajarilmaydi.
