/* Підписи українською, форматування дат і групування хронології. */

export const ACTIVITY_LABELS = {
    lecture: "Лекція",
    practice: "Практичне заняття",
    reading: "Читання",
    self_study: "Самостійне навчання",
    exam_prep: "Підготовка до іспиту"
};

export const EVENT_LABELS = {
    exam: "Іспит",
    test: "Контрольна",
    deadline: "Дедлайн",
    other: "Інше"
};

export const ROLE_LABELS = {
    owner: "Власник",
    viewer: "Перегляд",
    commenter: "Коментування"
};

/* ---------- безпека ---------- */

/* Текст користувача вставляється в HTML тільки через цю функцію */
export function escapeHtml(value) {
    return String(value == null ? "" : value)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

/* ---------- дати ---------- */

function pad(number) {
    return String(number).padStart(2, "0");
}

/* Локальна дата у вигляді "YYYY-MM-DD" */
export function dateKey(date) {
    return date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate());
}

/* "2026-11-06" -> локальна дата. Не через new Date("2026-11-06"),
   інакше UTC може зсунути день. */
export function parseDateOnly(value) {
    const [year, month, day] = value.split("-").map(Number);
    return new Date(year, month - 1, day);
}

function addDays(date, days) {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);
}

function capitalize(text) {
    return text.charAt(0).toUpperCase() + text.slice(1);
}

/* Заголовок дня в хронології: "Сьогодні, 5 листопада", "П'ятниця, 6 листопада" */
export function formatDayHeading(key) {
    const date = parseDateOnly(key);
    const text = date.toLocaleDateString("uk-UA", {
        weekday: "long",
        day: "numeric",
        month: "long"
    });
    const today = new Date();
    if (key === dateKey(today)) return "Сьогодні, " + text;
    if (key === dateKey(addDays(today, 1))) return "Завтра, " + text;
    return capitalize(text);
}

/* Дата події: "6 листопада 2026 р." */
export function formatEventDate(value) {
    return parseDateOnly(value).toLocaleDateString("uk-UA", {
        day: "numeric",
        month: "long",
        year: "numeric"
    });
}

export function formatTime(iso) {
    return new Date(iso).toLocaleTimeString("uk-UA", {
        hour: "2-digit",
        minute: "2-digit"
    });
}

/* "10:00–11:30" у місцевому часі */
export function formatTimeRange(iso, minutes) {
    const start = new Date(iso);
    const end = new Date(start.getTime() + minutes * 60000);
    return formatTime(start.toISOString()) + "–" + formatTime(end.toISOString());
}

export function formatDuration(minutes) {
    const hours = Math.floor(minutes / 60);
    const rest = minutes % 60;
    if (hours && rest) return hours + " год " + rest + " хв";
    if (hours) return hours + " год";
    return rest + " хв";
}

/* ---------- поля форм ---------- */

/* ISO з сервера -> значення для <input type="datetime-local"> (місцевий час) */
export function toDatetimeLocalValue(iso) {
    const date = new Date(iso);
    return dateKey(date) + "T" + pad(date.getHours()) + ":" + pad(date.getMinutes());
}

/* Значення <input type="datetime-local"> -> ISO з часовим поясом (UTC).
   Повертає null, якщо поле порожнє або некоректне. */
export function fromDatetimeLocalValue(value) {
    if (!value) return null;
    const date = new Date(value); // рядок без пояса розбирається як місцевий час
    return isNaN(date.getTime()) ? null : date.toISOString();
}

/* Початкове значення для нової сесії: найближча ціла година */
export function defaultStartValue() {
    const date = new Date();
    date.setMinutes(0, 0, 0);
    date.setHours(date.getHours() + 1);
    return dateKey(date) + "T" + pad(date.getHours()) + ":00";
}

export function todayKey() {
    return dateKey(new Date());
}

/* ---------- хронологія ---------- */

function compareInDay(a, b) {
    if (a.kind !== b.kind) return a.kind === "event" ? -1 : 1; // події дня зверху
    if (a.kind === "session") return new Date(a.start_time) - new Date(b.start_time);
    return a.event_id - b.event_id;
}

/* Плоский список з /timeline -> [{ key: "2026-11-06", items: [...] }, ...]
   Групування за місцевою датою користувача. */
export function groupTimeline(items) {
    const groups = new Map();
    for (const item of items) {
        const key = item.kind === "event"
            ? item.event_date
            : dateKey(new Date(item.start_time));
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(item);
    }
    return [...groups.keys()].sort().map(function (key) {
        return { key: key, items: groups.get(key).sort(compareInDay) };
    });
}