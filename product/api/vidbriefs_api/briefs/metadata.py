from yt_dlp import YoutubeDL
from yt_dlp.utils import YoutubeDLError


def video_info(youtube_id):  # title, duration, chapters, heatmap; {} if yt-dlp fails
    options = {'quiet': True, 'no_warnings': True, 'skip_download': True, 'socket_timeout': 10, 'extractor_retries': 0}
    try:
        with YoutubeDL(options) as ydl:
            return ydl.extract_info(f'https://www.youtube.com/watch?v={youtube_id}', download=False) or {}
    except YoutubeDLError:  # blocked, private or removed: the transcript still works
        return {}
