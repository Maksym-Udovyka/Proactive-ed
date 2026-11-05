/* Екран «Учасники»: список, ролі, запрошення за посиланням, вихід із плану. */

import { planning } from "../api.js";
import { ROLE_LABELS, escapeHtml } from "../format.js";
import {
    beginScreen, confirmDialog, friendlyError, haptic, isCurrent, render,
    setHeaderAction, setTitle, showError, showLoading, showToast
} from "../ui.js";

const tg = window.Telegram && window.Telegram.WebApp;

/* Заповніть після /newapp у BotFather:
   посилання матиме вигляд https://t.me/<BOT_USERNAME>/<APP_SHORT_NAME>?startapp=<токен> */
const BOT_USERNAME = "";
const APP_SHORT_NAME = "";

const ASSIGNABLE_ROLES = ["viewer", "commenter"];

/* ---------- Посилання й поширення ---------- */

function linkConfigured() {
    return !!(BOT_USERNAME && APP_SHORT_NAME);
}

function inviteLink(token) {
    return "https://t.me/" + BOT_USERNAME + "/" + APP_SHORT_NAME +
        "?startapp=" + encodeURIComponent(token);
}

function shareInvite(plan, token) {
    const text = "Запрошую до навчального плану «" + plan.title + "»";
    const url = "https://t.me/share/url?url=" + encodeURIComponent(inviteLink(token)) +
        "&text=" + encodeURIComponent(text);
    if (tg && tg.openTelegramLink) tg.openTelegramLink(url);
    else window.open(url, "_blank");
}

async function copyInvite(token) {
    try {
        await navigator.clipboard.writeText(inviteLink(token));
        haptic("success");
        showToast("Посилання скопійовано");
    } catch (e) {
        showToast("Не вдалося скопіювати. Скористайтеся кнопкою «Поділитися».");
    }
}

/* Вибір ролі для нового запрошення: null, якщо користувач скасував */
function chooseRole() {
    return new Promise(function (resolve) {
        if (tg && tg.showPopup && tg.isVersionAtLeast && tg.isVersionAtLeast("6.2")) {
            tg.showPopup({
                title: "Нове запрошення",
                message: "Яку роль отримає запрошений?",
                buttons: [
                    { id: "viewer", type: "default", text: ROLE_LABELS.viewer },
                    { id: "commenter", type: "default", text: ROLE_LABELS.commenter },
                    { type: "cancel" }
                ]
            }, function (id) {
                resolve(ASSIGNABLE_ROLES.indexOf(id) !== -1 ? id : null);
            });
        } else {
            resolve("viewer");
        }
    });
}

/* ---------- Розмітка ---------- */

function formatUntil(iso) {
    return new Date(iso).toLocaleDateString("uk-UA", { day: "numeric", month: "long" });
}

function roleBadge(role) {
    return '<span class="badge' + (role === "owner" ? " badge-owner" : "") + '">' +
        escapeHtml(ROLE_LABELS[role] || role) + "</span>";
}

function memberHtml(member, canManage) {
    const manage = canManage && member.role !== "owner";
    const options = ASSIGNABLE_ROLES.map(function (role) {
        return '<option value="' + role + '"' + (role === member.role ? " selected" : "") + ">" +
            escapeHtml(ROLE_LABELS[role]) + "</option>";
    }).join("");

    return '<div class="member">' +
        '<div class="member-info">' +
        '<span class="member-name">' + escapeHtml(member.name) + "</span>" +
        roleBadge(member.role) +
        "</div>" +
        (manage
            ? '<div class="member-actions">' +
              '<select class="field-input member-role" data-user="' + member.user_id +
              '" aria-label="Роль учасника">' + options + "</select>" +
              '<button class="danger-button member-remove" type="button" data-user="' +
              member.user_id + '">Видалити</button>' +
              "</div>"
            : "") +
        "</div>";
}

function inviteHtml(invite) {
    return '<div class="member invite">' +
        '<div class="member-info">' +
        '<span class="member-name">' + escapeHtml(ROLE_LABELS[invite.role] || invite.role) + "</span>" +
        '<span class="item-meta">діє до ' + escapeHtml(formatUntil(invite.expires_at)) + "</span>" +
        "</div>" +
        '<div class="member-actions">' +
        '<button class="main-button invite-share" type="button" data-token="' +
        escapeHtml(invite.token) + '">Поділитися</button>' +
        '<button class="secondary-button invite-copy" type="button" data-token="' +
        escapeHtml(invite.token) + '">Копіювати</button>' +
        '<button class="danger-button invite-revoke" type="button" data-id="' +
        invite.plan_invite_id + '">Відкликати</button>' +
        "</div></div>";
}

/* ---------- Малювання ---------- */

function draw(state, screen) {
    const owner = state.plan.role === "owner";

    let html = '<h3 class="section-title">Учасники (' + state.members.length + ")</h3>" +
        '<div class="member-list">' +
        state.members.map(function (member) { return memberHtml(member, owner); }).join("") +
        "</div>";

    if (owner) {
        html += '<h3 class="section-title">Активні запрошення</h3>';
        if (state.invites.length === 0) {
            html += '<p class="field-hint">Активних запрошень немає. Натисніть «Запросити» вгорі. ' +
                "Кожне посилання одноразове й діє 7 днів.</p>";
        } else {
            html += '<div class="member-list">' + state.invites.map(inviteHtml).join("") + "</div>";
        }
    } else {
        html += '<div class="profile-actions">' +
            '<button class="danger-button" id="leaveBtn" type="button">Покинути план</button></div>';
    }

    const view = render(html);

    function setAllBusy(busy) {
        view.querySelectorAll("button, select").forEach(function (el) { el.disabled = busy; });
    }

    /* Виконує дію, показує результат і перезавантажує списки */
    async function act(work, successText) {
        setAllBusy(true);
        try {
            await work();
            haptic("success");
            if (successText) showToast(successText);
        } catch (error) {
            if (!isCurrent(screen)) return;
            haptic("error");
            showToast(friendlyError(error));
        }
        if (isCurrent(screen)) await refresh(state, screen);
    }

    view.querySelectorAll(".member-role").forEach(function (select) {
        select.addEventListener("change", function () {
            const userId = Number(select.dataset.user);
            act(function () {
                return planning.updateMemberRole(state.plan.plan_id, userId, select.value);
            }, "Роль змінено");
        });
    });

    view.querySelectorAll(".member-remove").forEach(function (button) {
        button.addEventListener("click", async function () {
            const ok = await confirmDialog("Видалити учасника з плану? Він втратить доступ.");
            if (!ok) return;
            act(function () {
                return planning.removeMember(state.plan.plan_id, Number(button.dataset.user));
            }, "Учасника видалено");
        });
    });

    view.querySelectorAll(".invite-share").forEach(function (button) {
        button.addEventListener("click", function () {
            if (!linkConfigured()) return showToast("Посилання ще не налаштовано");
            shareInvite(state.plan, button.dataset.token);
        });
    });

    view.querySelectorAll(".invite-copy").forEach(function (button) {
        button.addEventListener("click", function () {
            if (!linkConfigured()) return showToast("Посилання ще не налаштовано");
            copyInvite(button.dataset.token);
        });
    });

    view.querySelectorAll(".invite-revoke").forEach(function (button) {
        button.addEventListener("click", async function () {
            const ok = await confirmDialog("Відкликати запрошення? Посилання перестане працювати.");
            if (!ok) return;
            act(function () {
                return planning.revokeInvite(state.plan.plan_id, Number(button.dataset.id));
            }, "Запрошення відкликано");
        });
    });

    const leaveBtn = document.getElementById("leaveBtn");
    if (leaveBtn) {
        leaveBtn.addEventListener("click", async function () {
            const ok = await confirmDialog(
                "Покинути план «" + state.plan.title + "»? Щоб повернутися, потрібне нове запрошення."
            );
            if (!ok) return;
            setAllBusy(true);
            try {
                await planning.leavePlan(state.plan.plan_id);
                haptic("success");
                showToast("Ви покинули план");
                if (isCurrent(screen)) location.replace("#/");
            } catch (error) {
                if (!isCurrent(screen)) return;
                haptic("error");
                showToast(friendlyError(error));
                setAllBusy(false);
            }
        });
    }
}

async function refresh(state, screen) {
    try {
        const owner = state.plan.role === "owner";
        const result = await Promise.all([
            planning.listMembers(state.plan.plan_id),
            owner ? planning.listInvites(state.plan.plan_id) : Promise.resolve([])
        ]);
        state.members = result[0];
        state.invites = result[1];
    } catch (error) {
        if (!isCurrent(screen)) return;
        showError(friendlyError(error), function () { showMembers({ planId: state.plan.plan_id }); });
        return;
    }
    if (!isCurrent(screen)) return;
    draw(state, screen);
}

/* ---------- Вхід на екран ---------- */

async function createAndShareInvite(state, screen) {
    if (!linkConfigured()) {
        showToast("Посилання ще не налаштовано: потрібен /newapp у BotFather");
        return;
    }
    const role = await chooseRole();
    if (!role || !isCurrent(screen)) return;
    try {
        const invite = await planning.createInvite(state.plan.plan_id, role);
        haptic("success");
        if (!isCurrent(screen)) return;
        await refresh(state, screen);
        shareInvite(state.plan, invite.token);
    } catch (error) {
        if (!isCurrent(screen)) return;
        haptic("error");
        showToast(friendlyError(error));
    }
}

export async function showMembers(params) {
    const screen = beginScreen();
    const planId = params.planId;

    setTitle("Учасники");
    showLoading();

    let plan;
    try {
        plan = await planning.getPlan(planId);
    } catch (error) {
        if (!isCurrent(screen)) return;
        showError(friendlyError(error), function () { showMembers(params); });
        return;
    }
    if (!isCurrent(screen)) return;

    const state = { plan: plan, members: [], invites: [] };
    if (plan.role === "owner") {
        setHeaderAction("Запросити", function () { createAndShareInvite(state, screen); });
    }
    await refresh(state, screen);
}