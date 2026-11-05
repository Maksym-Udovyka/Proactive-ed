/* Форма навчальної сесії: створення, редагування, видалення. */

import { planning } from "../api.js";
import {
    ACTIVITY_LABELS, defaultStartValue, escapeHtml,
    fromDatetimeLocalValue, toDatetimeLocalValue
} from "../format.js";
import {
    ICONS, back, beginScreen, confirmDialog, emptyHtml, friendlyError, haptic,
    isCurrent, render, setBusy, setTitle, showError, showLoading, showToast
} from "../ui.js";

const QUICK_DURATIONS = [30, 45, 60, 90, 120];

function formHtml(session, editing) {
    const options = Object.keys(ACTIVITY_LABELS).map(function (key) {
        return `<option value="${key}"${key === session.activity_type ? " selected" : ""}>${escapeHtml(ACTIVITY_LABELS[key])}</option>`;
    }).join("");

    const chips = QUICK_DURATIONS.map(function (minutes) {
        return `<button class="chip-button" type="button" data-minutes="${minutes}" aria-pressed="false">${minutes} хв</button>`;
    }).join("");

    return `<form class="form" id="sessionForm" novalidate>
        <label class="field-label" for="sTitle">Назва</label>
        <input class="field-input" id="sTitle" type="text" maxlength="200"
               autocomplete="off" enterkeyhint="next" value="${escapeHtml(session.title || "")}">

        <label class="field-label" for="sType">Тип активності</label>
        <select class="field-input" id="sType">${options}</select>

        <label class="field-label" for="sStart">Початок</label>
        <input class="field-input" id="sStart" type="datetime-local" value="${escapeHtml(session.startValue)}">

        <label class="field-label" for="sDuration">Тривалість, хв</label>
        <input class="field-input" id="sDuration" type="number" inputmode="numeric"
               min="1" max="1440" step="5" value="${escapeHtml(String(session.duration_minutes))}">
        <div class="quick-values">${chips}</div>
        <p class="field-hint">Від 1 до 1440 хвилин. Час вказується у вашому часовому поясі.</p>

        <p class="field-error" id="formError" role="alert" hidden></p>
        <div class="profile-actions">
            <button class="main-button" id="saveBtn" type="submit">Зберегти</button>
            <button class="secondary-button" id="cancelBtn" type="button">Скасувати</button>
            ${editing ? '<button class="danger-button" id="deleteBtn" type="button">Видалити заняття</button>' : ""}
        </div>
    </form>`;
}

export async function showSessionForm(params) {
    const screen = beginScreen();
    const editing = !!params.sessionId;
    setTitle(editing ? "Редагування заняття" : "Нове заняття");
    showLoading();

    let session = null;
    let plan;
    try {
        if (editing) {
            session = await planning.getSession(params.sessionId);
            plan = await planning.getPlan(session.plan_id);
        } else {
            plan = await planning.getPlan(params.planId);
        }
    } catch (error) {
        if (!isCurrent(screen)) return;
        showError(friendlyError(error), function () { showSessionForm(params); });
        return;
    }
    if (!isCurrent(screen)) return;

    if (plan.role !== "owner") {
        render(emptyHtml(ICONS.alert, "Недостатньо прав", "Змінювати план може лише його власник."));
        return;
    }

    const planId = plan.plan_id;
    const initial = session
        ? {
            title: session.title,
            activity_type: session.activity_type,
            startValue: toDatetimeLocalValue(session.start_time),
            duration_minutes: session.duration_minutes
        }
        : {
            title: "",
            activity_type: "lecture",
            startValue: defaultStartValue(),
            duration_minutes: 60
        };

    render(formHtml(initial, editing));

    const form = document.getElementById("sessionForm");
    const titleInput = document.getElementById("sTitle");
    const typeSelect = document.getElementById("sType");
    const startInput = document.getElementById("sStart");
    const durationInput = document.getElementById("sDuration");
    const formError = document.getElementById("formError");
    const saveBtn = document.getElementById("saveBtn");
    const cancelBtn = document.getElementById("cancelBtn");
    const deleteBtn = document.getElementById("deleteBtn");
    const buttons = [saveBtn, cancelBtn, deleteBtn];
    const chips = Array.from(document.querySelectorAll(".chip-button"));

    function showFormError(text) {
        formError.textContent = text;
        formError.hidden = false;
        haptic("error");
    }

    function syncChips() {
        const current = Number(durationInput.value);
        chips.forEach(function (chip) {
            chip.setAttribute("aria-pressed", String(Number(chip.dataset.minutes) === current));
        });
    }

    chips.forEach(function (chip) {
        chip.addEventListener("click", function () {
            durationInput.value = chip.dataset.minutes;
            syncChips();
        });
    });
    durationInput.addEventListener("input", syncChips);
    syncChips();

    if (!editing) titleInput.focus();

    cancelBtn.addEventListener("click", function () { back("#/plan/" + planId); });

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        formError.hidden = true;

        const title = titleInput.value.trim();
        if (!title) {
            showFormError("Введіть назву заняття.");
            titleInput.focus();
            return;
        }
        const startIso = fromDatetimeLocalValue(startInput.value);
        if (!startIso) {
            showFormError("Вкажіть дату й час початку.");
            startInput.focus();
            return;
        }
        const duration = Number(durationInput.value);
        if (!Number.isInteger(duration) || duration < 1 || duration > 1440) {
            showFormError("Тривалість має бути цілим числом від 1 до 1440 хвилин.");
            durationInput.focus();
            return;
        }

        const payload = {
            title: title,
            activity_type: typeSelect.value,
            start_time: startIso,
            duration_minutes: duration
        };

        setBusy(buttons, true);
        try {
            if (editing) await planning.updateSession(params.sessionId, payload);
            else await planning.createSession(planId, payload);
            haptic("success");
            showToast(editing ? "Зміни збережено" : "Заняття додано");
            if (isCurrent(screen)) back("#/plan/" + planId);
        } catch (error) {
            if (!isCurrent(screen)) return;
            showFormError(friendlyError(error));
            setBusy(buttons, false);
        }
    });

    if (deleteBtn) {
        deleteBtn.addEventListener("click", async function () {
            const ok = await confirmDialog("Видалити заняття «" + session.title + "»?");
            if (!ok) return;
            setBusy(buttons, true);
            try {
                await planning.deleteSession(params.sessionId);
                haptic("success");
                showToast("Заняття видалено");
                if (isCurrent(screen)) back("#/plan/" + planId);
            } catch (error) {
                if (!isCurrent(screen)) return;
                showFormError(friendlyError(error));
                setBusy(buttons, false);
            }
        });
    }
}