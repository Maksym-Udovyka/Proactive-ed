/* Запуск сторінки навчальних планів і маршрутизація за адресою після #.

   Маршрути:
     #/                          список планів
     #/plan/new                  новий план
     #/plan/5                    сторінка плану
     #/plan/5/edit               редагування плану
     #/plan/5/members            учасники плану                  (НОВЕ)
     #/plan/5/session/new        нова сесія
     #/session/12/edit           редагування сесії
     #/plan/5/event/new          нова подія
     #/event/3/edit              редагування події
     #/invite/<токен>            вступ за запрошенням            (НОВЕ)

   Екрани підвантажуються лише тоді, коли користувач на них переходить. */

import { isInTelegram } from "./api.js";
import { back, beginScreen, setPageState, setTitle, showError } from "./ui.js";

const tg = window.Telegram && window.Telegram.WebApp;
const root = document.documentElement;
const backBtn = document.getElementById("backBtn");
const retryBtn = document.getElementById("retryBtn");

/* text: true означає, що параметр лишається рядком (токен), а не стає числом */
const routes = [
    { re: /^\/$/, names: [], load: () => import("./screens/plans.js"), fn: "showPlans" },
    { re: /^\/plan\/new$/, names: [], load: () => import("./screens/plans.js"), fn: "showPlanForm" },
    { re: /^\/plan\/(\d+)$/, names: ["planId"], load: () => import("./screens/plan.js"), fn: "showPlan" },
    { re: /^\/plan\/(\d+)\/edit$/, names: ["planId"], load: () => import("./screens/plans.js"), fn: "showPlanForm" },
    { re: /^\/plan\/(\d+)\/members$/, names: ["planId"], load: () => import("./screens/members.js"), fn: "showMembers" },
    { re: /^\/plan\/(\d+)\/session\/new$/, names: ["planId"], load: () => import("./screens/session.js"), fn: "showSessionForm" },
    { re: /^\/session\/(\d+)\/edit$/, names: ["sessionId"], load: () => import("./screens/session.js"), fn: "showSessionForm" },
    { re: /^\/plan\/(\d+)\/event\/new$/, names: ["planId"], load: () => import("./screens/event.js"), fn: "showEventForm" },
    { re: /^\/event\/(\d+)\/edit$/, names: ["eventId"], load: () => import("./screens/event.js"), fn: "showEventForm" },
    { re: /^\/invite\/([A-Za-z0-9_-]{1,100})$/, names: ["token"], text: true, load: () => import("./screens/invite.js"), fn: "showInvite" }
];

let navId = 0;

function currentPath() {
    return location.hash.replace(/^#/, "") || "/";
}

async function route() {
    const path = currentPath();
    const mine = ++navId;

    for (const entry of routes) {
        const match = path.match(entry.re);
        if (!match) continue;

        const params = {};
        entry.names.forEach(function (name, index) {
            params[name] = entry.text ? match[index + 1] : Number(match[index + 1]);
        });

        try {
            const module = await entry.load();
            if (mine !== navId) return; // пользователь уже перешёл на другой экран
            await module[entry.fn](params);
        } catch (error) {
            if (mine !== navId) return;
            beginScreen();
            setTitle("Навчальні плани");
            showError(error && error.message ? error.message : "Невідома помилка", route);
        }
        return;
    }

    // Невідомий адрес: повертаємось до списку планів
    location.replace("#/");
}

/* Назад: зі списку планів на головну, з інших екранів на попередній */
function goBack() {
    if (currentPath() === "/") location.href = "index.html";
    else back("#/");
}

/* ---------- Telegram ---------- */

function hasSavedTheme() {
    try {
        const value = localStorage.getItem("proactive-ed-theme");
        return value === "light" || value === "dark";
    } catch (e) {
        return false;
    }
}

function syncColors() {
    const bg = getComputedStyle(root).getPropertyValue("--bg-color").trim();
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute("content", bg);
    try {
        tg.setHeaderColor(bg);
        tg.setBackgroundColor(bg);
    } catch (e) { /* не підтримується */ }
}

function setupTelegram() {
    tg.ready();
    tg.expand();
    syncColors();

    tg.onEvent("themeChanged", function () {
        if (!hasSavedTheme()) {
            root.dataset.theme = tg.colorScheme;
            syncColors();
        }
    });

    // Кнопка «Назад» Telegram замінює стрілку на сторінці
    if (tg.BackButton && tg.isVersionAtLeast && tg.isVersionAtLeast("6.1")) {
        tg.BackButton.onClick(goBack);
        tg.BackButton.show();
        backBtn.hidden = true;
    }
}

/* ---------- Запуск ---------- */

if (isInTelegram()) {
    setupTelegram();
    backBtn.addEventListener("click", goBack);
    retryBtn.addEventListener("click", function () {
        setPageState("ready");
        route();
    });
    window.addEventListener("hashchange", route);
    setPageState("ready");
    route();
}
// Поза Telegram залишається екран «Відкрийте в Telegram» (його ставить planning.html)