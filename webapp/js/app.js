/* Proactive Ed — Mini App. Подключается в <head> без defer (тема и экран выбираются до отрисовки).

   Экраны (атрибут data-state на <html>):
     loading  — открыто из Telegram, идёт вход
     ready    — вход выполнен, показываем приложение и аватар
     error    — вход не удался (кнопка «Спробувати ще раз»)
     outside  — открыто не из Telegram */
(function () {
    "use strict";

    /* Ім'я Telegram-бота без @ (наприклад "proactive_ed_bot").
       Потрібне для кнопки «Відкрити в Telegram» на екрані для звичайного браузера.
       Якщо залишити порожнім, кнопку буде приховано. */
    var BOT_USERNAME = "proactive_ed_bot";

    var API = "/api/auth/v1";
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

    /* ---------- 1. Тема и экран сразу, до отрисовки (без мигания) ----------
       Приоритет темы: выбор пользователя > тема Telegram > тема системы.
       tg.colorScheme учитываем только внутри Telegram: вне его SDK всегда отдаёт "light". */
    root.setAttribute("data-theme",
        savedTheme() ||
        (inTelegram && tg.colorScheme) ||
        (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));

    root.setAttribute("data-state", inTelegram ? "loading" : "outside");

    /* ---------- 2. Остальное после загрузки DOM ---------- */
    document.addEventListener("DOMContentLoaded", function () {
        var themeBtn = document.getElementById("themeBtn");
        var greeting = document.getElementById("greeting");
        var avatar = document.getElementById("avatar");
        var toast = document.getElementById("toast");
        var errorText = document.getElementById("errorText");
        var retryBtn = document.getElementById("retryBtn");
        var openBotBtn = document.getElementById("openBotBtn");

        function setState(state) { root.setAttribute("data-state", state); }

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

        /* ---------- Аватар ----------
           Спочатку показуємо круг з першою літерою імені. Якщо Telegram передав photo_url
           і картинка завантажилась, підміняємо літеру фото. Фото може бути відсутнім
           (немає аватара або він прихований налаштуваннями приватності). */
        function renderAvatar(name, photoUrl) {
            var first = Array.from((name || "").trim())[0] || "?";
            avatar.textContent = first.toUpperCase();
            if (!photoUrl) return;
            var img = new Image();
            img.alt = "";
            img.referrerPolicy = "no-referrer";
            img.onload = function () {
                avatar.textContent = "";
                avatar.appendChild(img);
            };
            img.src = photoUrl;
        }

        function showUser(user, tgUser) {
            var name = user.first_name || tgUser.first_name || "";
            greeting.textContent = name ? "Привіт, " + name + "!" : "Привіт!";
            greeting.hidden = false;
            renderAvatar(name, tgUser.photo_url);
        }

        function fail(message) {
            errorText.textContent = message;
            setState("error");
        }

        function readJson(res) {
            return res.json().catch(function () { return {}; });
        }

        /* ---------- Автоматичний вхід / реєстрація ----------
           Сервіс auth перевіряє підпис initData і створює користувача при першому вході.
           Шлях: Mini App -> Netlify -> тунель -> auth -> PostgreSQL.
           Заголовок ngrok-skip-browser-warning потрібен лише поки використовується ngrok. */
        var busy = false;
        async function login() {
            if (busy) return;
            busy = true;
            setState("loading");
            var tgUser = (tg.initDataUnsafe && tg.initDataUnsafe.user) || {};
            try {
                var res = await fetch(API + "/telegram-login", {
                    method: "POST",
                    headers: { "Content-Type": "application/json", "ngrok-skip-browser-warning": "true" },
                    body: JSON.stringify({ initData: tg.initData })
                });
                var data = await readJson(res);
                if (!res.ok || !data.token) {
                    fail("Помилка входу (" + res.status + "): " + (data.error || "невідома"));
                    return;
                }
                try { localStorage.setItem(TOKEN_KEY, data.token); } catch (e) {}

                var me = await fetch(API + "/me", {
                    headers: {
                        "Authorization": "Bearer " + data.token,
                        "ngrok-skip-browser-warning": "true"
                    }
                });
                var meData = await readJson(me);
                if (!me.ok || !meData.user) {
                    fail("Помилка профілю (" + me.status + "): " + (meData.error || "невідома"));
                    return;
                }

                showUser(meData.user, tgUser);
                setState("ready");
            } catch (e) {
                fail("Немає зв'язку з сервером. Перевірте інтернет і спробуйте ще раз.");
            } finally {
                busy = false;
            }
        }

        retryBtn.addEventListener("click", login);

        if (inTelegram) {
            tg.ready();
            tg.expand();
            tg.onEvent("themeChanged", function () {
                if (!savedTheme()) { root.dataset.theme = tg.colorScheme; syncColors(); }
            });
            login();
        } else if (BOT_USERNAME) {
            openBotBtn.href = "https://t.me/" + BOT_USERNAME;
            openBotBtn.hidden = false;
        }
    });
})();
