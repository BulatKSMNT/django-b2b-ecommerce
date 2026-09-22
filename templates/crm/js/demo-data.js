(() => {
    const date = new Date().toISOString().slice(0, 10);

    const employees = [
        { id: 1, name: "Анна Смирнова", available: true, limit: 20 },
        { id: 2, name: "Игорь Соколов", available: false, limit: 20 },
        { id: 3, name: "Дмитрий Ковалёв", available: true, limit: 20 },
        { id: 4, name: "Дмитрий Волков", available: true, limit: 20 }
    ];

    const common = {
        date,
        time: "10:00",
        email: "client@example.com",
        phone: "+7 (000) 000-00-00",
        request: "Просим уточнить стоимость и сроки поставки.",
        next: "",
        nextTime: "",
        items: [],
        comments: [],
        interactions: [],
        history: ["Заявка поступила с сайта"],
        behavior: []
    };

    const leads = [
        {
            id: 1042,
            company: "ООО «СтройКомплект»",
            person: "Алексей Морозов",
            subject: "Кровельные сэндвич-панели",
            source: "cart",
            amount: 3150600,
            status: "in_progress",
            priority: "high",
            score: 82,
            assignee: 1,
            sla: "completed",
            slaText: "Выполнено за 5 мин",
            next: "Перезвонить клиенту",
            nextTime: "15:00",
            request: "Требуется поставка кровельных панелей. Уточните сроки и возможность доставки частями.",
            items: [
                { name: "Сэндвич-панель Минвата 150 мм", price: 2450, quantity: 1200 },
                { name: "Комплект фасонных элементов", price: 185000, quantity: 1 },
                { name: "Саморезы, упаковка", price: 3200, quantity: 8 }
            ],
            comments: [
                { author: "Анна Смирнова", time: "10:10", text: "Клиент ожидает уточнения сроков поставки." }
            ],
            interactions: [
                { channel: "Телефон", result: "Не ответил", time: "10:05", text: "Повторить звонок после обеда." }
            ],
            history: [
                "10:05 — зарегистрирована попытка звонка",
                "10:03 — заявка переведена в работу",
                "10:01 — назначена Анне Смирновой",
                "10:00 — заявка поступила из корзины"
            ],
            behavior: [
                "Просмотр карточки кровельных панелей",
                "Добавление панелей в корзину",
                "Отправка заявки из корзины"
            ]
        },
        {
            id: 1043,
            company: "ООО «РегионМонтаж»",
            person: "Илья Петров",
            subject: "Крепёж для металлоконструкций",
            source: "product",
            amount: 120000,
            status: "assigned",
            priority: "high",
            score: 79,
            assignee: 4,
            sla: "overdue",
            slaText: "Просрочено на 42 мин",
            next: "Уточнить объём",
            nextTime: "16:00"
        },
        {
            id: 1044,
            company: "ООО «МеталлПроект»",
            person: "Мария Иванова",
            subject: "Металлический уголок",
            source: "cart",
            amount: 460000,
            status: "contacted",
            priority: "medium",
            score: 58,
            assignee: 3,
            sla: "completed",
            slaText: "Выполнено",
            next: "Обсудить поставку",
            nextTime: "17:00"
        },
        {
            id: 1045,
            company: "ООО «СеверСтрой»",
            person: "Сергей Орлов",
            subject: "Консультация по кровле",
            source: "contact",
            amount: null,
            status: "new",
            priority: "medium",
            score: null,
            assignee: null,
            sla: "pending",
            slaText: "Осталось 80 мин"
        },
        {
            id: 1046,
            company: "ООО «ФасадГрупп»",
            person: "Ольга Белова",
            subject: "Фасадные кассеты",
            source: "product",
            amount: 850000,
            status: "new",
            priority: "high",
            score: 88,
            assignee: null,
            sla: "overdue",
            slaText: "Просрочено на 6 мин"
        },
        {
            id: 1047,
            company: "ООО «ПромСтрой»",
            person: "Андрей Волков",
            subject: "Доборные элементы",
            source: "cart",
            amount: 95000,
            status: "qualified",
            priority: "medium",
            score: 62,
            assignee: 2,
            sla: "completed",
            slaText: "Выполнено"
        },
        {
            id: 1048,
            company: "ООО «Монолит»",
            person: "Елена Котова",
            subject: "Профнастил",
            source: "product",
            amount: 210000,
            status: "won",
            priority: "low",
            score: 35,
            assignee: 1,
            sla: "completed",
            slaText: "Выполнено",
            closeComment: "Потребность клиента удовлетворена."
        }
    ].map(item => ({
        ...structuredClone(common),
        ...item
    }));

    window.CRM_DEMO = {
        currentEmployee: 4,
        employees,
        leads,
        notifications: [
            {
                id: 1,
                leadId: 1043,
                title: "Вам назначена заявка",
                text: "Крепёж для металлоконструкций.",
                time: "5 мин назад",
                read: false
            },
            {
                id: 2,
                leadId: 1043,
                title: "Срок первой реакции нарушен",
                text: "Зарегистрируйте попытку связи с клиентом.",
                time: "15 мин назад",
                read: false
            },
            {
                id: 3,
                leadId: 1042,
                title: "Новый комментарий",
                text: "Анна Смирнова уточнила следующий шаг.",
                time: "30 мин назад",
                read: false
            },
            {
                id: 4,
                leadId: null,
                title: "Заявка больше недоступна",
                text: "Доступ к обращению изменён.",
                time: "Вчера",
                read: true
            }
        ]
    };
})();
