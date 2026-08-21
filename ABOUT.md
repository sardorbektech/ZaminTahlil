# ZaminTahlil — Aqlli Qishloq Xo‘jaligi Monitoringi va Agro-AI Platformasi

**ZaminTahlil** — O‘zbekiston va Markaziy Osiyo qishloq xo‘jaligi maydonlarini sun’iy yo‘ldosh tasvirlari ($Sentinel-2$ L2A), ko‘p provayderli agrometeorologiya ($Open\text{-}Meteo$, $NASA\ POWER$), Mashinali O‘rganish ($ML$) algoritmlari hamda 4-pog‘onali $RAG$ (Retrieval-Augmented Generation) agronomik sun’iy intellekti orqali kompleks tahlil qiluvchi innovatsion veb-platformadir.

Ushbu hujjat platformaning me’moriy tuzilishi, funksional imkoniyatlari, matematik-agronomik modellari, ma’lumotlar bazasi arxitekturasi va API spetsifikatsiyasini to‘liq qamrab oladi.

---

## 📑 Mundarija

1. [Strategik Missiya va Loyiha Maqsadi](#1-strategik-missiya-va-loyiha-maqsadi)
2. [Tizim Arxitekturasi va Ma’lumotlar Oqimi](#2-tizim-arxitekturasi-va-malumotlar-oqimi)
3. [Asosiy Funktsional Modullar](#3-asosiy-funktsional-modullar)
   - [3.1. Geofazoviy Xaritalash va Dala Boshqaruvi](#31-geofazoviy-xaritalash-va-dala-boshqaruvi)
   - [3.2. Sentinel-2 L2A Spektral Tahlili va A/B Swipe Viewer](#32-sentinel-2-l2a-spektral-tahlili-va-ab-swipe-viewer)
   - [3.3. 5 Bosqichli Biofizik va Fazoviy Anomaliyalar Diagnostikasi Moduli](#33-5-bosqichli-biofizik-va-fazoviy-anomaliyalar-diagnostikasi-moduli)
   - [3.4. Ko‘p Provayderli Chidamli Ob-havo Dvigateli (4 Qatlamli Arxitektura)](#34-kop-provayderli-chidamli-ob-havo-dvigateli-4-qatlamli-arxitektura)
   - [3.5. 4-Pog‘onali RAG Agronomik Bilimlar Bazasi](#35-4-pogonali-rag-agronomik-bilimlar-bazasi)
   - [3.6. Mashinali O‘rganish (ML) Hosildorlik Bashorati](#36-mashinali-organish-ml-hosildorlik-bashorati)
   - [3.7. Dala Muloqotlari, Avtomatik Xulosa va Manba Belgilari (Provenance Badges)](#37-dala-muloqotlari-avtomatik-xulosa-va-manba-belgilari-provenance-badges)
   - [3.8. Yillik va Tarixiy Indekslar Dinamikasi](#38-yillik-va-tarixiy-indekslar-dinamikasi)
   - [3.9. Dala Maydonlari Bazasini Xavfsiz Tozalash](#39-dala-maydonlari-bazasini-xavfsiz-tozalash)
4. [Matematik Formulalar va Hisoblash Metodologiyasi](#4-matematik-formulalar-va-hisoblash-metodologiyasi)
5. [Texnologiyalar Steki](#5-texnologiyalar-steki)
6. [Ma’lumotlar Bazasi Sxemasi (Schema v7)](#6-malumotlar-bazasi-sxemasi-schema-v7)
7. [API Spetsifikatsiyasi (REST Endpoints)](#7-api-spetsifikatsiyasi-rest-endpoints)
8. [Xavfsizlik, Maxfiylik va Ish Rejimlari](#8-xavfsizlik-maxfiylik-va-ish-rejimlari)

---

## 1. Strategik Missiya va Loyiha Maqsadi

An’anaviy dehqonchilikda dalalarni monitoring qilish ko‘p vaqt, jismoniy mehnat va katta xarajat talab qiladi. Sug‘orishdagi nomutanosibliklar, o‘g‘it yetishmasligi, begona o‘tlar yoki vilt kasalliklari ko‘pincha hosil nobud bo‘lgach aniqlanadi.

**ZaminTahlil** ushbu muammolarni quyidagi asosiy yo‘nalishlarda hal etadi:
- **Kosmik monitoring**: Yevropa Kosmik Agentligi ($ESA$) ning $Sentinel-2$ sun’iy yo‘ldoshidan olingan 10 metrlik multispektral tasvirlar orqali dalaning har bir qismini masofadan turib to‘liq skanerlash;
- **Ko‘p provayderli ob-havo va tuproq integratsiyasi**: $Open\text{-}Meteo$ va $NASA\ POWER$ orqali dalaning aniq geografik nuqtasidagi havo harorati, quyosh radiatsiyasi, bug‘lanish ($ET_0$) va 3 ta chuqurlikdagi (0–7 sm, 7–28 sm, 28–100 sm) tuproq namligini kuzatish;
- **Aniqlik darajasi yuqori hosil bashorati**: 122 ta agrometeorologik va spektral xususiyatlar asosida $CatBoost$, $LightGBM$, $XGBoost$, $RandomForest$ va $GradientBoosting$ algoritmlari yordamida gektariga hosildorlikni ($t/ga$) va jami hosilni ($tonna$) oldindan bashorat qilish;
- **4-Pog‘onali RAG Agronomik AI Maslahatchisi**: Agronomiya kitoblari va darsliklarining mahalliy 768-o‘lchamli vektor bazasi ($RAG$) hamda bilimlar grafi orqali dehqon va agronomlarning har bir savoliga ilmiy asoslangan, kitob sahifasiga havola qilingan, samimiy va oddiy tushunarli amaliy javoblar berish.

---

## 2. Tizim Arxitekturasi va Ma’lumotlar Oqimi

```mermaid
graph TD
    User([Foydalanuvchi / Dehqon / Agronom]) <--> Frontend[Zamonaviy Veb Interfeys: Leaflet Hybrid + Chart.js]
    Frontend <--> FastAPI[FastAPI Backend Server]

    subgraph Tashqi Xizmatlar
        CDSE[Copernicus Data Space Ecosystem / Sentinel-2]
        OpenMeteo[Open-Meteo Multi-Endpoint: Forecast, ECMWF, GFS, DWD]
        NASAPower[NASA POWER Global Agroclimatology API]
        OpenAI[OpenAI LLM API: Primary & Fallback]
    end

    subgraph Lokal ML & 4-Pog'onali RAG Dvigatellari
        Embed768[Local 768-dim Embedding Engine: nomic-ai/nomic-embed-text-v1.5]
        BM25RRF[Hybrid Search: BM25Okapi + Reciprocal Rank Fusion + MMR + Reranker]
        GraphRAG[Knowledge Graph Engine: Agronomic Nodes, Edges & BFS Expansion]
        MLModels[Pre-trained ML Modellar: CatBoost, LightGBM, XGBoost, RF, GB]
    end

    subgraph Ma'lumotlar Saqlash
        SQLite[(SQLite Database v7: Fields, Chunks, Chat, Yield, Provenance)]
        ArtifactsDir[(Artifacts: PNG Heatmaps & NPY Vektorlar)]
        WeatherCache[(Local Weather Cache: PKL)]
    end

    FastAPI <--> CDSE
    FastAPI <--> OpenMeteo
    FastAPI <--> NASAPower
    FastAPI <--> OpenAI
    FastAPI <--> Embed768
    FastAPI <--> BM25RRF
    FastAPI <--> GraphRAG
    FastAPI <--> MLModels
    FastAPI <--> SQLite
    FastAPI <--> ArtifactsDir
    FastAPI <--> WeatherCache
```

---

## 3. Asosiy Funktsional Modullar

### 3.1. Geofazoviy Xaritalash va Dala Boshqaruvi
- **Gibrid Sun’iy Yo‘ldosh Xaritasi**: $Esri\ World\ Imagery$ sun’iy yo‘ldosh qatlami ustiga aholi punktlari, tuman/viloyat chegaralari va yo‘llar tarmog‘i ($World\ Boundaries\ \&\ Places$, $World\ Transportation$) gibrid tarzda qoplangan.
- **Interaktiv Chizish**: $Leaflet\text{-}Draw$ vositasida dala konturi erkin polygon sifatida chiziladi.
- **Geodezik Maydon Hisoblash**: $PyProj$ kutubxonasining WGS84 ellipsoidi ($Geod$) yordamida yer egriligi hisobga olingan holda gektar ($ga$) birligida 100% aniqlikda hisoblanadi.
- **8 Xonali Public ID**: Har bir yangi kiritilgan dalaga ixcham 8 xonali kichik harf va raqamlardan iborat noyob identifikator beriladi (masalan: `r1ntw4h8`, `a7k9b2x4`).
- **Dublikatlardan Himoya**: Dala geometriyasidan olingan SHA-256 xesh kodi orqali ayni bir xil dala qayta kiritilishining oldi olinadi.

### 3.2. Sentinel-2 L2A Spektral Tahlili va A/B Swipe Viewer
- **Haqiqiy Ko‘p Qatlamli Tahlil**: Sentinel Hub orqali oxirgi 5 ta kuzatuv yuklanadi va 10 metrli piksellar katagida quyidagi qatlamlar hisoblanadi:
  1. `RGB`: Tabiiy rangli optik tasvir;
  2. `NDVI`: Normallashtirilgan vegetatsiya indeksi (biomassa zichligi va yashillik);
  3. `NDMI`: Barg namligi va suv indeksi;
  4. `NDRE`: Qizil chegara xlorofill va azot indeksi;
  5. `EVI`: Rivojlangan vegetatsiya indeksi (atmosfera xatoliklaridan tozalangan);
  6. `BSI`: Ochiq tuproq va sho‘rlanish indeksi;
  7. `QA`: Sifat nazorati (SCL va dataMask bo‘yicha bulut/soya filtri).
- **A/B Swipe Taqqoslash**: Turli sanalardagi yoki turli indekslardagi tasvirlarni slayd (swipe) chizig‘i orqali o‘zaro solishtirish imkoniyati.
- **Aniq Koordinatali Overlay**: Barcha qatlamlar o‘zining haqiqiy geodezik bounding boxi (`artifact.bbox`) bo‘yicha to‘g‘ridan-to‘g‘ri dala xaritasiga joylashtiriladi (`L.imageOverlay`).

### 3.3. 5 Bosqichli Biofizik va Fazoviy Anomaliyalar Diagnostikasi Moduli
Sentinel-2 L2A spektral kanallari asosida daladagi o‘choqli muammolarni matematik va biofizik jihatdan aniqlash hamda ularning kelib chiqish sabablarini bir-biridan ajratish:
1. **1-Bosqich: Spektral Piksellarni Qirqish va Filtrlash**:
   - Dala chegarasi polygon maskasi (`data_mask`) yordamida dala tashqarisidagi barcha yo‘llar va ob’yektlar chiqarib tashlanadi.
   - Oxirgi 60 kunlik o‘tishlar ichidan bulutlilik qoplami $\le 30\%$ bo‘lgan eng tiniq va ishonchli piksellar olinadi.
2. **2-Bosqich: 10+ Biofizik Spektral Indekslar Hisoblash**:
   - $NDVI = \frac{B08 - B04}{B08 + B04}$ (Vegetatsiya indeksi)
   - $SAVI = \frac{B08 - B04}{B08 + B04 + 0.5} \times 1.5$ (Tuproq ta'siridan tozalangan vegetatsiya)
   - $LAI = 0.57 \times \exp(2.33 \times NDVI)$ (Barg sathi yuzasi indeksi)
   - $NDRE = \frac{B8A - B05}{B8A + B05}$ (Qizil chegara xlorofill va azot holati)
   - $BRI = \frac{B02}{B04}$ (Bargning erta oqarishi va nekroz ko‘rsatkichi)
   - $LCI = \frac{B8A - B05}{B8A + B04}$ (Barg xlorofill indeksi)
   - $NDWI = \frac{B8A - B11}{B8A + B11}$ (O‘simlik to‘qimalari suv ta’minoti)
   - $MSI = \frac{B11}{B08}$ (Namlik stressi indeksi)
   - $NDSI = \frac{B03 - B11}{B03 + B11}$ (Tuproq va o‘simlik sho‘rlanish darajasi)
   - $\Delta T = (1 - NDWI) \times (1 - NDVI) \times 6.0^\circ\text{C}$ (Transpiratsiya tushishi oqibatidagi barg harorati anomaliyasi)
3. **3-Bosqich: Fazoviy Anomaliyalarni Qidirish va Klasterlash**:
   - Binar anomaliya sharti: $(NDVI < 0.55) \lor (NDVI < \overline{NDVI}_{\text{field}} - 0.10) \lor (NDRE < 0.48) \lor (NDWI < 0.28) \lor (NDSI > 0.38)$.
   - 8-Connectivity fazoviy bog‘lanish (`scipy.ndimage.label`) orqali maydoni $200\text{ m}^2$ (2 piksel) dan katta o‘choqlar klasterlanadi.
   - Maydoni va og‘irligi bo‘yicha eng xavfli **Top 5** ta o‘choq saralanadi va 8 ta kompas sektori (Shimoliy, Janubiy, Sharqiy, G'arbiy va h.k.) hamda koordinata markazi aniqlanadi.
4. **4-Bosqich: 4 Bosqichli Differensial Qarorlar Modeli (Decision Tree)**:
   - **Sho‘rlanish Stressi:** $NDSI \ge 0.38 \land SAVI < 0.30 \to$ Osmotik sho‘r bosimi, fosfogips (3-4 t/ga) va chuqur sho‘r yuvish.
   - **Erta Zamburug‘ Infeksiyasi:** $NDRE < 0.45 \land BRI > 1.20 \land NDWI \ge 0.38 \to$ O‘simlik suvga to‘la bo‘lsa-da xlorofill tez parchalanmoqda (*Verticillium dahliae*, *Puccinia striiformis*, *Phytophthora infestans*). Topsin-M (1.5 kg/ga) yoki Ridomil Gold (2.5 kg/ga) bilan shoshilinch purkash.
   - **Ksilema Blokadasi vs Gidrostress:** $NDWI < 0.25 \land NDRE < 0.40 \to$ Agar oxirgi 60 kunlik dinamikada $NDRE$ oldin tushgan bo‘lsa $\to$ Ildiz/poya tomirlarining zamburug‘li blokadasi; agar $NDWI$ oldin tushgan bo‘lsa $\to$ Sof tuproq namligi tanqisligi (gidrostress).
5. **5-Bosqich: Fazoviy Anizotropiya & Egat Geometriyasi**:
   - Kovariatsiya matritsasi xos qiymatlari $\lambda_{\max}, \lambda_{\min}$ orqali cho‘ziqlik koeffitsiyenti hisoblanadi:
     $$E = \sqrt{\frac{\lambda_{\max}}{\lambda_{\min} + 10^{-4}}}$$
   - $E > 3.0 \to$ Egat bo‘ylab cho‘zilgan chiziqli anomaliya (kultivator, traktor g‘ildiragi zichlashi, o‘g‘it solgich tiqilishi, egat sug‘orish maromi buzilishi);
   - $E \le 3.0 \to$ Markazdan tarqaluvchi konsentrik doirasimon o‘choq (infeksiya tarqalishi, lokal sho‘rxok, mikro-relyef chuqurligi).

### 3.4. Ko‘p Provayderli Chidamli Ob-havo Dvigateli (4 Qatlamli Arxitektura)
Ob-havo ma’lumotlarini olishda tashqi serverlardagi `503 Service Unavailable` va uzilishlarni to‘liq bartaraf etuvchi 4 pog‘onali himoya tizimi:
1. **1-Qatlam (Mahalliy Kesh)**: `data/weather_cache/` katalogida koordinatalar va sana oralig‘i bo‘yicha kesh saqlanadi. Bir xil so‘rovlar 0ms tezlikda keshdan olinadi;
2. **2-Qatlam (Open-Meteo Multi-Endpoint + Exponential Backoff)**: Asosiy prognoz ishlamasa, **ECMWF**, **GFS** va **DWD-ICON** modellari o‘rtasida 3 martalik kutish bilan qayta ulanadi;
3. **3-Qatlam (NASA POWER Global Agroclimatology API)**: NASA ning ochiq agrometeorologiya tarmog‘i (`power.larc.nasa.gov`) orqali bepul quyosh radiatsiyasi, harorat, yog‘in va shamol ko‘rsatkichlari olinadi;
4. **4-Qatlam (O‘zbekiston Dinamik Iqlimiy Modeli)**: Agar barcha tashqi tarmoqlar o‘chsa, O‘zbekiston kengliklari ($37^\circ\text{N}-45^\circ\text{N}$) va FAO-56 Penman-Monteith / Hargreaves quyosh geometriyasi formulalari asosida hisoblangan real dinamik iqlimiy egri chiziqlar generatsiya qilinadi.

### 3.5. 4-Pog‘onali RAG Agronomik Bilimlar Bazasi
Loyiha 4 ta ixtisoslashgan agronomik RAG strategiyasini o‘z ichiga oladi va foydalanuvchi interfeysdan kerakli rejimni erkin tanlay oladi:

| RAG Usuli | Algoritm va Texnologiya | Vazifasi |
| :--- | :--- | :--- |
| **🔬 Advanced RAG (Default)** | Multi-Query Generator + Gibrid (Dense 768-dim + Sparse BM25Okapi) + RRF ($k=60$) + MMR ($\lambda=0.65$) + Cross-Scoring Reranker | Savollarni kengaytirish, kalit so‘zlar va semantika muvozanati, dublikatlarni tozalash |
| **⚡ All-in-One Parallel RAG** | `ThreadPoolExecutor(max_workers=3)` orqali 3 ta RAGni parallel yurgizish + Score thresholding + Sintez | Barcha usullarni bir vaqtda ishga tushirib eng boy agronomik kontekstni yig‘ish |
| **🕸️ Graph RAG** | Agronomik bilimlar grafi (Node, Edge, Graph) + BFS qo‘shnilarni qidirish ($depth=2$) | Ekin, tuproq, o‘g‘it, kasallik va spektral indekslar munosabatlari grafi |
| **📚 Naive RAG** | `nomic-ai/nomic-embed-text-v1.5` (768-dim L2-normallashtirilgan) + Cosine similarity | Matn bo‘laklari bilan to‘g‘ridan-to‘g‘ri tezkor semantik o‘xshashlik qidiruvi |
| **🤖 Umumiy LLM (RAGsiz)** | To‘g‘ridan-to‘g‘ri sun’iy intellekt bilimlari | Kitob kontekstisiz umumiy maslahatlar |

- **Kafolatlangan Qidiruv**: Foydalanuvchi RAG rejimini tanlaganda, tizim majburiy ravishda indekslangan kitoblar bazasidan eng mos nomzod bo‘laklarni ajratib AI kontekstiga kiritadi.

### 3.6. Mashinali O‘rganish (ML) Hosildorlik Bashorati
- **Ko‘p manbali 122 ta parametr matritsasi**:
  - Kunlik agrometeorologiya (harorat, namlik, quyosh radiatsiyasi, $ET_0$, 3 chuqurlikdagi tuproq namligi);
  - $Sentinel-2$ optik spektral indekslari ($NDVI, EVI, GNDVI, SAVI, MSAVI, OSAVI, NDRE, NDMI, NDWI$);
  - $Sentinel-1$ SAR radar ko‘rsatkichlari ($VV, VH$, radar nisbati $VV-VH$);
  - Ekin fenologiyasi (ekilganidan beri o‘tgan kunlar, o‘rim-yig‘imgacha qolgan kunlar, mavsumiy rivojlanish fazasi, siklik sinus/kosinus parametrlar).
- **Pre-trained Modellar**: `CatBoost`, `LightGBM`, `XGBoost`, `Random Forest`, `Gradient Boosting`.
- **Natijalar**: 1 Gektar hosildorligi ($t/ga$), ishonchlilik oralig‘i ($\pm \sigma$), butun dalaning jami hosili ($tonna$), eng muhim 10 ta ta’sir omili ($Top\ Features$) hamda 2 o‘qli interaktiv fenologiya grafigi (`Chart.js`) va oylik batafsil jadval.

### 3.7. Dala Muloqotlari, Avtomatik Xulosa va Manba Belgilari (Provenance Badges)
- **Doimiy Xotira**: Muloqot xabarlari server SQLite bazasiga (`field_chat_messages`) saqlanadi.
- **RAG Manba Nishonlari (Provenance Badges)**:
  - `⚡ All-in-One RAG (Advanced + Graph)` (Binafsha/moviy gradient nishon);
  - `🔬 Advanced RAG (Gibrid + Reranker)` (Moviy nishon);
  - `🕸️ Graph RAG (Bilimlar Grafi)` (Sariq/olovrang nishon);
  - `📚 Naive RAG (Vektor Qidiruv)` (Zumrad yashil nishon);
  - `🤖 Umumiy LLM Bilimlari` (Kulrang nishon).
- **Oddiy va Dehqonbop AI Tili**: AI tavsiyalari va suhbat javoblari quruq ilmiy atamalardan xoli, samimiy, tushunarli, o‘ta lo‘nda va 1-2 gaplik aniq amaliy bandlarda taqdim etiladi.
- **Lo‘nda Xulosa (Summary)**: Har bir muloqotdan so‘ng sun’iy intellekt suhbatning qisqa xulosasini (`field_chat_summaries`) avtomatik yangilab boradi.

### 3.8. Yillik va Tarixiy Indekslar Dinamikasi
- **Boshlanish Sanasi**: Sukut bo‘yicha **`01.01.2026`** (joriy yilning 1-yanvari) qilib sozlangan va yil o‘zgarganda avtomatik sinxronlanadi.
- **Chart.js Dinamikasi**: Barcha 5 ta asosiy indeksning ($NDVI, NDMI, NDRE, EVI, BSI$) yillar bo‘yicha o‘zgarish egri chizig‘i.

### 3.9. Dala Maydonlari Bazasini Xavfsiz Tozalash
- **Sidebar Tozalash Tugmasi**: `🗑️ Tozalash` tugmasi va xavfsizlik modali;
- **Tasdiqlash Paroli**: **`roziman`** paroli kiritilganda bazadagi barcha dala maydonlari, hisob-kitoblar, xaritalar va chat xabarlari to‘liq o‘chiriladi (agronom kitoblari saqlanadi).

---

## 4. Matematik Formulalar va Hisoblash Metodologiyasi

### 4.1. Spektral va Biofizik Indekslar Formulalari

| Indeks | To‘liq Nomi | Matematik Formula | Agronomik Ahamiyati |
| :--- | :--- | :--- | :--- |
| **NDVI** | Normalized Difference Vegetation Index | $\frac{B08 - B04}{B08 + B04}$ | Yashil biomassa zichligi va fotosintez faolligi |
| **SAVI** | Soil-Adjusted Vegetation Index | $\frac{B08 - B04}{B08 + B04 + 0.5} \times 1.5$ | Tuproq ochiq joylarida aniq o‘sish ko‘rsatkichi |
| **LAI** | Leaf Area Index | $0.57 \times \exp(2.33 \times NDVI)$ | Barg yuzasi maydoni ($m^2/m^2$) |
| **NDMI** | Normalized Difference Moisture Index | $\frac{B08 - B11}{B08 + B11}$ | O‘simlik barg to‘qimalaridagi suv va namlik |
| **NDRE** | Normalized Difference Red Edge Index | $\frac{B8A - B05}{B8A + B05}$ | Xlorofill miqdori va erta azot yetishmovchiligi |
| **BRI** | Bleaching / Browning Reflectance Index | $\frac{B02}{B04}$ | Barglarning sarg‘ayishi, xloroz va nekroz xavfi |
| **LCI** | Leaf Chlorophyll Index | $\frac{B8A - B05}{B8A + B04}$ | Bargdagi xlorofillning bevosita konsentratsiyasi |
| **NDWI** | Normalized Difference Water Index | $\frac{B8A - B11}{B8A + B11}$ | O‘simlik suv stressi va to‘qima turgori |
| **MSI** | Moisture Stress Index | $\frac{B11}{B08}$ | O‘simlikning qurg‘oqchilikka chidamliligi |
| **NDSI** | Normalized Difference Salinity Index | $\frac{B03 - B11}{B03 + B11}$ | Tuproq va o‘simlikdagi tuz to‘planishi |
| **$\Delta T$** | Canopy Temperature Anomaly | $(1 - NDWI)(1 - NDVI) \times 6.0^\circ\text{C}$ | Transpiratsiya susayishi natijasida qizish |
| **$E$** | Furrow Anisotropy Ratio | $\sqrt{\frac{\lambda_{\max}}{\lambda_{\min} + 10^{-4}}}$ | Egat bo‘yicha chiziqli ($>3.0$) yoki radial doiraviy ($\le 3.0$) o‘choq shakli |
| **EVI** | Enhanced Vegetation Index | $2.5 \times \frac{B08 - B04}{B08 + 6B04 - 7.5B02 + 1}$ | Zich biomassada to‘yinishsiz rivojlanish |
| **BSI** | Bare Soil Index | $\frac{(B11 + B04) - (B08 + B02)}{(B11 + B04) + (B08 + B02)}$ | Ochiq tuproq, mineral holat va sho‘rlanish |

### 4.2. RAG Reciprocal Rank Fusion (RRF) Formulasi
Ko‘p qidiruvli tizimlar o‘rinlarini birlashtirish:
$$RRF\text{ Score}(d) = \sum_{m \in M} \frac{1}{k + r_m(d)}, \quad k = 60$$

### 4.3. RAG Kosinus O‘xshashlik Formulasi
$$\text{Similarity}(\vec{u}, \vec{v}) = \frac{\vec{u} \cdot \vec{v}}{\|\vec{u}\|_2 \|\vec{v}\|_2}$$

---

## 5. Texnologiyalar Steki

| Qatlam | Asosiy Texnologiyalar |
| :--- | :--- |
| **Backend** | Python 3.12+, FastAPI, Uvicorn, Pydantic v2, HTTPX |
| **Ma’lumotlar Bazasi** | SQLite 3 (WAL mode, Foreign Keys ON, Schema v7) |
| **Geofazoviy Tahlil** | Shapely 2.0+, PyProj 3.6+, SciPy 1.18+ (ndimage, linalg), NumPy |
| **Machine Learning** | Scikit-learn, CatBoost, LightGBM, XGBoost, Pandas, Joblib |
| **NLP & RAG** | FastEmbed 768-dim (`nomic-ai/nomic-embed-text-v1.5`), BM25Okapi, MMR, Knowledge Graph BFS, PyPDF, OpenAI API |
| **Tashqi API-lar** | Copernicus Data Space Ecosystem (Sentinel-2 L2A), Open-Meteo Multi-Endpoint, NASA POWER API |
| **Frontend** | Vanilla JavaScript (ES6+), Leaflet, Leaflet-Draw, Chart.js, Marked.js, DOMPurify |
| **Dizayn Tizimi** | Modern Vanilla CSS (Sonar Radar Marker, Glassmorphism, Responsive Grid & Flexbox) |
| **Xavfsizlik & Test** | Pure ASGI Security Headers, Sensitive Data Log Masking, PyTest (66 test) |

---

## 6. Ma’lumotlar Bazasi Sxemasi (Schema v7)

Loyiha quyidagi 10 ta jadvaldan iborat relying bazaga ega:

1. **`fields`**: `id`, `public_id` (8 xonali ID), `geometry_json`, `geometry_hash` (UNIQUE), `area_hectares`, `crop_name`, `planted_on`, `growth_stage`, `created_at`, `updated_at`.
2. **`acquisitions`**: Sentinel-2 tasvirlari sanasi, mahsulot ID, reviziya kaliti, bulutlilik ko‘rsatkichi.
3. **`index_values`**: Har bir tasvir va indeks bo‘yicha hisoblangan `mean_value`, `min_value`, `median_value`, `max_value`.
4. **`artifacts`**: Qatlamlarning PNG render tasvirlari, koordinata bounding boxlari (`bbox_json`), kenglik va balandligi.
5. **`recommendations`**: AI va ekspert agronomik tavsiyalari (Qizil, Sariq, Yashil guruhlar va anomaliya hisoboti).
6. **`field_chat_messages`**: Dala yozishmalari tarixi (role, content, `rag_sources_json`, `rag_strategy`, `rag_source_title`, vaqti).
7. **`field_chat_summaries`**: Dala muloqotlarining lo‘nda, qisqa xulosasi (Summary) va xabarlar soni.
8. **`rag_documents`**: Bazaga kiritilgan PDF kitoblar (`is_active`, `embedding_model`, `embedding_dim`, nomi, fayl yo‘li, sahifalar va bo‘laklar soni).
9. **`rag_chunks`**: Kitoblardan ajratilgan matn bo‘laklari va 768-o‘lchamli vektorlar (`embedding BLOB`).
10. **`yield_predictions`**: Hosildorlik bashorati tarixi (model, $t/ga$, jami tonna, top parametrlar, fenologiya).

---

## 7. API Spetsifikatsiyasi (REST Endpoints)

### Dala Boshqaruvi
- `POST /api/fields` — Yangi dala qo‘shish (GeoJSON polygon, ekin nomi, ekilgan sana, rivojlanish bosqichi).
- `GET /api/fields` — Barcha saqlangan dalalar ro‘yxati.
- `GET /api/fields/{id}` — Dala tafsilotlari (id yoki 8 xonali public_id orqali).
- `POST /api/database/purge-fields` — Barcha dala maydonlari va tahlillarni tozalash (Parol: `roziman`).

### Sun’iy Yo‘ldosh Tahlili & Radar Hotspot
- `POST /api/fields/{id}/analyze` — Oxirgi 14 kunlik Sentinel Hub tasvirlarini yuklash va 10+ indekslarni hisoblash.
- `GET /api/fields/{id}/acquisitions` — Dalaning barcha mavjud kuzatuvlari.
- `GET /api/fields/{id}/acquisitions/{acq_id}/artifacts` — Qatlamlar statistikasi, rasm havolalari va eng past NDRE o‘chog‘ining `hotspot_coordinates` [lat, lon] qiymati.
- `GET /api/fields/{id}/acquisitions/{acq_id}/images/{layer}` — Qatlamning PNG tasvirini olish (RGB, NDVI, NDMI, NDRE, EVI, BSI, QA).
- `GET /api/fields/{id}/annual-metrics?year=2026` — Yillik indekslar dinamikasi.
- `POST /api/fields/{id}/historical-metrics` — Boshlang‘ich sanadan boshlab tarixiy tasvirlarni yuklash.

### Hosildorlikni Bashorat Qilish (ML)
- `GET /api/yield/models` — Mavjud ML modellari (`CatBoost`, `LightGBM`, `XGBoost`, `RandomForest`, `GradientBoosting`).
- `POST /api/fields/{id}/predict-yield` — 122 ta parametr asosida hosildorlikni hisoblash ($t/ga$, jami tonna, ishonchlilik oralig‘i, top omillar).
- `GET /api/fields/{id}/yield-latest` — Dalaning oxirgi hosildorlik bashorati.

### RAG Bilimlar Bazasi (Ko‘p Kitobli va 4-Pog‘onali Boshqaruv)
- `GET /api/rag/books` — `data/books/` papkasidagi barcha PDF kitoblar holati (`indexed`, `is_active`, `size_mb`).
- `POST /api/rag/books/index-file` — Tanlangan PDF kitobni 768-dim model bilan indekslash.
- `POST /api/rag/books/{id}/toggle` — Kitobni RAG qidiruvi uchun yoqish yoki o‘chirish (`is_active`).
- `POST /api/rag/upload` — Yangi PDF kitobni `data/books/` papkasiga yuklash va avtomatik indekslash.
- `POST /api/rag/ingest` — PDF kitobni kiritish va embedding hisoblash.
- `GET /api/rag/documents` — Kiritilgan barcha kitoblar ro‘yxati.
- `DELETE /api/rag/documents/{id}` — Kitobni bazadan o‘chirish.

### Chat & Dala Xulosasi
- `GET /api/fields/{id}/chat/history` — Dala bo‘yicha yozishmalar tarixi (va RAG manba belgilari).
- `GET /api/fields/{id}/chat/summary` — Dala muloqotlarining umumlashtirilgan xulosasi.
- `POST /api/fields/{id}/chat` — Tanlangan RAG usuli (`rag_mode`: `advanced`, `all_in_one`, `graph`, `naive`, `direct_llm`), faol kitoblar (`selected_book_ids`), 5 kunlik NDVI va Summary konteksti bilan AI ga savol yuborish.

---

## 8. Xavfsizlik, Maxfiylik va Ish Rejimlari

### 8.1. Ish Rejimlari (`APP_ENV`)
- **`APP_ENV=demo` (Standart)**:
  - Swagger UI (`/docs`), ReDoc (`/redoc`) va OpenAPI spetsifikatsiyasi yoqilgan;
  - To‘liq xatolik izlari (traceback) ko‘rsatiladi;
  - Ishlab chiqish va sinovlar uchun qulay.
- **`APP_ENV=prod` (Ishlab Chiqarish)**:
  - Barcha API hujjatlari yopiq (404);
  - Xatolar umumlashtirilgan holda ko‘rsatiladi (`"Ichki server xatosi"`), tafsilotlar faqat server loglariga yoziladi;
  - Faqat `CORS_ORIGINS` da ruxsat berilgan domenlarga javob beriladi.

### 8.2. Loglarni Avtomatik Maskalash (`SensitiveDataFilter`)
Prod rejimida tizim loglaridagi barcha maxfiy kalitlar (`Bearer ...`, `sk-...`, `client_secret`, parollar va API kalitlar) avtomatik ravishda `***` bilan maskalanadi.

### 8.3. Xavfsizlik Sarlavhalari (`SecurityHeadersMiddleware`)
Har bir HTTP javobga avtomatik tarzda quyidagi xavfsizlik sarlavhalari qo‘shiladi:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: camera=(), microphone=(), geolocation=()`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` (HTTPS so‘rovlar uchun).

### 8.4. 4 Tilda To‘liq Qo‘llab-quvvatlash
Interfeys va AI muloqot tizimi to‘liq 4 ta tilda ishlaydi:
- **O‘zbekcha (lotin)** (`uz-latn`)
- **Ўзбекча (кирилл)** (`uz-cyrl`)
- **Русский** (`ru`)
- **English** (`en`)
