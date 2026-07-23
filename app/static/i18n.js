/* i18n.js — ZaminTahlil translation engine
   Languages: uz-latn (default), uz-cyrl, ru, en
   Usage: i18n.t('some.key', {var: value}) / i18n.setLanguage('ru') / i18n.applyStatic()
*/
(function () {
  const DICTS = {
    "uz-latn": {
      meta: { title: "ZaminTahlil — Boshqaruv paneli", description: "ZaminTahlil orqali dala chegaralari, sun'iy yo'ldosh tahlili va AI tavsiyalarini boshqaring." },
      nav: {
        statusLabel: "Tizim holati",
        statusLoading: "Server tekshirilmoqda...",
        statusOk: "Server ishlayapti",
        statusError: "Server bilan aloqa yo'q",
        langLabel: "Til"
      },
      header: {
        eyebrow: "RAQAMLI DALA MONITORINGI",
        title: "ZaminTahlil",
        lead: "Dalalarni bitta boshqaruv oynasida kuzating: kontur chizing, Sentinel-2 tasvirlarini taqqoslang, indekslarni tekshiring va amaliy tavsiyalar oling."
      },
      stats: {
        fields: "Jami dalalar",
        selectedArea: "Tanlangan maydon",
        latestCapture: "Oxirgi kuzatuv",
        notAnalyzed: "Tahlil qilinmagan",
        dash: "—"
      },
      story: {
        step: "01",
        eyebrow: "BOSHLANG'ICH QADAM",
        title: "Nazorat markazi",
        copy: "Ish oqimi oddiy: avval dala konturini chizing, keyin ekin ma'lumotlarini kiriting. Saqlangan dala bo'yicha tasvir, tavsiya va yillik dinamika avtomatik ochiladi.",
        mapStateLabel: "Xarita holati",
        fieldNotSelected: "Dala tanlanmagan",
        fieldSelected: "Dala tanlandi",
        mapStateHint: "Saqlangan dalani bosing yoki yangi polygon chizing.",
        contourLabel: "Kontur bo'yicha",
        contourStart: "Polygon chizishni boshlang",
        contourReady: "Kontur tayyor, formani to'ldiring",
        contourHint: "Maydon avtomatik hisoblanadi va serverda qayta tekshiriladi."
      },
      workspace: {
        step: "02",
        eyebrow: "XARITA WORKSPACE",
        title: "Dala konturi va tanlov",
        badge: "O'zbekiston ko'rinishi",
        hint: "Yangi dala uchun polygon chizing yoki saqlangan ko'k maydonni tanlang."
      },
      composer: {
        step: "03",
        eyebrow: "YANGI DALA",
        title: "Ma'lumotlarni kiriting",
        areaLabel: "Hisoblangan maydon",
        areaPlaceholder: "Avval xaritada polygon chizing",
        areaReady: "{area} ga (server qayta hisoblaydi)",
        cropLabel: "O'simlik yoki ekin nomi",
        cropPlaceholder: "Masalan: Paxta",
        plantedLabel: "Ekin ekilgan sana",
        stageLabel: "Rivojlanish bosqichi",
        stagePlaceholder: "Masalan: Gullash bosqichi",
        submit: "Dalani saqlash",
        msgSaving: "Dala saqlanmoqda...",
        msgSaved: "Dala saqlandi: {area} ga",
        msgNoDraft: "Avval xaritada polygon chizing."
      },
      empty: {
        eyebrow: "TANLOV KUTILMOQDA",
        title: "Tahlil paneli hali ochilmagan",
        copy: "Saqlangan dala tanlangach, shu sahifada tasvirlarni solishtirish, AI tavsiyalar va yillik indekslar ko'rinadi."
      },
      detail: {
        eyebrow: "TANLANGAN DALA",
        metaTemplate: "{area} ga · Ekilgan: {planted} · {stage}",
        modeLabel: "Tahlil rejimi",
        modeLatest: "Oxirgi ma'lumot",
        modeLatestCloudFree: "Oxirgi bulutsiz ma'lumot",
        analyzeButton: "Tahlil qilish",
        msgLoadingField: "Dala ma'lumotlari yuklanmoqda...",
        msgHasAcquisitions: "{count} ta kuzatuv mavjud.",
        msgNoAcquisitions: "Hali tahlil qilinmagan.",
        msgAnalyzing: "Sentinel Hub'dan oxirgi 5 ta tasvir tekshirilmoqda...",
        msgAnalyzeResult: "{count} ta yangi kuzatuv qayta ishlandi. Tanlangan sana: {date}, bulut: {cloud}.",
        cloudNone: "mavjud emas",
        cloudPct: "{value}%"
      },
      viewer: {
        eyebrow: "SUN'IY YO'LDOSH TASVIRLARI",
        title: "Qatlam va vaqt taqqoslovi",
        compareLabel: "Solishtirish rejimi",
        legendA: "A tasvir",
        legendB: "B tasvir",
        prevLayer: "Oldingi qatlam",
        nextLayer: "Keyingi qatlam",
        prevDate: "Oldingi sana",
        nextDate: "Keyingi sana",
        stateNoAcquisition: "Acquisition mavjud emas. Tahlil tugmasini bosing.",
        stateLoading: "Tasvir yuklanmoqda...",
        stateError: "Tasvirni yuklashda xato yuz berdi",
        stateNoArtifact: "Bu qatlam uchun artifact mavjud emas",
        stateFullyCloudy: "To'liq bulutli: indeks uchun yaroqli piksel yo'q",
        opacityLabel: "Shaffoflik",
        qaLabel: "QA yoki maska",
        mobileA: "A ni ko'rsatish",
        mobileB: "B ni ko'rsatish"
      },
      imageMeta: {
        layer: "Qatlam",
        date: "Sana",
        productId: "Product ID",
        cloud: "Bulut",
        validPixels: "Yaroqli piksel",
        notAvailable: "Mavjud emas"
      },
      recommendation: {
        eyebrow: "AI TAVSIYASI",
        title: "Dalaga amaliy xulosa",
        placeholder: "Tahlildan keyin tavsiya shu yerda chiqadi.",
        groupRedTitle: "Qilinishi shart",
        groupRedSub: "Eng ustuvor ishlar",
        groupYellowTitle: "Chora ko'rilishi kerak",
        groupYellowSub: "Nazorat va ehtiyot chorasi",
        groupGreenTitle: "Yaxshi jarayonlar",
        groupGreenSub: "Ijobiy holatlar",
        noAdvice: "Alohida tavsiya aniqlanmadi."
      },
      chat: {
        eyebrow: "SAVOL-JAVOB",
        title: "Dalaga oid savol yuboring",
        inputLabel: "Savolingiz",
        inputPlaceholder: "Masalan: NDVI pasayishi nimani anglatadi?",
        submit: "Savol yuborish",
        privacy: "Chatning oxirgi xabarlari shu brauzer sessiyasida saqlanadi."
      },
      chart: {
        eyebrow: "YILLIK DINAMIKA",
        title: "Asosiy indekslar harakati",
        yearLabel: "Yil",
        fromDateLabel: "Boshlanish sanasi",
        loadButton: "Hozirgacha yuklash",
        note: "Har nuqta bir kuzatuv bo'yicha indeks qiymatini ko'rsatadi.",
        emptyState: "Kuzatuv mavjud emas",
        axisTitle: "Indeks qiymati",
        msgLoading: "{date} sanasidan hozirgacha ma'lumotlar yuklanmoqda...",
        msgResult: "{found} ta kuzatuv topildi, {processed} tasi yangi qayta ishlandi.",
        msgChooseDate: "Boshlanish sanasini tanlang.",
        tooltipNoData: "bulut yoki no-data",
        tooltipCloud: "bulut {value}%"
      },
      units: { ha: "ga" },
      error: { generic: "Xato ({status})" }
    },

    "uz-cyrl": {
      meta: { title: "ЗаминТаҳлил — Бошқарув панели", description: "ЗаминТаҳлил орқали дала чегаралари, сунъий йўлдош таҳлили ва АИ тавсияларини бошқаринг." },
      nav: {
        statusLabel: "Тизим ҳолати",
        statusLoading: "Сервер текширилмоқда...",
        statusOk: "Сервер ишлаяпти",
        statusError: "Сервер билан алоқа йўқ",
        langLabel: "Тил"
      },
      header: {
        eyebrow: "РАҚАМЛИ ДАЛА МОНИТОРИНГИ",
        title: "ЗаминТаҳлил",
        lead: "Далаларни битта бошқарув ойнасида кузатинг: контур чизинг, Sentinel-2 тасвирларини таққосланг, индексларни текширинг ва амалий тавсиялар олинг."
      },
      stats: {
        fields: "Жами далалар",
        selectedArea: "Танланган майдон",
        latestCapture: "Охирги кузатув",
        notAnalyzed: "Таҳлил қилинмаган",
        dash: "—"
      },
      story: {
        step: "01",
        eyebrow: "БОШЛАНҒИЧ ҚАДАМ",
        title: "Назорат маркази",
        copy: "Иш оқими оддий: аввал дала конурини чизинг, кейин экин маълумотларини киритинг. Сақланган дала бўйича тасвир, тавсия ва йиллик динамика автоматик очилади.",
        mapStateLabel: "Харита ҳолати",
        fieldNotSelected: "Дала танланмаган",
        fieldSelected: "Дала танланди",
        mapStateHint: "Сақланган далани босинг ёки янги полигон чизинг.",
        contourLabel: "Контур бўйича",
        contourStart: "Полигон чизишни бошланг",
        contourReady: "Контур тайёр, форманни тўлдиринг",
        contourHint: "Майдон автоматик ҳисобланади ва серверда қайта текширилади."
      },
      workspace: {
        step: "02",
        eyebrow: "ХАРИТА ИШ МАЙДОНИ",
        title: "Дала контури ва танлов",
        badge: "Ўзбекистон кўриниши",
        hint: "Янги дала учун полигон чизинг ёки сақланган кўк майдонни танланг."
      },
      composer: {
        step: "03",
        eyebrow: "ЯНГИ ДАЛА",
        title: "Маълумотларни киритинг",
        areaLabel: "Ҳисобланган майдон",
        areaPlaceholder: "Аввал харитада полигон чизинг",
        areaReady: "{area} га (сервер қайта ҳисоблайди)",
        cropLabel: "Ўсимлик ёки экин номи",
        cropPlaceholder: "Масалан: Пахта",
        plantedLabel: "Экин экилган сана",
        stageLabel: "Ривожланиш босқичи",
        stagePlaceholder: "Масалан: Гуллаш босқичи",
        submit: "Далани сақлаш",
        msgSaving: "Дала сақланмоқда...",
        msgSaved: "Дала сақланди: {area} га",
        msgNoDraft: "Аввал харитада полигон чизинг."
      },
      empty: {
        eyebrow: "ТАНЛОВ КУТИЛМОҚДА",
        title: "Таҳлил панели ҳали очилмаган",
        copy: "Сақланган дала танлангач, шу саҳифада тасвирларни солиштириш, АИ тавсиялар ва йиллик индекслар кўринади."
      },
      detail: {
        eyebrow: "ТАНЛАНГАН ДАЛА",
        metaTemplate: "{area} га · Экилган: {planted} · {stage}",
        modeLabel: "Таҳлил режими",
        modeLatest: "Охирги маълумот",
        modeLatestCloudFree: "Охирги булутсиз маълумот",
        analyzeButton: "Таҳлил қилиш",
        msgLoadingField: "Дала маълумотлари юкланмоқда...",
        msgHasAcquisitions: "{count} та кузатув мавжуд.",
        msgNoAcquisitions: "Ҳали таҳлил қилинмаган.",
        msgAnalyzing: "Sentinel Hub'дан охирги 5 та тасвир текширилмоқда...",
        msgAnalyzeResult: "{count} та янги кузатув қайта ишланди. Танланган сана: {date}, булут: {cloud}.",
        cloudNone: "мавжуд эмас",
        cloudPct: "{value}%"
      },
      viewer: {
        eyebrow: "СУНЪИЙ ЙЎЛДОШ ТАСВИРЛАРИ",
        title: "Қатлам ва вақт таққослаш",
        compareLabel: "Солиштириш режими",
        legendA: "А тасвир",
        legendB: "Б тасвир",
        prevLayer: "Олдинги қатлам",
        nextLayer: "Кейинги қатлам",
        prevDate: "Олдинги сана",
        nextDate: "Кейинги сана",
        stateNoAcquisition: "Acquisition мавжуд эмас. Таҳлил тугмасини босинг.",
        stateLoading: "Тасвир юкланмоқда...",
        stateError: "Тасвирни юклашда хато юз берди",
        stateNoArtifact: "Бу қатлам учун артефакт мавжуд эмас",
        stateFullyCloudy: "Тўлиқ булутли: индекс учун яроқли пиксел йўқ",
        opacityLabel: "Шаффофлик",
        qaLabel: "QA ёки маска",
        mobileA: "А ни кўрсатиш",
        mobileB: "Б ни кўрсатиш"
      },
      imageMeta: {
        layer: "Қатлам",
        date: "Сана",
        productId: "Product ID",
        cloud: "Булут",
        validPixels: "Яроқли пиксел",
        notAvailable: "Мавжуд эмас"
      },
      recommendation: {
        eyebrow: "АИ ТАВСИЯСИ",
        title: "Далага амалий хулоса",
        placeholder: "Таҳлилдан кейин тавсия шу ерда чиқади.",
        groupRedTitle: "Қилиниши шарт",
        groupRedSub: "Энг устувор ишлар",
        groupYellowTitle: "Чора кўрилиши керак",
        groupYellowSub: "Назорат ва эҳтиёт чораси",
        groupGreenTitle: "Яхши жараёнлар",
        groupGreenSub: "Ижобий ҳолатлар",
        noAdvice: "Алоҳида тавсия аниқланмади."
      },
      chat: {
        eyebrow: "САВОЛ-ЖАВОБ",
        title: "Далага оид савол юборинг",
        inputLabel: "Саволингиз",
        inputPlaceholder: "Масалан: NDVI пасайиши нимани англатади?",
        submit: "Савол юбориш",
        privacy: "Чатнинг охирги хабарлари шу браузер сессиясида сақланади."
      },
      chart: {
        eyebrow: "ЙИЛЛИК ДИНАМИКА",
        title: "Асосий индекслар ҳаракати",
        yearLabel: "Йил",
        fromDateLabel: "Бошланиш санаси",
        loadButton: "Ҳозиргача юклаш",
        note: "Ҳар нуқта бир кузатув бўйича индекс қийматини кўрсатади.",
        emptyState: "Кузатув мавжуд эмас",
        axisTitle: "Индекс қиймати",
        msgLoading: "{date} санасидан ҳозиргача маълумотлар юкланмоқда...",
        msgResult: "{found} та кузатув топилди, {processed} таси янги қайта ишланди.",
        msgChooseDate: "Бошланиш санасини танланг.",
        tooltipNoData: "булут ёки no-data",
        tooltipCloud: "булут {value}%"
      },
      units: { ha: "га" },
      error: { generic: "Хато ({status})" }
    },

    ru: {
      meta: { title: "ZaminTahlil — Панель управления", description: "Управляйте границами полей, спутниковым анализом и рекомендациями ИИ через ZaminTahlil." },
      nav: {
        statusLabel: "Статус системы",
        statusLoading: "Проверка сервера...",
        statusOk: "Сервер работает",
        statusError: "Нет связи с сервером",
        langLabel: "Язык"
      },
      header: {
        eyebrow: "ЦИФРОВОЙ МОНИТОРИНГ ПОЛЕЙ",
        title: "ZaminTahlil",
        lead: "Следите за полями в едином окне управления: рисуйте контур, сравнивайте снимки Sentinel-2, проверяйте индексы и получайте практические рекомендации."
      },
      stats: {
        fields: "Всего полей",
        selectedArea: "Площадь поля",
        latestCapture: "Последний снимок",
        notAnalyzed: "Не анализировано",
        dash: "—"
      },
      story: {
        step: "01",
        eyebrow: "ПЕРВЫЙ ШАГ",
        title: "Центр управления",
        copy: "Процесс прост: сначала нарисуйте контур поля, затем укажите данные о культуре. После сохранения автоматически откроются снимки, рекомендации и годовая динамика.",
        mapStateLabel: "Статус карты",
        fieldNotSelected: "Поле не выбрано",
        fieldSelected: "Поле выбрано",
        mapStateHint: "Нажмите на сохранённое поле или нарисуйте новый полигон.",
        contourLabel: "По контуру",
        contourStart: "Начните рисовать полигон",
        contourReady: "Контур готов, заполните форму",
        contourHint: "Площадь рассчитывается автоматически и перепроверяется на сервере."
      },
      workspace: {
        step: "02",
        eyebrow: "РАБОЧАЯ ОБЛАСТЬ КАРТЫ",
        title: "Контур поля и выбор",
        badge: "Вид Узбекистана",
        hint: "Нарисуйте полигон для нового поля или выберите сохранённое синее поле."
      },
      composer: {
        step: "03",
        eyebrow: "НОВОЕ ПОЛЕ",
        title: "Введите данные",
        areaLabel: "Расчётная площадь",
        areaPlaceholder: "Сначала нарисуйте полигон на карте",
        areaReady: "{area} га (сервер пересчитает)",
        cropLabel: "Название культуры",
        cropPlaceholder: "Например: Хлопок",
        plantedLabel: "Дата посева",
        stageLabel: "Стадия развития",
        stagePlaceholder: "Например: Стадия цветения",
        submit: "Сохранить поле",
        msgSaving: "Поле сохраняется...",
        msgSaved: "Поле сохранено: {area} га",
        msgNoDraft: "Сначала нарисуйте полигон на карте."
      },
      empty: {
        eyebrow: "ОЖИДАНИЕ ВЫБОРА",
        title: "Панель анализа ещё не открыта",
        copy: "После выбора сохранённого поля здесь появятся сравнение снимков, рекомендации ИИ и годовые индексы."
      },
      detail: {
        eyebrow: "ВЫБРАННОЕ ПОЛЕ",
        metaTemplate: "{area} га · Посев: {planted} · {stage}",
        modeLabel: "Режим анализа",
        modeLatest: "Последние данные",
        modeLatestCloudFree: "Последние данные без облаков",
        analyzeButton: "Анализировать",
        msgLoadingField: "Загрузка данных поля...",
        msgHasAcquisitions: "Доступно наблюдений: {count}.",
        msgNoAcquisitions: "Ещё не анализировано.",
        msgAnalyzing: "Проверка последних 5 снимков в Sentinel Hub...",
        msgAnalyzeResult: "Обработано новых наблюдений: {count}. Выбранная дата: {date}, облачность: {cloud}.",
        cloudNone: "нет данных",
        cloudPct: "{value}%"
      },
      viewer: {
        eyebrow: "СПУТНИКОВЫЕ СНИМКИ",
        title: "Сравнение слоёв и дат",
        compareLabel: "Режим сравнения",
        legendA: "Снимок A",
        legendB: "Снимок B",
        prevLayer: "Предыдущий слой",
        nextLayer: "Следующий слой",
        prevDate: "Предыдущая дата",
        nextDate: "Следующая дата",
        stateNoAcquisition: "Нет наблюдений. Нажмите кнопку анализа.",
        stateLoading: "Загрузка снимка...",
        stateError: "Ошибка при загрузке снимка",
        stateNoArtifact: "Для этого слоя нет данных",
        stateFullyCloudy: "Полная облачность: нет пригодных пикселей для индекса",
        opacityLabel: "Прозрачность",
        qaLabel: "QA или маска",
        mobileA: "Показать A",
        mobileB: "Показать B"
      },
      imageMeta: {
        layer: "Слой",
        date: "Дата",
        productId: "ID продукта",
        cloud: "Облачность",
        validPixels: "Годных пикселей",
        notAvailable: "Нет данных"
      },
      recommendation: {
        eyebrow: "РЕКОМЕНДАЦИЯ ИИ",
        title: "Практический вывод по полю",
        placeholder: "Рекомендация появится здесь после анализа.",
        groupRedTitle: "Требуется действие",
        groupRedSub: "Первоочередные задачи",
        groupYellowTitle: "Нужен контроль",
        groupYellowSub: "Наблюдение и меры предосторожности",
        groupGreenTitle: "Хорошие процессы",
        groupGreenSub: "Положительные показатели",
        noAdvice: "Отдельных рекомендаций не выявлено."
      },
      chat: {
        eyebrow: "ВОПРОСЫ И ОТВЕТЫ",
        title: "Задайте вопрос о поле",
        inputLabel: "Ваш вопрос",
        inputPlaceholder: "Например: что означает снижение NDVI?",
        submit: "Отправить вопрос",
        privacy: "Последние сообщения чата хранятся только в этой сессии браузера."
      },
      chart: {
        eyebrow: "ГОДОВАЯ ДИНАМИКА",
        title: "Динамика основных индексов",
        yearLabel: "Год",
        fromDateLabel: "Дата начала",
        loadButton: "Загрузить по сегодня",
        note: "Каждая точка — значение индекса по одному наблюдению.",
        emptyState: "Наблюдений нет",
        axisTitle: "Значение индекса",
        msgLoading: "Загрузка данных с {date} по сегодня...",
        msgResult: "Найдено наблюдений: {found}, из них новых обработано: {processed}.",
        msgChooseDate: "Выберите дату начала.",
        tooltipNoData: "облачно или нет данных",
        tooltipCloud: "облачность {value}%"
      },
      units: { ha: "га" },
      error: { generic: "Ошибка ({status})" }
    },

    en: {
      meta: { title: "ZaminTahlil — Dashboard", description: "Manage field boundaries, satellite analysis and AI recommendations with ZaminTahlil." },
      nav: {
        statusLabel: "System status",
        statusLoading: "Checking server...",
        statusOk: "Server is running",
        statusError: "Cannot reach server",
        langLabel: "Language"
      },
      header: {
        eyebrow: "DIGITAL FIELD MONITORING",
        title: "ZaminTahlil",
        lead: "Track your fields from a single control panel: draw boundaries, compare Sentinel-2 imagery, check vegetation indices, and get practical recommendations."
      },
      stats: {
        fields: "Total fields",
        selectedArea: "Selected area",
        latestCapture: "Latest capture",
        notAnalyzed: "Not analyzed yet",
        dash: "—"
      },
      story: {
        step: "01",
        eyebrow: "GETTING STARTED",
        title: "Control center",
        copy: "The workflow is simple: draw the field boundary first, then enter the crop details. Once a field is saved, imagery, recommendations and yearly trends open automatically.",
        mapStateLabel: "Map status",
        fieldNotSelected: "No field selected",
        fieldSelected: "Field selected",
        mapStateHint: "Click a saved field or draw a new polygon.",
        contourLabel: "Boundary status",
        contourStart: "Start drawing a polygon",
        contourReady: "Boundary ready, fill in the form",
        contourHint: "Area is calculated automatically and re-verified on the server."
      },
      workspace: {
        step: "02",
        eyebrow: "MAP WORKSPACE",
        title: "Field boundary and selection",
        badge: "Uzbekistan view",
        hint: "Draw a polygon for a new field or select a saved blue field."
      },
      composer: {
        step: "03",
        eyebrow: "NEW FIELD",
        title: "Enter field details",
        areaLabel: "Calculated area",
        areaPlaceholder: "Draw a polygon on the map first",
        areaReady: "{area} ha (server will recalculate)",
        cropLabel: "Crop name",
        cropPlaceholder: "e.g. Cotton",
        plantedLabel: "Planting date",
        stageLabel: "Growth stage",
        stagePlaceholder: "e.g. Flowering stage",
        submit: "Save field",
        msgSaving: "Saving field...",
        msgSaved: "Field saved: {area} ha",
        msgNoDraft: "Draw a polygon on the map first."
      },
      empty: {
        eyebrow: "AWAITING SELECTION",
        title: "Analysis panel is not open yet",
        copy: "Once a saved field is selected, imagery comparison, AI recommendations, and yearly indices will appear on this page."
      },
      detail: {
        eyebrow: "SELECTED FIELD",
        metaTemplate: "{area} ha · Planted: {planted} · {stage}",
        modeLabel: "Analysis mode",
        modeLatest: "Latest data",
        modeLatestCloudFree: "Latest cloud-free data",
        analyzeButton: "Run analysis",
        msgLoadingField: "Loading field data...",
        msgHasAcquisitions: "{count} observation(s) available.",
        msgNoAcquisitions: "Not analyzed yet.",
        msgAnalyzing: "Checking the last 5 images from Sentinel Hub...",
        msgAnalyzeResult: "{count} new observation(s) processed. Selected date: {date}, cloud cover: {cloud}.",
        cloudNone: "not available",
        cloudPct: "{value}%"
      },
      viewer: {
        eyebrow: "SATELLITE IMAGERY",
        title: "Layer and time comparison",
        compareLabel: "Compare mode",
        legendA: "Image A",
        legendB: "Image B",
        prevLayer: "Previous layer",
        nextLayer: "Next layer",
        prevDate: "Previous date",
        nextDate: "Next date",
        stateNoAcquisition: "No acquisitions available. Click Run analysis.",
        stateLoading: "Loading image...",
        stateError: "Error loading image",
        stateNoArtifact: "No artifact available for this layer",
        stateFullyCloudy: "Fully cloudy: no valid pixels for this index",
        opacityLabel: "Opacity",
        qaLabel: "QA / mask",
        mobileA: "Show A",
        mobileB: "Show B"
      },
      imageMeta: {
        layer: "Layer",
        date: "Date",
        productId: "Product ID",
        cloud: "Cloud cover",
        validPixels: "Valid pixels",
        notAvailable: "Not available"
      },
      recommendation: {
        eyebrow: "AI RECOMMENDATION",
        title: "Practical takeaways for this field",
        placeholder: "A recommendation will appear here after analysis.",
        groupRedTitle: "Action required",
        groupRedSub: "Top priority items",
        groupYellowTitle: "Needs monitoring",
        groupYellowSub: "Watch and take precautions",
        groupGreenTitle: "Healthy processes",
        groupGreenSub: "Positive conditions",
        noAdvice: "No specific recommendation identified."
      },
      chat: {
        eyebrow: "Q&A",
        title: "Ask a question about this field",
        inputLabel: "Your question",
        inputPlaceholder: "e.g. What does a drop in NDVI mean?",
        submit: "Send question",
        privacy: "Recent chat messages are stored only in this browser session."
      },
      chart: {
        eyebrow: "YEARLY TREND",
        title: "Key index movement",
        yearLabel: "Year",
        fromDateLabel: "Start date",
        loadButton: "Load through today",
        note: "Each point shows the index value for one observation.",
        emptyState: "No observations available",
        axisTitle: "Index value",
        msgLoading: "Loading data from {date} through today...",
        msgResult: "{found} observation(s) found, {processed} newly processed.",
        msgChooseDate: "Choose a start date.",
        tooltipNoData: "cloudy or no data",
        tooltipCloud: "cloud {value}%"
      },
      units: { ha: "ha" },
      error: { generic: "Error ({status})" }
    }
  };

  const LOCALE_MAP = {
    "uz-latn": "uz-Latn",
    "uz-cyrl": "uz-Cyrl",
    ru: "ru-RU",
    en: "en-US"
  };

  const LANG_NAMES = {
    "uz-latn": "O'zbekcha (lotin)",
    "uz-cyrl": "Ўзбекча (кирилл)",
    ru: "Русский",
    en: "English"
  };

  let current = "uz-latn";
  const listeners = [];

  function getPath(obj, path) {
    return path.split(".").reduce((acc, key) => (acc && acc[key] !== undefined ? acc[key] : undefined), obj);
  }

  function t(key, vars) {
    let str = getPath(DICTS[current], key);
    if (str === undefined) str = getPath(DICTS["uz-latn"], key);
    if (str === undefined) return key;
    if (vars) {
      Object.keys(vars).forEach((k) => {
        str = str.replace(new RegExp(`\\{${k}\\}`, "g"), vars[k]);
      });
    }
    return str;
  }

  function applyStatic(root = document) {
    root.querySelectorAll("[data-i18n]").forEach((element) => {
      element.textContent = t(element.getAttribute("data-i18n"));
    });
    root.querySelectorAll("[data-i18n-placeholder]").forEach((element) => {
      element.setAttribute("placeholder", t(element.getAttribute("data-i18n-placeholder")));
    });
    root.querySelectorAll("[data-i18n-title]").forEach((element) => {
      element.setAttribute("title", t(element.getAttribute("data-i18n-title")));
    });
    document.documentElement.lang = current.startsWith("uz") ? "uz" : current;
    document.title = t("meta.title");
    const descriptionTag = document.querySelector('meta[name="description"]');
    if (descriptionTag) descriptionTag.setAttribute("content", t("meta.description"));
  }

  function setLanguage(lang) {
    if (!DICTS[lang]) return;
    current = lang;
    applyStatic();
    listeners.forEach((fn) => fn(lang));
  }

  function onChange(fn) {
    listeners.push(fn);
  }

  function getLocale() {
    return LOCALE_MAP[current] || "en-US";
  }

  window.i18n = {
    t,
    setLanguage,
    applyStatic,
    onChange,
    getLocale,
    get current() {
      return current;
    },
    languages: LANG_NAMES
  };
})();