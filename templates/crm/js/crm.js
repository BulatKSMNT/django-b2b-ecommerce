(() => {
    "use strict";

    const data = window.CRM_DEMO;
    const page = document.body.dataset.page;
    const $ = selector => document.querySelector(selector);
    const $$ = selector => [...document.querySelectorAll(selector)];

    const statusLabels = {
        new: "Новая",
        assigned: "Назначена",
        in_progress: "В работе",
        contacted: "Контакт установлен",
        qualified: "Квалифицирована",
        won: "Успешно закрыта",
        lost: "Закрыта без результата"
    };

    const priorityLabels = {
        high: "Высокий",
        medium: "Средний",
        low: "Низкий"
    };

    const sourceLabels = {
        cart: "Из корзины",
        product: "Карточка товара",
        contact: "Контактная форма"
    };

    const money = value => value == null
        ? "Не указана"
        : new Intl.NumberFormat("ru-RU", {
            style: "currency",
            currency: "RUB",
            maximumFractionDigits: 0
        }).format(value);

    const escape = value => String(value ?? "").replace(
        /[&<>"']/g,
        char => ({
            "&": "&amp;",
            "<": "&lt;",
            ">": "&gt;",
            '"': "&quot;",
            "'": "&#39;"
        })[char]
    );

    const isClosed = lead => ["won", "lost"].includes(lead.status);
    const employee = id => data.employees.find(item => item.id === id);
    const assigneeName = lead => employee(lead.assignee)?.name || "Не назначен";
    const dateLabel = lead => `${lead.date.split("-").reverse().join(".")} ${lead.time}`;
    const leadUrl = id => `/crm/leads/${id}/`;

    function statusBadge(lead) {
        const color = {
            new: "neutral",
            assigned: "amber",
            in_progress: "blue",
            contacted: "green",
            qualified: "green",
            won: "green",
            lost: "red"
        }[lead.status];

        return `<span class="badge badge-${color}">
            ${statusLabels[lead.status]}
        </span>`;
    }

    function priorityBadge(lead) {
        const color = { high: "red", medium: "amber", low: "neutral" }[lead.priority];
        return `<span class="badge badge-${color}">
            ${priorityLabels[lead.priority]}
        </span>`;
    }

    function scoreLabel(lead) {
        return lead.score == null ? "Расчёт ожидается" : `${lead.score}/100`;
    }

    function slaLabel(lead) {
        const color = lead.sla === "overdue"
            ? "text-red-700"
            : lead.sla === "completed"
                ? "text-primary"
                : "text-amber-700";

        return `<span class="text-xs font-medium ${color}">
            ${escape(lead.slaText)}
        </span>`;
    }

    let toastTimer;

    function toast(message) {
        const element = $("#toast");
        clearTimeout(toastTimer);
        element.textContent = message;
        element.hidden = false;
        toastTimer = setTimeout(() => element.hidden = true, 4000);
    }

    function updateUnread() {
        const count = data.notifications.filter(item => !item.read).length;
        $("#header-unread").textContent = count;
        $("#header-unread").hidden = count === 0;
    }

    function initShell() {
        const activePage = page === "lead_detail" ? "lead_list" : page;
        const activeLink = $(`[data-nav="${activePage}"]`);

        if (activeLink) {
            activeLink.classList.add("is-active");
            activeLink.setAttribute("aria-current", "page");
        }

        const sidebar = $("#crm-sidebar");
        const overlay = $("#sidebar-overlay");

        function setMenu(open) {
            sidebar.classList.toggle("is-open", open);
            overlay.hidden = !open;
            $("#sidebar-open").setAttribute("aria-expanded", String(open));
        }

        $("#sidebar-open").addEventListener("click", () => setMenu(true));
        $("#sidebar-close").addEventListener("click", () => setMenu(false));
        overlay.addEventListener("click", () => setMenu(false));

        document.addEventListener("keydown", event => {
            if (event.key === "Escape") setMenu(false);
        });

        matchMedia("(min-width: 768px)").addEventListener("change", event => {
            if (event.matches) setMenu(false);
        });

        $$("[data-refresh]").forEach(button => {
            button.addEventListener("click", () => {
                toast("Демо: подключение обновления через API пока отсутствует.");
            });
        });

        updateUnread();
    }

    function initDashboard() {
        const open = data.leads.filter(lead => !isClosed(lead));
        const actions = open.filter(lead => lead.next);

        $("#current-date").textContent = new Date().toLocaleDateString("ru-RU");
        $("#kpi-open").textContent = open.length;
        $("#kpi-pending").textContent = open.filter(l => l.sla !== "completed").length;
        $("#kpi-overdue").textContent = open.filter(l => l.sla === "overdue").length;
        $("#kpi-actions").textContent = actions.length;

        $("#dashboard-rows").innerHTML = open
            .filter(lead => lead.sla !== "completed")
            .map(lead => `
                <tr>
                    <td>
                        <a class="text-link" href="${leadUrl(lead.id)}">
                            №${lead.id}
                        </a>
                        <p class="font-semibold mt-1">${escape(lead.company)}</p>
                    </td>
                    <td>${statusBadge(lead)}</td>
                    <td>${priorityBadge(lead)}</td>
                    <td>${slaLabel(lead)}</td>
                </tr>
            `).join("");

        $("#dashboard-actions").innerHTML = actions.map(lead => `
            <a href="${leadUrl(lead.id)}" class="info-box block">
                <div class="flex justify-between gap-2 text-xs">
                    <strong class="text-primary">${escape(lead.nextTime)}</strong>
                    <span class="text-muted">№${lead.id}</span>
                </div>
                <p class="font-semibold text-sm mt-2">${escape(lead.company)}</p>
                <p class="text-xs text-muted mt-2">${escape(lead.next)}</p>
            </a>
        `).join("");
    }

    function initLeadList() {
        let activeTab = "all";
        let currentPage = 1;
        const quick = new Set();

        $("#lead-status").insertAdjacentHTML("beforeend",
            Object.entries(statusLabels).map(([key, label]) =>
                `<option value="${key}">${label}</option>`
            ).join("")
        );

        $("#lead-assignee").insertAdjacentHTML("beforeend",
            data.employees.map(item =>
                `<option value="${item.id}">${escape(item.name)}</option>`
            ).join("")
        );

        const query = new URLSearchParams(location.search);
        if (query.has("assigned_to")) {
            $("#lead-assignee").value = query.get("assigned_to");
        }
        if (query.get("sla") === "overdue") {
            quick.add("overdue");
        }

        function render() {
            const text = $("#lead-search").value.trim().toLowerCase();
            const status = $("#lead-status").value;
            const priority = $("#lead-priority").value;
            const responsible = $("#lead-assignee").value;
            const source = $("#lead-source").value;
            const from = $("#lead-date-from").value;
            const to = $("#lead-date-to").value;

            const filtered = data.leads.filter(lead => {
                if (activeTab === "closed" ? !isClosed(lead) : isClosed(lead)) return false;
                if (activeTab === "mine" && lead.assignee !== data.currentEmployee) return false;
                if (status && lead.status !== status) return false;
                if (priority && lead.priority !== priority) return false;
                if (responsible && lead.assignee !== Number(responsible)) return false;
                if (source && lead.source !== source) return false;
                if (from && lead.date < from) return false;
                if (to && lead.date > to) return false;
                if (quick.has("overdue") && lead.sla !== "overdue") return false;
                if (quick.has("high") && lead.priority !== "high") return false;
                if (quick.has("today") && !lead.next) return false;
                if (query.get("reaction") === "pending" && lead.sla === "completed") return false;

                return !text || [
                    lead.id, lead.company, lead.person, lead.email, lead.phone
                ].join(" ").toLowerCase().includes(text);
            });

            const size = Number($("#lead-page-size").value);
            const pages = Math.max(1, Math.ceil(filtered.length / size));
            currentPage = Math.min(currentPage, pages);
            const start = (currentPage - 1) * size;
            const visible = filtered.slice(start, start + size);

            $("#lead-count").textContent = filtered.length;
            $("#lead-empty").hidden = filtered.length > 0;

            $("#lead-rows").innerHTML = visible.map(lead => `
                <tr>
                    <td class="whitespace-nowrap">
                        <a href="${leadUrl(lead.id)}" class="text-link">№${lead.id}</a>
                        <p class="text-xs text-muted mt-1">${dateLabel(lead)}</p>
                    </td>
                    <td>
                        <p class="font-semibold">${escape(lead.company)}</p>
                        <p class="text-xs text-muted mt-1">${escape(lead.person)}</p>
                    </td>
                    <td>${statusBadge(lead)}</td>
                    <td>
                        ${priorityBadge(lead)}
                        <p class="text-xs text-muted mt-1">${scoreLabel(lead)}</p>
                    </td>
                    <td class="whitespace-nowrap">${money(lead.amount)}</td>
                    <td>${slaLabel(lead)}</td>
                    <td>${escape(assigneeName(lead))}</td>
                </tr>
            `).join("");

            $("#lead-mobile").innerHTML = visible.map(lead => `
                <article class="mobile-card">
                    <div class="flex justify-between items-center gap-2">
                        <a href="${leadUrl(lead.id)}" class="text-link">№${lead.id}</a>
                        ${priorityBadge(lead)}
                    </div>
                    <p class="font-semibold text-sm mt-3">${escape(lead.company)}</p>
                    <p class="text-xs text-muted mt-1">${escape(lead.subject)}</p>
                    <div class="flex flex-wrap justify-between gap-2 mt-3">
                        ${statusBadge(lead)}
                        ${slaLabel(lead)}
                    </div>
                </article>
            `).join("");

            $("#lead-summary").textContent = filtered.length
                ? `${start + 1}–${start + visible.length} из ${filtered.length}`
                : "0 результатов";

            $("#lead-page").textContent = `${currentPage} / ${pages}`;
            $("#lead-prev").disabled = currentPage === 1;
            $("#lead-next").disabled = currentPage === pages;

            $$("[data-quick]").forEach(button => {
                const active = quick.has(button.dataset.quick);
                button.classList.toggle("is-active", active);
                button.setAttribute("aria-pressed", String(active));
            });
        }

        [
            "#lead-search", "#lead-status", "#lead-priority",
            "#lead-assignee", "#lead-source", "#lead-date-from",
            "#lead-date-to", "#lead-page-size"
        ].forEach(selector => {
            $(selector).addEventListener("input", () => {
                currentPage = 1;
                render();
            });
        });

        $$("[data-list-tab]").forEach(button => {
            button.addEventListener("click", () => {
                activeTab = button.dataset.listTab;
                currentPage = 1;
                $$("[data-list-tab]").forEach(item => {
                    item.classList.toggle("is-active", item === button);
                });
                render();
            });
        });

        $$("[data-quick]").forEach(button => {
            button.addEventListener("click", () => {
                const key = button.dataset.quick;
                quick.has(key) ? quick.delete(key) : quick.add(key);
                currentPage = 1;
                render();
            });
        });

        $("#lead-prev").onclick = () => { currentPage--; render(); };
        $("#lead-next").onclick = () => { currentPage++; render(); };

        $("#lead-reset").onclick = () => {
            [
                "#lead-search", "#lead-status", "#lead-priority",
                "#lead-assignee", "#lead-source", "#lead-date-from",
                "#lead-date-to"
            ].forEach(selector => $(selector).value = "");

            query.delete("reaction");
            quick.clear();
            currentPage = 1;
            render();
        };

        render();
    }

    function initQueue() {
        function render() {
            const queue = data.leads.filter(lead =>
                lead.assignee === null && lead.status === "new"
            );

            const search = $("#queue-search").value.trim().toLowerCase();
            const priority = $("#queue-priority").value;
            const source = $("#queue-source").value;

            const visible = queue.filter(lead =>
                (!search || `${lead.id} ${lead.subject}`.toLowerCase().includes(search)) &&
                (!priority || lead.priority === priority) &&
                (!source || lead.source === source)
            );

            $("#queue-count").textContent = `${queue.length} неназначенных`;
            $("#queue-empty").hidden = visible.length > 0;
            $("#queue-empty-title").textContent = queue.length
                ? "Ничего не найдено"
                : "Все заявки распределены";
            $("#queue-empty-text").textContent = queue.length
                ? "Измени параметры поиска."
                : "Новые обращения появятся здесь.";

            const button = lead => `
                <button type="button" class="btn btn-primary"
                        data-claim="${lead.id}">Взять</button>
            `;

            $("#queue-rows").innerHTML = visible.map(lead => `
                <tr>
                    <td>
                        <strong>№${lead.id}</strong>
                        <p class="text-xs text-muted mt-1">${dateLabel(lead)}</p>
                    </td>
                    <td>${escape(lead.subject)}</td>
                    <td>${sourceLabels[lead.source]}</td>
                    <td class="whitespace-nowrap">${money(lead.amount)}</td>
                    <td>
                        ${priorityBadge(lead)}
                        <p class="text-xs text-muted mt-1">${scoreLabel(lead)}</p>
                    </td>
                    <td>${slaLabel(lead)}</td>
                    <td>${button(lead)}</td>
                </tr>
            `).join("");

            $("#queue-mobile").innerHTML = visible.map(lead => `
                <article class="mobile-card">
                    <div class="flex justify-between gap-2">
                        <strong class="text-sm">№${lead.id}</strong>
                        ${priorityBadge(lead)}
                    </div>
                    <p class="text-sm font-semibold mt-3">${escape(lead.subject)}</p>
                    <p class="text-xs text-muted mt-2">${sourceLabels[lead.source]}</p>
                    <div class="flex justify-between items-center gap-3 mt-4">
                        ${slaLabel(lead)}
                        ${button(lead)}
                    </div>
                </article>
            `).join("");
        }

        ["#queue-search", "#queue-priority", "#queue-source"].forEach(selector => {
            $(selector).addEventListener("input", render);
        });

        document.addEventListener("click", event => {
            const button = event.target.closest("[data-claim]");
            if (!button) return;

            const lead = data.leads.find(item => item.id === Number(button.dataset.claim));
            if (!lead || lead.assignee !== null) {
                toast("Заявка уже назначена.");
                return;
            }

            lead.assignee = data.currentEmployee;
            lead.status = "assigned";
            render();
            toast("Демо: заявка назначена вам. После перезагрузки изменения сбросятся.");
        });

        render();
    }

    function initTeam() {
        function render() {
            const search = $("#team-search").value.trim().toLowerCase();
            const status = $("#team-status").value;

            const visible = data.employees.filter(item =>
                (!search || item.name.toLowerCase().includes(search)) &&
                (!status || item.available === (status === "available"))
            );

            const view = item => {
                const leads = data.leads.filter(lead =>
                    lead.assignee === item.id && !isClosed(lead)
                );
                return {
                    ...item,
                    open: leads.length,
                    overdue: leads.filter(l => l.sla === "overdue").length,
                    actions: leads.filter(l => l.next).length
                };
            };

            const availability = item => `
                <span class="badge badge-${item.available ? "green" : "neutral"}">
                    ${item.available ? "Принимает заявки" : "Недоступен"}
                </span>
            `;

            $("#team-rows").innerHTML = visible.map(view).map(item => `
                <tr>
                    <td class="font-semibold">${escape(item.name)}</td>
                    <td>${availability(item)}</td>
                    <td>
                        <p class="text-xs mb-2">${item.open} из ${item.limit}</p>
                        <div class="progress-track">
                            <div class="progress-fill"
                                 style="width:${Math.min(100, item.open / item.limit * 100)}%">
                            </div>
                        </div>
                    </td>
                    <td class="${item.overdue ? "text-red-700 font-semibold" : ""}">
                        ${item.overdue}
                    </td>
                    <td>${item.actions}</td>
                    <td>
                        <a class="text-link" href="/crm/leads/?assigned_to=${item.id}">
                            Заявки сотрудника
                        </a>
                    </td>
                </tr>
            `).join("");

            $("#team-mobile").innerHTML = visible.map(view).map(item => `
                <article class="mobile-card">
                    <p class="font-semibold text-sm mb-2">${escape(item.name)}</p>
                    ${availability(item)}
                    <p class="text-xs text-muted mt-3">
                        Открыто: ${item.open} из ${item.limit} · Просрочено: ${item.overdue}
                    </p>
                    <a class="text-link inline-block mt-3"
                       href="/crm/leads/?assigned_to=${item.id}">
                        Заявки сотрудника
                    </a>
                </article>
            `).join("");

            $("#team-empty").hidden = visible.length > 0;
        }

        $("#team-search").addEventListener("input", render);
        $("#team-status").addEventListener("change", render);
        render();
    }

    let detailLead;

    function initDetail() {
        const id = Number(location.pathname.match(/\/leads\/(\d+)\/?$/)?.[1] || 1042);
        detailLead = data.leads.find(item => item.id === id);

        if (!detailLead) {
            $(".crm-content").innerHTML = `
                <section class="panel empty-state">
                    <h1>Заявка не найдена</h1>
                    <p>Такой заявки нет в демонстрационном наборе.</p>
                    <a href="/crm/leads/" class="text-link inline-block mt-4">К списку</a>
                </section>
            `;
            return;
        }

        $$("[data-detail-tab]").forEach(button => {
            button.onclick = () => {
                $$("[data-detail-tab]").forEach(item => {
                    item.classList.toggle("is-active", item === button);
                });
                $$("[data-detail-panel]").forEach(panel => {
                    panel.hidden = panel.dataset.detailPanel !== button.dataset.detailTab;
                });
            };
        });

        $("#comment-body").addEventListener("input", event => {
            $("#comment-counter").textContent = `${event.target.value.length} / 5000`;
        });

        $("#comment-form").addEventListener("submit", event => {
            event.preventDefault();
            const text = $("#comment-body").value.trim();
            if (!text) return;

            detailLead.comments.unshift({
                author: employee(data.currentEmployee).name,
                time: "Только что",
                text
            });
            detailLead.history.unshift("Добавлен внутренний комментарий");
            $("#comment-body").value = "";
            $("#comment-counter").textContent = "0 / 5000";
            renderDetail();
            toast("Демо: комментарий добавлен только в текущую страницу.");
        });

        $("#copy-phone").onclick = () => copy(detailLead.phone);
        $("#copy-email").onclick = () => copy(detailLead.email);

        renderDetail();
    }

    async function copy(value) {
        try {
            await navigator.clipboard.writeText(value);
            toast("Скопировано.");
        } catch {
            toast("Не удалось скопировать. Выдели текст вручную.");
        }
    }

    function renderDetail() {
        const lead = detailLead;
        const closed = isClosed(lead);

        $("#detail-title").textContent = `Заявка №${lead.id}`;
        $("#detail-status").innerHTML = statusBadge(lead);
        $("#detail-meta").textContent = `${dateLabel(lead)} · ${sourceLabels[lead.source]}`;
        $("#detail-company").textContent = lead.company;
        $("#detail-person").textContent = lead.person;
        $("#detail-phone").textContent = lead.phone;
        $("#detail-email").textContent = lead.email;
        $("#detail-request").textContent = lead.request;
        $("#detail-total").textContent = money(lead.amount);
        $("#detail-assignee").textContent = assigneeName(lead);

        $("#detail-items").innerHTML = lead.items.map(item => `
            <tr>
                <td>${escape(item.name)}</td>
                <td class="whitespace-nowrap">${money(item.price)}</td>
                <td>${item.quantity}</td>
                <td class="whitespace-nowrap">${money(item.price * item.quantity)}</td>
            </tr>
        `).join("");
        $("#detail-items-empty").hidden = lead.items.length > 0;

        $("#detail-priority").innerHTML = priorityBadge(lead);
        $("#detail-score").textContent = lead.score == null ? "Ожидается" : `${lead.score} / 100`;
        $("#detail-score-bar").style.width = `${lead.score ?? 0}%`;
        $("#detail-score-meta").textContent = lead.score == null
            ? "Результат расчёта пока отсутствует"
            : "Эвристическая оценка · демонстрационный результат";
        $("#detail-score-factors").hidden = lead.score == null;
        $("#detail-factors").innerHTML = [
            "Источник обращения",
            "Состав и сумма заявки",
            "Доступная активность посетителя"
        ].map(text => `<li>${text}</li>`).join("");

        $("#detail-reaction").innerHTML = slaLabel(lead);
        $("#detail-resolution").textContent = closed
            ? "Цикл завершён"
            : "72 часа от открытия цикла · демо";

        $("#detail-next-action").textContent = lead.next
            ? `${lead.next} · ${lead.nextTime}`
            : "Не запланировано";

        $("#detail-closed").hidden = !closed;
        $("#detail-closed").textContent = lead.closeComment || "Цикл обработки завершён.";
        $("#next-action-button").hidden = closed;
        $("#assignee-button").hidden = closed;
        $("#interaction-add-button").hidden = closed || lead.status === "new";
        $("#assignee-button").dataset.dialog = lead.assignee == null ? "assign" : "reassign";
        $("#assignee-button").textContent = lead.assignee == null ? "Назначить" : "Переназначить";

        let actions = [];

        if (closed) {
            actions.push(["reopen", "Открыть повторно"]);
        } else {
            if (lead.status === "new") actions.push(["assign", "Назначить"]);
            if (lead.status === "assigned") actions.push(["start", "Начать обработку"]);
            if (lead.status !== "new") actions.push(["interaction", "Зарегистрировать контакт"]);
            if (lead.status === "contacted") actions.push(["qualify", "Квалифицировать"]);
            if (lead.status === "qualified") actions.push(["close_won", "Закрыть успешно"]);
            actions.push(["close_lost", "Закрыть без результата"]);
        }

        $("#detail-actions").innerHTML = actions.map(([key, label], index) => `
            <button class="btn ${index === 0 ? "btn-primary" : "btn-secondary"}"
                    type="button" data-dialog="${key}">
                ${label}
            </button>
        `).join("");

        $("#detail-timeline").innerHTML = lead.history.map(text => `
            <div class="timeline-event">
                <p class="text-sm">${escape(text)}</p>
            </div>
        `).join("");

        $("#detail-comments").innerHTML = lead.comments.length
            ? lead.comments.map(comment => `
                <article class="info-box">
                    <div class="flex justify-between gap-2 text-xs mb-3">
                        <strong>${escape(comment.author)}</strong>
                        <span class="text-muted">${escape(comment.time)}</span>
                    </div>
                    <p class="text-sm whitespace-pre-wrap">${escape(comment.text)}</p>
                </article>
            `).join("")
            : '<p class="text-sm text-muted">Комментариев пока нет.</p>';

        $("#detail-interactions").innerHTML = lead.interactions.length
            ? lead.interactions.map(item => `
                <article class="info-box">
                    <p class="font-semibold text-sm">
                        ${escape(item.channel)} · ${escape(item.result)}
                    </p>
                    <p class="text-xs text-muted mt-1">${escape(item.time)}</p>
                    <p class="text-sm mt-3">${escape(item.text)}</p>
                </article>
            `).join("")
            : '<p class="text-sm text-muted">Контакты ещё не зарегистрированы.</p>';

        $("#behavior-source").textContent = `Источник заявки: ${sourceLabels[lead.source]}`;
        $("#detail-behavior").innerHTML = lead.behavior.length
            ? lead.behavior.map(text => `<p class="info-box text-sm">${escape(text)}</p>`).join("")
            : '<p class="text-sm text-muted">История посещений не связана с этой заявкой.</p>';
    }

    function initNotifications() {
        let filter = "all";

        function render() {
            const unread = data.notifications.filter(item => !item.read).length;
            const visible = data.notifications.filter(item => filter !== "unread" || !item.read);

            $("#notifications-count").textContent = `${unread} новых`;
            $("#read-all").disabled = unread === 0;
            $("#notifications-empty").hidden = visible.length > 0;
            $("#notifications-empty-title").textContent = filter === "unread"
                ? "Все уведомления прочитаны"
                : "Нет уведомлений";

            $("#notifications-list").innerHTML = visible.map(item => `
                <article class="notification-row ${item.read ? "" : "is-unread"}">
                    <div class="min-w-0">
                        <p class="text-sm font-semibold">${escape(item.title)}</p>
                        <p class="text-xs text-muted mt-2">${escape(item.text)}</p>
                        <div class="flex flex-wrap gap-3 mt-3">
                            <span class="text-xs text-muted">${escape(item.time)}</span>
                            ${item.leadId ? `
                                <a href="${leadUrl(item.leadId)}" class="text-link">
                                    Заявка №${item.leadId}
                                </a>
                            ` : ""}
                        </div>
                    </div>
                    ${!item.read ? `
                        <button type="button" class="icon-button shrink-0"
                                data-read="${item.id}" aria-label="Отметить прочитанным">
                            <span class="material-symbols-outlined">done</span>
                        </button>
                    ` : ""}
                </article>
            `).join("");

            updateUnread();
        }

        $$("[data-notification-filter]").forEach(button => {
            button.onclick = () => {
                filter = button.dataset.notificationFilter;
                $$("[data-notification-filter]").forEach(item => {
                    item.classList.toggle("is-active", item === button);
                });
                render();
            };
        });

        $("#read-all").onclick = () => {
            data.notifications.forEach(item => item.read = true);
            render();
        };

        $("#notifications-list").onclick = event => {
            const button = event.target.closest("[data-read]");
            if (!button) return;
            data.notifications.find(item => item.id === Number(button.dataset.read)).read = true;
            render();
        };

        render();
    }

    function initSLA() {
        const form = $("#sla-form");
        let version = 1;
        let saved = Object.fromEntries(new FormData(form));

        $("#sla-reset").onclick = () => {
            Object.entries(saved).forEach(([key, value]) => {
                form.elements.namedItem(key).value = value;
            });
            $("#sla-error").hidden = true;
        };

        form.addEventListener("submit", event => {
            event.preventDefault();

            const values = Object.fromEntries(
                [...new FormData(form)].map(([key, value]) => [key, Number(value)])
            );

            const error = $("#sla-error");
            const valid = Object.values(values).every(value =>
                Number.isInteger(value) && value > 0
            );

            if (!valid || values.warning >= Math.min(
                values.high, values.medium, values.low, values.resolution * 60
            )) {
                error.textContent = "Укажи положительные целые значения. Предупреждение должно быть раньше самого короткого срока.";
                error.hidden = false;
                return;
            }

            error.hidden = true;
            saved = values;
            version++;
            $("#sla-version").textContent = `Демонстрационная версия: ${version}`;
            toast("Демо: новая версия сохранена только до перезагрузки страницы.");
        });
    }

    function initDialogs() {
        const dialog = $("#action-dialog");
        const form = $("#action-form");
        let action = "";
        let initialState = "";

        const serialize = () => JSON.stringify([...new FormData(form)]);

        const select = (name, label, options) => `
            <div>
                <label class="field-label" for="dialog-${name}">${label}</label>
                <select id="dialog-${name}" name="${name}" class="field" required>
                    ${options.map(([value, text]) =>
                        `<option value="${escape(value)}">${escape(text)}</option>`
                    ).join("")}
                </select>
            </div>
        `;

        const textarea = (name, label) => `
            <div>
                <label class="field-label" for="dialog-${name}">${label}</label>
                <textarea id="dialog-${name}" name="${name}" class="field"
                          rows="3" maxlength="5000" required></textarea>
            </div>
        `;

        const input = (name, label, type = "text") => `
            <div>
                <label class="field-label" for="dialog-${name}">${label}</label>
                <input id="dialog-${name}" name="${name}" type="${type}"
                       class="field" required>
            </div>
        `;

        const employees = () => [
            ["", "Выберите сотрудника"],
            ...data.employees.filter(item => item.available).map(item => [item.id, item.name])
        ];

        function close() {
            if (serialize() !== initialState &&
                !confirm("Закрыть форму без сохранения изменений?")) {
                return;
            }
            dialog.close();
        }

        $$("[data-dialog-close]").forEach(button => button.onclick = close);
        dialog.addEventListener("cancel", event => {
            event.preventDefault();
            close();
        });

        document.addEventListener("click", event => {
            const button = event.target.closest("[data-dialog]");
            if (!button || !detailLead) return;

            action = button.dataset.dialog;

            if (action === "start") {
                detailLead.status = "in_progress";
                detailLead.history.unshift("Начата обработка заявки");
                renderDetail();
                toast("Демо: статус изменён.");
                return;
            }

            const config = {
                assign: {
                    title: "Назначить ответственного",
                    fields: select("assignee", "Ответственный", employees()),
                    hint: "Сроки обработки не изменятся."
                },
                reassign: {
                    title: "Переназначить заявку",
                    fields: select("assignee", "Новый ответственный", employees()) +
                        textarea("comment", "Причина переназначения"),
                    hint: "История и текущие сроки сохранятся."
                },
                interaction: {
                    title: "Зарегистрировать контакт",
                    fields:
                        select("channel", "Канал", [
                            ["phone", "Телефон"], ["email", "Email"],
                            ["messenger", "Мессенджер"], ["meeting", "Встреча"],
                            ["other", "Другое"]
                        ]) +
                        select("direction", "Направление", [
                            ["outgoing", "Исходящий"], ["incoming", "Входящий"]
                        ]) +
                        select("outcome", "Результат", [
                            ["successful", "Успешный контакт"],
                            ["no_answer", "Не ответил"],
                            ["message_sent", "Сообщение отправлено"],
                            ["failed", "Не удалось выполнить"]
                        ]) +
                        input("occurred_at", "Дата и время", "datetime-local") +
                        textarea("comment", "Содержание взаимодействия"),
                    hint: "Запись вносится вручную. Звонок или отправка письма не выполняются."
                },
                qualify: {
                    title: "Квалифицировать заявку",
                    fields: textarea("comment", "Подтверждённая потребность"),
                    hint: "Зафиксируйте потребность клиента."
                },
                close_won: {
                    title: "Закрыть успешно",
                    fields: textarea("comment", "Итог обработки"),
                    hint: "Успешное закрытие не означает автоматическую оплату."
                },
                close_lost: {
                    title: "Закрыть без результата",
                    fields: select("reason", "Причина", [
                        ["", "Выберите причину"],
                        ["no_response", "Не удалось связаться"],
                        ["not_interested", "Не заинтересован"],
                        ["price", "Цена"],
                        ["delivery_terms", "Сроки"],
                        ["out_of_stock", "Нет продукции"],
                        ["duplicate", "Дубль"],
                        ["spam", "Спам"],
                        ["other", "Другое"]
                    ]) +
                    '<div id="duplicate-field" hidden>' +
                    '<label class="field-label" for="dialog-duplicate">Номер основной заявки</label>' +
                    '<input id="dialog-duplicate" class="field" type="number" min="1" name="duplicate">' +
                    '</div>' +
                    textarea("comment", "Пояснение"),
                    hint: "Причина и результат сохранятся в истории."
                },
                next_action: {
                    title: "Следующее действие",
                    fields: input("description", "Что необходимо сделать") +
                        input("scheduled_at", "Дата и время", "datetime-local"),
                    hint: "Напоминание не изменяет сроки SLA."
                },
                reopen: {
                    title: "Открыть повторно",
                    fields: textarea("comment", "Причина повторного открытия") +
                        select("assignee", "Ответственный", employees()),
                    hint: "Будет создан новый цикл. Предыдущая история сохранится."
                }
            }[action];

            if (!config) return;

            $("#dialog-title").textContent = config.title;
            $("#dialog-fields").innerHTML = config.fields;
            $("#dialog-hint").textContent = config.hint;
            $("#dialog-error").hidden = true;
            $("#dialog-submit").className = `btn ${
                action === "close_lost" ? "btn-danger" : "btn-primary"
            }`;

            initialState = serialize();
            dialog.showModal();
        });

        form.addEventListener("change", event => {
            if (event.target.name !== "reason") return;
            const duplicate = event.target.value === "duplicate";
            $("#duplicate-field").hidden = !duplicate;
            $("#dialog-duplicate").required = duplicate;
        });

        form.addEventListener("submit", event => {
            event.preventDefault();
            if (!detailLead) return;

            const values = Object.fromEntries(new FormData(form));
            const error = $("#dialog-error");

            if ([...form.querySelectorAll("[required]")].some(
                field => !field.value.trim()
            )) {
                error.textContent = "Заполните обязательные поля.";
                error.hidden = false;
                return;
            }

            if (action === "interaction" &&
                new Date(values.occurred_at).getTime() > Date.now()) {
                error.textContent = "Контакт не может быть зарегистрирован будущим временем.";
                error.hidden = false;
                return;
            }

            if (action === "next_action" &&
                new Date(values.scheduled_at).getTime() <= Date.now()) {
                error.textContent = "Выберите будущее время.";
                error.hidden = false;
                return;
            }

            const lead = detailLead;

            if (["assign", "reassign", "reopen"].includes(action)) {
                lead.assignee = Number(values.assignee);
                if (lead.status === "new" || action === "reopen") {
                    lead.status = "assigned";
                }
            }

            if (action === "interaction") {
                const label = name =>
                    form.elements.namedItem(name).selectedOptions[0].textContent;

                lead.interactions.unshift({
                    channel: `${label("channel")} · ${label("direction")}`,
                    result: label("outcome"),
                    time: new Date(values.occurred_at).toLocaleString("ru-RU"),
                    text: values.comment
                });

                if (values.direction === "outgoing" &&
                    values.outcome !== "failed" &&
                    lead.sla !== "completed") {
                    lead.slaText = lead.sla === "overdue"
                        ? "Выполнено с опозданием"
                        : "Выполнено";
                    lead.sla = "completed";
                }

                if (values.outcome === "successful" &&
                    ["assigned", "in_progress"].includes(lead.status)) {
                    lead.status = "contacted";
                }
            }

            if (action === "qualify") lead.status = "qualified";

            if (action === "close_won" || action === "close_lost") {
                lead.status = action === "close_won" ? "won" : "lost";
                lead.closeComment = values.comment;
            }

            if (action === "reopen") {
                lead.sla = "pending";
                lead.slaText = "Новый цикл · ожидает первой реакции";
                lead.next = "";
                lead.nextTime = "";
            }

            if (action === "next_action") {
                lead.next = values.description;
                lead.nextTime = new Date(values.scheduled_at).toLocaleString("ru-RU");
            }

            lead.history.unshift(
                `${$("#dialog-title").textContent}${values.comment ? ": " + values.comment : ""}`
            );

            dialog.close();
            renderDetail();
            toast("Демо: действие выполнено локально, без сохранения на сервере.");
        });
    }

    initShell();
    initDialogs();

    ({
        dashboard: initDashboard,
        lead_list: initLeadList,
        queue: initQueue,
        team: initTeam,
        lead_detail: initDetail,
        notifications: initNotifications,
        sla_settings: initSLA
    })[page]?.();
})();
