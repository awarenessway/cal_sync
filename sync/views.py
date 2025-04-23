import datetime
import requests
import icalendar
from django.conf import settings
from django.http import HttpResponse
from rest_framework import viewsets, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Booking
from .serializers import BookingSerializer

class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.all()
    serializer_class = BookingSerializer

class SyncView(APIView):
    """
    - POST /api/sync/{apt}/      → pull Airbnb iCal, upsert into Booking
    - GET  /ical/availability/{apt}.ics → emit ICS of all Booking for apt
    """
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

    def get(self, request, apartment_id, format=None):
        cal = icalendar.Calendar()
        for b in Booking.objects.filter(apartment_id=apartment_id):
            ev = icalendar.Event()
            ev.add('uid', b.external_id)
            ev.add('dtstart', b.start_date)
            ev.add('dtend',   b.end_date + datetime.timedelta(days=1))
            ev.add('summary', b.title)
            cal.add_component(ev)
        return HttpResponse(cal.to_ical(), content_type='text/calendar')

