# sync/views.py

import datetime
import requests
import icalendar
from django.conf import settings
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from sync.models import Booking
from rest_framework import viewsets
from sync.serializers import BookingSerializer


class BookingViewSet(viewsets.ModelViewSet):
    """
    Provides the standard CRUD endpoints at /api/bookings/
    Lookup by external_id so DELETE/PUT by that works.
    """
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer

    # Use external_id (not numeric PK) in the URL for retrieve/update/delete
    lookup_field = 'external_id'
    lookup_value_regex = '[^/]+'   # allow alphanumeric, dashes, etc.


class SyncView(APIView):
    """
    - POST /api/sync/{apt}/      → pull Airbnb iCal, upsert into Booking
    - GET  /ical/availability/{apt}.ics → emit ICS of all Booking for apt
    """
    # allow .ics suffix
    format_suffixes = ['ics', 'json']
    permission_classes = [AllowAny]

    def get(self, request, apartment_id, format=None):
        # Build VCALENDAR with required headers
        cal = icalendar.Calendar()
        cal.add('VERSION', '2.0')
        cal.add('PRODID', '-//cal-sync//nairobi-apartments//EN')
        cal.add('CALSCALE', 'GREGORIAN')

        # Include every Booking in our DB for this apartment_id
        for b in Booking.objects.filter(apartment_id=apartment_id):
            ev = icalendar.Event()
            ev.add('uid',    b.external_id)
            ev.add('dtstart', b.start_date)
            ev.add('dtend',   b.end_date + datetime.timedelta(days=1))
            ev.add('summary', b.title or 'Booking')
            cal.add_component(ev)

        ics_content = cal.to_ical()
        return HttpResponse(ics_content, content_type='text/calendar')

    def post(self, request, apartment_id):
        # 1) look up the real ICS URL from settings
        ics_url = settings.AIRBNB_ICS_URLS.get(int(apartment_id))
        if not ics_url:
            return Response(
                {"error": f"No ICS URL for apartment {apartment_id}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2) fetch the feed
        try:
            r = requests.get(ics_url, timeout=10)
            r.raise_for_status()
        except requests.RequestException as e:
            return Response(
                {"error": "cannot fetch ICS", "details": str(e)},
                status=status.HTTP_502_BAD_GATEWAY
            )

        # 3) parse and upsert each VEVENT
        try:
            cal = icalendar.Calendar.from_ical(r.text)
            for comp in cal.walk():
                if comp.name != "VEVENT":
                    continue

                # decoded may return date or datetime
                raw_start = comp.decoded('dtstart')
                start = raw_start.date() if hasattr(raw_start, 'date') else raw_start

                raw_end = comp.decoded('dtend')
                end = (raw_end.date() if hasattr(raw_end, 'date') else raw_end) \
                      - datetime.timedelta(days=1)

                uid = str(comp.get('uid'))
                Booking.objects.update_or_create(
                    external_id=uid,
                    defaults={
                        'apartment_id': apartment_id,
                        'start_date':   start,
                        'end_date':     end,
                        'title':        str(comp.get('summary', 'Airbnb'))
                    }
                )
        except Exception as e:
            return Response(
                {"error": "ICS parse failed", "details": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        return Response({"synced": True})
