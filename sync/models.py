from django.db import models

class Booking(models.Model):
    external_id   = models.CharField(max_length=255, unique=True)
    apartment_id  = models.IntegerField()
    start_date    = models.DateField()
    end_date      = models.DateField()
    title         = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"{self.external_id} @ apt {self.apartment_id}"

