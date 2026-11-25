from rest_framework import serializers

from .models import Video, TranscriptSegment, Part

'''
'rest_framework.serializers' for the Video and TranscriptSegment models (converts model instances to JSON and vice versa)
'''

class TranscriptSegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = TranscriptSegment
        fields = ['start', 'end', 'text']


class PartSerializer(serializers.ModelSerializer):
    class Meta:
        model = Part
        fields = ['id', 'start', 'end', 'text']  # the id is what the app logs plays against


class VideoSerializer(serializers.ModelSerializer):
    segments = TranscriptSegmentSerializer(many=True, read_only=True)  # in start order, via the model's Meta
    parts = PartSerializer(many=True, read_only=True)

    class Meta:
        model = Video
        fields = ['youtube_id', 'title', 'created_at', 'segments', 'parts']