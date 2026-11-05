/* Екран плану: опис, вкладки «Хронологія / Заняття / Події». */

import { planning } from "../api.js";
import {
    ACTIVITY_LABELS, EVENT_LABELS, ROLE_LABELS, escapeHtml,
    formatDayHeading, formatDuration, formatTimeRange, groupTimeline
} from "../format.js";
import {
    ICONS, beginScreen, emptyHtml, friendlyError, go, isCurrent, render,
    setFab, setHeaderAction, setTitle, showError, showLoading
} from "../ui.js";

const tg = window.Telegram && window.Telegram.WebApp;

/* Остання відкрита вкладка запам'ятовується, щоб після редагування
   повертатися туди ж, а не на «Хронологію» */
let lastPlanId = null;
let lastTab = "timeline";

/* ---------- Елементи списку ---------- */

function sessionItem(session, owner) {
    const times = formatTimeRange(session.start_time, session.duration_minutes).split("–");
    const tag = owner ? "a" : "div";
    const href = owner ? ' href="#/session/' + session.study_session_id + '/edit"' : "";
    return `<${tag} class="item item-session"${href}>
        <div class="item-time">${escapeHtml(times[0])}<br>${escapeHtml(times[1])}</div>
        <div class="item-body">
            <span class="item-title">${escapeHtml(session.title)}</span>
            <span class="chip">${escapeHtml(ACTIVITY_LABELS[session.activity_type] || session.activity_type)}</span>
            <span class="item-meta">${escapeHtml(formatDuration(session.duration_minutes))}</span>
        </div>
    </${tag}>`;
}

function eventItem(event, owner) {
    const tag = owner ? "a" : "div";
    const href = owner ? ' href="#/event/' + event.event_id + '/edit"' : "";
    return `<${tag} class="item item-event"${href}>
        <div class="item-time">Подія</div>
        <div class="item-body">
            <span class="item-title">${escapeHtml(event.title)}</span>
            <span class="chip">${escapeHtml(EVENT_LABELS[event.event_type] || event.event_type)}</span>
            ${event.description ? `<span class="item-meta">${escapeHtml(event.description)}</span>` : ""}
        </div>
    </${tag}>`;
}

function dayHtml(group, owner) {
    const items = group.items.map(function (item) {
        return item.kind === "event" ? eventItem(item, owner) : sessionItem(item, owner);
    }).join("");
    return `<section class="day">
        <h3 class="day-title">${escapeHtml(formatDayHeading(group.key))}</h3>
        <div class="day-items">${items}</div>
    </section>`;
}

/* ---------- Додавання ---------- */

function addSession(planId) { go("#/plan/" + planId + "/session/new"); }
function addEvent(planId) { go("#/plan/" + planId + "/event/new"); }

/* На вкладці «Хронологія» просимо обрати, що додати */
function chooseNew(planId) {
    if (tg && tg.showPopup && tg.isVersionAtLeast && tg.isVersionAtLeast("6.2")) {
        tg.showPopup({
            title: "Що додати?",
            message: "Оберіть, що створити в цьому плані.",
            buttons: [
                { id: "session", type: "default", text: "Заняття" },
                { id: "event", type: "default", text: "Подія" },
                { type: "cancel" }
            ]
        }, function (id) {
            if (id === "session") addSession(planId);
            else if (id === "event") addEvent(planId);
        });
    } else {
        addSession(planId);
    }
}

function addAction(tab, planId) {
    if (tab === "sessions") return function () { addSession(planId); };
    if (tab === "events") return function () { addEvent(planId); };
    return function () { chooseNew(planId); };
}

/* ---------- Малювання екрана ---------- */

const EMPTY = {
    timeline: { title: "У плані поки порожньо", text: "Додайте перше заняття або подію.", button: "Додати" },
    sessions: { title: "Занять немає", text: "Додайте навчальне заняття: лекцію, практичну, читання чи самостійне навчання.", button: "Додати заняття" },
    events: { title: "Подій немає", text: "Додайте іспит, контрольну або дедлайн.", button: "Додати подію" }
};

function draw(state) {
    const plan = state.plan;
    const owner = plan.role === "owner";
    const sessions = state.items.filter(function (item) { return item.kind === "session"; });
    const events = state.items.filter(function (item) { return item.kind === "event"; });

    const shown = lastTab === "sessions" ? sessions
        : lastTab === "events" ? events
        : state.items;

    const tabs = [
        ["timeline", "Хронологія"],
        ["sessions", "Заняття (" + sessions.length + ")"],
        ["events", "Події (" + events.length + ")"]
    ].map(function (tab) {
        return `<button class="tab" type="button" role="tab" data-tab="${tab[0]}"
            aria-selected="${tab[0] === lastTab}">${tab[1]}</button>`;
    }).join("");

    let body;
    if (shown.length === 0) {
        const empty = EMPTY[lastTab];
        body = emptyHtml(
            lastTab === "events" ? ICONS.calendar : ICONS.plans,
            empty.title,
            owner ? empty.text : "Власник плану ще нічого не додав.",
            owner ? empty.button : ""
        );
    } else {
        body = groupTimeline(shown).map(function (group) { return dayHtml(group, owner); }).join("");
    }

    /* НОВЕ: рядок-вхід на екран «Учасники» для всіх ролей */
    render(`
        ${plan.description ? `<p class="plan-description">${escapeHtml(plan.description)}</p>` : ""}
        <div class="plan-meta">
            <span class="badge${owner ? " badge-owner" : ""}">${escapeHtml(ROLE_LABELS[plan.role] || plan.role)}</span>
            <a class="members-link" href="#/plan/${plan.plan_id}/members">Учасники</a>
        </div>
        <div class="tabs" role="tablist">${tabs}</div>
        ${body}
        ${owner ? "" : '<p class="readonly-note">Ви можете лише переглядати цей план.</p>'}
    `);

    document.querySelectorAll(".tab").forEach(function (button) {
        button.addEventListener("click", function () {
            lastTab = button.dataset.tab;
            draw(state);
        });
    });

    if (owner) {
        const add = addAction(lastTab, plan.plan_id);
        const emptyButton = document.getElementById("emptyAction");
        if (emptyButton) emptyButton.addEventListener("click", add);
        setFab(add, lastTab === "events" ? "Додати подію" : lastTab === "sessions" ? "Додати заняття" : "Додати");
    }
}

export async function showPlan(params) {
    const screen = beginScreen();
    const planId = params.planId;

    if (lastPlanId !== planId) {
        lastPlanId = planId;
        lastTab = "timeline";
    }

    setTitle("План");
    showLoading();

    let plan;
    let items;
    try {
        const result = await Promise.all([planning.getPlan(planId), planning.timeline(planId)]);
        plan = result[0];
        items = result[1];
    } catch (error) {
        if (!isCurrent(screen)) return;
        showError(friendlyError(error), function () { showPlan(params); });
        return;
    }
    if (!isCurrent(screen)) return;

    setTitle(plan.title);
    if (plan.role === "owner") {
        setHeaderAction("Змінити", function () { go("#/plan/" + planId + "/edit"); });
    }
    draw({ plan: plan, items: items });
}