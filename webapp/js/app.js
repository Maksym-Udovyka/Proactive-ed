/* Proactive Ed — Mini App. Подключается в <head> без defer (тема и экран выбираются до отрисовки).

   Экраны (атрибут data-state на <html>):
     loading  — открыто из Telegram, идёт вход
     ready    — вход выполнен, показываем приложение и аватар
     profile  — экран профиля (открывается по нажатию на аватар)
     error    — вход не удался (кнопка «Спробувати ще раз»)
     outside  — открыто не из Telegram */
(function () {
    "use strict";

    /* Ім'я Telegram-бота без @ (наприклад "proactive_ed_bot").
       Потрібне для кнопки «Відкрити в Telegram» на екрані для звичайного браузера.
       Якщо залишити порожнім, кнопку буде приховано. */
    var BOT_USERNAME = "";

    var API = "/api/auth/v1";
    var STORAGE_KEY = "proactive-ed-theme";
    var TOKEN_KEY = "proactive-ed-token";
    var INVITE_SEEN_KEY = "proactive-ed-invite-seen"; // НОВЕ
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

    /* ---------- НОВЕ: запрошення за посиланням ----------
       Посилання t.me/<бот>/<застосунок>?startapp=<токен> передає токен у start_param.
       Токен однаковий для всієї сесії, тому переходимо на екран запрошення
       один раз: інакше «Назад» з planning.html знову вів би на нього. */
    function inviteToken() {
        var param = tg && tg.initDataUnsafe && tg.initDataUnsafe.start_param;
        return typeof param === "string" && /^[A-Za-z0-9_-]{1,100}$/.test(param) ? param : null;
    }

    function openInviteIfAny() {
        var token = inviteToken();
        if (!token) return false;
        try {
            if (sessionStorage.getItem(INVITE_SEEN_KEY) === token) return false;
            sessionStorage.setItem(INVITE_SEEN_KEY, token);
        } catch (e) { /* сховище недоступне: переходимо без захисту від повтору */ }
        location.replace("planning.html#/invite/" + encodeURIComponent(token));
        return true;
    }

    /* ---------- 2. Остальное после загрузки DOM ---------- */
    document.addEventListener("DOMContentLoaded", function () {
        var themeBtn = document.getElementById("themeBtn");
        var greeting = document.getElementById("greeting");
        var avatar = document.getElementById("avatar");
        var toast = document.getElementById("toast");
        var errorText = document.getElementById("errorText");
        var retryBtn = document.getElementById("retryBtn");
        var openBotBtn = document.getElementById("openBotBtn");
        var profileForm = document.getElementById("profileForm");
        var nameInput = document.getElementById("nameInput");
        var profileError = document.getElementById("profileError");
        var saveBtn = document.getElementById("saveBtn");
        var cancelBtn = document.getElementById("cancelBtn");

        var token = null;        // JWT після входу
        var currentUser = null;  // користувач з /me: name, display_name, first_name, ...
        var tgUser = {};         // дані користувача з Telegram (для фото)

        function getState() { return root.getAttribute("data-state"); }
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
        var avatarHasPhoto = false;

        function setAvatarInitial(name) {
            if (avatarHasPhoto) return;
            var first = Array.from((name || "").trim())[0] || "?";
            avatar.textContent = first.toUpperCase();
        }

        function renderAvatar(name, photoUrl) {
            setAvatarInitial(name);
            if (!photoUrl || avatarHasPhoto) return;
            var img = new Image();
            img.alt = "";
            img.referrerPolicy = "no-referrer";
            img.onload = function () {
                avatarHasPhoto = true;
                avatar.textContent = "";
                avatar.appendChild(img);
            };
            img.src = photoUrl;
        }

        /* Ім'я для показу: display_name, якщо задано, інакше ім'я з Telegram (поле name від сервера) */
        function shownName() {
            return (currentUser && (currentUser.name || currentUser.first_name)) || tgUser.first_name || "";
        }

        function showUser() {
            var name = shownName();
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

        function authHeaders(extra) {
            var h = { "Authorization": "Bearer " + token, "ngrok-skip-browser-warning": "true" };
            for (var k in (extra || {})) h[k] = extra[k];
            return h;
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
            tgUser = (tg.initDataUnsafe && tg.initDataUnsafe.user) || {};
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
                token = data.token;
                try { localStorage.setItem(TOKEN_KEY, token); } catch (e) {}

                /* НОВЕ: токен збережено, planning.html підхопить його з localStorage.
                   Якщо відкрито за запрошенням, одразу йдемо на екран вступу. */
                if (openInviteIfAny()) return;

                var me = await fetch(API + "/me", { headers: authHeaders() });
                var meData = await readJson(me);
                if (!me.ok || !meData.user) {
                    fail("Помилка профілю (" + me.status + "): " + (meData.error || "невідома"));
                    return;
                }

                currentUser = meData.user;
                showUser();
                setState("ready");
            } catch (e) {
                fail("Немає зв'язку з сервером. Перевірте інтернет і спробуйте ще раз.");
            } finally {
                busy = false;
            }
        }

        retryBtn.addEventListener("click", login);

        /* ---------- Профіль: зміна відображуваного імені ----------
           display_name зберігається на сервері й не перезаписується при наступному вході.
           Порожнє поле скидає ім'я до імені з Telegram. */
        function openProfile() {
            if (!currentUser) return;
            nameInput.value = currentUser.display_name || "";
            nameInput.placeholder = currentUser.first_name || "Ваше ім'я";
            profileError.hidden = true;
            setState("profile");
            nameInput.focus();
        }

        function closeProfile() { setState("ready"); }

        avatar.addEventListener("click", function () {
            if (getState() === "ready") openProfile();
            else if (getState() === "profile") closeProfile();
        });
        cancelBtn.addEventListener("click", closeProfile);

        var saving = false;
        profileForm.addEventListener("submit", async function (e) {
            e.preventDefault();
            if (saving) return;
            saving = true;
            saveBtn.disabled = true;
            profileError.hidden = true;
            try {
                var res = await fetch(API + "/me", {
                    method: "PATCH",
                    headers: authHeaders({ "Content-Type": "application/json" }),
                    body: JSON.stringify({ display_name: nameInput.value })
                });
                if (res.status === 401) {   // токен прострочений: входимо знову
                    login();
                    return;
                }
                var data = await readJson(res);
                if (!res.ok || !data.user) {
                    profileError.textContent = data.error || "Не вдалося зберегти. Спробуйте ще раз.";
                    profileError.hidden = false;
                    return;
                }
                currentUser = data.user;
                showUser();
                setAvatarInitial(shownName());
                setState("ready");
                showToast("Ім'я збережено");
            } catch (err) {
                profileError.textContent = "Немає зв'язку з сервером. Спробуйте ще раз.";
                profileError.hidden = false;
            } finally {
                saving = false;
                saveBtn.disabled = false;
            }
        });

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