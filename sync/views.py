import datetime
import requests
import icalendar
from django.conf import settings
from django.http import HttpResponse
from rest_framework.permissions import AllowAny
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from sync.models import Booking
from sync.serializers import BookingSerializer

class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer
    
    lookup_field = 'external_id'
    lookup_value_regex = '[^/]+'   # allow dashes, etc.



class SyncView(APIView):
    """
    - POST /api/sync/{apt}/      → pull Airbnb iCal, upsert into Booking
    - GET  /ical/availability/{apt}.ics → emit ICS of all Booking for apt
    """
    format_suffixes = ['.ics', '.json']
    permission_classes = [AllowAny]

    def get(self, request, apartment_id, format=None):
        # 1) Trigger cal_sync to refresh its Airbnb pull
        try:
            sync_url = settings.CAL_SYNC_UPDATE_URL.format(apartment_id=apartment_id)
            requests.post(sync_url, timeout=5)
        except requests.RequestException:
            # ignore failures here
            pass

        # 2) Build a proper VCALENDAR with required headers
        cal = icalendar.Calendar()
        cal.add('VERSION', '2.0')
        cal.add('PRODID', '-//cal-sync//nairobi-apartments//EN')
        cal.add('CALSCALE', 'GREGORIAN')

        # 3) Add one VEVENT per Booking in our DB
        for b in Booking.objects.filter(apartment_id=apartment_id):
            ev = icalendar.Event()
            ev.add('uid', b.external_id)
            ev.add('dtstart', b.start_date)
            # DTEND is exclusive in iCal, so add one day
            ev.add('dtend', b.end_date + datetime.timedelta(days=1))
            ev.add('summary', b.title or 'Booking')
            cal.add_component(ev)

        # add a dummy event for testing
        ev = icalendar.Event()
        ev.add('uid', 'test-event-1')
        ev.add('dtstart', datetime.date.today())
        ev.add('dtend', datetime.date.today() + datetime.timedelta(days=1))
        ev.add('summary', 'TEST BLOCK')
        cal.add_component(ev)

        # 4) Return the calendar as text/calendar
        ics_content = cal.to_ical()
        return HttpResponse(ics_content, content_type='text/calendar')

    def post(self, request, apartment_id):
        # 1) look up the apartment and its real Airbnb ICS URL
        ics_url = settings.AIRBNB_ICS_URLS.get(int(apartment_id))
        if not ics_url:
            return Response(
                {"error": f"No ICS URL configured for apartment {apartment_id}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 2) fetch the feed
        try:
            r = requests.get(ics_url, timeout=10)
            r.raise_for_status()
        except requests.RequestException as e:
            return Response({"error": "cannot fetch ICS", "details": str(e)}, status=status.HTTP_502_BAD_GATEWAY)

        # 3) parse and upsert each VEVENT
        try:
            cal = icalendar.Calendar.from_ical(r.text)
            for comp in cal.walk():
                if comp.name != "VEVENT":
                    continue
                uid = str(comp.get('uid'))
                start = comp.decoded('dtstart').date()
                # subtract one day because DTEND in Airbnb ICS is exclusive
                end = comp.decoded('dtend').date() - datetime.timedelta(days=1)
                Booking.objects.update_or_create(
                    external_id=uid,
                    defaults={
                        'apartment_id': apartment_id,
                        'start_date': start,
                        'end_date': end,
                        'title': str(comp.get('summary', 'Airbnb'))
                    }
                )
        except Exception as e:
            return Response(
                {"error": "ICS parse failed", "details": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

        return Response({"synced": True})