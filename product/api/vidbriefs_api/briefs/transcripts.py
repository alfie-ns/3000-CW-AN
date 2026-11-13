from django.db import transaction
from youtube_transcript_api import YouTubeTranscriptApi

from .models import Video, TranscriptSegment, Part
from .parts import cut_parts


def fully_stored(video):  # everything the pipeline saves for a video, so far
    return video.parts.exists()


def fetch_transcript(youtube_id, title=''):
    video = Video.objects.filter(youtube_id=youtube_id).first()
    if video and fully_stored(video):
        return video  # store without needing to re-fetch

    fetched = YouTubeTranscriptApi().fetch(youtube_id) # fetch the transcript from YouTube API
    if not fetched:
        return None # kill process if no video-transcript
    pieces = cut_parts(fetched)  # worked out before the database is locked

    with transaction.atomic():  # no Video row without its segments
        video, _ = Video.objects.get_or_create(youtube_id=youtube_id, defaults={'title': title or youtube_id})
        if fully_stored(video):
            return video  # a double tap already stored it
        video.segments.all().delete()  # rows saved by an earlier step
        video.parts.all().delete()
        TranscriptSegment.objects.bulk_create(
            TranscriptSegment(video=video, start=s.start, end=s.start + s.duration, text=s.text)
            for s in fetched
        )
        Part.objects.bulk_create(Part(video=video, start=start, end=end, text=text) for start, end, text in pieces)
    return video
