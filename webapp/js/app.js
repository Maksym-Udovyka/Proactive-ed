/* Proactive Ed — Mini App. Подключается в <head> без defer (тема ставится до отрисовки). */
(function () {
    "use strict";

    var STORAGE_KEY = "proactive-ed-theme";
    var TOKEN_KEY = "proactive-ed-token";
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

        /* Кнопка перевірки зв'язку: логін через сервіс auth + запит /me.
           Перевіряє весь шлях: Mini App -> Netlify -> тунель -> auth -> PostgreSQL.
           Заголовок ngrok-skip-browser-warning потрібен лише поки використовується ngrok. */
        mainBtn.addEventListener("click", async function () {
            if (!inTelegram) { showToast("Відкрийте цю сторінку з Telegram"); return; }
            var h = { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true" };
            try {
                var res = await fetch("/api/auth/v1/telegram-login", {
                    method: "POST",
                    headers: h,
                    body: JSON.stringify({ initData: tg.initData })
                });
                var data = await res.json().catch(function () { return {}; });
                if (!res.ok) {
                    tg.showAlert("Помилка входу (" + res.status + "): " + (data.error || "невідома"));
                    return;
                }
                try { localStorage.setItem(TOKEN_KEY, data.token); } catch (e) {}

                var me = await fetch("/api/auth/v1/me", {
                    headers: {
                        "Authorization": "Bearer " + data.token,
                        "ngrok-skip-browser-warning": "true"
                    }
                });
                var meData = await me.json().catch(function () { return {}; });
                if (!me.ok) {
                    tg.showAlert("Помилка /me (" + me.status + "): " + (meData.error || "невідома"));
                    return;
                }
                tg.showAlert("Вхід успішний! user_id=" + meData.user.user_id + ", " + meData.user.first_name);
            } catch (e) {
                tg.showAlert("Немає зв'язку з сервером: " + e.message);
            }
        });
    });
})();