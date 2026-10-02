# Translation review — tour 301 (Nice, France), LOCAL-561

Three engines translated all 10 stops of tour 301 to **Russian** and **Spanish**.
Engines are blinded as **X / Y / Z** so you can judge the prose blind; the key is at
the very bottom. The service was called directly (no HTTP, no cache); no rows were
written to the database for this review.

## Cost and wall time (10 stops each)

| Engine | ru cost | ru time | es cost | es time |
|--------|---------|---------|---------|---------|
| **X** | $0.0162 (OpenAI tokens) | 54s | $0.0159 (OpenAI tokens) | 67s |
| **Y** | $0.2760 (AWS Translate chars; no LLM tokens) | 1s | $0.2760 (AWS Translate chars; no LLM tokens) | 1s |
| **Z** | $0.0814 (OpenAI tokens) | 48s | $0.0774 (OpenAI tokens) | 38s |

Notes: AWS cost is its per-character charge for the tour text (it does no names
glossary and no per-token billing). The LLM engines' cost is the summed OpenAI token
cost (gpt-4o names pass + prose pass), metered per call and summed per tour. Polly TTS
is identical for all three and is excluded here.

## Russian — stops 1–3, spoken lines side by side

### Stop 1

**X** — header `Остановка 1:`

- Title: Замковая гора Ниццы
- Orientation: Как сориентироваться: Следует двигаться на северо-восток по набережной Quai des États-Unis, затем подняться по лестнице на холм, открывающем захватывающие виды впереди. Находясь на краю Замковой горы Ниццы, можно полюбоваться лазурными водами Средиземного моря. Здесь можно увидеть остатки древних укреплений и зелёные сады внизу.
- Directions: Как пройти: Покидая Замковую гору Ниццы, направляйтесь вниз к Старому городу. Прогуляйтесь по очаровательным узким улочкам, пока не достигнете Rue Droite. Следуйте по этой улице, пока не дойдёте до Пале Ласкарис, красивого барочного дворца слева.

**Y** — header `Остановка 1:`

- Title: Замковая гора в Ницце
- Orientation: Ориентация: двигайтесь на северо-восток по набережной США, затем поднимитесь по лестнице на холм, откуда открывается потрясающий вид на окрестности. Встаньте на краю Замковой горы в Ницце с видом на лазурные воды Средиземного моря. Посмотрите на остатки древних укреплений и пышных садов внизу.
- Directions: Как добраться: Покидая Замковый холм в Ницце, спуститесь к Старому городу. Прогуляйтесь по очаровательным узким улочкам, пока не дойдете до улицы Rue Droite. Следуйте по этой улице, пока не доберетесь до Palais Lascaris, красивого дворца в стиле барокко слева от вас.

**Z** — header `Остановка 1:`

- Title: Замковая гора Ниццы
- Orientation: Как сориентироваться: Направляйтесь на северо-восток по набережной Кэ дез Этат-Юни, затем поднимитесь по лестнице на холм, откуда откроются потрясающие виды. На краю Замковой горы Ниццы перед вами раскинется лазурное Средиземное море. Здесь можно увидеть остатки древних укреплений и пышные сады внизу.
- Directions: Как пройти: Покидая Замковую гору Ниццы, спуститесь в сторону Старого города. Прогуляйтесь по очаровательным узким улочкам, пока не дойдете до улицы Друат. Следуйте по этой улице, пока не окажетесь у Пале Ласкарис, красивого барочного дворца слева.

### Stop 2

**X** — header `Остановка 2:`

- Title: Пале Ласкарис
- Orientation: Как сориентироваться: Прибыв в Пале Ласкарис в сердце Старого города, можно увидеть величественный фасад этого аристократического здания XVII века. Когда-то резиденция влиятельной семьи Винтимиль-Ласкарис, сегодня он стал музеем, в котором хранится более 500 музыкальных инструментов — сокровищница звука и истории, ожидающая своего открытия.
- Directions: Как пройти: От Пале Ласкарис двигайтесь на юг по улице Друит, пока не достигнете Площади Россетти с ее оживленными кафе. Продолжайте прямо по улице Префектуры, пока не доберетесь до Оперы Ниццы, величественного здания с красивым фасадом. Наслаждайтесь прогулкой по очаровательным улочкам Старого города Ниццы!

**Y** — header `Остановка 2:`

- Title: Дворец Ласкари
- Orientation: Ориентация: Прибыв во дворец Ласкари в самом сердце Старого города, обратите внимание на величественный фасад этого аристократического здания семнадцатого века. Когда-то это была резиденция влиятельной семьи Винтимиль-Ласкари, а теперь здесь находится музей, в котором представлено более 500 музыкальных инструментов. Это сокровищница звука и истории, которая ждет своего открытия.
- Directions: Как добраться: из Дворца Ласкари отправляйтесь на юг по улице Друйте, пока не дойдете до площади Россетти с ее оживленными кафе. Продолжайте движение прямо по улице Префектуры, пока не доберетесь до Оперы Ниццы — величественного здания с красивым фасадом. Насладитесь прогулкой по очаровательным улочкам Старого города Ниццы!

**Z** — header `Остановка 2:`

- Title: Пале Ласкарис
- Orientation: Как сориентироваться: Прибыв в Пале Ласкарис в самом сердце Старого города, вы увидите величественный фасад этого аристократического здания XVII века. Когда-то резиденция влиятельной семьи Винтимиль-Ласкарис, теперь это музей, в котором хранится более 500 музыкальных инструментов — настоящая сокровищница звуков и истории.
- Directions: Как пройти: От Пале Ласкарис идите на юг по улице Рю Друат, пока не дойдёте до Площади Росетти с её оживлёнными кафе. Продолжайте прямо по улице Рю де ла Префектюр, пока не доберётесь до Оперы Ниццы, величественного здания с красивым фасадом. Наслаждайтесь прогулкой по очаровательным улицам Старого города Ниццы!

### Stop 3

**X** — header `Остановка 3:`

- Title: Опера Ниццы
- Orientation: Как сориентироваться: Стоя перед Оперой Ниццы, стоит уделить время, чтобы оценить её элегантный фасад, который стал свидетелем выступлений таких известных композиторов, как Берлиоз и Верди. Расположенная в самом сердце Ниццы, эта опера сыграла значительную роль в формировании культурного ландшафта города.
- Directions: Как пройти: Направляйтесь на юг по проспекту Жан Жореса от Опера Ниццы, пока не достигнете очаровательного Старого города. Оказавшись там, прогуляйтесь по красочным улочкам, полным кафе и магазинов, пока не доберётесь до шумного Cours Saleya Market. Вы не сможете пропустить яркие торговые ряды, где продаются свежие продукты, цветы и местные товары.

**Y** — header `Остановка 3:`

- Title: Опера Ниццы
- Orientation: Ориентация: Стоя перед Оперой Ниццы, уделите время тому, чтобы полюбоваться ее элегантным фасадом, на котором выступали такие известные композиторы, как Берлиоз и Верди. Этот оперный театр, расположенный в самом центре Ниццы, сыграл важную роль в формировании культурного ландшафта города.
- Directions: Как добраться: от Оперы Ниццы направляйтесь на юг по проспекту Жана Жореса, пока не доберетесь до очаровательного Старого города. Оказавшись там, прогуляйтесь по красочным улицам с кафе и магазинами, пока не дойдете до оживленного рынка Кур-Салея. Обязательно посетите оживленные рыночные прилавки, где продаются свежие продукты, цветы и местные товары.

**Z** — header `Остановка 3:`

- Title: Опера Ниццы
- Orientation: Как сориентироваться: Перед Оперой Ниццы стоит остановиться и полюбоваться её элегантным фасадом, который стал свидетелем выступлений таких известных композиторов, как Берлиоз и Верди. Расположенный в самом сердце Ниццы, этот оперный театр сыграл значительную роль в формировании культурного облика города.
- Directions: Как пройти: Идите на юг по авеню Жан Жорес от Оперы Ниццы, пока не достигнете очаровательного Старого города. Там прогуляйтесь по красочным улицам, полным кафе и магазинов, пока не доберетесь до оживленного рынка Cours Saleya Market. Вы не сможете пропустить яркие рыночные прилавки, продающие свежие продукты, цветы и местные товары.

## Russian — full Stop 2, each engine verbatim

### X — `Остановка 2:`

```
Пале Ласкарис

Как сориентироваться: Прибыв в Пале Ласкарис в сердце Старого города, можно увидеть величественный фасад этого аристократического здания XVII века. Когда-то резиденция влиятельной семьи Винтимиль-Ласкарис, сегодня он стал музеем, в котором хранится более 500 музыкальных инструментов — сокровищница звука и истории, ожидающая своего открытия.

Построенный в начале XVII века и позже модифицированный в XVIII веке, Пале Ласкарис был символом власти и престижа для семьи Винтимиль-Ласкарис до начала XIX века. В 1942 году город Ницца приобрел дворец, чтобы преобразовать его в музей, что позволило сохранить его богатое наследие и предложить посетителям возможность заглянуть в его роскошное прошлое. Переступив порог дворца, вы сразу же погружаетесь в сенсорное путешествие во времени. Скрип половиц под ногами отзывается шагами аристократов, когда-то бродивших по этим залам. Легкий аромат старого дерева и истории витает в воздухе, приглашая вас исследовать дальше. Роскошные барочные интерьеры Пале Ласкарис скрывают истории некогда могущественной семьи Савой, чье влияние определяло судьбу региона. Бродя по комнатам, украшенным изысканными гобеленами и роскошной мебелью, можно представить себе величие и элегантность, которые когда-то наполняли эти пространства. Эта остановка в нашем пешеходном туре по Ницце связана с нашей темой, демонстрируя пересечение искусства, истории и культуры. Пале Ласкарис служит окном в прошлое, предлагая взгляд на ушедшую эпоху, когда музыка и роскошь переплетались, создавая мир красоты и утонченности. Чуть дальше от этого богатого исторического места ждут эхо оперного прошлого, намекая на величие и драму, которые когда-то украшали этот яркий город.

Как пройти: От Пале Ласкарис двигайтесь на юг по улице Друит, пока не достигнете Площади Россетти с ее оживленными кафе. Продолжайте прямо по улице Префектуры, пока не доберетесь до Оперы Ниццы, величественного здания с красивым фасадом. Наслаждайтесь прогулкой по очаровательным улочкам Старого города Ниццы!
```

### Y — `Остановка 2:`

```
Ориентация: Прибыв во дворец Ласкари в самом сердце Старого города, обратите внимание на величественный фасад этого аристократического здания семнадцатого века. Когда-то это была резиденция влиятельной семьи Винтимиль-Ласкари, а теперь здесь находится музей, в котором представлено более 500 музыкальных инструментов. Это сокровищница звука и истории, которая ждет своего открытия.

Дворец Ласкари, построенный в начале семнадцатого века и позже измененный в восемнадцатом веке, до начала XIX века был символом могущества и престижа семьи Винтимиль-Ласкари. В 1942 году Ницца приобрела дворец и превратила его в музей. Это решение позволило сохранить богатое наследие дворца и познакомить посетителей с его богатым прошлым. Зайдя во дворец, вы сразу же погрузитесь в чувственное путешествие во времени. Скрип деревянных полов под ногами напоминает шаги аристократов, которые когда-то бродили по этим залам. В воздухе витает слабый аромат состаренного дерева и истории, который приглашает вас к новым открытиям. В роскошных интерьерах дворца Ласкари в стиле барокко скрываются истории некогда могущественной семьи Савойи, влияние которой определило судьбу региона. Прогуливаясь по комнатам, украшенным замысловатыми гобеленами и изысканной мебелью, представьте себе величие и элегантность, которые когда-то наполняли эти помещения. Эта остановка в нашей пешеходной экскурсии по Ницце посвящена нашей теме, демонстрируя пересечение искусства, истории и культуры. Дворец Ласкари — это окно в прошлое, позволяющее заглянуть в ушедшую эпоху, когда музыка и роскошь переплетались в мир красоты и изысканности. Прямо за этим богатым историческим памятником вас ждут отголоски оперного прошлого, намекающие на величие и драматизм, которые когда-то были присущи этому оживленному городу.

Как добраться: из Дворца Ласкари отправляйтесь на юг по улице Друйте, пока не дойдете до площади Россетти с ее оживленными кафе. Продолжайте движение прямо по улице Префектуры, пока не доберетесь до Оперы Ниццы — величественного здания с красивым фасадом. Насладитесь прогулкой по очаровательным улочкам Старого города Ниццы!
```

### Z — `Остановка 2:`

```
Пале Ласкарис

Как сориентироваться: Прибыв в Пале Ласкарис в самом сердце Старого города, вы увидите величественный фасад этого аристократического здания XVII века. Когда-то резиденция влиятельной семьи Винтимиль-Ласкарис, теперь это музей, в котором хранится более 500 музыкальных инструментов — настоящая сокровищница звуков и истории.

Построенный в начале XVII века и позже изменённый в XVIII веке, Пале Ласкарис был символом власти и престижа семьи Винтимиль-Ласкарис до начала XIX века. В 1942 году город Ницца приобрёл дворец, чтобы превратить его в музей, что позволило сохранить его богатое наследие и предложить посетителям заглянуть в его роскошное прошлое. Войдя в дворец, вы сразу погружаетесь в чувственное путешествие во времени. Скрип деревянных полов под ногами напоминает о шагах аристократов, когда-то бродивших по этим залам. Лёгкий аромат старинного дерева и истории витает в воздухе, приглашая исследовать дальше. Роскошные барочные интерьеры Пале Ласкарис скрывают истории о некогда могущественной семье Савойи, чьё влияние формировало судьбу региона. Прогуливаясь по комнатам, украшенным сложными гобеленами и изысканной мебелью, представьте себе величие и элегантность, которые когда-то наполняли эти пространства. Эта остановка на нашем пешем туре по Ницце соединяет нашу тему, демонстрируя пересечение искусства, истории и культуры. Пале Ласкарис служит окном в прошлое, предлагая заглянуть в ушедшую эпоху, когда музыка и роскошь переплетались, создавая мир красоты и утончённости. За пределами этого богатого исторического места ждут отголоски оперного прошлого, намекая на величие и драму, которые когда-то украшали этот яркий город.

Как пройти: От Пале Ласкарис идите на юг по улице Рю Друат, пока не дойдёте до Площади Росетти с её оживлёнными кафе. Продолжайте прямо по улице Рю де ла Префектюр, пока не доберётесь до Оперы Ниццы, величественного здания с красивым фасадом. Наслаждайтесь прогулкой по очаровательным улицам Старого города Ниццы!
```

## Spanish — stops 1–3, spoken lines side by side

### Stop 1

**X** — header `Parada 1:`

- Title: Colline du Château
- Orientation: Orientación: Dirígete al noreste por el Quai des États-Unis, luego sube por las escaleras que llevan a la colina, ofreciendo un adelanto de las impresionantes vistas que te esperan. Colócate en el borde de la Colline du Château, con vistas a las aguas azules del mar Mediterráneo. Busca los restos de antiguas fortificaciones y los exuberantes jardines que se encuentran abajo.
- Directions: Cómo llegar: Al dejar la Colline du Château, dirígete hacia el casco antiguo. Pasea por las encantadoras calles estrechas hasta llegar a la Rue Droite. Sigue esta calle hasta que llegues al Palais Lascaris, un hermoso palacio barroco a tu izquierda.

**Y** — header `Parada 1:`

- Title: Colina del Castillo de Niza
- Orientation: Orientación: Diríjase hacia el noreste por el Quai des États-Unis y, a continuación, suba la colina por las escaleras para disfrutar de una vista previa de las impresionantes vistas que tiene por delante. Colócate en el borde de la colina del castillo de Niza, con vistas a las aguas azules del mar Mediterráneo. A continuación, busca los restos de antiguas fortificaciones y exuberantes jardines.
- Directions: Cómo llegar: Al salir de la colina del castillo de Niza, diríjase hacia el casco antiguo. Pasea por las encantadoras calles estrechas hasta llegar a la Rue Droite. Siga por esta calle hasta llegar al Palais Lascaris, un hermoso palacio barroco a su izquierda.

**Z** — header `Parada 1:`

- Title: Colina del Castillo de Niza
- Orientation: Orientación: Dirígete al noreste por el Quai des États-Unis, luego sube las escaleras de la colina, que ofrecen un adelanto de las impresionantes vistas que te esperan. Desde el borde de la Colina del Castillo de Niza, se puede contemplar las aguas azules del mar Mediterráneo. El visitante puede encontrar los restos de antiguas fortificaciones y jardines exuberantes abajo.
- Directions: Cómo llegar: Al dejar la Colina del Castillo de Niza, desciende hacia el Casco Antiguo. Pasea por las encantadoras calles estrechas hasta llegar a la Rue Droite. Sigue esta calle hasta llegar al Palacio Lascaris, un hermoso palacio barroco a tu izquierda.

### Stop 2

**X** — header `Parada 2:`

- Title: Palais Lascaris
- Orientation: Orientación: Al llegar al Palais Lascaris en el corazón del Casco Antiguo, se puede admirar la gran fachada de este edificio aristocrático del siglo XVII. Una vez residencia de la influyente familia Vintimille-Lascaris, ahora alberga un museo con más de 500 instrumentos musicales, un tesoro de sonido e historia que espera ser descubierto.
- Directions: Cómo llegar: Desde el Palais Lascaris, dirígete hacia el sur por la Rue Droite hasta llegar a la Place Rossetti con sus bulliciosos cafés. Continúa recto por la Rue de la Préfecture hasta que llegues al Opéra de Nice, un gran edificio con una hermosa fachada. ¡Disfruta del paseo por las encantadoras calles del Casco Antiguo de Niza!

**Y** — header `Parada 2:`

- Title: Palacio Lascaris
- Orientation: Orientación: Al llegar al Palais Lascaris, en el corazón del casco antiguo, busque la gran fachada de este edificio aristocrático del siglo XVII. Antiguamente la residencia de la influyente familia Vintimille-Lascaris, ahora es un museo que alberga más de 500 instrumentos musicales, un tesoro de sonido e historia que espera ser descubierto.
- Directions: Cómo llegar: Desde el Palais Lascaris, diríjase hacia el sur por la Rue Droite hasta llegar a la Place Rossetti, con sus bulliciosas cafeterías. Continúe recto por la Rue de la Préfecture hasta llegar a la Opéra de Nice, un gran edificio con una hermosa fachada. ¡Disfruta del paseo por las encantadoras calles del casco antiguo de Niza!

**Z** — header `Parada 2:`

- Title: Palacio Lascaris
- Orientation: Orientación: Al llegar al Palacio Lascaris en el corazón del Casco Antiguo, se encontrará con la majestuosa fachada de este edificio aristocrático del siglo XVII. Antiguamente residencia de la influyente familia Vintimille-Lascaris, hoy se erige como un museo que alberga más de 500 instrumentos musicales, un tesoro de sonido e historia esperando ser descubierto.
- Directions: Cómo llegar: Desde el Palacio Lascaris, dirígete al sur por la Rue Droite hasta llegar a la Place Rossetti con sus animados cafés. Continúa recto por la Rue de la Préfecture hasta llegar a la Ópera de Niza, un majestuoso edificio con una hermosa fachada. ¡Disfruta del paseo por las encantadoras calles del Casco Antiguo de Niza!

### Stop 3

**X** — header `Parada 3:`

- Title: Opéra de Nice
- Orientation: Orientación: Al estar frente al Opéra de Nice, se puede apreciar su elegante fachada que ha sido testigo de las actuaciones de renombrados compositores como Berlioz y Verdi. Situada en el corazón de Niza, esta casa de ópera ha desempeñado un papel significativo en la configuración del paisaje cultural de la ciudad.
- Directions: Cómo llegar: Dirígete hacia el sur por la Avenida Jean Jaurès desde el Opéra de Nice hasta llegar al encantador Casco Antiguo. Una vez allí, pasea por las coloridas calles llenas de cafés y tiendas hasta que llegues al bullicioso Mercado de Cours Saleya. No puedes perderte los vibrantes puestos del mercado que venden productos frescos, flores y productos locales.

**Y** — header `Parada 3:`

- Title: Opéra de Nice
- Orientation: Orientación: Mientras se encuentra frente a la Ópera de Niza, tómese un momento para apreciar su elegante fachada, que ha sido testigo de las actuaciones de compositores de renombre como Berlioz y Verdi. Ubicado en el corazón de Niza, este teatro de ópera ha desempeñado un papel importante en la configuración del panorama cultural de la ciudad.
- Directions: Cómo llegar: Diríjase hacia el sur por la avenida Jean Jaurès desde la Ópera de Niza hasta llegar al encantador casco antiguo. Una vez allí, pasea por las coloridas calles llenas de cafés y tiendas hasta llegar al bullicioso mercado de Cours Saleya. No te puedes perder los animados puestos del mercado que venden productos frescos, flores y productos locales.

**Z** — header `Parada 3:`

- Title: Ópera de Niza
- Orientation: Orientación: Al situarse frente a la Ópera de Niza, se puede apreciar su elegante fachada que ha sido testigo de las actuaciones de compositores renombrados como Berlioz y Verdi. Ubicada en el corazón de Niza, esta casa de ópera ha desempeñado un papel significativo en la configuración del paisaje cultural de la ciudad.
- Directions: Cómo llegar: Dirígete al sur por la Avenue Jean Jaurès desde la Ópera de Niza hasta llegar al encantador Casco Antiguo. Una vez allí, pasea por las coloridas calles llenas de cafés y tiendas hasta llegar al bullicioso Mercado de Cours Saleya. No te pierdas los vibrantes puestos del mercado que venden productos frescos, flores y artículos locales.

## Spanish — full Stop 2, each engine verbatim

### X — `Parada 2:`

```
Palais Lascaris

Orientación: Al llegar al Palais Lascaris en el corazón del Casco Antiguo, se puede admirar la gran fachada de este edificio aristocrático del siglo XVII. Una vez residencia de la influyente familia Vintimille-Lascaris, ahora alberga un museo con más de 500 instrumentos musicales, un tesoro de sonido e historia que espera ser descubierto.

Construido a principios del siglo XVII y modificado posteriormente en el siglo XVIII, el Palais Lascaris fue un símbolo de poder y prestigio para la familia Vintimille-Lascaris hasta principios del siglo XIX. En 1942, la ciudad de Niza adquirió el palacio para transformarlo en un museo, una decisión que preservaría su rico patrimonio y ofrecería a los visitantes un vistazo a su opulento pasado. Al entrar en el palacio, se es recibido de inmediato en un viaje sensorial a través del tiempo. El crujir de los suelos de madera bajo los pies resuena con los pasos de los aristócratas que una vez recorrieron estos pasillos. El tenue aroma de la madera envejecida y la historia permanece en el aire, invitando a explorar más. Los lujosos interiores barrocos del Palais Lascaris ocultan historias de una poderosa familia de Saboya cuya influencia moldeó el destino de la región. Al deambular por las habitaciones adornadas con intrincadas tapicerías y muebles ornamentados, se puede imaginar la grandeza y elegancia que una vez llenaron estos espacios. Esta parada en nuestro recorrido a pie por Niza se conecta con nuestro tema al mostrar la intersección del arte, la historia y la cultura. El Palais Lascaris sirve como una ventana al pasado, ofreciendo un vistazo a una época pasada cuando la música y el lujo se entrelazaban para crear un mundo de belleza y refinamiento. Justo más allá de este rico sitio histórico, los ecos de un pasado operístico esperan, insinuando la grandeza y el drama que una vez adornaron esta vibrante ciudad.

Cómo llegar: Desde el Palais Lascaris, dirígete hacia el sur por la Rue Droite hasta llegar a la Place Rossetti con sus bulliciosos cafés. Continúa recto por la Rue de la Préfecture hasta que llegues al Opéra de Nice, un gran edificio con una hermosa fachada. ¡Disfruta del paseo por las encantadoras calles del Casco Antiguo de Niza!
```

### Y — `Parada 2:`

```
Orientación: Al llegar al Palais Lascaris, en el corazón del casco antiguo, busque la gran fachada de este edificio aristocrático del siglo XVII. Antiguamente la residencia de la influyente familia Vintimille-Lascaris, ahora es un museo que alberga más de 500 instrumentos musicales, un tesoro de sonido e historia que espera ser descubierto.

Construido a principios del siglo XVII y modificado posteriormente en el siglo XVIII, el Palais Lascaris fue un símbolo de poder y prestigio para la familia Vintimille-Lascaris hasta principios del siglo XIX. En 1942, la ciudad de Niza adquirió el palacio para transformarlo en museo, una decisión que preservaría su rico patrimonio y ofrecería a los visitantes una visión de su opulento pasado. Entra en el palacio e inmediatamente te verás envuelto en un viaje sensorial a través del tiempo. El crujido de los pisos de madera bajo tus pies recuerda los pasos de los aristócratas que alguna vez deambularon por estas salas. El leve aroma de la madera envejecida y la historia perdura en el aire e invita a explorar más a fondo. Los lujosos interiores barrocos del Palais Lascaris esconden las historias de una familia Saboya que alguna vez fue poderosa y cuya influencia marcó el destino de la región. Mientras pasea por las habitaciones adornadas con intrincados tapices y muebles ornamentados, imagine la grandeza y la elegancia que alguna vez llenaron estos espacios. Esta parada de nuestro recorrido a pie por Niza se conecta con nuestro tema al mostrar la intersección del arte, la historia y la cultura. El Palais Lascaris sirve como una ventana al pasado y ofrece una visión de una época pasada en la que la música y el lujo se entrelazaban para crear un mundo de belleza y refinamiento. Un poco más allá de este rico sitio histórico, te esperan los ecos de un pasado operístico, que hacen alusión a la grandeza y el drama que alguna vez adornaron a esta vibrante ciudad.

Cómo llegar: Desde el Palais Lascaris, diríjase hacia el sur por la Rue Droite hasta llegar a la Place Rossetti, con sus bulliciosas cafeterías. Continúe recto por la Rue de la Préfecture hasta llegar a la Opéra de Nice, un gran edificio con una hermosa fachada. ¡Disfruta del paseo por las encantadoras calles del casco antiguo de Niza!
```

### Z — `Parada 2:`

```
Palacio Lascaris

Orientación: Al llegar al Palacio Lascaris en el corazón del Casco Antiguo, se encontrará con la majestuosa fachada de este edificio aristocrático del siglo XVII. Antiguamente residencia de la influyente familia Vintimille-Lascaris, hoy se erige como un museo que alberga más de 500 instrumentos musicales, un tesoro de sonido e historia esperando ser descubierto.

Construido a principios del siglo XVII y modificado posteriormente en el siglo XVIII, el Palacio Lascaris fue un símbolo de poder y prestigio para la familia Vintimille-Lascaris hasta principios del siglo XIX. En 1942, la ciudad de Niza adquirió el palacio para transformarlo en un museo, una decisión que preservaría su rico patrimonio y ofrecería a los visitantes un vistazo a su opulento pasado. Al entrar en el palacio, se inicia un viaje sensorial a través del tiempo. El crujir de los suelos de madera bajo sus pies evoca las pisadas de los aristócratas que una vez recorrieron estos pasillos. El tenue aroma de madera envejecida e historia flota en el aire, invitándole a explorar más. Los lujosos interiores barrocos del Palacio Lascaris esconden historias de una poderosa familia de Saboya cuya influencia moldeó el destino de la región. Al recorrer las salas adornadas con intrincados tapices y muebles ornamentados, se puede imaginar la grandeza y elegancia que una vez llenaron estos espacios. Esta parada en nuestro recorrido a pie por Niza se conecta con nuestro tema al mostrar la intersección del arte, la historia y la cultura. El Palacio Lascaris sirve como una ventana al pasado, ofreciendo un vistazo a una era pasada cuando la música y el lujo se entrelazaban para crear un mundo de belleza y refinamiento. Justo más allá de este rico sitio histórico, los ecos de un pasado operístico esperan, insinuando la grandeza y el drama que una vez adornaron esta vibrante ciudad.

Cómo llegar: Desde el Palacio Lascaris, dirígete al sur por la Rue Droite hasta llegar a la Place Rossetti con sus animados cafés. Continúa recto por la Rue de la Préfecture hasta llegar a la Ópera de Niza, un majestuoso edificio con una hermosa fachada. ¡Disfruta del paseo por las encantadoras calles del Casco Antiguo de Niza!
```

## Glossary built by the names pass (gpt-4o)

The new design builds a per-tour names glossary once (gpt-4o), which the prose pass
then reuses. For reference (not blinded — this is the mechanism, not the prose):

**Russian** (guidebook design):

- Castle Hill of Nice → Замковая гора Ниццы
- Palais Lascaris → Пале Ласкарис
- Opéra de Nice → Опера Ниццы
- Cours Saleya Market → Cours Saleya Market
- Promenade des Anglais → Променад дез Англе
- Nice Cathedral → Собор Святой Репараты
- Place Masséna → Площадь Массена
- MAMAC (Musée d'Art Moderne et d'Art Contemporain) → Музей современного и современного искусства (MAMAC)
- Russian Orthodox Cathedral → Русский православный собор
- Colline du Château → Коллин дю Шато

**Spanish** (guidebook design):

- Castle Hill of Nice → Colline du Château
- Palais Lascaris → Palais Lascaris
- Opéra de Nice → Opéra de Nice
- Cours Saleya Market → Mercado de Cours Saleya
- Promenade des Anglais → Promenade des Anglais
- Nice Cathedral → Catedral de Niza
- Place Masséna → Place Masséna
- MAMAC (Musée d'Art Moderne et d'Art Contemporain) → MAMAC (Musée d'Art Moderne et d'Art Contemporain)
- Russian Orthodox Cathedral → Catedral Ortodoxa Rusa de Niza
- Colline du Château → Colline du Château

---

> LEAD note: unspoken lines (address, coordinates, type) and the heading line were removed from all three full-stop blocks so the comparison is of spoken text only.
> Y's headers and full Stop 2 were replaced with AWS's real output (translate_text + _restore_metadata_labels, as the app does). The harness had sent AWS the body without its heading and skipped label restoration, which showed an English "Stop N:" and Russian address labels the app never shows.

## Blind key (do not read until you have judged)

- **X** = new guidebook design (gpt-4o names + gpt-4o-mini prose)
- **Y** = AWS Translate (current default)
- **Z** = gpt-4o for names AND prose

---

## Provenance & database safety

- The three engines were run by calling the translation methods **directly** (not the
  HTTP endpoint), so no translation cache was involved and each engine produced fresh
  output.
- **No database rows were created or modified for this review.** The harness only called
  the text-translation methods; it never called `translate_tour_with_audio`, never wrote
  to `audio_tours`, and never touched `original_tour_id`. Row counts before and after were
  identical: 198 total `audio_tours` rows, 10 pre-existing tour-301 translations (from
  earlier work, untouched). There was therefore nothing to hide (no lat/lng NULLing was
  needed), and no `DELETE` was ever issued.

## A note on the Spanish glossary (for your judgement)

Per the spec, **Wikidata labels win over the model** when present. For several Nice
landmarks Wikidata's label is the French endonym (e.g. "Palais Lascaris", "Place
Masséna", "Colline du Château"), so those appear in French inside the Spanish output
rather than a Spanish exonym like "Palacio Lascaris". That is the rule behaving as
written. If you prefer the Spanish exonym to win over Wikidata's French label, that is a
one-line change to the override precedence — flag it and I'll adjust.


