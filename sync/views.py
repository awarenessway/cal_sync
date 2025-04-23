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
        ics_url = f"https://www.airbnb.com/calendar/ical/<YOUR_TOKEN>_{apartment_id}.ics"
        resp = requests.get(ics_url)
        resp.raise_for_status()
        cal = icalendar.Calendar.from_ical(resp.text)

        for comp in cal.walk():
            if comp.name == "VEVENT":
                uid   = str(comp.get('uid'))
                start = comp.decoded('dtstart').date()
                end   = comp.decoded('dtend').date() - datetime.timedelta(days=1)
                Booking.objects.update_or_create(
                    external_id=uid,
                    defaults={
                        'apartment_id': apartment_id,
                        'start_date': start,
                        'end_date': end,
                        'title': str(comp.get('summary', 'Airbnb'))
                    }
                )
        return Response({"synced": True})
