/* Екран вступу за запрошенням: #/invite/<токен>. */

import { planning } from "../api.js";
import { ROLE_LABELS, escapeHtml } from "../format.js";
import {
    ICONS, beginScreen, emptyHtml, friendlyError, haptic, isCurrent, render,
    setBusy, setTitle, showError, showLoading, showToast
} from "../ui.js";

const ROLE_HINTS = {
    viewer: "Ви зможете переглядати заняття та події плану.",
    commenter: "Ви зможете переглядати план. Коментарі з'являться пізніше."
};

function formatUntil(iso) {
    return new Date(iso).toLocaleDateString("uk-UA", {
        day: "numeric",
        month: "long",
        year: "numeric"
    });
}

function toPlans() {
    location.replace("#/");
}

/* Екран зі станом, у якому вступити неможливо: повідомлення й одна кнопка */
function blocked(title, text, buttonLabel, onClick) {
    render(emptyHtml(ICONS.alert, title, text, buttonLabel));
    document.getElementById("emptyAction").addEventListener("click", onClick);
}

function validHtml(invite) {
    return '<div class="invite-card">' +
        '<div class="status-icon" aria-hidden="true">' + ICONS.users + "</div>" +
        '<h2 class="empty-title">Запрошення до плану</h2>' +
        '<p class="invite-plan">' + escapeHtml(invite.plan_title) + "</p>" +
        '<p class="empty-text">' +
        (invite.invited_by_name
            ? escapeHtml(invite.invited_by_name) + " запрошує вас до цього плану."
            : "Вас запрошено до цього плану.") +
        "</p>" +
        '<p class="invite-line"><span class="badge">' +
        escapeHtml(ROLE_LABELS[invite.role] || invite.role) + "</span></p>" +
        '<p class="field-hint">' + escapeHtml(ROLE_HINTS[invite.role] || "") + "</p>" +
        '<p class="field-hint">Діє до ' + escapeHtml(formatUntil(invite.expires_at)) +
        ". Посилання одноразове.</p>" +
        '<div class="profile-actions">' +
        '<button class="main-button" id="acceptBtn" type="button">Приєднатися</button>' +
        '<button class="secondary-button" id="declineBtn" type="button">Не зараз</button>' +
        "</div></div>";
}

export async function showInvite(params) {
    const screen = beginScreen();
    const token = params.token;

    setTitle("Запрошення");
    showLoading();

    let invite;
    try {
        invite = await planning.getInvite(token);
    } catch (error) {
        if (!isCurrent(screen)) return;
        if (error.status === 404) {
            blocked(
                "Запрошення не знайдено",
                "Посилання недійсне або його вже відкликав власник плану.",
                "До моїх планів",
                toPlans
            );
        } else {
            showError(friendlyError(error), function () { showInvite(params); });
        }
        return;
    }
    if (!isCurrent(screen)) return;

    const openPlan = function () { location.replace("#/plan/" + invite.plan_id); };

    if (invite.state === "own_plan") {
        blocked("Це ваш власний план", "Запрошення не потрібне: ви його власник.", "Відкрити план", openPlan);
        return;
    }
    if (invite.state === "already_member") {
        blocked("Ви вже в цьому плані", "Ви вже є учасником плану «" + invite.plan_title + "».", "Відкрити план", openPlan);
        return;
    }
    if (invite.state === "used") {
        blocked("Запрошення вже використано", "Попросіть власника плану створити нове посилання.", "До моїх планів", toPlans);
        return;
    }
    if (invite.state === "expired") {
        blocked("Термін дії минув", "Попросіть власника плану створити нове посилання.", "До моїх планів", toPlans);
        return;
    }

    render(validHtml(invite));

    const acceptBtn = document.getElementById("acceptBtn");
    const declineBtn = document.getElementById("declineBtn");
    const buttons = [acceptBtn, declineBtn];

    declineBtn.addEventListener("click", toPlans);

    acceptBtn.addEventListener("click", async function () {
        setBusy(buttons, true);
        try {
            const result = await planning.acceptInvite(token);
            haptic("success");
            showToast("Ви приєдналися до плану");
            if (isCurrent(screen)) location.replace("#/plan/" + result.plan_id);
        } catch (error) {
            if (!isCurrent(screen)) return;
            haptic("error");
            showToast(friendlyError(error));
            if (error.status === 0) {
                setBusy(buttons, false); // немає зв'язку: можна спробувати ще раз
            } else {
                showInvite(params); // стан змінився: показуємо актуальний екран
            }
        }
    });
}