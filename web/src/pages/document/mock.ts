// Тестовые данные для формы документа: кнопка «Заполнить демо-данными», которую
// видит только админ на время демонстрации жюри. Значение получает каждое поле,
// обязательное и нет; оно полурандомное, но проходит проверку сервера
// (core.domain.documents): ИНН, ОГРН и ключ расчётного счёта вычисляются по
// контрольным суммам, а не подбираются попытками, а счёт ключуется БИК той же
// стороны, что выберет сервер (_bic_for), — иначе кнопка давала бы ошибки там,
// где человек их не делал.
//
// У стороны одна организация на все её поля: название, ИНН, банк и почта
// сходятся между собой, а продавец и клиент различаются. Сторона стандартного
// поля — в префиксе ключа (seller_*, client_*), своего — в словах названия и
// ключа: «ИНН заказчика» — клиент, «Название исполнителя» — продавец. ИП
// выпадает только стороне без поля КПП: у ИП его не бывает. Смысл текстовых
// полей угадывается по ключу и по названию — у своих шаблонов ключ — транслит
// названия, поэтому одинаково важны оба.
//
// Функция чистая: с переданными random и today результат повторяется в тестах.
import type { FieldSpec, FieldType } from '@/api/client';
import { pluralize } from '@/lib/format';

interface MockOptions {
  today?: Date;
  random?: () => number;
}

type Random = () => number;

interface Bank {
  name: string;
  bic: string;
}

type Side = 'seller' | 'client';

interface Party {
  // ИП: ИНН из 12 цифр, ОГРНИП из 15, счёт 40802.
  sole: boolean;
  title: string;
  slug: string;
  person: string;
  city: string;
  address: string;
  inn: string;
  kpp: string;
  ogrn: string;
  bank: Bank;
  phone: string;
  email: string;
}

interface MockItem {
  name: string;
  quantity: number;
  unit: string;
  price: number;
}

interface Project {
  title: string;
  // «Оказание услуг по …» — дательный падеж для предмета договора.
  by: string;
  items: readonly string[];
}

const COMPANIES = [
  ['Вектор', 'vector'],
  ['Северный ветер', 'severny-veter'],
  ['Горизонт', 'gorizont'],
  ['Меридиан', 'meridian'],
  ['Техностиль', 'tehnostil'],
  ['Байкал Софт', 'baikal-soft'],
  ['Светлый дом', 'svetly-dom'],
  ['Кедр', 'kedr'],
  ['Импульс', 'impuls'],
  ['Стройресурс', 'stroyresurs'],
  ['Прайм Логистик', 'prime-logistic'],
  ['Зелёная линия', 'zelenaya-liniya'],
] as const;

// Женская фамилия — мужская с «а»: у всех фамилий списка так.
const SURNAMES = [
  ['Смирнов', 'smirnov'],
  ['Иванов', 'ivanov'],
  ['Кузнецов', 'kuznetsov'],
  ['Соколов', 'sokolov'],
  ['Лебедев', 'lebedev'],
  ['Новиков', 'novikov'],
  ['Морозов', 'morozov'],
  ['Волков', 'volkov'],
  ['Орлов', 'orlov'],
  ['Павлов', 'pavlov'],
  ['Зайцев', 'zaitsev'],
  ['Фёдоров', 'fedorov'],
] as const;
const MALE_NAMES = ['Алексей', 'Дмитрий', 'Сергей', 'Андрей', 'Михаил', 'Илья', 'Павел', 'Роман'];
const FEMALE_NAMES = ['Анна', 'Елена', 'Мария', 'Ольга', 'Татьяна', 'Наталья', 'Ирина', 'Дарья'];
const PATRONYMICS = [
  ['Петрович', 'Петровна'],
  ['Сергеевич', 'Сергеевна'],
  ['Александрович', 'Александровна'],
  ['Игоревич', 'Игоревна'],
  ['Викторович', 'Викторовна'],
  ['Андреевич', 'Андреевна'],
  ['Николаевич', 'Николаевна'],
] as const;

// Код региона — начало ИНН, КПП и часть ОГРН; индекс — первые три цифры.
const CITIES = [
  { name: 'Москва', region: '77', zip: [101, 129] },
  { name: 'Санкт-Петербург', region: '78', zip: [190, 199] },
  { name: 'Казань', region: '16', zip: [420, 420] },
  { name: 'Екатеринбург', region: '66', zip: [620, 620] },
  { name: 'Новосибирск', region: '54', zip: [630, 630] },
  { name: 'Нижний Новгород', region: '52', zip: [603, 603] },
  { name: 'Краснодар', region: '23', zip: [350, 350] },
  { name: 'Самара', region: '63', zip: [443, 443] },
] as const;
const STREETS = [
  'ул. Лесная',
  'ул. Садовая',
  'пр-т Мира',
  'ул. Гагарина',
  'ул. Профсоюзная',
  'наб. Речная',
  'ул. Московская',
  'ул. Строителей',
  'пер. Почтовый',
  'ул. Пушкина',
];

// Настоящие БИК московских отделений: счёт ключуется по ним, а банк в
// документе сходится со своим БИК.
const BANKS: readonly Bank[] = [
  { name: 'ПАО Сбербанк', bic: '044525225' },
  { name: 'АО «Т-Банк»', bic: '044525974' },
  { name: 'АО «Альфа-Банк»', bic: '044525593' },
  { name: 'Банк ВТБ (ПАО)', bic: '044525187' },
  { name: 'АО «Райффайзенбанк»', bic: '044525700' },
  { name: 'ПАО «Промсвязьбанк»', bic: '044525555' },
];

// Один проект на документ: тема, состав работ и предмет договора — об одном.
const PROJECTS: readonly Project[] = [
  {
    title: 'Разработка сайта',
    by: 'разработке сайта',
    items: [
      'Прототип и дизайн главной страницы',
      'Вёрстка страниц под компьютер и телефон',
      'Настройка системы управления сайтом',
      'Подключение форм заявок и аналитики',
      'Перенос сайта на хостинг заказчика',
    ],
  },
  {
    title: 'Настройка контекстной рекламы',
    by: 'настройке контекстной рекламы',
    items: [
      'Анализ конкурентов и подбор ключевых слов',
      'Создание рекламных кампаний',
      'Настройка целей и сквозной аналитики',
      'Ведение кампаний в течение месяца',
      'Отчёт по результатам',
    ],
  },
  {
    title: 'Бухгалтерское сопровождение',
    by: 'бухгалтерскому сопровождению',
    items: [
      'Ведение бухгалтерского учёта',
      'Расчёт заработной платы',
      'Подготовка и сдача отчётности',
      'Консультации по налогам',
      'Работа с банком-клиентом',
    ],
  },
  {
    title: 'Ремонт офисного помещения',
    by: 'ремонту офисного помещения',
    items: [
      'Демонтаж старого покрытия',
      'Выравнивание и покраска стен',
      'Укладка напольного покрытия',
      'Замена светильников',
      'Вывоз строительного мусора',
    ],
  },
  {
    title: 'Разработка мобильного приложения',
    by: 'разработке мобильного приложения',
    items: [
      'Проектирование экранов',
      'Разработка под iOS и Android',
      'Интеграция с сервером заказчика',
      'Тестирование на устройствах',
      'Публикация в магазинах приложений',
    ],
  },
  {
    title: 'Фотосъёмка каталога продукции',
    by: 'фотосъёмке каталога продукции',
    items: [
      'Предметная съёмка до 50 позиций',
      'Обработка и ретушь фотографий',
      'Подготовка изображений для сайта',
      'Съёмка в интерьере',
      'Передача исходных файлов',
    ],
  },
  {
    title: 'Обслуживание компьютерной техники',
    by: 'обслуживанию компьютерной техники',
    items: [
      'Диагностика рабочих мест',
      'Настройка локальной сети',
      'Установка и обновление программ',
      'Резервное копирование данных',
      'Выезд специалиста по заявке',
    ],
  },
];

const TERMS = [
  '5 рабочих дней',
  '10 рабочих дней',
  '15 рабочих дней',
  '20 рабочих дней',
  '3 недели',
  '1 месяц',
  '30 календарных дней',
];
const PAYMENTS = [
  '100% предоплата',
  '50% предоплата, 50% после подписания акта',
  'Оплата после подписания акта',
  'В течение 5 банковских дней после выставления счёта',
];
const COMMENTS = [
  'В назначении платежа укажите номер счёта.',
  'Работы начинаются после поступления оплаты.',
  'Акт выполненных работ направляется по электронной почте.',
  'Закрывающие документы — через ЭДО.',
];
const GENERIC_LINES = [
  'Документ составлен в двух экземплярах, по одному для каждой стороны.',
  'Изменения согласуются сторонами письменно.',
  'Споры решаются путём переговоров.',
  'Стороны сохраняют конфиденциальность условий.',
];

// Пределы длины сервера (normalize): max_length поля, иначе по типу. «0» там
// тоже значит «не задан» — Python читает его как ложь.
const TYPE_LIMIT: Partial<Record<FieldType, number>> = {
  multiline: 5000,
  email: 254,
  items: 50_000,
};
const TEXT_LIMIT = 1000;

// --- случайность ---------------------------------------------------------

function int(random: Random, min: number, max: number): number {
  return Math.min(max, min + Math.floor(random() * (max - min + 1)));
}

function at<T>(list: readonly T[], index: number): T {
  const item = list[index];
  if (item === undefined) throw new Error('mock: индекс вне списка');
  return item;
}

function pick<T>(random: Random, list: readonly T[]): T {
  return at(list, int(random, 0, list.length - 1));
}

function sample<T>(random: Random, list: readonly T[], count: number): T[] {
  const rest = [...list];
  const out: T[] = [];
  while (out.length < count && rest.length > 0) {
    out.push(...rest.splice(int(random, 0, rest.length - 1), 1));
  }
  return out;
}

function digits(random: Random, count: number): string {
  return Array.from({ length: count }, () => String(int(random, 0, 9))).join('');
}

function mobile(random: Random): string {
  return `+7 9${digits(random, 2)} ${digits(random, 3)}-${digits(random, 2)}-${digits(random, 2)}`;
}

// Индекс из пула, ещё не занятый другой стороной: продавец и клиент — разные.
function pickFree(random: Random, size: number, taken: Set<number>): number {
  const all = Array.from({ length: size }, (_, index) => index);
  const free = all.filter((index) => !taken.has(index));
  const index = pick(random, free.length > 0 ? free : all);
  taken.add(index);
  return index;
}

// --- реквизиты с контрольными суммами ----------------------------------

const INN10 = [2, 4, 10, 3, 5, 9, 4, 6, 8];
const INN11 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8];
const INN12 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8];

function innCheck(head: string, weights: readonly number[]): string {
  const sum = weights.reduce((total, weight, index) => total + weight * Number(head[index]), 0);
  return String((sum % 11) % 10);
}

// 9 цифр → ИНН организации, 10 → ИНН ИП (две контрольные, вторая — с учётом первой).
function innOf(head: string): string {
  if (head.length === 9) return head + innCheck(head, INN10);
  const eleven = head + innCheck(head, INN11);
  return eleven + innCheck(eleven, INN12);
}

// Остаток считается по цифрам: так длина числа не упирается в точность Number.
function remainder(value: string, divisor: number): number {
  return [...value].reduce((rest, digit) => (rest * 10 + Number(digit)) % divisor, 0);
}

// 12 цифр → ОГРН (контроль по модулю 11), 14 → ОГРНИП (по модулю 13).
function ogrnOf(head: string): string {
  return head + String(remainder(head, head.length === 12 ? 11 : 13) % 10);
}

const ACCOUNT_WEIGHTS = [7, 1, 3];

function weighted(value: string): number {
  return [...value].reduce(
    (total, digit, index) => total + Number(digit) * (ACCOUNT_WEIGHTS[index % 3] ?? 0),
    0,
  );
}

// Счёт = 8 цифр начала + ключ + 11 цифр. Сервер складывает по весам 7-1-3 три
// цифры БИК и 20 цифр счёта; ключ стоит на месте веса 3, а 3 обратимо по
// модулю 10 (3 × 7 = 21), поэтому ключ вычисляется одной формулой. Расчётный
// счёт ключуется последними тремя цифрами БИК, корреспондентский — «0» и
// цифрами 5–6 (core.domain.documents.account_key_valid).
function accountOf(head: string, tail: string, bic: string, correspondent = false): string {
  const prefix = correspondent ? '0' + bic.slice(4, 6) : bic.slice(6, 9);
  const partial = weighted(prefix + head + '0' + tail);
  const key = ((10 - (partial % 10)) * 7) % 10;
  return `${head}${key}${tail}`;
}

// Расчётный счёт организации начинается с 40702, ИП — с 40802; 810 — рубли.
function settlementHead(party: Party): string {
  return party.sole ? '40802810' : '40702810';
}

// Сторона реквизита для пары счёт — БИК, как у сервера (core.domain.documents._side):
// банковский хвост ключа (corr_account, account, bic) отрезается целиком, так
// seller_corr_account и seller_bic — одна сторона; у прочих ключей — всё до
// последнего «_». Это не организация: у транслита inn_zakazchika «сторона» — inn.
const BANK_SUFFIX = /_?(?:corr_account|account|bic)$/;

function sideOf(key: string): string {
  if (BANK_SUFFIX.test(key)) return key.replace(BANK_SUFFIX, '');
  const at = key.lastIndexOf('_');
  return at === -1 ? '' : key.slice(0, at);
}

// БИК, с которым сервер сверит счёт (core.domain.documents._bic_for).
function bicFor(account: FieldSpec, bics: readonly FieldSpec[]): FieldSpec | undefined {
  const side = sideOf(account.key);
  const sameSide = bics.find((bic) => sideOf(bic.key) === side);
  if (sameSide !== undefined) return sameSide;
  return bics.length === 1 ? bics[0] : undefined;
}

// Кто из сторон назван в своём поле: ключ — транслит названия, сторона в нём
// последним словом («ИНН заказчика» → inn_zakazchika).
const CLIENT_WORDS = /заказчик|покупател|клиент|zakazchik|pokupatel|klient/;
const SELLER_WORDS = /исполнител|поставщик|продав|ispolnitel|postavschik|prodav/;

// Организация поля: seller_bank_bic — продавец, как и seller_name. Своё поле
// без стороны («Адрес», «ИНН организации») — тоже продавец: такие поля обычно
// про того, кто составляет документ, и они сходятся между собой, а не дают по
// организации на каждое слово ключа. Названы обе стороны — решает первая.
function partyOf(field: FieldSpec): Side {
  if (field.key.startsWith('seller_')) return 'seller';
  if (field.key.startsWith('client_')) return 'client';
  const words = `${field.label.toLowerCase()} ${field.key}`;
  const client = words.search(CLIENT_WORDS);
  const seller = words.search(SELLER_WORDS);
  return client !== -1 && (seller === -1 || client < seller) ? 'client' : 'seller';
}

// --- форматы -------------------------------------------------------------

function pad(value: number): string {
  return String(value).padStart(2, '0');
}

// ISO — то, что держит <input type="date"> формы и принимает parse_date.
function isoDate(date: Date): string {
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

function shiftDays(date: Date, days: number): Date {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

function groupDigits(value: number): string {
  return String(value).replace(/\B(?=(\d{3})+(?!\d))/g, ' ');
}

// «30 833,33» — сумма с копейками, как в подсказке поля НДС.
function withKopecks(kopecks: number): string {
  return `${groupDigits(Math.floor(kopecks / 100))},${pad(kopecks % 100)}`;
}

const ONES = ['', 'один', 'два', 'три', 'четыре', 'пять', 'шесть', 'семь', 'восемь', 'девять'];
const ONES_FEMININE = ['', 'одна', 'две', ...ONES.slice(3)];
const TEENS = [
  'десять',
  'одиннадцать',
  'двенадцать',
  'тринадцать',
  'четырнадцать',
  'пятнадцать',
  'шестнадцать',
  'семнадцать',
  'восемнадцать',
  'девятнадцать',
];
const TENS = [
  '',
  '',
  'двадцать',
  'тридцать',
  'сорок',
  'пятьдесят',
  'шестьдесят',
  'семьдесят',
  'восемьдесят',
  'девяносто',
];
const HUNDREDS = [
  '',
  'сто',
  'двести',
  'триста',
  'четыреста',
  'пятьсот',
  'шестьсот',
  'семьсот',
  'восемьсот',
  'девятьсот',
];

function triad(value: number, feminine: boolean): string[] {
  const rest = value % 100;
  const words = [HUNDREDS[Math.floor(value / 100)]];
  if (rest >= 10 && rest < 20) words.push(TEENS[rest - 10]);
  else words.push(TENS[Math.floor(rest / 10)], (feminine ? ONES_FEMININE : ONES)[rest % 10]);
  return words.filter((word): word is string => Boolean(word));
}

// «Сто восемьдесят пять тысяч рублей 00 копеек» — для полей «Сумма прописью».
function rublesInWords(rubles: number): string {
  const millions = Math.floor(rubles / 1_000_000) % 1000;
  const thousands = Math.floor(rubles / 1000) % 1000;
  const words: string[] = [];
  if (millions > 0) {
    words.push(...triad(millions, false), pluralize(millions, 'миллион', 'миллиона', 'миллионов'));
  }
  if (thousands > 0) {
    words.push(...triad(thousands, true), pluralize(thousands, 'тысяча', 'тысячи', 'тысяч'));
  }
  words.push(...triad(rubles % 1000, false));
  const text = words.join(' ') || 'ноль';
  const rubleWord = pluralize(rubles, 'рубль', 'рубля', 'рублей');
  return `${text[0]?.toUpperCase() ?? ''}${text.slice(1)} ${rubleWord} 00 копеек`;
}

// --- смысл поля по ключу и названию ------------------------------------

interface Rule {
  key: RegExp;
  label: RegExp;
}

// Ключ сверяется по целым частям между «_»: post не ловит postavki.
function rule(keys: string, label: RegExp): Rule {
  return { key: new RegExp(`(^|_)(${keys})(_|$)`), label };
}

// Аббревиатура отдельным словом: «ИНН», но не «длинный».
function word(stem: string): RegExp {
  return new RegExp(`(^|[^а-яё])(${stem})`);
}

function matches(field: FieldSpec, { key, label }: Rule): boolean {
  return key.test(field.key) || label.test(field.label.toLowerCase());
}

type TextKind =
  | 'vat'
  | 'words'
  | 'phone'
  | 'email'
  | 'site'
  | 'passport'
  | 'number'
  | 'requisites'
  | 'inn'
  | 'kpp'
  | 'ogrn'
  | 'bic'
  | 'money'
  | 'account'
  | 'bank'
  | 'position'
  | 'person'
  | 'address'
  | 'city'
  | 'date'
  | 'purpose'
  | 'payment'
  | 'term'
  | 'warranty'
  | 'quantity'
  | 'unit'
  | 'items'
  | 'subject'
  | 'comment'
  | 'org';

// Порядок решает спорные названия: «Номер телефона» — телефон, «БИК банка» —
// БИК, «Сумма НДС» — НДС, «Срок оплаты» — оплата, «Название банка» — банк.
const NUMBER = rule('number|num|no|nomer', /номер|№/);
const QUANTITY = rule('qty|quantity|count|kolichestvo', /кол-во|количеств/);
const VAT = rule('vat|nds', word('ндс'));
const TEXT_RULES: ReadonlyArray<[TextKind, Rule]> = [
  ['vat', VAT],
  ['words', rule('propis|propisyu|words', /пропис/)],
  ['phone', rule('phone|tel|telefon', /телефон/)],
  ['email', rule('email|mail|pochta', /почт[аыуе]|e-?mail/)],
  ['site', rule('site|website|url|sayt', /сайт/)],
  ['passport', rule('passport|pasport', /паспорт/)],
  ['number', NUMBER],
  ['requisites', rule('requisites|details|rekvizity', /реквизит/)],
  ['inn', rule('inn', word('инн'))],
  ['kpp', rule('kpp', word('кпп'))],
  ['ogrn', rule('ogrn|ogrnip', word('огрн'))],
  ['bic', rule('bic|bik', word('бик'))],
  [
    'money',
    rule('total|sum|summa|price|cost|amount|stoimost|tsena', /сумм|стоимост|цен[аы]|итого/),
  ],
  ['account', rule('account|schet|rs', word('сч[её]т|р/с'))],
  ['bank', rule('bank', /банк/)],
  ['position', rule('position|post|dolzhnost', /должност/)],
  [
    'person',
    rule(
      'director|signer|signatory|head|manager|contact|person|fio|podpisant|rukovoditel',
      /фио|подписант|директор|руководител|менеджер|контактн|ответственн|представител|(^|[^а-яё])имя/,
    ),
  ],
  ['address', rule('address|adres', /адрес/)],
  ['city', rule('city|town|gorod', /город|населённый пункт|место (составления|заключения)/)],
  ['date', rule('date|data', word('дат[аыуе]'))],
  ['purpose', rule('purpose|naznachenie', /назначени/)],
  ['payment', rule('payment|pay|oplata|oplaty|raschety', /оплат|плат[её]ж|расч[её]т/)],
  ['term', rule('term|terms|period|duration|deadline|timeline|srok', /срок|период|длительност/)],
  ['warranty', rule('warranty|guarantee|garantiya', /гарант/)],
  ['quantity', QUANTITY],
  ['unit', rule('unit|edinitsa', /единиц|ед\.\s*изм/)],
  [
    'items',
    rule(
      'item|items|scope|services|works|goods|products|positions|sostav|perechen',
      /состав|перечень|список|позиц|наименование (работ|услуг|товар)/,
    ),
  ],
  ['subject', rule('subject|topic|theme|project|predmet|tema', word('тема|предмет|проект|цель'))],
  ['items', rule('raboty|uslugi|tovary', /работ|услуг|товар/)],
  [
    'comment',
    rule(
      'comment|comments|note|notes|remark|primechanie|kommentariy',
      /комментар|примечан|пожелан|дополнительн|особые/,
    ),
  ],
  [
    'org',
    rule(
      'name|company|organization|org|nazvanie|naimenovanie|firma',
      /назван|наименован|организац|компан|контрагент|покупател|поставщик|заказчик|исполнител|продав|клиент|фирм/,
    ),
  ],
];

const PREPAY = rule('prepay|prepayment|advance|avans|predoplata', /аванс|предоплат/);
const CORR = rule('corr|korr|correspondent', /корр/);
const BIRTH = rule('birth|birthday|dob|rozhdeniya', /рожден/);
const DATE_END = rule(
  'due|until|till|end|deadline|expire|expires|expiry|valid|finish|to|do|okonchaniya|srok|oplatit',
  /(^|\s)до(\s|$)|оконч|истека|срок|действ|заверш|крайн|оплатить/,
);
const PERCENT = rule('percent|pct|protsent', /%|процент/);
const MONTHS = rule('months|mesyats|mesyatsev', /месяц|мес\./);
const DAYS = rule('days|dney|dni|srok|term', /дн|срок/);

function textKind(field: FieldSpec): TextKind | undefined {
  return TEXT_RULES.find(([, textRule]) => matches(field, textRule))?.[0];
}

// --- сборка --------------------------------------------------------------

// Не длиннее предела сервера: у длинного текста сначала отпадают строки, потом
// слова; обрезанное значение по-прежнему непустое.
function fit(field: FieldSpec, value: string): string {
  // Позиции — JSON: обрезанный посередине список сервер не прочтёт.
  if (field.type === 'items') return value;
  const limit = field.max_length || TYPE_LIMIT[field.type] || TEXT_LIMIT;
  const length = (text: string) => [...text].length;
  if (limit <= 0 || length(value) <= limit) return value;
  const lines = value.split('\n');
  while (lines.length > 1 && length(lines.join('\n')) > limit) lines.pop();
  const kept = lines.join('\n');
  if (length(kept) <= limit) return kept;
  const cut = [...kept].slice(0, limit).join('');
  const space = cut.lastIndexOf(' ');
  const trimmed = (space >= limit / 2 ? cut.slice(0, space) : cut).trimEnd();
  return trimmed || cut;
}

function generator(fields: readonly FieldSpec[], random: Random, today: Date) {
  const parties = new Map<Side, Party>();
  const takenCompanies = new Set<number>();
  const takenSurnames = new Set<number>();
  // ИП бывает только у стороны без поля КПП: у ИП КПП нет.
  const withKpp = new Set(fields.filter((field) => field.type === 'kpp').map(partyOf));
  const bics = fields.filter((field) => field.type === 'bic');
  const totalKey =
    fields.find((field) => field.type === 'money' && field.key === 'total')?.key ??
    fields.find(
      (field) => field.type === 'money' && !matches(field, VAT) && !matches(field, PREPAY),
    )?.key;
  let project: Project | undefined;
  let total: number | undefined;
  let lines: MockItem[] | undefined;
  // Есть таблица позиций — итог документа и НДС считаются из неё, как на сервере.
  const withItems = fields.some((field) => field.type === 'items');

  const amount = () => int(random, 10, 500) * 1000;
  const theProject = () => (project ??= pick(random, PROJECTS));
  // Цена кратна 500 ₽, количество — от 1 до 5: итог круглый, НДС сходится с ним.
  const theItems = (): MockItem[] =>
    (lines ??= sample(random, theProject().items, int(random, 1, 4)).map((name) => ({
      name,
      quantity: int(random, 1, 5),
      unit: pick(random, ['усл.', 'шт.', 'ч']),
      price: int(random, 1, 100) * 500,
    })));
  const totalAmount = () =>
    (total ??= withItems
      ? theItems().reduce((sum, item) => sum + item.quantity * item.price, 0)
      : amount());

  const party = (name: Side): Party => {
    const known = parties.get(name);
    if (known) return known;
    const city = pick(random, CITIES);
    const [surname, latin] = at(SURNAMES, pickFree(random, SURNAMES.length, takenSurnames));
    const female = random() < 0.4;
    const patronymic = pick(random, PATRONYMICS)[female ? 1 : 0];
    const first = pick(random, female ? FEMALE_NAMES : MALE_NAMES);
    const person = `${surname}${female ? 'а' : ''} ${first} ${patronymic}`;
    const sole = !withKpp.has(name) && random() < 0.3;
    const [company, companySlug] = sole
      ? ['', '']
      : at(COMPANIES, pickFree(random, COMPANIES.length, takenCompanies));
    const office = `${city.region}${pad(int(random, 1, 30))}`;
    const inn = innOf(office + digits(random, sole ? 6 : 5));
    const year = pad(int(random, 2, 24));
    const street = pick(random, STREETS);
    const house = int(random, 1, 150);
    const room = random() < 0.6 ? `, офис ${int(random, 1, 60)}` : '';
    const zip = `${int(random, city.zip[0], city.zip[1])}${digits(random, 3)}`;
    const slug = sole ? `${latin}${female ? 'a' : ''}` : companySlug;
    const created: Party = {
      sole,
      title: sole ? `ИП ${person}` : `${random() < 0.75 ? 'ООО' : 'АО'} «${company}»`,
      slug,
      person,
      city: city.name,
      address: `${zip}, г. ${city.name}, ${street}, д. ${house}${room}`,
      inn,
      kpp: `${inn.slice(0, 4)}01001`,
      ogrn: sole
        ? ogrnOf(`3${year}${city.region}${digits(random, 9)}`)
        : ogrnOf(`1${year}${city.region}${digits(random, 7)}`),
      bank: pick(random, BANKS),
      phone: mobile(random),
      email: `${pick(random, ['info', 'office', 'sales', 'hello'])}@${slug}-test.ru`,
    };
    parties.set(name, created);
    return created;
  };

  const sideParty = (field: FieldSpec) => party(partyOf(field));

  // Счёт ключуется тем БИК, с которым его сверит сервер; нет такого — своим банком.
  const account = (field: FieldSpec): string => {
    const own = sideParty(field);
    const bicField = bicFor(field, bics);
    const bic = bicField === undefined ? own.bank.bic : sideParty(bicField).bank.bic;
    // Корреспондентским сервер считает только поле *_corr_account; «корр. счёт»
    // своего шаблона он ключует как расчётный, и мок — так же.
    if (matches(field, CORR)) {
      const correspondent = field.key.endsWith('corr_account');
      return accountOf('30101810', `00000000${bic.slice(6, 9)}`, bic, correspondent);
    }
    return accountOf(settlementHead(own), digits(random, 11), bic);
  };

  // Документ и начало срока — сегодня, «оплатить до» и «действует до» — через 5–30 дней.
  const dateOf = (field: FieldSpec): Date => {
    if (matches(field, BIRTH)) {
      return new Date(int(random, 1965, 2000), int(random, 0, 11), int(random, 1, 28));
    }
    if (matches(field, DATE_END)) return shiftDays(today, int(random, 5, 30));
    return today;
  };

  // НДС — 20/120 от суммы с НДС: так его выделяют из итога счёта. У ИП — без НДС.
  const vatKopecks = () => Math.round((totalAmount() * 100) / 6);
  const vatText = () =>
    party('seller').sole || random() < 0.3 ? 'Без НДС' : `20% — ${withKopecks(vatKopecks())}`;

  const money = (field: FieldSpec): string => {
    if (matches(field, VAT)) return party('seller').sole ? '0' : withKopecks(vatKopecks());
    if (matches(field, PREPAY)) {
      return groupDigits(Math.round(totalAmount() * pick(random, [0.3, 0.5])));
    }
    return groupDigits(field.key === totalKey ? totalAmount() : amount());
  };

  const integer = (field: FieldSpec): number => {
    if (matches(field, NUMBER)) return int(random, 1, 999);
    if (matches(field, PERCENT)) return pick(random, [10, 15, 20, 25, 30, 50]);
    if (matches(field, MONTHS)) return pick(random, [1, 3, 6, 12, 24, 36]);
    if (matches(field, QUANTITY)) return int(random, 1, 20);
    if (matches(field, DAYS)) return pick(random, [3, 5, 7, 10, 14, 15, 20, 30, 45, 60]);
    return int(random, 1, 60);
  };

  const numbered = (items: readonly string[]) =>
    items.map((item, index) => `${index + 1}. ${item}`).join('\n');

  const text = (field: FieldSpec): string => {
    const multiline = field.type === 'multiline';
    const own = () => sideParty(field);
    switch (textKind(field)) {
      case 'vat':
        return vatText();
      case 'words':
        return rublesInWords(totalAmount());
      case 'phone':
        return own().phone;
      case 'email':
        return own().email;
      case 'site':
        return `www.${own().slug}-test.ru`;
      case 'passport':
        return `${digits(random, 2)} ${digits(random, 2)} ${digits(random, 6)}`;
      case 'number':
        return String(int(random, 1, 999));
      case 'requisites': {
        // Текст без проверки сервера, но счёт в нём всё равно сходится со своим БИК.
        const side = own();
        const registry = side.sole ? `ОГРНИП ${side.ogrn}` : `КПП ${side.kpp}`;
        const bank = side.bank;
        const settlement = accountOf(settlementHead(side), digits(random, 11), bank.bic);
        const lines = [
          `${side.title}, ИНН ${side.inn}, ${registry}`,
          side.address,
          `р/с ${settlement} в ${bank.name}, БИК ${bank.bic}`,
        ];
        return lines.join(multiline ? '\n' : '; ');
      }
      case 'inn':
        return own().inn;
      case 'kpp':
        return own().kpp;
      case 'ogrn':
        return own().ogrn;
      case 'bic':
        return own().bank.bic;
      case 'money':
        return `${groupDigits(totalAmount())} руб.`;
      case 'account':
        return account(field);
      case 'bank':
        return own().bank.name;
      case 'position':
        return own().sole
          ? 'Индивидуальный предприниматель'
          : pick(random, ['Генеральный директор', 'Директор']);
      case 'person':
        return own().person;
      case 'address':
        return own().address;
      case 'city':
        // «Город» документа — город своей организации.
        return `г. ${own().city}`;
      case 'date': {
        const iso = isoDate(dateOf(field));
        return iso.split('-').reverse().join('.');
      }
      case 'purpose':
        return `Оплата услуг по ${theProject().by}`;
      case 'payment':
        return /срок/.test(field.label.toLowerCase())
          ? `В течение ${pick(random, [3, 5, 10])} банковских дней`
          : pick(random, PAYMENTS);
      case 'term':
        return pick(random, TERMS);
      case 'warranty':
        return pick(random, ['6 месяцев', '12 месяцев', '24 месяца']);
      case 'quantity':
        return String(int(random, 1, 20));
      case 'unit':
        return pick(random, ['усл.', 'шт.', 'ч']);
      case 'items': {
        const chosen = sample(random, theProject().items, int(random, 2, 4));
        return multiline ? numbered(chosen) : theProject().title;
      }
      case 'subject': {
        if (!multiline) return theProject().title;
        const chosen = sample(random, theProject().items, int(random, 2, 4));
        return [`Оказание услуг по ${theProject().by}:`, ...chosen.map((item) => `— ${item}`)].join(
          '\n',
        );
      }
      case 'comment':
        return multiline ? sample(random, COMMENTS, 2).join('\n') : pick(random, COMMENTS);
      case 'org':
        return own().title;
      default:
        if (multiline) return sample(random, GENERIC_LINES, 2).join('\n');
        return field.label.trim() ? `${field.label.trim()} (тест)` : 'Тестовое значение';
    }
  };

  return (field: FieldSpec): string => {
    switch (field.type) {
      case 'email':
        return sideParty(field).email;
      case 'phone':
        return sideParty(field).phone;
      case 'money':
        return money(field);
      case 'date':
        return isoDate(dateOf(field));
      case 'integer':
        return String(integer(field));
      case 'inn':
        return sideParty(field).inn;
      case 'kpp':
        return sideParty(field).kpp;
      case 'ogrn':
        return sideParty(field).ogrn;
      case 'bic':
        return sideParty(field).bank.bic;
      case 'account':
        return account(field);
      case 'name':
        return sideParty(field).person;
      case 'address':
        return sideParty(field).address;
      case 'items':
        return JSON.stringify(
          theItems().map((item) => ({
            name: item.name,
            quantity: String(item.quantity),
            unit: item.unit,
            price: String(item.price),
          })),
        );
      default:
        return text(field);
    }
  };
}

export function mockValues(
  fields: readonly FieldSpec[],
  options: MockOptions = {},
): Record<string, string> {
  const valueOf = generator(fields, options.random ?? Math.random, options.today ?? new Date());
  const values: Record<string, string> = {};
  for (const field of fields) values[field.key] = fit(field, valueOf(field));
  return values;
}
