/* Форма події (іспит, контрольна, дедлайн, інше): створення, редагування, видалення. */

import { planning } from "../api.js";
import { EVENT_LABELS, escapeHtml, todayKey } from "../format.js";
import {
    ICONS, back, beginScreen, confirmDialog, emptyHtml, friendlyError, haptic,
    isCurrent, render, setBusy, setTitle, showError, showLoading, showToast
} from "../ui.js";

function formHtml(event, editing) {
    const options = Object.keys(EVENT_LABELS).map(function (key) {
        return `<option value="${key}"${key === event.event_type ? " selected" : ""}>${escapeHtml(EVENT_LABELS[key])}</option>`;
    }).join("");

    return `<form class="form" id="eventForm" novalidate>
        <label class="field-label" for="eTitle">Назва</label>
        <input class="field-input" id="eTitle" type="text" maxlength="200"
               autocomplete="off" enterkeyhint="next" value="${escapeHtml(event.title || "")}">

        <label class="field-label" for="eType">Тип події</label>
        <select class="field-input" id="eType">${options}</select>

        <label class="field-label" for="eDate">Дата</label>
        <input class="field-input" id="eDate" type="date" value="${escapeHtml(event.event_date)}">

        <label class="field-label" for="eDesc">Опис</label>
        <textarea class="field-input" id="eDesc" maxlength="2000" rows="4">${escapeHtml(event.description || "")}</textarea>
        <p class="field-hint">Опис необов'язковий: наприклад, аудиторія або що взяти з собою.</p>

        <p class="field-error" id="formError" role="alert" hidden></p>
        <div class="profile-actions">
            <button class="main-button" id="saveBtn" type="submit">Зберегти</button>
            <button class="secondary-button" id="cancelBtn" type="button">Скасувати</button>
            ${editing ? '<button class="danger-button" id="deleteBtn" type="button">Видалити подію</button>' : ""}
        </div>
    </form>`;
}

export async function showEventForm(params) {
    const screen = beginScreen();
    const editing = !!params.eventId;
    setTitle(editing ? "Редагування події" : "Нова подія");
    showLoading();

    let event = null;
    let plan;
    try {
        if (editing) {
            event = await planning.getEvent(params.eventId);
            plan = await planning.getPlan(event.plan_id);
        } else {
            plan = await planning.getPlan(params.planId);
        }
    } catch (error) {
        if (!isCurrent(screen)) return;
        showError(friendlyError(error), function () { showEventForm(params); });
        return;
    }
    if (!isCurrent(screen)) return;

    if (plan.role !== "owner") {
        render(emptyHtml(ICONS.alert, "Недостатньо прав", "Змінювати план може лише його власник."));
        return;
    }

    const planId = plan.plan_id;
    const initial = event || {
        title: "",
        event_type: "exam",
        event_date: todayKey(),
        description: ""
    };

    render(formHtml(initial, editing));

    const form = document.getElementById("eventForm");
    const titleInput = document.getElementById("eTitle");
    const typeSelect = document.getElementById("eType");
    const dateInput = document.getElementById("eDate");
    const descInput = document.getElementById("eDesc");
    const formError = document.getElementById("formError");
    const saveBtn = document.getElementById("saveBtn");
    const cancelBtn = document.getElementById("cancelBtn");
    const deleteBtn = document.getElementById("deleteBtn");
    const buttons = [saveBtn, cancelBtn, deleteBtn];

    function showFormError(text) {
        formError.textContent = text;
        formError.hidden = false;
        haptic("error");
    }

    if (!editing) titleInput.focus();

    cancelBtn.addEventListener("click", function () { back("#/plan/" + planId); });

    form.addEventListener("submit", async function (e) {
        e.preventDefault();
        formError.hidden = true;

        const title = titleInput.value.trim();
        if (!title) {
            showFormError("Введіть назву події.");
            titleInput.focus();
            return;
        }
        if (!/^\d{4}-\d{2}-\d{2}$/.test(dateInput.value)) {
            showFormError("Вкажіть дату події.");
            dateInput.focus();
            return;
        }

        const payload = {
            title: title,
            event_type: typeSelect.value,
            event_date: dateInput.value,
            description: descInput.value.trim() || null
        };

        setBusy(buttons, true);
        try {
            if (editing) await planning.updateEvent(params.eventId, payload);
            else await planning.createEvent(planId, payload);
            haptic("success");
            showToast(editing ? "Зміни збережено" : "Подію додано");
            if (isCurrent(screen)) back("#/plan/" + planId);
        } catch (error) {
            if (!isCurrent(screen)) return;
            showFormError(friendlyError(error));
            setBusy(buttons, false);
        }
    });

    if (deleteBtn) {
        deleteBtn.addEventListener("click", async function () {
            const ok = await confirmDialog("Видалити подію «" + event.title + "»?");
            if (!ok) return;
            setBusy(buttons, true);
            try {
                await planning.deleteEvent(params.eventId);
                haptic("success");
                showToast("Подію видалено");
                if (isCurrent(screen)) back("#/plan/" + planId);
            } catch (error) {
                if (!isCurrent(screen)) return;
                showFormError(friendlyError(error));
                setBusy(buttons, false);
            }
        });
    }
}