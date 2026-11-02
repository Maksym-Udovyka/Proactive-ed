/* Proactive Ed — Mini App. Подключается в <head> без defer (тема ставится до отрисовки). */
(function () {
    "use strict";

    var STORAGE_KEY = "proactive-ed-theme";
    var root = document.documentElement;
    var tg = window.Telegram && window.Telegram.WebApp;
    var inTelegram = !!(tg && tg.initData); // true только при открытии из Telegram

    function savedTheme() {
        try {
            var t = localStorage.getItem(STORAGE_KEY);
            return t === "light" || t === "dark" ? t : null;
        } catch (e) { return null; }
    }

    /* ---------- 1. Тема сразу, до отрисовки (без мигания) ----------
       Приоритет: выбор пользователя > тема Telegram > тема системы */
    root.setAttribute("data-theme",
        savedTheme() ||
        (tg && tg.colorScheme) ||
        (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));

    /* ---------- 2. Остальное после загрузки DOM ---------- */
    document.addEventListener("DOMContentLoaded", function () {
        var themeBtn = document.getElementById("themeBtn");
        var mainBtn = document.getElementById("mainBtn");
        var greeting = document.getElementById("greeting");
        var toast = document.getElementById("toast");

        function syncColors() {
            var dark = root.dataset.theme === "dark";
            themeBtn.setAttribute("aria-pressed", String(dark));
            var bg = getComputedStyle(root).getPropertyValue("--bg-color").trim();
            var meta = document.querySelector('meta[name="theme-color"]');
            if (meta) meta.setAttribute("content", bg);
            if (inTelegram) {
                try { tg.setHeaderColor(bg); tg.setBackgroundColor(bg); } catch (e) {}
            }
        }

        var toastTimer;
        function showToast(text) {
            toast.textContent = text;
            toast.classList.add("show");
            clearTimeout(toastTimer);
            toastTimer = setTimeout(function () { toast.classList.remove("show"); }, 2500);
        }

        /* Переключатель темы */
        themeBtn.addEventListener("click", function () {
            var next = root.dataset.theme === "dark" ? "light" : "dark";
            root.dataset.theme = next;
            try { localStorage.setItem(STORAGE_KEY, next); } catch (e) {}
            syncColors();
        });
        syncColors();

        /* Telegram */
        if (inTelegram) {
            tg.ready();
            tg.expand();
            tg.onEvent("themeChanged", function () {
                if (!savedTheme()) { root.dataset.theme = tg.colorScheme; syncColors(); }
            });
            var user = tg.initDataUnsafe && tg.initDataUnsafe.user;
            if (user && user.first_name) {
                greeting.textContent = "Привіт, " + user.first_name + "!";
                greeting.hidden = false;
            }
        }

        /* Картки-розділи.
           data-status="soon"  -> заглушка, показывает подсказку
           data-status="ready" -> готовый раздел (переход по href) */
        document.querySelectorAll(".card[data-section]").forEach(function (card) {
            card.addEventListener("click", function (e) {
                if (card.dataset.status !== "ready") {
                    e.preventDefault();
                    showToast("Розділ «" + card.dataset.title + "» ще в розробці");
                }
            });
        });

        /* Кнопка перевірки зв'язку */
        mainBtn.addEventListener("click", function () {
            if (inTelegram) tg.showAlert("Mini App працює. Платформа: " + tg.platform);
            else showToast("Відкрийте цю сторінку з Telegram");
        });
    });
})();
