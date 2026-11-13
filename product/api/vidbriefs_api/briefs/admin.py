from django.contrib import admin

from .models import Video, TranscriptSegment, Part

# Register your models here.
admin.site.register(Video)
admin.site.register(TranscriptSegment)
admin.site.register(Part)
