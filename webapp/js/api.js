/* Запити до сервера: вхід через Telegram і робота з сервісом planning.
   Токен спільний із головною сторінкою (app.js): ключ proactive-ed-token у localStorage. */

const AUTH_API = "/api/auth/v1";
const PLANNING_API = "/api/planning/v1";
const TOKEN_KEY = "proactive-ed-token";

const tg = window.Telegram && window.Telegram.WebApp;

export class ApiError extends Error {
    constructor(status, message) {
        super(message);
        this.status = status;
    }
}

export function isInTelegram() {
    return !!(tg && tg.initData);
}

function readToken() {
    try { return localStorage.getItem(TOKEN_KEY); } catch { return null; }
}

function saveToken(value) {
    try { localStorage.setItem(TOKEN_KEY, value); } catch { /* сховище недоступне */ }
}

let token = readToken();
let loginPromise = null;

async function readJson(res) {
    try { return await res.json(); } catch { return {}; }
}

/* Вхід через initData. Паралельні виклики об'єднуються в один запит. */
export function login() {
    if (!isInTelegram()) {
        return Promise.reject(new ApiError(0, "Відкрийте застосунок у Telegram"));
    }
    if (!loginPromise) {
        loginPromise = (async () => {
            let res;
            try {
                res = await fetch(AUTH_API + "/telegram-login", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json",
                        "ngrok-skip-browser-warning": "true"
                    },
                    body: JSON.stringify({ initData: tg.initData })
                });
            } catch {
                throw new ApiError(0, "Немає зв'язку з сервером");
            }
            const data = await readJson(res);
            if (!res.ok || !data.token) {
                throw new ApiError(res.status, data.error || "Помилка входу (" + res.status + ")");
            }
            token = data.token;
            saveToken(token);
            return token;
        })().finally(() => { loginPromise = null; });
    }
    return loginPromise;
}

async function request(method, path, body, retry = true) {
    if (!token) await login();

    let res;
    try {
        const headers = {
            "Authorization": "Bearer " + token,
            "ngrok-skip-browser-warning": "true"
        };
        if (body !== undefined) headers["Content-Type"] = "application/json";
        res = await fetch(PLANNING_API + path, {
            method,
            headers,
            body: body !== undefined ? JSON.stringify(body) : undefined
        });
    } catch {
        throw new ApiError(0, "Немає зв'язку з сервером");
    }

    // Токен прострочений: входимо ще раз і повторюємо запит один раз
    if (res.status === 401 && retry) {
        token = null;
        await login();
        return request(method, path, body, false);
    }

    if (res.status === 204) return null;

    const data = await readJson(res);
    if (!res.ok) {
        throw new ApiError(res.status, data.error || "Помилка (" + res.status + ")");
    }
    return data;
}

export const planning = {
    /* плани */
    listPlans: () => request("GET", "/plans?limit=100"),
    getPlan: (id) => request("GET", `/plans/${id}`),
    createPlan: (data) => request("POST", "/plans", data),
    updatePlan: (id, data) => request("PATCH", `/plans/${id}`, data),
    deletePlan: (id) => request("DELETE", `/plans/${id}`),
    timeline: (planId) => request("GET", `/plans/${planId}/timeline`),

    /* сесії */
    listSessions: (planId) => request("GET", `/plans/${planId}/sessions`),
    createSession: (planId, data) => request("POST", `/plans/${planId}/sessions`, data),
    getSession: (id) => request("GET", `/sessions/${id}`),
    updateSession: (id, data) => request("PATCH", `/sessions/${id}`, data),
    deleteSession: (id) => request("DELETE", `/sessions/${id}`),

    /* події */
    listEvents: (planId) => request("GET", `/plans/${planId}/events`),
    createEvent: (planId, data) => request("POST", `/plans/${planId}/events`, data),
    getEvent: (id) => request("GET", `/events/${id}`),
    updateEvent: (id, data) => request("PATCH", `/events/${id}`, data),
    deleteEvent: (id) => request("DELETE", `/events/${id}`),

    /* учасники (НОВЕ) */
    listMembers: (planId) => request("GET", `/plans/${planId}/members`),
    updateMemberRole: (planId, userId, role) =>
        request("PATCH", `/plans/${planId}/members/${userId}`, { role: role }),
    removeMember: (planId, userId) =>
        request("DELETE", `/plans/${planId}/members/${userId}`),
    leavePlan: (planId) => request("DELETE", `/plans/${planId}/membership`),

    /* запрошення (НОВЕ) */
    listInvites: (planId) => request("GET", `/plans/${planId}/invites`),
    createInvite: (planId, role) =>
        request("POST", `/plans/${planId}/invites`, { role: role }),
    revokeInvite: (planId, inviteId) =>
        request("DELETE", `/plans/${planId}/invites/${inviteId}`),
    getInvite: (token) => request("GET", `/invites/${encodeURIComponent(token)}`),
    acceptInvite: (token) =>
        request("POST", `/invites/${encodeURIComponent(token)}/accept`)
};