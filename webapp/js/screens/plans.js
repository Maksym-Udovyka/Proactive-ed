/* Екрани: список планів і форма плану (створення, редагування, видалення). */

import { planning } from "../api.js";
import { ROLE_LABELS, escapeHtml } from "../format.js";
import {
    ICONS, back, beginScreen, confirmDialog, emptyHtml, friendlyError, go, haptic,
    isCurrent, render, setBusy, setFab, setTitle, showError, showLoading, showToast
} from "../ui.js";

/* ---------- Список планів ---------- */

function planCard(plan) {
    const owner = plan.role === "owner";
    return '<a class="plan-card" href="#/plan/' + plan.plan_id + '">' +
        '<span class="plan-card-title">' + escapeHtml(plan.title) + "</span>" +
        (plan.description
            ? '<span class="plan-card-text">' + escapeHtml(plan.description) + "</span>"
            : "") +
        '<span class="plan-card-meta">' +
        '<span class="badge' + (owner ? " badge-owner" : "") + '">' +
        escapeHtml(ROLE_LABELS[plan.role] || plan.role) + "</span>" +
        "</span></a>";
}

export async function showPlans() {
    const screen = beginScreen();
    setTitle("Навчальні плани");
    showLoading();

    let plans;
    try {
        plans = await planning.listPlans();
    } catch (error) {
        if (!isCurrent(screen)) return;
        showError(friendlyError(error), showPlans);
        return;
    }
    if (!isCurrent(screen)) return;

    if (plans.length === 0) {
        render(emptyHtml(
            ICONS.plans,
            "Планів ще немає",
            "Створіть перший навчальний план, щоб додавати до нього заняття та події.",
            "Створити план"
        ));
        document.getElementById("emptyAction")
            .addEventListener("click", function () { go("#/plan/new"); });
    } else {
        render('<div class="plan-list">' + plans.map(planCard).join("") + "</div>");
    }
    setFab(function () { go("#/plan/new"); }, "Створити план");
}

/* ---------- Форма плану ---------- */

function formHtml(plan, editing) {
    return '<form class="form" id="planForm" novalidate>' +
        '<label class="field-label" for="titleInput">Назва</label>' +
        '<input class="field-input" id="titleInput" type="text" maxlength="200" ' +
        'autocomplete="off" enterkeyhint="next" value="' + escapeHtml(plan.title || "") + '">' +
        '<label class="field-label" for="descInput">Опис</label>' +
        '<textarea class="field-input" id="descInput" maxlength="2000" rows="4">' +
        escapeHtml(plan.description || "") + "</textarea>" +
        '<p class="field-hint">Опис необов\'язковий.</p>' +
        '<p class="field-error" id="formError" role="alert" hidden></p>' +
        '<div class="profile-actions">' +
        '<button class="main-button" id="saveBtn" type="submit">Зберегти</button>' +
        '<button class="secondary-button" id="cancelBtn" type="button">Скасувати</button>' +
        (editing
            ? '<button class="danger-button" id="deleteBtn" type="button">Видалити план</button>'
            : "") +
        "</div></form>";
}

export async function showPlanForm(params) {
    const screen = beginScreen();
    const planId = params && params.planId;
    const editing = !!planId;
    setTitle(editing ? "Редагування плану" : "Новий план");

    let plan = {};
    if (editing) {
        showLoading();
        try {
            plan = await planning.getPlan(planId);
        } catch (error) {
            if (!isCurrent(screen)) return;
            showError(friendlyError(error), function () { showPlanForm(params); });
            return;
        }
        if (!isCurrent(screen)) return;
        if (plan.role !== "owner") {
            render(emptyHtml(ICONS.alert, "Недостатньо прав", "Змінювати план може лише його власник."));
            return;
        }
    }

    render(formHtml(plan, editing));

    const form = document.getElementById("planForm");
    const titleInput = document.getElementById("titleInput");
    const descInput = document.getElementById("descInput");
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

    cancelBtn.addEventListener("click", function () {
        back(editing ? "#/plan/" + planId : "#/");
    });

    form.addEventListener("submit", async function (event) {
        event.preventDefault();
        formError.hidden = true;

        const title = titleInput.value.trim();
        if (!title) {
            showFormError("Введіть назву плану.");
            titleInput.focus();
            return;
        }
        const payload = { title: title, description: descInput.value.trim() || null };

        setBusy(buttons, true);
        try {
            const saved = editing
                ? await planning.updatePlan(planId, payload)
                : await planning.createPlan(payload);
            haptic("success");
            showToast(editing ? "Зміни збережено" : "План створено");
            if (!isCurrent(screen)) return;
            if (editing) back("#/plan/" + planId);
            else location.replace("#/plan/" + saved.plan_id);
        } catch (error) {
            if (!isCurrent(screen)) return;
            showFormError(friendlyError(error));
            setBusy(buttons, false);
        }
    });

    if (deleteBtn) {
        deleteBtn.addEventListener("click", async function () {
            const ok = await confirmDialog(
                "Видалити план «" + plan.title + "»? Усі його заняття та події теж буде видалено."
            );
            if (!ok) return;
            setBusy(buttons, true);
            try {
                await planning.deletePlan(planId);
                haptic("success");
                showToast("План видалено");
                if (isCurrent(screen)) location.replace("#/");
            } catch (error) {
                if (!isCurrent(screen)) return;
                showFormError(friendlyError(error));
                setBusy(buttons, false);
            }
        });
    }
}