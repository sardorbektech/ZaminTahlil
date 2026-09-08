# ZaminTahlil — FRONTEND.md

## 1. Hujjat maqsadi

Ushbu hujjat **ZaminTahlil** web-platformasining frontend arxitekturasi,
UX/UI konsepsiyasi, sahifalar, komponentlar, API integratsiyasi, state
management, responsive dizayn, loading/error holatlari va accessibility
talablarini belgilaydi.

Frontendning asosiy vazifasi — murakkab satellite, agronomik, ML va RAG
ma’lumotlarini dehqon, agronom va texnik foydalanuvchi uchun **tez
tushunarli, ishonchli va amaliy** ko’rinishga keltirish.

Backend FastAPI REST API orqali ishlaydi. Mavjud API tarkibida field
management, Sentinel-2 analysis, historical metrics, recommendations,
chat/RAG va yield prediction modullari mavjud.

------------------------------------------------------------------------

# 2. Product Vision

## 2.1. Asosiy prinsip

ZaminTahlil frontend quyidagi savolga javob berishi kerak:

> **“Mening dalalarimning holati qanday va hozir nima qilishim kerak?”**

Shuning uchun dashboard faqat ma’lumot ko’rsatadigan monitoring paneli
emas, balki **decision-support interface** bo’ladi.

Foydalanuvchi sahifaga kirganda eng muhim ma’lumotlar yuqorida chiqadi:

1.  Dala holati
2.  Oxirgi Sentinel-2 kuzatuvi
3.  Muammoli zonalar
4.  AI tavsiyasi
5.  Hosildorlik bashorati
6.  Vaqt bo’yicha o’zgarish
7.  AI agronom bilan chat

------------------------------------------------------------------------

# 3. Target Users

## 3.1. Dehqon

Unga texnik tafsilotlar minimal ko’rsatiladi.

Asosiy ma’lumotlar:

- Dala maydoni
- Ekin turi
- Holat
- Muammo
- Tavsiya
- Hosil bashorati
- Xarita

## 3.2. Agronom

Batafsil monitoring kerak:

- NDVI
- NDRE
- NDMI
- EVI
- BSI
- tarixiy grafiklar
- hotspotlar
- bulutlilik
- Sentinel acquisition
- weather
- RAG manbalari
- AI tavsiyalar

## 3.3. Texnik / admin

Qo’shimcha:

- RAG kitoblari
- active/inactive books
- model tanlash
- database purge
- API health
- debugging status

------------------------------------------------------------------------

# 4. UX Principles

Frontend quyidagi 10 prinsip asosida quriladi:

1.  **Map first** — dala xaritasi markaziy element.
2.  **Action first** — foydalanuvchiga keyingi harakat aniq
    ko’rsatiladi.
3.  **Progressive disclosure** — murakkab ma’lumotlar kerak bo’lganda
    ochiladi.
4.  **No information overload** — bitta ekranda haddan tashqari ko’p
    grafik bo’lmaydi.
5.  **Mobile friendly** — telefon ekranida ham asosiy funksiyalar
    ishlaydi.
6.  **Fast feedback** — har bir API amali loading/progress bilan
    ko’rsatiladi.
7.  **Trust by provenance** — AI javobining manbasi ko’rsatiladi.
8.  **Consistent terminology** — indeks nomlari va agronomik terminlar
    barcha sahifalarda bir xil.
9.  **Accessible colors** — rangning o’zi yagona signal bo’lmaydi.
10. **Safe destructive actions** — o’chirish amallari alohida
    tasdiqlanadi.

------------------------------------------------------------------------

# 5. Visual Design Direction

## 5.1. Umumiy uslub

Tavsiya qilinadigan uslub:

**Modern AgriTech + Satellite Intelligence + Professional SaaS**

Interfeys:

- clean
- premium
- professional
- light
- data-driven
- subtle glassmorphism
- soft shadows
- rounded cards
- dense but readable dashboards

Frontend mavjud stack bilan mos bo’lishi kerak:

- Vanilla JavaScript ES6+
- Vanilla CSS
- Leaflet
- Leaflet-Draw
- Chart.js
- Marked.js
- DOMPurify

Bu stack loyiha ABOUT hujjatida ko’rsatilgan frontend texnologiyalariga
mos keladi.

------------------------------------------------------------------------

# 6. Color System

Ranglar ma’noli statuslarga ajratiladi.

## 6.1. Primary

``` text
Primary:        #166534
Primary Dark:   #14532D
Primary Soft:   #DCFCE7
```

## 6.2. Accent

``` text
Satellite Blue: #2563EB
AI Purple:       #7C3AED
```

## 6.3. Status

``` text
Success: #16A34A
Warning: #D97706
Danger:  #DC2626
Info:    #2563EB
```

## 6.4. Neutral

``` text
Background: #F6F8F7
Surface:    #FFFFFF
Border:     #E5E7EB
Text:       #17201A
Muted:      #667085
```

### Muhim

Statusni faqat rang bilan ko’rsatmaslik kerak.

Masalan:

``` text
🟢 Yaxshi
🟡 Diqqat
🔴 Muammo
```

------------------------------------------------------------------------

# 7. Typography

Tavsiya:

``` text
Font:
Inter, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif
```

Hierarxiya:

``` text
H1: 28–36px
H2: 22–28px
H3: 18–22px
Body: 14–16px
Small: 12–13px
Metric: 28–40px
```

Dashboard metriclarida katta raqam va kichik label ishlatiladi.

Misol:

``` text
72.4
NDVI o'rtacha
```

------------------------------------------------------------------------

# 8. Application Layout

Desktop layout:

``` text
┌────────────────────────────────────────────────────────────┐
│ Top Header                                                 │
├───────────────┬────────────────────────────────────────────┤
│               │                                            │
│ Sidebar       │ Main Content                               │
│               │                                            │
│ Dashboard     │                                            │
│ Fields        │                                            │
│ Analysis      │                                            │
│ Yield         │                                            │
│ AI Agronom    │                                            │
│ Knowledge     │                                            │
│ Settings      │                                            │
│               │                                            │
└───────────────┴────────────────────────────────────────────┘
```

Desktop:

``` text
Sidebar: 250–280px
Header: 64–72px
Main padding: 24–32px
```

Mobile:

``` text
┌──────────────────────┐
│ Header               │
├──────────────────────┤
│ Main                 │
│                      │
│ Cards                │
│                      │
│ Map                  │
│                      │
│ Charts               │
├──────────────────────┤
│ Bottom Navigation    │
└──────────────────────┘
```

------------------------------------------------------------------------

# 9. Global Header

Header elementlari:

### Chap tomon

- ZaminTahlil logo
- sahifa nomi

### O’ng tomon

- language selector
- system status
- current field
- profile/settings

Language:

``` text
O'zbekcha
Ўзбекча
Русский
English
```

Backend chat API ushbu 4 tilni qo’llab-quvvatlaydi.

------------------------------------------------------------------------

# 10. Sidebar Navigation

Sidebar:

``` text
🌍 Dashboard
🌾 Mening dalalarim
🛰️ Sun'iy yo'ldosh
📊 Monitoring
🌱 Hosildorlik
🤖 AI Agronom
📚 Bilimlar bazasi
⚙️ Sozlamalar
```

Active item:

- left accent bar
- subtle background
- icon
- bold text

Sidebar pastida:

``` text
System status
● Online
```

------------------------------------------------------------------------

# 11. Main Dashboard

## 11.1. Dashboard maqsadi

Dashboard foydalanuvchiga 10–15 soniya ichida umumiy holatni
tushuntirishi kerak.

## 11.2. Top metrics

``` text
┌────────────┬────────────┬────────────┬────────────┐
│ Dalalar    │ Maydon     │ Monitoring │ Hosil      │
│ 12         │ 284.6 ha   │ 94%        │ 5.8 t/ha   │
└────────────┴────────────┴────────────┴────────────┘
```

Agar real qiymat mavjud bo’lmasa:

``` text
— 
Ma'lumot mavjud emas
```

`0` ni noto’g’ri ravishda “ma’lumot yo’q” sifatida ishlatmaslik kerak.

------------------------------------------------------------------------

# 12. Field Management Page

## 12.1. Fields list

Har bir field card:

``` text
┌──────────────────────────────────────────────┐
│ 🌾 Paxta                         🟢 Yaxshi   │
│                                              │
│ 42.8 ha                                      │
│ Sulton                                       │
│ Ekilgan: 2026-04-18                          │
│                                              │
│ Oxirgi kuzatuv: 2026-09-04                   │
│ NDVI: 0.71                                   │
│                                              │
│ [Tahlil] [Ochish]                            │
└──────────────────────────────────────────────┘
```

Field backenddan quyidagi ma’lumotlarni oladi:

- id
- public_id
- geometry
- area_hectares
- crop_name
- planted_on
- growth_stage
- created_at
- updated_at

------------------------------------------------------------------------

# 13. Add Field Flow

Foydalanuvchi yangi dala qo’shganda 3 bosqichli wizard ishlatiladi.

## Step 1 — Xarita

``` text
Dala chegarasini chizing

[ Polygon ]

[Chizishni boshlash]
```

Leaflet-Draw ishlatiladi.

## Step 2 — Dala ma’lumotlari

``` text
Ekin turi
[ Paxta ▼ ]

Ekilgan sana
[ 2026-04-18 ]

Rivojlanish bosqichi
[ Vegetativ o'sish ▼ ]
```

## Step 3 — Confirm

``` text
Maydon: 42.8 ha
Ekin: Paxta
Ekish sanasi: 18 Apr 2026

[Bekor qilish] [Dalani saqlash]
```

Maydon backend tomonidan geodezik hisoblanadi.

------------------------------------------------------------------------

# 14. Field Detail Page

Field detail — platformaning eng muhim sahifasi.

Layout:

``` text
┌─────────────────────────────────────────────────────────┐
│ Paxta · Sulton                         42.8 ha          │
│ Public ID: a7k9b2x4                                     │
├─────────────────────────────────────────────────────────┤
│ Status banner                                           │
├──────────────────────────────┬──────────────────────────┤
│                              │ Quick metrics             │
│                              │                          │
│            MAP               │ NDVI                     │
│                              │ NDRE                     │
│                              │ NDMI                     │
│                              │ Cloud                    │
│                              │ Last observation         │
├──────────────────────────────┴──────────────────────────┤
│ AI Recommendation                                       │
├─────────────────────────────────────────────────────────┤
│ Satellite analysis                                      │
├─────────────────────────────────────────────────────────┤
│ Historical charts                                       │
├─────────────────────────────────────────────────────────┤
│ Yield prediction                                        │
└─────────────────────────────────────────────────────────┘
```

------------------------------------------------------------------------

# 15. Field Status Banner

Status avtomatik aniqlangan bo’lishi mumkin:

### Green

``` text
🟢 Dala holati yaxshi

Vegetatsiya ko'rsatkichlari barqaror.
```

### Yellow

``` text
🟡 E'tibor talab qiladigan holat

Ayrim hududlarda stress belgilari kuzatilmoqda.
```

### Red

``` text
🔴 Muammo aniqlangan

Dalaning ayrim qismlarida kuchli anomaliya mavjud.
```

Status card ichida:

- status
- confidence
- last update
- primary reason

------------------------------------------------------------------------

# 16. Satellite Analysis Page

## 16.1. Main map

Map markaziy komponent bo’ladi.

Layers:

``` text
Base:
- Esri World Imagery

Overlay:
- Field boundary
- RGB
- NDVI
- NDMI
- NDRE
- EVI
- BSI
- QA
```

Backend API mavjud layer nomlari RGB, NDVI, NDMI, NDRE, EVI, BSI va QA
ni qaytaradi.

------------------------------------------------------------------------

# 17. Layer Selector

Map ustida compact control:

``` text
Layer

○ RGB
● NDVI
○ NDMI
○ NDRE
○ EVI
○ BSI
○ QA
```

Har bir index uchun legend ko’rsatiladi.

Misol:

``` text
NDVI

Low                         High
0.0 ─────────────────────── 1.0
```

------------------------------------------------------------------------

# 18. Acquisition Selector

``` text
Kuzatuv sanasi

04 Sep 2026  ·  8% cloud
31 Aug 2026  ·  12% cloud
27 Aug 2026  ·  4% cloud
23 Aug 2026  ·  16% cloud
19 Aug 2026  ·  7% cloud
```

Bir kun ichidagi takroriy Sentinel acquisition frontendda bitta sana
sifatida ko’rsatiladi.

------------------------------------------------------------------------

# 19. A/B Swipe Viewer

A/B mode:

``` text
┌───────────────────────────────────────────────┐
│ A: NDVI · 04 Sep       B: NDVI · 19 Aug       │
│                                               │
│              [SWIPE MAP]                      │
│                                               │
└───────────────────────────────────────────────┘
```

Control:

``` text
A layer
A date

B layer
B date
```

Swipe divider draggable bo’ladi.

Mobile qurilmada:

- horizontal swipe
- yoki split toggle

------------------------------------------------------------------------

# 20. Pixel / Artifact Statistics

Layer tanlanganda side panel:

``` text
NDVI

O'rtacha
0.71

Median
0.73

Min
0.22

Max
0.89

Valid pixels
18,422
```

Artifact API ushbu statistikalar uchun:

- mean_value
- min_value
- median_value
- max_value
- layer_valid_pixel_count
- hotspot_coordinates

ma’lumotlarini qaytaradi.

------------------------------------------------------------------------

# 21. Hotspot UX

Agar `hotspot_coordinates` mavjud bo’lsa:

Mapda:

``` text
⚠ Hotspot
```

marker ko’rsatiladi.

Marker bosilganda:

``` text
Muammoli hudud

Koordinata:
41.123456, 69.123456

Asosiy signal:
NDRE past

[ Batafsil tahlil ]
```

Hotspot foydalanuvchini to’g’ridan-to’g’ri muammoli joyga olib borishi
kerak.

------------------------------------------------------------------------

# 22. Anomaly Dashboard

Alohida analysis panel:

``` text
Aniqlangan muammolar

🔴 Yuqori xavf
2 zona

🟡 O'rta xavf
4 zona

🟢 Normal
87% maydon
```

Har bir anomaly:

``` text
#1
Shimoliy-g'arbiy qism

Maydon: 0.84 ha
Risk: Yuqori

Ehtimoliy sabab:
Namlik stressi

[ Xaritada ko'rsatish ]
```

------------------------------------------------------------------------

# 23. Historical Metrics

Chart.js yordamida line chart.

Default:

``` text
NDVI
NDMI
NDRE
EVI
BSI
```

User checkbox orqali indekslarni yoqadi/o’chiradi.

Chart:

- responsive
- tooltip
- date formatting
- legend
- zoom/pan faqat desktopda kerak bo’lsa
- empty state

Tooltip:

``` text
📅 04 Sep 2026

NDVI   0.71
NDMI   0.46
NDRE   0.52
EVI    0.48
BSI    0.12
```

Yillik series endpoint `year` parametri orqali chaqiriladi.

------------------------------------------------------------------------

# 24. Historical Range Selector

``` text
Davr

[ 01 Jan 2026 ] → [ 08 Sep 2026 ]

[30 kun] [90 kun] [Mavsum] [Yil]
```

Historical metrics endpointga:

``` json
{
  "from_date": "2026-01-01"
}
```

ko’rinishida yuboriladi.

------------------------------------------------------------------------

# 25. Recommendation Page

Recommendation UI uch guruhga bo’linadi.

## Red

``` text
🔴 Shoshilinch

1. ...
2. ...
3. ...
```

## Yellow

``` text
🟡 Kuzatish kerak

1. ...
2. ...
```

## Green

``` text
🟢 Yaxshi holat

1. ...
2. ...
```

Backend `AdviceGroups` modeli red/yellow/green guruhlarini beradi.

------------------------------------------------------------------------

# 26. Recommendation Detail

Har bir tavsiya:

``` text
Muammo
↓

Dalil
↓

Ehtimoliy sabab
↓

Amaliy tavsiya
↓

Qachon qayta tekshirish kerak
```

Frontend backendda yo’q ma’lumotni o’zi uydirmaydi.

------------------------------------------------------------------------

# 27. Yield Prediction Page

Hosildorlik sahifasi foydalanuvchi uchun “prediction dashboard”
ko’rinishida bo’ladi.

## Hero metric

``` text
Kutilayotgan hosildorlik

5.82 t/ga

Kutilayotgan interval

5.20 — 6.40 t/ga

Jami kutilayotgan hosil

249.1 tonna
```

Backend `YieldPredictResponse` ushbu qiymatlarni beradi:

- predicted_yield_t_ha
- yield_min_expected
- yield_max_expected
- total_expected_yield_tons
- total_yield_min_tons
- total_yield_max_tons
- field_area_ha

------------------------------------------------------------------------

# 28. Yield Model Selector

Model selector:

``` text
Model

[ CatBoost ▼ ]

CatBoost
LightGBM
XGBoost
RandomForest
GradientBoosting
```

Mavjud model ro’yxati `/api/yield/models` orqali olinadi.

Default:

``` text
CatBoost
```

------------------------------------------------------------------------

# 29. Yield Prediction Form

``` text
Ekin
[ Avtomatik ]

Ekish sanasi
[ Avtomatik ]

Hosil sanasi
[ Ixtiyoriy ]

Model
[ CatBoost ]

[ Hosilni bashorat qilish ]
```

Field ma’lumotlari mavjud bo’lsa, formani avtomatik to’ldirish kerak.

------------------------------------------------------------------------

# 30. Top Features

Backend `top_features` qaytaradi.

UI:

``` text
Eng muhim omillar

1. NDVI
██████████████████  31%

2. Soil moisture
██████████████      24%

3. Temperature
███████████         18%

4. NDRE
████████            13%
```

Har bir feature:

- name
- importance
- description

bilan ko’rsatiladi.

------------------------------------------------------------------------

# 31. Phenology Timeline

Chart.js line chart:

``` text
NDVI
NDRE
NDMI
Temperature
Rain
Soil moisture
```

Backend phenology pointlarida:

- month
- ndvi
- evi
- ndre
- ndmi
- s1_vh
- s1_vv_vh
- temp_mean
- rain_sum
- soil_moisture

mavjud.

Desktopda ikki chartdan foydalanish mumkin:

1.  vegetation
2.  environment

Mobileda bitta chart + selector.

------------------------------------------------------------------------

# 32. Yield Data Sources

Predictionning ishonchliligini oshirish uchun manbalar alohida cardlar
bilan ko’rsatiladi.

Misol:

``` text
🛰️ Sentinel-2
Real optik kuzatuvlar

🌤️ Agrometeorologiya
Harorat, yog'in, radiatsiya

🌱 Tuproq
3 ta chuqurlikdagi namlik

📡 Sentinel-1
VV / VH radar ma'lumotlari
```

Bu ma’lumotlar `data_sources` API response orqali keladi.

------------------------------------------------------------------------

# 33. AI Agronom Page

AI chat platformaning asosiy UX elementlaridan biri.

Layout:

``` text
┌────────────────────────────────────────────────────┐
│ AI Agronom                                         │
├──────────────────────────────┬─────────────────────┤
│                              │ Dala konteksti      │
│ Chat                         │                     │
│                              │ Ekin                │
│ User                         │ Maydon              │
│                              │ Oxirgi NDVI         │
│ AI                           │ Oxirgi observation  │
│                              │                     │
├──────────────────────────────┴─────────────────────┤
│ [Savolingizni yozing...]                 [Yuborish]│
└────────────────────────────────────────────────────┘
```

------------------------------------------------------------------------

# 34. Chat Message Design

User:

``` text
Menimcha dalaning janubiy qismi sust rivojlanmoqda.
Nima sabab bo'lishi mumkin?
```

AI:

``` text
Janubiy qismda NDVI pasayishi kuzatilmoqda.
Bunga namlik stressi yoki o'simlik rivojlanishidagi
farq sabab bo'lishi mumkin.

Tavsiyam:
1. Janubiy hududni xaritada tekshiring.
2. NDMI va NDRE ni solishtiring.
3. Sug'orish bir tekisligini nazorat qiling.
```

------------------------------------------------------------------------

# 35. RAG Mode Selector

Chat oynasida advanced setting:

``` text
AI rejimi

🔬 Advanced RAG
⚡ All-in-One
🕸️ Graph RAG
📚 Naive RAG
🤖 Umumiy AI
```

Backend quyidagi qiymatlarni qabul qiladi:

``` text
advanced
all_in_one
graph
naive
direct_llm
auto
```

Default:

``` text
advanced
```

------------------------------------------------------------------------

# 36. RAG Source Badges

AI javobining pastida badge:

``` text
🔬 Advanced RAG
```

yoki:

``` text
🕸️ Graph RAG
```

yoki:

``` text
📚 Naive RAG
```

yoki:

``` text
🤖 Umumiy LLM
```

Badge ranglari farqlanadi, lekin accessibility uchun text va icon ham
mavjud bo’ladi.

------------------------------------------------------------------------

# 37. RAG Sources Drawer

AI javobida source mavjud bo’lsa:

``` text
📚 Manbalar (3)
```

bosilganda drawer:

``` text
Agronomiya asoslari

Sahifa 42

Score: 0.89

"..."

[Manbani ochish]
```

Backend `RAGSourceOut`:

- document_name
- page_number
- score
- text

qaytaradi.

Frontend source matnini xavfsiz render qilish uchun DOMPurify ishlatadi.

------------------------------------------------------------------------

# 38. Chat Summary

Chat tarixidan tashqari summary card:

``` text
📝 Dala bo'yicha qisqa xulosa

Dalada umumiy vegetatsiya yaxshi.
Janubiy qismda namlik stressi ehtimoli bor.
Keyingi kuzatuv tavsiya etiladi.

12 ta xabar
Yangilangan: 08 Sep 2026
```

Backend `/chat/summary` orqali olinadi.

------------------------------------------------------------------------

# 39. Chat History

History panel:

``` text
Bugun
12:31  User
12:32  AI

Kecha
16:42  User
16:43  AI
```

Frontend pagination qo’llashi mumkin, ammo mavjud API faqat history list
qaytaradi; backend pagination keyinchalik qo’shilsa frontend
moslashtiriladi.

------------------------------------------------------------------------

# 40. Knowledge Base Page

RAG books sahifasi foydalanuvchiga oddiy bo’lishi kerak.

``` text
Bilimlar bazasi

Faol kitoblar: 4
Indekslangan: 4

┌─────────────────────────────────────────────┐
│ Agronomiya asoslari                         │
│ 320 pages · 1240 chunks                     │
│                                             │
│ ● AI uchun faol                             │
│                                   [ON/OFF] │
└─────────────────────────────────────────────┘
```

Backend kitoblar uchun:

- name
- size_mb
- total_pages
- chunk_count
- embedding_model
- is_active
- indexed

ma’lumotlarini beradi.

------------------------------------------------------------------------

# 41. Book Toggle

Toggle:

``` text
ON  → RAG qidiruvida ishlatiladi
OFF → RAG qidiruvida ishlatilmaydi
```

Toggle request:

``` json
{
  "is_active": true
}
```

API:

``` text
POST /api/rag/books/{book_id}/toggle
```

Frontend optimistic update qilishi mumkin, ammo API xato bersa eski
holatga qaytaradi.

------------------------------------------------------------------------

# 42. Admin / Settings

Settings sahifasida:

### Language

``` text
O'zbekcha
Ўзбекча
Русский
English
```

### Analysis preferences

``` text
Default layer: NDVI
Default analysis: Latest
```

### Danger Zone

``` text
⚠️ Dala ma'lumotlarini tozalash

Barcha dala maydonlari, tahlillar,
xaritalar va chatlar o'chiriladi.

[Rasmiy tasdiqlash]
```

Database purge juda xavfli amal sifatida alohida ko’rsatiladi.

------------------------------------------------------------------------

# 43. Purge Confirmation Modal

Modal:

``` text
Dala ma'lumotlarini o'chirish

Bu amal qaytarib bo'lmaydi.

Quyidagilar o'chiriladi:
• barcha dalalar
• tahlillar
• xaritalar
• tavsiyalar
• chatlar

Agronomik kitoblar saqlanadi.

Tasdiqlash uchun:
[ roziman ]

[Bekor qilish] [Hammasini o'chirish]
```

Frontend parolni oddiy UI loglariga yozmasligi kerak.

------------------------------------------------------------------------

# 44. API Client Architecture

Frontend barcha API chaqiruvlarini bitta `api.js` qatlamidan o’tkazadi.

Tavsiya:

``` text
frontend/
├── index.html
├── styles.css
├── app.js
├── api.js
├── i18n.js
├── state.js
├── components/
│   ├── map.js
│   ├── charts.js
│   ├── fields.js
│   ├── analysis.js
│   ├── yield.js
│   ├── chat.js
│   └── modal.js
├── utils/
│   ├── format.js
│   ├── validation.js
│   └── errors.js
└── assets/
    ├── logo.svg
    └── icons/
```

Agar mavjud loyiha single-file frontenddan foydalansa, yuqoridagi
bo’linish mantiqiy arxitektura sifatida qabul qilinadi va birdaniga
majburiy refactor qilinmaydi.

------------------------------------------------------------------------

# 45. API Base URL

Development:

``` text
http://localhost:8000
```

Production:

``` text
relative URL
```

Tavsiya:

``` javascript
const API_BASE = window.API_BASE || "";
```

Frontend backend bilan bir domen orqali ishlaganda CORS va deployment
murakkabligi kamayadi.

------------------------------------------------------------------------

# 46. API Mapping

## Health

``` text
GET /api/health
```

UI:

``` text
● Online
```

------------------------------------------------------------------------

## Fields

``` text
GET  /api/fields
POST /api/fields
GET  /api/fields/{field_id}
```

------------------------------------------------------------------------

## Analysis

``` text
POST /api/fields/{field_id}/analyze
GET  /api/fields/{field_id}/acquisitions
GET  /api/fields/{field_id}/acquisitions/{acquisition_id}/artifacts
GET  /api/fields/{field_id}/acquisitions/{acquisition_id}/images/{layer_name}
GET  /api/fields/{field_id}/annual-metrics?year=2026
POST /api/fields/{field_id}/historical-metrics
GET  /api/fields/{field_id}/historical-metrics?from_date=2026-01-01
GET  /api/fields/{field_id}/recommendation
```

------------------------------------------------------------------------

## Yield

``` text
GET  /api/yield/models
POST /api/fields/{field_id}/predict-yield
GET  /api/fields/{field_id}/yield-latest
```

------------------------------------------------------------------------

## Chat

``` text
GET  /api/fields/{field_id}/chat/history
GET  /api/fields/{field_id}/chat/summary
POST /api/fields/{field_id}/chat
```

------------------------------------------------------------------------

## RAG

``` text
GET  /api/rag/books
POST /api/rag/books/{book_id}/toggle
```

Admin/internal:

``` text
POST   /api/rag/books/index-file
POST   /api/rag/upload
POST   /api/rag/ingest
GET    /api/rag/documents
DELETE /api/rag/documents/{document_id}
```

Upload/ingest funksiyalari production user UI uchun default ravishda
yashiriladi, chunki loyiha arxitekturasida RAG ingestion
developer-side/offline jarayon sifatida qaraladi.

------------------------------------------------------------------------

# 47. API Error Handling

Frontend HTTP statuslarga qarab UX ko’rsatadi.

## 400

``` text
Kiritilgan ma'lumot noto'g'ri.
Dala chegarasini tekshiring.
```

## 409

``` text
Bu dala avval saqlangan.
```

## 422

``` text
Ma'lumotlar formatini tekshiring.
```

## 500

``` text
Serverda vaqtinchalik muammo yuz berdi.
Keyinroq qayta urinib ko'ring.
```

## Network error

``` text
Internet yoki server bilan aloqa yo'q.
[Qayta urinish]
```

Backend xatosining texnik tracebackini oddiy foydalanuvchiga
ko’rsatmaslik kerak.

------------------------------------------------------------------------

# 48. Loading States

Har bir API request uchun skeleton/loading state bo’lishi kerak.

## Map loading

``` text
🛰️ Sun'iy yo'ldosh ma'lumotlari yuklanmoqda...
```

## Analysis

``` text
Tasvirlar tekshirilmoqda...
Indekslar hisoblanmoqda...
Natijalar tayyorlanmoqda...
```

## Yield

``` text
122 ta parametr tahlil qilinmoqda...
```

## AI

``` text
AI agronom javob tayyorlamoqda...
```

------------------------------------------------------------------------

# 49. Long-running Analysis UX

Analysis request uzoq davom etishi mumkin.

Button:

``` text
[ Tahlil qilish ]
```

request vaqtida:

``` text
[ ◌ Tahlil qilinmoqda... ]
```

Button disabled bo’ladi.

Foydalanuvchi boshqa tugmalarni tasodifan bosib requestni
ko’paytirmasligi kerak.

------------------------------------------------------------------------

# 50. Empty States

## No fields

``` text
🌾 Hali dala qo'shilmagan

Birinchi dalangizni xaritada belgilang.

[ Dala qo'shish ]
```

## No satellite data

``` text
🛰️ Hozircha sun'iy yo'ldosh kuzatuvi topilmadi.

Boshqa sanani tanlang yoki keyinroq qayta urinib ko'ring.
```

## No recommendation

``` text
🤖 Hozircha AI tavsiyasi mavjud emas.

Avval dala tahlilini ishga tushiring.
```

## No yield prediction

``` text
🌱 Hali hosil bashorati mavjud emas.

[ Bashorat qilish ]
```

## No chat

``` text
Suhbatni boshlang.

Masalan:
"Daladagi muammo nimada?"
```

------------------------------------------------------------------------

# 51. Responsive Breakpoints

Tavsiya:

``` text
Mobile:   < 640px
Tablet:   640–1024px
Desktop:  > 1024px
Large:    > 1440px
```

## Mobile

- sidebar → bottom navigation / drawer
- cards → 1 column
- map → full width
- charts → 1 column
- table → horizontal scroll
- chat → full screen

## Tablet

- 2-column cards
- collapsible sidebar

## Desktop

- 3–4 metric cards
- map + side panel
- multi-column dashboard

------------------------------------------------------------------------

# 52. Mobile Map UX

Mobileda map kamida:

``` text
height: 55vh
```

bo’lishi kerak.

Controls:

- locate field
- layers
- zoom
- hotspot
- fullscreen

Mapni pastdagi chartlar ustidan yopib qo’ymaslik kerak.

------------------------------------------------------------------------

# 53. Chart UX

Chartlar:

- responsive
- legend
- tooltip
- empty state
- accessible labels
- date localization

Chartda 100+ point bo’lsa frontend avtomatik downsampling qilishi
mumkin.

Backenddan kelgan original data o’zgartirilmaydi.

------------------------------------------------------------------------

# 54. Number Formatting

Area:

``` text
42.80 ha
```

Yield:

``` text
5.82 t/ga
```

Temperature:

``` text
34.2 °C
```

Percent:

``` text
8.4%
```

Coordinates:

``` text
41.123456, 69.123456
```

Metric qiymatlari uchun 2 decimal default.

------------------------------------------------------------------------

# 55. Date Formatting

Internal API:

``` text
YYYY-MM-DD
```

UI:

``` text
04 Sep 2026
```

O’zbekcha:

``` text
04 Sen 2026
```

Tooltip:

``` text
04.09.2026
```

Locale i18n orqali boshqariladi.

------------------------------------------------------------------------

# 56. Internationalization

Frontendda barcha static textlar `i18n.js` orqali olinadi.

Misol:

``` javascript
t("fields.add")
t("analysis.ndvi")
t("yield.prediction")
```

Language object:

``` javascript
{
  "uz-latn": {},
  "uz-cyrl": {},
  "ru": {},
  "en": {}
}
```

HTML ichida hardcoded user-facing text minimal bo’lishi kerak.

------------------------------------------------------------------------

# 57. Accessibility

Majburiy:

- keyboard navigation
- visible focus state
- semantic buttons
- `aria-label`
- modal focus trap
- sufficient contrast
- form labels
- error messages
- status icon + text

Map-only information uchun qo’shimcha textual summary beriladi.

------------------------------------------------------------------------

# 58. Security

Frontend quyidagilarga amal qiladi:

1.  API keylarni frontendga joylashtirmaslik.
2.  Bearer token bo’lsa localStorage ishlatishdan oldin threat model
    ko’rib chiqish.
3.  AI response HTML sifatida to’g’ridan-to’g’ri render qilinmasligi.
4.  Markdown → DOMPurify orqali sanitize.
5.  User-generated text escape qilinishi.
6.  Sensitive backend errors UIga chiqarilmasligi.
7.  Destructive actions confirmation bilan himoyalanishi.

------------------------------------------------------------------------

# 59. AI Content Rendering

AI response Markdown bo’lishi mumkin.

Pipeline:

``` text
API response
    ↓
Marked.js
    ↓
DOMPurify
    ↓
DOM
```

Hech qachon:

``` javascript
element.innerHTML = rawAIResponse;
```

ishlatilmasin.

------------------------------------------------------------------------

# 60. State Management

Global state minimal bo’lishi kerak.

Tavsiya:

``` javascript
const state = {
  fields: [],
  selectedFieldId: null,
  selectedAcquisitionId: null,
  selectedLayer: "NDVI",
  selectedYear: new Date().getFullYear(),
  language: "uz-latn",
  ragMode: "advanced",
  yieldModel: "CatBoost"
};
```

Server state va UI state ajratiladi.

------------------------------------------------------------------------

# 61. Caching

Frontend quyidagilarni cache qilishi mumkin:

- fields list
- acquisitions
- annual metrics
- RAG books
- latest yield

Cache invalidation:

``` text
create field → fields cache invalidate
new analysis → acquisitions/artifacts/recommendation invalidate
new yield → yield-latest invalidate
new chat → history/summary invalidate
toggle book → books cache invalidate
```

------------------------------------------------------------------------

# 62. Asset Cache Busting

Static assets version bilan yuklanadi:

``` html
<link rel="stylesheet" href="/static/styles.css?v=20260908">
<script src="/static/app.js?v=20260908"></script>
<script src="/static/i18n.js?v=20260908"></script>
```

Production deploymentda version build/release ID bilan avtomatik
o’zgartirilishi ma’qul.

------------------------------------------------------------------------

# 63. Toast Notifications

Global toast system:

``` text
✓ Dala muvaffaqiyatli saqlandi
✓ Tahlil tugadi
✓ Kitob holati yangilandi
✓ Bashorat tayyor
```

Error:

``` text
✕ Tahlilni bajarib bo'lmadi
```

Toast 3–5 sekunddan keyin yo’qoladi.

Muhim xatolar toast bilan birga inline ko’rsatiladi.

------------------------------------------------------------------------

# 64. Modal System

Modal turlari:

``` text
Confirm
Warning
Danger
Info
```

Modal:

- Escape bilan yopiladi
- overlay click bilan yopilishi mumkin
- danger action uchun overlay click orqali yopilish xavfsiz
- focus trap

------------------------------------------------------------------------

# 65. Map Architecture

Leaflet map lifecycle:

``` text
initMap()
loadBaseLayer()
loadFieldBoundary()
loadArtifacts()
updateLayer()
showHotspot()
fitToField()
```

Map DOM element qayta render qilinganda Leaflet instance ikki marta
yaratilib qolmasligi kerak.

------------------------------------------------------------------------

# 66. Field Geometry

Backend GeoJSON geometry qabul qiladi.

Frontend:

``` text
Feature
└── geometry
    └── Polygon
```

Save oldidan:

- polygon closedligini Leaflet orqali tekshirish
- minimal point count
- invalid shape handling
- userga preview

Backend validation har doim authoritative hisoblanadi.

------------------------------------------------------------------------

# 67. Field Detail Data Flow

``` text
Open Field
    ↓
GET /fields/{id}
    ↓
renderFieldHeader()
    ↓
GET acquisitions
    ↓
select latest acquisition
    ↓
GET artifacts
    ↓
renderMap()
    ↓
GET recommendation
    ↓
renderRecommendation()
    ↓
load historical metrics
    ↓
renderCharts()
    ↓
load yield-latest
    ↓
renderYield()
```

Parallel requestlardan foydalanish mumkin, agar ular bir-biriga bog’liq
bo’lmasa.

------------------------------------------------------------------------

# 68. Analysis Data Flow

``` text
User clicks "Tahlil qilish"
        ↓
POST /analyze
        ↓
Loading state
        ↓
selected_acquisition
        ↓
new_acquisitions_processed
        ↓
recommendation
        ↓
reload artifacts
        ↓
reload charts
        ↓
update dashboard
```

Agar `recommendation_error` mavjud bo’lsa, satellite analysis natijalari
baribir ko’rsatiladi.

------------------------------------------------------------------------

# 69. Yield Data Flow

``` text
Open Yield page
      ↓
GET yield/models
      ↓
Select model
      ↓
POST predict-yield
      ↓
Loading
      ↓
Prediction response
      ↓
Hero metric
      ↓
Range
      ↓
Top features
      ↓
Phenology
      ↓
Data sources
```

------------------------------------------------------------------------

# 70. Chat Data Flow

``` text
Open field
    ↓
GET chat/history
GET chat/summary
    ↓
Render
    ↓
User sends message
    ↓
POST chat
    ↓
Render answer
    ↓
Render RAG badge
    ↓
Render sources
    ↓
Update summary
```

Chat request:

``` json
{
  "messages": [
    {
      "role": "user",
      "content": "Dalada nima muammo bor?"
    }
  ],
  "language": "uz-latn",
  "selected_book_ids": [],
  "rag_mode": "advanced"
}
```

------------------------------------------------------------------------

# 71. Component Library

Minimal reusable components:

``` text
Button
IconButton
Badge
StatusBadge
Card
MetricCard
Modal
Toast
Dropdown
Tabs
SegmentedControl
DatePicker
Skeleton
EmptyState
ErrorState
MapPanel
ChartCard
DataTable
ChatMessage
SourceBadge
SourceDrawer
```

------------------------------------------------------------------------

# 72. Button Hierarchy

Primary:

``` text
[ Tahlil qilish ]
[ Dala qo'shish ]
[ Bashorat qilish ]
```

Secondary:

``` text
[ Batafsil ]
[ Xaritada ko'rsatish ]
```

Ghost:

``` text
[ Bekor qilish ]
```

Danger:

``` text
[ Hammasini o'chirish ]
```

Har bir sahifada primary CTA bitta dominant bo’lishi kerak.

------------------------------------------------------------------------

# 73. Design Anti-Patterns

Quyidagilarni ishlatmaslik:

- haddan tashqari gradient
- 10+ rangli dashboard
- har bir metric uchun alohida katta card
- doimiy modal oynalar
- technical API terminology
- foydalanuvchini JSON bilan bezovta qilish
- AI javobini manbasiz ko’rsatish
- loading paytida butun sahifani blank qilish
- `alert()` ga tayanish
- juda kichik map
- chartlarda 20+ rang

------------------------------------------------------------------------

# 74. Performance

Maqsad:

``` text
Initial UI render: < 1.5 sec
Interaction feedback: < 100 ms
Route/page transition: < 200 ms
```

Tavsiya:

- lazy render
- image lazy loading
- debounce map controls
- debounce search
- chart destroy/reuse
- duplicate API request prevention
- cache
- minimal DOM manipulation

Satellite PNG artifactlar kerak bo’lmaguncha yuklanmasin.

------------------------------------------------------------------------

# 75. Offline / Network Failure UX

Agar backend vaqtincha ishlamasa:

``` text
⚠ Server bilan aloqa uzildi

Saqlangan ma'lumotlarning ayrimlari
ko'rsatilishi mumkin.

[ Qayta ulanish ]
```

Map base layer ishlashi mumkin, lekin analysis data mavjud bo’lmasa aniq
ko’rsatiladi.

------------------------------------------------------------------------

# 76. Trust & Transparency

AI recommendation va yield prediction sahifalarida:

``` text
Ma'lumot manbalari
```

degan alohida section bo’lishi kerak.

Foydalanuvchi:

- qaysi satellite
- qaysi model
- qaysi RAG
- qaysi kitob
- qaysi observation

ishlatilganini tushunishi kerak.

------------------------------------------------------------------------

# 77. Model Information

Yield prediction card:

``` text
Model
CatBoost

Features
122

Execution
2.84 sec
```

Bu ma’lumot backend response’dagi:

- model_used
- features_count
- execution_time_sec

dan olinadi.

------------------------------------------------------------------------

# 78. Latest Observation Card

``` text
🛰️ Oxirgi kuzatuv

04 Sep 2026

Cloud
8%

Valid pixels
18,422

Status
✓ Ishonchli
```

`fully_cloudy=true` bo’lsa:

``` text
⚠ Tasvir to'liq bulutli
```

va index cardlarda noto’g’ri qiymatlar ko’rsatilmasligi kerak.

------------------------------------------------------------------------

# 79. Data Quality UX

Cloud coverage:

``` text
0–10%    Excellent
10–30%   Good
30–60%   Limited
>60%     Poor
```

Bu ranglar bilan birga text bilan ko’rsatiladi.

`cloud_coverage=null` bo’lsa:

``` text
Noma'lum
```

------------------------------------------------------------------------

# 80. Field Comparison

Kelajakdagi UX uchun:

``` text
Dala A
vs
Dala B
```

taqqoslash:

- area
- crop
- NDVI
- NDRE
- NDMI
- yield
- status

Lekin MVPda comparison alohida sahifa sifatida majburiy emas.

------------------------------------------------------------------------

# 81. Recommended Dashboard Information Priority

### Priority 1

``` text
Status
NDVI
Latest observation
AI recommendation
Map
```

### Priority 2

``` text
NDRE
NDMI
Historical trend
Hotspots
Yield
```

### Priority 3

``` text
Detailed artifacts
RAG sources
Model features
Technical metadata
```

------------------------------------------------------------------------

# 82. Desktop Dashboard Wireframe

``` text
┌──────────────────────────────────────────────────────────────┐
│ ZaminTahlil                 Dala: Paxta 42.8 ha    Uz ▼     │
├───────────────┬──────────────────────────────────────────────┤
│ Dashboard     │ 🟢 Dala holati yaxshi                       │
│ Dalalar       ├──────────────────────────────────────────────┤
│ Monitoring    │ NDVI       NDRE       NDMI       Yield       │
│ Hosildorlik   │ 0.71       0.52       0.46       5.82 t/ha  │
│ AI Agronom    ├──────────────────────────────┬───────────────┤
│ Bilimlar      │                              │ AI tavsiya    │
│ Sozlamalar    │            MAP               │               │
│               │                              │ 🔴 1           │
│               │                              │ 🟡 2           │
│               │                              │ 🟢 3           │
│               ├──────────────────────────────┴───────────────┤
│               │ NDVI / NDRE / NDMI History                  │
│               │                 CHART                        │
│               ├──────────────────────────────────────────────┤
│               │ Yield Prediction                            │
└───────────────┴──────────────────────────────────────────────┘
```

------------------------------------------------------------------------

# 83. Mobile Dashboard Wireframe

``` text
┌──────────────────────────┐
│ ☰  ZaminTahlil      ⋮   │
├──────────────────────────┤
│ 🟢 Dala yaxshi           │
│ Paxta · 42.8 ha          │
├──────────────────────────┤
│ NDVI      NDRE           │
│ 0.71      0.52           │
├──────────────────────────┤
│                          │
│          MAP             │
│                          │
├──────────────────────────┤
│ 🤖 AI tavsiya            │
│ ...                      │
├──────────────────────────┤
│ 📈 Vegetation            │
│                          │
├──────────────────────────┤
│ 🌱 Hosil                 │
│ 5.82 t/ga                │
├──────────────────────────┤
│ 🏠     🌾     🤖    ⚙️  │
└──────────────────────────┘
```

------------------------------------------------------------------------

# 84. Frontend File Responsibilities

## `index.html`

- application shell
- semantic layout
- root containers
- script/style imports

## `styles.css`

- design tokens
- layout
- responsive rules
- components
- animations

## `app.js`

- application bootstrap
- routing
- state coordination
- event handling

## `api.js`

- HTTP client
- API methods
- error normalization

## `i18n.js`

- translations
- locale management

## `map.js`

- Leaflet
- draw
- layers
- markers
- swipe

## `charts.js`

- Chart.js
- historical chart
- phenology chart
- feature chart

## `chat.js`

- chat history
- send message
- RAG badge
- sources
- summary

------------------------------------------------------------------------

# 85. API Wrapper Pattern

Recommended:

``` javascript
async function getFields() {
  return api.get("/api/fields");
}

async function getField(id) {
  return api.get(`/api/fields/${id}`);
}

async function analyzeField(id, mode = "latest") {
  return api.post(`/api/fields/${id}/analyze`, { mode });
}

async function getYield(id) {
  return api.get(`/api/fields/${id}/yield-latest`);
}
```

UI componentlar `fetch()` bilan to’g’ridan-to’g’ri ishlamasligi kerak.

------------------------------------------------------------------------

# 86. Error Normalization

API client bitta format qaytarsin:

``` javascript
{
  status: 422,
  message: "Ma'lumotlar noto'g'ri",
  detail: ...
}
```

UI faqat shu normalized object bilan ishlaydi.

------------------------------------------------------------------------

# 87. Request Cancellation

Agar user fieldni tez almashtirsa:

``` text
Field A request
      ↓
Field B selected
      ↓
Abort Field A request
      ↓
Load Field B
```

`AbortController` ishlatish tavsiya qilinadi.

------------------------------------------------------------------------

# 88. Prevent Duplicate Requests

Button bosilganda:

``` text
idle
 ↓
loading
 ↓
success/error
 ↓
idle
```

Bir request tugamasdan ikkinchi request yuborilmaydi.

------------------------------------------------------------------------

# 89. Accessibility of Maps

Map uchun:

``` text
aria-label="Dala xaritasi"
```

va text summary:

``` text
Dala 42.8 gektar.
Muammoli hotspot shimoliy-g'arbiy qismda.
```

Mapdan foydalana olmaydigan user uchun ham asosiy xulosa mavjud bo’lishi
kerak.

------------------------------------------------------------------------

# 90. Browser Support

Target:

- Chrome latest
- Edge latest
- Firefox latest
- Safari latest
- Android Chrome
- iOS Safari

ES6+ ishlatiladi.

------------------------------------------------------------------------

# 91. Testing Strategy

Frontend testlar:

## Unit

- formatter
- date formatter
- number formatter
- API error normalization
- i18n
- validation

## Integration

- create field
- analyze field
- yield prediction
- chat
- RAG toggle

## E2E

Asosiy flow:

``` text
Open app
↓
Create field
↓
Open field
↓
Analyze
↓
View satellite layer
↓
View recommendation
↓
Predict yield
↓
Ask AI
```

------------------------------------------------------------------------

# 92. Critical Acceptance Criteria

Frontend tayyor hisoblanadi, agar:

- [ ] Dala xaritada chiziladi.
- [ ] Dala maydoni ko’rsatiladi.
- [ ] Dala saqlanadi.
- [ ] Dublikat dala tushunarli xabar bilan rad qilinadi.
- [ ] Field detail ochiladi.
- [ ] Latest Sentinel observation ko’rsatiladi.
- [ ] RGB/NDVI/NDMI/NDRE/EVI/BSI/QA layerlari ishlaydi.
- [ ] A/B comparison ishlaydi.
- [ ] Artifact statistics ko’rsatiladi.
- [ ] Hotspot xaritada ko’rsatiladi.
- [ ] Historical chart ishlaydi.
- [ ] AI recommendation uch guruhda ko’rsatiladi.
- [ ] Yield prediction ishlaydi.
- [ ] Top features ko’rsatiladi.
- [ ] Phenology chart ishlaydi.
- [ ] Data sources ko’rsatiladi.
- [ ] Chat history saqlangan holda ko’rsatiladi.
- [ ] RAG mode tanlanadi.
- [ ] RAG source badge ko’rsatiladi.
- [ ] RAG source drawer ishlaydi.
- [ ] Chat summary ko’rsatiladi.
- [ ] RAG books ON/OFF ishlaydi.
- [ ] 4 til ishlaydi.
- [ ] Mobile responsive.
- [ ] Loading state mavjud.
- [ ] Empty state mavjud.
- [ ] API error state mavjud.
- [ ] Destructive action confirmation mavjud.

------------------------------------------------------------------------

# 93. Recommended UX Improvements

## 93.1. “Field Health Score”

Frontend backenddan mavjud ma’lumotlardan foydalanib vizual health
summary ko’rsatishi mumkin, lekin yangi ilmiy score formulasi backend
bilan kelishilmasdan ishlab chiqilmasligi kerak.

Agar backend score bermasa, UI:

``` text
Holat: Yaxshi
```

kabi mavjud recommendation/status ma’lumotlarini ko’rsatishi kerak.

## 93.2. “What changed?”

Har bir yangi observationdan keyin:

``` text
Nima o'zgardi?

NDVI   +4.2%
NDRE   +2.1%
NDMI   -3.4%

Asosiy o'zgarish:
Janubiy hudud
```

Bu faqat kerakli backend ma’lumot mavjud bo’lganda hisoblanadi.

## 93.3. “What should I do?”

Har bir analysis sahifasining yuqori qismida:

``` text
Keyingi qadam

Sug'orish tizimini janubiy qism bo'yicha tekshiring.
```

ko’rinishidagi CTA tavsiya qilinadi.

------------------------------------------------------------------------

# 94. UX Copywriting Rules

Frontend tili:

- qisqa
- sodda
- dehqonbop
- aniq
- hurmatli

Yomon:

``` text
Multispectral reflectance anomaly detected.
```

Yaxshi:

``` text
Dalaning ayrim qismida o'simlik holati odatdagidan past.
```

Yomon:

``` text
HTTP 422 validation error.
```

Yaxshi:

``` text
Kiritilgan ma'lumotlardan birini tekshiring.
```

Technical details faqat “Batafsil” orqali ko’rsatiladi.

------------------------------------------------------------------------

# 95. Final Frontend Architecture

``` text
                     ZaminTahlil Frontend
                              │
              ┌───────────────┴───────────────┐
              │                               │
          Presentation                     State
              │                               │
      ┌───────┼────────┐              ┌───────┼───────┐
      │       │        │              │       │       │
     Map    Charts    Chat          Field   Analysis  Yield
      │       │        │              │       │       │
      └───────┴────────┴──────────────┴───────┴───────┘
                              │
                         API Client
                              │
                         FastAPI REST
                              │
        ┌─────────────────────┼──────────────────────┐
        │                     │                      │
   Sentinel-2              RAG/LLM                 ML
        │                     │                      │
     Maps                    Chat                 Yield
```

------------------------------------------------------------------------

# 96. Final Product Experience

Foydalanuvchi ZaminTahlilga kirganda quyidagi tajriba bo’lishi kerak:

``` text
1. Dala tanlaydi
        ↓
2. Xarita orqali holatni ko'radi
        ↓
3. Sentinel-2 observation tanlaydi
        ↓
4. NDVI/NDRE/NDMI orqali muammoni ko'radi
        ↓
5. Hotspotni xaritada topadi
        ↓
6. AI tavsiyasini o'qiydi
        ↓
7. Hosildorlikni ko'radi
        ↓
8. AI Agronomdan savol so'raydi
        ↓
9. Kitob/manba asosidagi javobni oladi
        ↓
10. Keyingi amaliy qadamni bajaradi
```

**Frontendning asosiy muvaffaqiyat mezoni — foydalanuvchi ko’p sonli
satellite va ML ma’lumotlari orasida adashib qolmasdan, o’z dalasi
haqida tez va ishonchli qaror qabul qila olishi.**

------------------------------------------------------------------------

# 97. Backend Contract Reference

Frontend backend contract sifatida quyidagi asosiy modellarni hisobga
oladi:

- `FieldCreate`
- `FieldOut`
- `FieldDetail`
- `AcquisitionOut`
- `ArtifactOut`
- `AnalyzeRequest`
- `AnalyzeResponse`
- `AnnualSeries`
- `HistoricalSeries`
- `RecommendationOut`
- `AdviceGroups`
- `ChatRequest`
- `ChatResponse`
- `ChatHistoryMessageOut`
- `ChatSummaryOut`
- `RAGBookOut`
- `RAGSourceOut`
- `YieldPredictRequest`
- `YieldPredictResponse`
- `FeatureImportanceOut`
- `PhenologyPointOut`
- `YieldSourceItem`

API contractdagi fieldlar o’zgarsa frontend adapter qatlamida
o’zgartirilishi kerak.

------------------------------------------------------------------------

# 98. Important Implementation Rule

Frontend backend tomonidan berilmagan agronomik faktni mustaqil ravishda
“aniq” deb ko’rsatmasligi kerak.

Masalan:

``` text
NDVI = 0.42
```

dan frontend o’zicha:

``` text
Kasallik bor
```

degan xulosa chiqarmaydi.

Frontend:

``` text
NDVI past
```

deya ko’rsatishi va backend recommendation/anomaly natijasini alohida
chiqarishi kerak.

Bu yondashuv ZaminTahlilning ilmiy ishonchliligi va explainability’sini
saqlaydi.

------------------------------------------------------------------------

# 99. Recommended MVP Development Order

### Phase 1

``` text
App shell
Sidebar
Header
Fields
Map
Create field
```

### Phase 2

``` text
Field detail
Satellite layers
Acquisition selector
Statistics
A/B viewer
```

### Phase 3

``` text
Recommendations
Historical charts
Hotspots
```

### Phase 4

``` text
Yield prediction
Phenology
Top features
Data sources
```

### Phase 5

``` text
AI chat
RAG modes
Sources
Summary
```

### Phase 6

``` text
Knowledge base
Settings
Purge
i18n
Accessibility
Performance
```

------------------------------------------------------------------------

# 100. Definition of Done

ZaminTahlil frontend production-ready hisoblanadi, agar:

1.  Asosiy user journey boshidan oxirigacha ishlasa.
2.  Backend API response’lari to’g’ri render qilinsa.
3.  Satellite map barcha kerakli layerlarni ko’rsatsa.
4.  Analysis va recommendation UX bir-biridan aniq ajratilgan bo’lsa.
5.  Yield prediction natijasi tushunarli ko’rsatilsa.
6.  AI javoblari source/provenance bilan ko’rsatilsa.
7.  4 til ishlasa.
8.  Mobile va desktop layoutlar barqaror bo’lsa.
9.  Loading, empty va error holatlari mavjud bo’lsa.
10. Xavfli amallar tasdiqlash bilan himoyalangan bo’lsa.
11. AI va satellite ma’lumotlari aralashtirib yuborilmasa.
12. Frontend foydalanuvchini texnik JSON/API tafsilotlari bilan ortiqcha
    yuklamasa.

------------------------------------------------------------------------

## ZaminTahlil

**Sun’iy intellekt + sun’iy yo’ldosh + agronomik bilim + mashinali
o’rganish**

Frontendning vazifasi ushbu texnologiyalarni foydalanuvchi uchun bitta
sodda tajribaga aylantirishdir.

> **Dala → Ma’lumot → Tahlil → Tushunish → Tavsiya → Qaror**
