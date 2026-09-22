"""Read models and additional operations for CRM pages; no parallel lead entities."""
from datetime import datetime, time, timedelta

from django.db import transaction
from django.db.models import BigIntegerField, Case, Count, Exists, F, IntegerField, OuterRef, Q, Value, When
from django.utils import timezone

from apps.accounts.access import require_employee, require_supervisor
from apps.accounts.models import EmployeeProfile
from apps.tracking.models import PageVisit, UserEvent
from .access import require_lead_access, visible_leads
from .management_service import (
    CLOSED_STATUSES, allowed_status_transitions, change_status, close_lead,
)
from .models import Lead, LeadComment, LeadHandlingCycle, LeadInteraction, Notification
from .sla import overdue_cycles_filter, warning_cycles_filter


def lead_read_queryset(actor):
    return visible_leads(actor, Lead.objects.all()).select_related(
        "profile", "visitor", "processed_by", "assignee", "score", "scoring_state"
    ).prefetch_related("items", "cycles")


def with_overdue(queryset, now=None):
    now = now or timezone.now()
    cycles = LeadHandlingCycle.objects.filter(lead_id=OuterRef("pk"), ended_at__isnull=True).filter(overdue_cycles_filter(now))
    return queryset.annotate(sla_overdue=Exists(cycles))


def with_warning(queryset, now=None):
    now = now or timezone.now()
    cycles = LeadHandlingCycle.objects.filter(lead_id=OuterRef("pk"), ended_at__isnull=True).filter(warning_cycles_filter(now))
    return queryset.annotate(sla_warning=Exists(cycles))


def with_awaiting_response(queryset):
    cycles = LeadHandlingCycle.objects.filter(
        lead_id=OuterRef("pk"), ended_at__isnull=True, first_response_at__isnull=True,
    )
    return queryset.annotate(awaiting_response=Exists(cycles))


def today_bounds(now):
    day = timezone.localdate(now)
    tz = timezone.get_current_timezone()
    return (timezone.make_aware(datetime.combine(day, time.min), tz),
            timezone.make_aware(datetime.combine(day + timedelta(days=1), time.min), tz))


def attention_filter(now):
    return Q(sla_overdue=True) | Q(sla_warning=True) | (
        ~Q(status__in=CLOSED_STATUSES) & (Q(next_action_at__lte=now) | Q(next_action_remind_at__lte=now))
    )


def notifications_for(actor):
    return Notification.objects.filter(
        recipient=actor, event__lead__in=visible_leads(actor, Lead.objects.all())
    ).select_related("event")


def current_employee(actor):
    role = require_employee(actor)
    employee = EmployeeProfile.objects.filter(user=actor).first()
    return {
        "employee_id": employee.pk if employee else None,
        "user_id": actor.pk, "username": actor.username,
        "first_name": actor.first_name, "last_name": actor.last_name,
        "role": role,
        "is_available": bool(employee and employee.is_active and employee.is_available),
        "permissions": {
            "view_team": role != "manager", "assign_leads": role != "manager",
            "manage_sla": role != "manager", "manage_employees": role == "administrator",
        },
    }


def lead_actions(actor, lead, cycle=None, *, queue=False, employee=None):
    employee = employee or current_employee(actor)
    if not queue:
        require_lead_access(actor, lead)
    else:
        require_employee(actor)
        if lead.status != Lead.Status.NEW or lead.assignee_id:
            return {"claim": False, "assign": False}
    is_open = lead.status not in CLOSED_STATUSES
    actions = {
        "claim": lead.status == Lead.Status.NEW and lead.assignee_id is None and employee["is_available"],
        "assign": is_open and employee["permissions"]["assign_leads"],
    }
    if queue:
        return actions
    transitions = allowed_status_transitions(lead, cycle)
    actions.update(
        transition=bool(transitions), reopen=not is_open,
        add_comment=is_open and cycle is not None,
        register_interaction=is_open and cycle is not None,
        set_next_action=is_open and cycle is not None,
    )
    return actions


def dashboard(actor, *, created_from=None, created_to=None):
    now = timezone.now()
    leads = visible_leads(actor, Lead.objects.all())
    if created_from:
        leads = leads.filter(created_at__gte=created_from)
    if created_to:
        leads = leads.filter(created_at__lte=created_to)
    leads = with_awaiting_response(with_warning(with_overdue(leads, now), now))
    day_start, day_end = today_bounds(now)
    counts = leads.aggregate(
        total=Count("id"), open=Count("id", filter=~Q(status__in=CLOSED_STATUSES)),
        completed=Count("id", filter=Q(status="completed")),
        canceled=Count("id", filter=Q(status="canceled")),
        overdue_count=Count("id", filter=Q(sla_overdue=True)),
        warning_count=Count("id", filter=Q(sla_warning=True)),
        awaiting_count=Count("id", filter=Q(awaiting_response=True)),
        requires_attention=Count("id", filter=attention_filter(now)),
        created_today=Count("id", filter=Q(created_at__gte=day_start, created_at__lt=day_end)),
        next_actions_today=Count("id", filter=Q(next_action_at__gte=day_start, next_action_at__lt=day_end) & ~Q(status__in=CLOSED_STATUSES)),
        next_action_overdue=Count("id", filter=Q(next_action_at__lte=now) & ~Q(status__in=CLOSED_STATUSES)),
        next_action_warning=Count("id", filter=Q(next_action_remind_at__lte=now, next_action_at__gt=now) & ~Q(status__in=CLOSED_STATUSES)),
    )
    counts["sla_overdue"] = counts.pop("overdue_count")
    counts["sla_warning"] = counts.pop("warning_count")
    counts["awaiting_response"] = counts.pop("awaiting_count")
    by_status = dict.fromkeys(Lead.Status.values, 0)
    by_status.update(dict(leads.order_by().values("status").annotate(count=Count("id")).values_list("status", "count")))
    return {
        "generated_at": now, "created_from": created_from, "created_to": created_to,
        "leads": counts, "by_status": by_status,
        "queue_count": Lead.objects.filter(status="new", assignee__isnull=True).count(),
        "unread_notifications": notifications_for(actor).filter(read_at__isnull=True).count(),
    }


def team_queryset(actor):
    require_supervisor(actor)
    now = timezone.now()
    day_start, day_end = today_bounds(now)
    overdue_ids = with_overdue(Lead.objects.all(), now).filter(sla_overdue=True).values("pk")
    warning_ids = with_warning(Lead.objects.all(), now).filter(sla_warning=True).values("pk")
    awaiting_ids = with_awaiting_response(Lead.objects.all()).filter(awaiting_response=True).values("pk")
    return EmployeeProfile.objects.select_related("user").annotate(
        assigned_count=Count("user__assigned_leads"),
        open_count=Count("user__assigned_leads", filter=~Q(user__assigned_leads__status__in=CLOSED_STATUSES)),
        overdue_count=Count("user__assigned_leads", filter=Q(user__assigned_leads__pk__in=overdue_ids)),
        warning_count=Count("user__assigned_leads", filter=Q(user__assigned_leads__pk__in=warning_ids)),
        awaiting_response_count=Count("user__assigned_leads", filter=Q(user__assigned_leads__pk__in=awaiting_ids)),
        due_today_count=Count("user__assigned_leads", filter=Q(
            user__assigned_leads__next_action_at__gte=day_start, user__assigned_leads__next_action_at__lt=day_end,
        ) & ~Q(user__assigned_leads__status__in=CLOSED_STATUSES)),
        next_action_overdue_count=Count("user__assigned_leads", filter=Q(
            user__assigned_leads__next_action_at__lte=now,
        ) & ~Q(user__assigned_leads__status__in=CLOSED_STATUSES)),
    )


def assignable_employees(actor):
    require_supervisor(actor)
    return EmployeeProfile.objects.filter(
        is_active=True, is_available=True, user__is_active=True
    ).select_related("user")


def behavior_queryset(actor, lead, *, kind=None, search=None, created_from=None, created_to=None):
    require_lead_access(actor, lead)
    if lead.profile_id:
        identity = Q(profile_id=lead.profile_id)
    elif lead.visitor_id:
        identity = Q(visitor_id=lead.visitor_id, profile__isnull=True)
    else:
        identity = Q(pk__in=[])
    association = "profile" if lead.profile_id else "visitor"
    window = Q(created_at__gte=lead.created_at - timedelta(days=30), created_at__lte=lead.created_at)
    requested_window = Q()
    if created_from:
        requested_window &= Q(created_at__gte=created_from)
    if created_to:
        requested_window &= Q(created_at__lte=created_to)
    browsing_kinds = ["product_view", "cart_add", "cart_update", "cart_remove", "cart_clear", "favorite_add", "favorite_remove"]
    creation_kinds = ["lead_contact_created", "lead_product_created", "lead_cart_created"]
    # Direct links survive missing visitor/profile and include the submission event.
    # Identity-only activity stays restricted to the original 30-day pre-submission window.
    direct = Q(lead_id=lead.pk, event_type__in=browsing_kinds + creation_kinds, created_at__lte=timezone.now())
    inferred = identity & window & Q(lead__isnull=True, event_type__in=browsing_kinds)
    events = UserEvent.objects.filter(direct | inferred).filter(requested_window).annotate(
               kind=F("event_type"), occurred_at=F("created_at"),
               association=Case(When(lead_id=lead.pk, then=Value("lead")), default=Value(association)),
               product_name=F("product__name"), route_name=Value(""),
               duration_ms=Value(None, output_field=IntegerField()))
    pages = PageVisit.objects.filter(identity, window, requested_window).exclude(
        Q(path__startswith="/admin/") | Q(path__startswith="/api/")
        | Q(path__startswith="/accounts/") | Q(path__startswith="/leads/") | Q(path__startswith="/crm/")
    ).annotate(kind=Value("page_view"), occurred_at=F("created_at"),
               association=Value(association),
               product_id=Value(None, output_field=BigIntegerField()),
               product_name=Value(""))
    if kind:
        pages = pages if kind == "page_view" else pages.none()
        events = events.filter(event_type=kind)
    if search:
        pages = pages.filter(route_name__icontains=search)
        events = events.filter(product__name__icontains=search)
    # Match column order and SQL types for portable UNION pagination.
    fields = ("id", "kind", "occurred_at", "product_id", "product_name", "route_name", "duration_ms", "association")
    return pages.order_by().values(*fields).union(events.order_by().values(*fields), all=True)


def enrich_timeline(events, lead):
    comments = {item.pk: item for item in LeadComment.objects.filter(
        lead=lead, pk__in=[e.data.get("resource_id") for e in events if e.kind == "add_comment"]
    )}
    interactions = {item.pk: item for item in LeadInteraction.objects.filter(
        lead=lead, pk__in=[e.data.get("resource_id") for e in events if e.kind == "register_interaction"]
    )}
    for event in events:
        event.crm_comment = comments.get(event.data.get("resource_id")) if event.kind == "add_comment" else None
        event.crm_interaction = interactions.get(event.data.get("resource_id")) if event.kind == "register_interaction" else None
    return events


def transition_lead(*, status, result=None, **kwargs):
    if status in CLOSED_STATUSES:
        return close_lead(status=status, result=result, **kwargs)
    return change_status(status=status, **kwargs)


@transaction.atomic
def mark_all_notifications_read(actor):
    require_employee(actor)
    # Use the same lock order as lead mutations and single-notification reads.
    lead_ids = list(notifications_for(actor).filter(read_at__isnull=True)
                    .values_list("event__lead_id", flat=True).order_by().distinct())
    leads = Lead.objects.select_for_update().filter(pk__in=lead_ids).order_by("pk")
    list(leads.values_list("pk", flat=True))  # Lock before rechecking access.
    count = notifications_for(actor).filter(
        event__lead_id__in=lead_ids, read_at__isnull=True
    ).update(read_at=timezone.now())
    return {"updated_count": count}
