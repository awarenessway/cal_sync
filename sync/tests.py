from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework import status
from .models import Booking
import datetime
from unittest.mock import patch
import icalendar

# a minimal sample ICS with two events
SAMPLE_ICS = """BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Airbnb//EN
BEGIN:VEVENT
UID:evt1
DTSTART;VALUE=DATE:20250110
DTEND;VALUE=DATE:20250112
SUMMARY:Test1
END:VEVENT
BEGIN:VEVENT
UID:evt2
DTSTART;VALUE=DATE:20250205
DTEND;VALUE=DATE:20250206
SUMMARY:Test2
END:VEVENT
END:VCALENDAR
"""

@override_settings(AIRBNB_ICS_URLS={1: "http://example.com/apt1.ics"})
class SyncTests(TestCase):
    def setUp(self):
        # ensure no bookings to start
        Booking.objects.all().delete()

    @patch("sync.views.requests.get")
    def test_post_sync_imports_events(self, mock_get):
        # mock requests.get to return our SAMPLE_ICS
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = SAMPLE_ICS

        url = reverse("sync:sync", kwargs={"apartment_id": 1})
        resp = self.client.post(url)
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        # two VEVENTs → two Booking rows
        qs = Booking.objects.filter(apartment_id=1)
        self.assertEqual(qs.count(), 2)
        b1 = qs.get(external_id="evt1")
        self.assertEqual(b1.start_date, datetime.date(2025,1,10))
        self.assertEqual(b1.end_date,   datetime.date(2025,1,11))  # dtend exclusive

    def test_get_ics_emits_events(self):
        # create two Booking rows manually
        Booking.objects.create(
            external_id="foo", apartment_id=1,
            start_date=datetime.date(2025,3,1),
            end_date  =datetime.date(2025,3,3),
            title="Local"
        )
        Booking.objects.create(
            external_id="bar", apartment_id=1,
            start_date=datetime.date(2025,4,5),
            end_date  =datetime.date(2025,4,5),
            title="Local2"
        )

        url = reverse("sync:ics", kwargs={"apartment_id": 1})
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp["Content-Type"], "text/calendar")

        cal = icalendar.Calendar.from_ical(resp.content)
        uids = {ev.get("uid") for ev in cal.walk() if ev.name=="VEVENT"}
        # we expect both foo and bar
        self.assertEqual(uids, {"foo","bar"})

