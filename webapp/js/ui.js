/* Спільні помічники для екранів: заголовок, кнопки, стани, тост, підтвердження. */

import { escapeHtml } from "./format.js";

const tg = window.Telegram && window.Telegram.WebApp;
const root = document.documentElement;
const view = document.getElementById("view");
const titleEl = document.getElementById("screenTitle");
const actionEl = document.getElementById("headerAction");
const fab = document.getElementById("fab");
const toast = document.getElementById("toast");
const errorText = document.getElementById("errorText");

export const ICONS = {
    plans: '<svg viewBox="0 0 24 24"><rect x="5" y="4" width="14" height="17" rx="2.5"/><path d="M9 4V3h6v1M9 10h6M9 14h6"/></svg>',
    calendar: '<svg viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="15" rx="2.5"/><path d="M8 3v4M16 3v4M4 10h16"/></svg>',
    alert: '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"/><path d="M12 7.5V13M12 16.5h.01"/></svg>'
};

/* ---------- Стан сторінки (loading / ready / error / outside) ---------- */

export function setPageState(state) {
    root.setAttribute("data-state", state);
}

export function showFatal(message) {
    errorText.textContent = message;
    setPageState("error");
}

/* ---------- Екрани ---------- */

let screenId = 0;

/* Кожен екран починає з beginScreen(): очищає шапку й кнопку «+»
   та повертає номер, за яким пізніше перевіряється, чи екран ще актуальний
   (користувач міг перейти далі, поки йшов запит). */
export function beginScreen() {
    screenId += 1;
    setHeaderAction(null);
    setFab(null);
    return screenId;
}

export function isCurrent(id) {
    return id === screenId;
}

export function setTitle(text) {
    titleEl.textContent = text;
    document.title = text + " - Proactive Ed";
}

export function setHeaderAction(label, handler) {
    actionEl.innerHTML = "";
    if (!label) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "text-button";
    button.textContent = label;
    button.addEventListener("click", handler);
    actionEl.appendChild(button);
}

let fabHandler = null;
fab.addEventListener("click", function () {
    if (fabHandler) fabHandler();
});

export function setFab(handler, label) {
    fabHandler = handler || null;
    fab.hidden = !handler;
    fab.setAttribute("aria-label", label || "Додати");
}

export function render(html) {
    view.innerHTML = html;
    view.scrollTop = 0;
    return view;
}

export function showLoading() {
    render('<div class="view-center"><div class="spinner" aria-hidden="true"></div></div>');
}

export function emptyHtml(icon, title, text, buttonLabel) {
    return '<div class="empty">' +
        '<div class="status-icon" aria-hidden="true">' + icon + "</div>" +
        '<h2 class="empty-title">' + escapeHtml(title) + "</h2>" +
        (text ? '<p class="empty-text">' + escapeHtml(text) + "</p>" : "") +
        (buttonLabel
            ? '<button class="main-button" id="emptyAction" type="button">' +
              escapeHtml(buttonLabel) + "</button>"
            : "") +
        "</div>";
}

export function showError(message, onRetry) {
    render(
        '<div class="empty" role="alert">' +
        '<div class="status-icon" aria-hidden="true">' + ICONS.alert + "</div>" +
        '<h2 class="empty-title">Не вдалося завантажити</h2>' +
        '<p class="empty-text">' + escapeHtml(message) + "</p>" +
        '<button class="main-button" id="viewRetry" type="button">Спробувати ще раз</button>' +
        "</div>"
    );
    document.getElementById("viewRetry").addEventListener("click", onRetry);
}

/* ---------- Навігація ---------- */

export function go(hash) {
    location.hash = hash;
}

export function back(fallbackHash) {
    if (history.length > 1) history.back();
    else go(fallbackHash || "#/");
}

/* ---------- Повідомлення й діалоги ---------- */

let toastTimer;
export function showToast(text) {
    toast.textContent = text;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("show"); }, 2500);
}

/* kind: "success" | "error" | "warning" */
export function haptic(kind) {
    try { tg.HapticFeedback.notificationOccurred(kind); } catch (e) { /* не підтримується */ }
}

export function confirmDialog(message) {
    return new Promise(function (resolve) {
        if (tg && tg.showConfirm) tg.showConfirm(message, function (ok) { resolve(!!ok); });
        else resolve(window.confirm(message));
    });
}

export function setBusy(buttons, busy) {
    buttons.forEach(function (button) {
        if (button) button.disabled = busy;
    });
}
/* Зрозумілий текст помилки для користувача */
export function friendlyError(error) {
    if (!error) return "Невідома помилка";
    if (error.status === 403) return "Недостатньо прав для цієї дії.";
    if (error.status === 404) return "Не знайдено. Можливо, це вже видалено.";
    if (error.status === 400 && error.message) return "Перевірте дані: " + error.message;
    return error.message || "Невідома помилка";
}