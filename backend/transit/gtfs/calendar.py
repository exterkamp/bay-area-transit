from datetime import date

from transit.models import ExceptionType, Feed, Service, ServiceDate


def active_service_ids(feed: Feed, on: date) -> set[int]:
    """Primary keys of the services running on ``on``.

    calendar.txt gives the weekly pattern within a date range; calendar_dates.txt
    then adds or removes individual dates, and wins over the pattern.
    """
    weekday = Service.WEEKDAYS[on.weekday()]
    running = set(
        Service.objects.filter(
            feed=feed, start_date__lte=on, end_date__gte=on, **{weekday: True}
        ).values_list("id", flat=True)
    )
    for service_id, exception_type in ServiceDate.objects.filter(feed=feed, date=on).values_list(
        "service_id", "exception_type"
    ):
        if exception_type == ExceptionType.ADDED:
            running.add(service_id)
        else:
            running.discard(service_id)
    return running
