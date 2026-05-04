from youtube_transcript_api import YouTubeTranscriptApi

t = YouTubeTranscriptApi.list_transcripts('dQw4w9WgXcQ')  # Rick Astley - has English
tr = t.find_transcript(['en'])
data = tr.fetch()
print("First item:", data[0])

print("Container type:", type(data))
print("First item type:", type(data[0]))
print("First item:", data[0])
print("Dir:", dir(data[0])) 
