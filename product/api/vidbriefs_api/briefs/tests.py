from unittest.mock import patch
from xml.etree.ElementTree import ParseError

from django.test import TestCase
from requests import ConnectionError
from rest_framework.test import APITestCase
from youtube_transcript_api import (
    AgeRestricted, FetchedTranscriptSnippet, InvalidVideoId, IpBlocked, NoTranscriptFound,
    PoTokenRequired, TranscriptsDisabled, VideoUnavailable,
)

from .models import Video, TranscriptSegment, Part
from .parts import MAX_SECONDS, MAX_WORDS, cut_parts
from .transcripts import fetch_transcript
from .views import youtube_id_from

# 1- AI-assisted: generated example code with ChatGPT for unit tests; utilised to create tests reviewed, tested and understood by me

'''
python manage.py test:

```output
fetch_transcript: Ran 3 tests in 0.002s
youtube_id_from: Ran 1 test in 0.000s
VideoView: Ran 2 tests in 0.007s
VideoView (400, 422): Ran 2 tests in 0.010s
VideoView (error codes): Ran 1 test in 0.006s

OK
Destroying test database for alias 'default'...
```

'''

# Create your tests here.

FAKE_CAPTIONS = [  # out of order, to check the model's ordering
    FetchedTranscriptSnippet(text='second line', start=4.0, duration=2.5),
    FetchedTranscriptSnippet(text='first line', start=0.5, duration=3.0),
]


# NOTE: Tests for fetch_transcript function, ensuring correct storage then handling of YouTube transcripts.

@patch('briefs.transcripts.YouTubeTranscriptApi')  # no real YouTube calls
class FetchTranscriptTests(TestCase):

    def test_stores_each_caption_with_start_and_end(self, api): # ensures each caption's stored with the genuine start and end times
        api.return_value.fetch.return_value = FAKE_CAPTIONS
        video = fetch_transcript('abcdefghijk', 'Test video')

        segments = list(video.segments.all())
        self.assertEqual([s.text for s in segments], ['first line', 'second line'])# 
        self.assertEqual((segments[0].start, segments[0].end), (0.5, 3.5))
        self.assertEqual((segments[1].start, segments[1].end), (4.0, 6.5))

    def test_stored_video_is_not_fetched_again(self, api): # ensure non-duplicate fetch for already stored video
        api.return_value.fetch.return_value = FAKE_CAPTIONS
        fetch_transcript('abcdefghijk')
        fetch_transcript('abcdefghijk')

        api.return_value.fetch.assert_called_once()
        self.assertEqual(TranscriptSegment.objects.count(), 2)

    def test_failed_fetch_leaves_no_video_row(self, api): # ensure fetches fail properely, i.e., no 'ghost' video row is created
        api.return_value.fetch.side_effect = VideoUnavailable('xxxxxxxxxxx')

        with self.assertRaises(VideoUnavailable):
            fetch_transcript('xxxxxxxxxxx')
        self.assertFalse(Video.objects.exists())

    def test_double_tap_stores_captions_once(self, api): # second request finishes whilst the first is still fetching
        calls = []

        def fetch(youtube_id):
            calls.append(youtube_id)
            if len(calls) == 1:
                fetch_transcript(youtube_id)  # the double tap
            return FAKE_CAPTIONS

        api.return_value.fetch.side_effect = fetch
        fetch_transcript('abcdefghijk')
        self.assertEqual(TranscriptSegment.objects.count(), 2)


# NOTE: Tests for cut_parts, i.e., the parts Jev will score

def lines(count, seconds=5.0, words=10):  # evenly spaced fake caption lines
    return [FetchedTranscriptSnippet(text=' '.join(['w'] * words), start=i * seconds, duration=seconds) for i in range(count)]


class CutPartsTests(TestCase):

    def test_short_video_is_one_part(self):
        self.assertEqual(len(cut_parts(lines(6))), 1)  # 30 s

    def test_parts_stay_under_both_caps(self):
        for count, words in [(40, 10), (40, 30)]:  # time-bound, then word-bound
            with self.subTest(words=words):
                for start, end, text in cut_parts(lines(count, words=words)):
                    self.assertLessEqual(end - start, MAX_SECONDS)
                    self.assertLessEqual(len(text.split()), MAX_WORDS)

    def test_no_caption_is_split_and_order_is_kept(self):
        parts = cut_parts(FAKE_CAPTIONS)  # out of order on purpose
        self.assertEqual(parts, [(0.5, 6.5, 'first line second line')])

    def test_overlapping_captions_still_close_the_part(self):  # a long line can outlast the next one
        long_then_short = [FetchedTranscriptSnippet(text='a', start=0.0, duration=65.0), FetchedTranscriptSnippet(text='b', start=2.0, duration=3.0)]
        self.assertEqual(len(cut_parts(long_then_short)), 2)

    def test_fetch_stores_parts(self):
        with patch('briefs.transcripts.YouTubeTranscriptApi') as api:
            api.return_value.fetch.return_value = lines(30)  # 150 s
            fetch_transcript('abcdefghijk')
        self.assertEqual([(p.start, p.end) for p in Part.objects.all()], [(0.0, 60.0), (60.0, 120.0), (120.0, 150.0)])

    def test_video_saved_before_parts_is_rebuilt(self):  # e.g. sent before this step existed
        video = Video.objects.create(youtube_id='abcdefghijk', title='old')
        TranscriptSegment.objects.create(video=video, start=0.0, end=5.0, text='old line')
        with patch('briefs.transcripts.YouTubeTranscriptApi') as api:
            api.return_value.fetch.return_value = lines(30)
            fetch_transcript('abcdefghijk')
        self.assertEqual((TranscriptSegment.objects.count(), Part.objects.count()), (30, 3))  # old line gone, no duplicates


class YouTubeIdTests(TestCase):

    def test_link_styles(self):  # test to verify youtube_id_from correctly extracts YouTube IDs from all the different url styles
        links = {
            'abcdefghijk': 'abcdefghijk',
            'https://www.youtube.com/watch?v=abcdefghijk&t=30s': 'abcdefghijk',
            'youtube.com/watch?v=abcdefghijk': 'abcdefghijk',
            'https://m.youtube.com/watch?v=abcdefghijk': 'abcdefghijk',
            'https://music.youtube.com/watch?v=abcdefghijk': 'abcdefghijk',
            'https://youtu.be/abcdefghijk?si=xyz': 'abcdefghijk',
            'https://www.youtube.com/shorts/abcdefghijk': 'abcdefghijk',
            'https://www.youtube.com/embed/abcdefghijk': 'abcdefghijk',
            'https://www.youtube.com/live/abcdefghijk': 'abcdefghijk',
            'https://youtube.com.evil.com/watch?v=abcdefghijk': None,  # lookalike host
            'https://vimeo.com/123456': None,
            'https://youtube.com/watch?v=short': None,
            'https://www.youtube.com/watch': None,
            'https://www.youtube.com/shorts/': None,
            'https://youtu.be/': None,
            'http://[': None,
        }
        for link, expected in links.items(): # loop through each link and test it
            with self.subTest(link=link):
                self.assertEqual(youtube_id_from(link), expected)


# NOTE: Tests for POST /api/videos/, i.e., what the app gets back for each link

@patch('briefs.transcripts.YouTubeTranscriptApi')  # no real YouTube calls
class VideoEndpointTests(APITestCase):

    '''
        1- init post helper method
        2- test new link with correctly ordered segments with captions returns 201 (Created)
        3- test stored video returns 200 (OK) without refetching transcript
    '''

    def post(self, body):
        return self.client.post('/api/videos/', body, format='json')

    def test_new_link_returns_201_with_ordered_segments(self, api):
        api.return_value.fetch.return_value = FAKE_CAPTIONS
        response = self.post({'url': 'https://youtu.be/abcdefghijk'})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['youtube_id'], 'abcdefghijk')
        self.assertEqual([s['text'] for s in response.data['segments']], ['first line', 'second line'])
        self.assertEqual(response.data['segments'][0]['end'], 3.5)

    def test_stored_video_returns_200_without_refetch(self, api):
        api.return_value.fetch.return_value = FAKE_CAPTIONS
        self.post({'url': 'https://youtu.be/abcdefghijk'})
        response = self.post({'url': 'https://www.youtube.com/watch?v=abcdefghijk'})  # same video, other link style

        self.assertEqual(response.status_code, 200)
        api.return_value.fetch.assert_called_once()

    def test_bad_input_returns_400_without_calling_youtube(self, api): # test various bad inputs and ensure YouTube API is not called
        for body in [{'url': 'https://vimeo.com/123456'}, {'url': 'https://evil.com/watch?v=abcdefghijk'}, {'url': ''}, {}, {'url': 42}, ['not', 'a', 'dict']]:
            with self.subTest(body=body): # test each bad input individually, e.g. is url valid, and not empty
                response = self.post(body)
                self.assertEqual(response.status_code, 400)
                self.assertIn('detail', response.data)

        response = self.client.post('/api/videos/', 'not json', content_type='application/json')
        self.assertEqual(response.status_code, 400)  # DRF's own errors share the 'detail' key
        api.return_value.fetch.assert_not_called()

    def test_empty_transcript_returns_422(self, api): # ensure empty-captioned video gives 422; TODO: this might change later down the dev line, however it is difficult to find a video that is not at least auto-transcribed
        api.return_value.fetch.return_value = []
        response = self.post({'url': 'abcdefghijk'}) # mocked non-caption video

        self.assertEqual(response.status_code, 422)
        self.assertIn('detail', response.data)
        self.assertFalse(Video.objects.exists()) # ensure no video is stored when transcript is empty
        

    def test_fetch_errors_map_to_status_codes(self, api):  # each failure the app must show, never a 500
        cases = [
            (InvalidVideoId('abcdefghijk'), 400),
            (VideoUnavailable('abcdefghijk'), 404),
            (TranscriptsDisabled('abcdefghijk'), 422),
            (NoTranscriptFound('abcdefghijk', ['en'], None), 422),
            (AgeRestricted('abcdefghijk'), 422),
            (IpBlocked('abcdefghijk'), 503),
            (ConnectionError(), 503),
            (PoTokenRequired('abcdefghijk'), 502),  # falls through to the catch-all
            (ParseError(), 502),
        ]
        for error, code in cases:
            with self.subTest(error=type(error).__name__):
                api.return_value.fetch.side_effect = error
                response = self.post({'url': 'abcdefghijk'})
                self.assertEqual(response.status_code, code)
                self.assertIn('detail', response.data)
        self.assertFalse(Video.objects.exists())


# NOTE: Tests for POST /api/videos/<youtube_id>/ask/, i.e., the AI's answer about a stored video

@patch('briefs.res.OpenAI')  # no real OpenAI calls
class AskEndpointTests(APITestCase):

    def setUp(self):
        self.video = Video.objects.create(youtube_id='abcdefghijk', title='Test video')
        Part.objects.create(video=self.video, start=0.0, end=5.0, text='first part')

    def ask(self, body, youtube_id='abcdefghijk'):
        return self.client.post(f'/api/videos/{youtube_id}/ask/', body, format='json')

    def test_answers_with_terra_at_max_effort(self, openai):
        openai.return_value.responses.create.return_value.output_text = 'an answer [1]'
        openai.return_value.responses.create.return_value.usage.output_tokens_details.reasoning_tokens = 42
        response = self.ask({'question': 'What is it about?'})

        self.assertEqual(response.status_code, 200)
        self.assertEqual((response.data['answer'], response.data['reasoning_tokens']), ('an answer [1]', 42))
        sent = openai.return_value.responses.create.call_args.kwargs
        self.assertEqual((sent['model'], sent['reasoning']), ('gpt-6.1-terra', {'effort': 'max'}))
        self.assertTrue(sent['input'].startswith('Video: "Test video", 0:05 long'))
        self.assertTrue(sent['input'].endswith('Question: What is it about?'))  # last, so the start caches

    def test_empty_answer_returns_502_and_missing_usage_is_none(self, openai):
        reply = openai.return_value.responses.create.return_value
        reply.output_text, reply.usage = '', None
        self.assertEqual(self.ask({'question': 'Why?'}).status_code, 502)
        reply.output_text = 'an answer [1]'
        response = self.ask({'question': 'Why?'})
        self.assertEqual((response.status_code, response.data['reasoning_tokens']), (200, None))

    def test_bad_question_or_unknown_video_never_calls_openai(self, openai):
        for body, youtube_id, code in [({}, 'abcdefghijk', 400), ({'question': '  '}, 'abcdefghijk', 400),
                                       ({'question': 42}, 'abcdefghijk', 400), ({'question': 'Why?'}, 'zzzzzzzzzzz', 404)]:
            with self.subTest(body=body, youtube_id=youtube_id):
                response = self.ask(body, youtube_id)
                self.assertEqual(response.status_code, code)
                self.assertIn('detail', response.data)
        openai.assert_not_called()

    def test_openai_failures_map_to_status_codes(self, openai):  # never a 500
        from openai import APIConnectionError, OpenAIError
        for error, code in [(APIConnectionError(request=None), 503), (OpenAIError('no key'), 502)]:
            with self.subTest(error=type(error).__name__):
                openai.return_value.responses.create.side_effect = error
                response = self.ask({'question': 'Why?'})
                self.assertEqual(response.status_code, code)
                self.assertIn('detail', response.data)
