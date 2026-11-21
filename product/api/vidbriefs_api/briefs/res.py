from openai import OpenAI

''''
TODO:
- [X] `gpt-6.1-terra` at max effort
- [ ] `gemini-4-hydrogen` at xhigh or high effort while visually watch the video
- [ ] consider lowering 6.1 terra effort if sufficient performance
'''

MODEL = 'gpt-6.1-terra'
EFFORT = 'max'

RULES = '''You are `VidBriefs`: a concise answerer. 

Answer the question using only the numbered parts of the video below.
Keep it short (concise), and end each point with the number of the part it came from, e.g. [12].
If the parts do not answer the question report truthfully instead of guessing.'''


def clock(seconds):  # 754.2 -> '12:34'
    return f'{int(seconds) // 60}:{int(seconds) % 60:02d}'


def build_prompt(video, question):  # video-or-question rebuilt
    parts = list(video.parts.all())
    if not parts:
        raise ValueError(f'{video} has no parts yet; fetch its transcript first')
    length = clock(max(part.end for part in parts))  # from the latest *end*, not the last part's (overlapping captions mean the last part may not indeed end last)
    numbered = '\n\n'.join(f'[{part.id}] {clock(part.start)}-{clock(part.end)}\n{part.text}' for part in parts)
    # return the video first, followed by the question, so the video's start is efficiently reuse-cached for subsequent questions
    return RULES, f'Video: "{video.title}", {length} long, cut into {len(parts)} parts.\n\nParts:\n{numbered}\n\nQuestion: {question}'


def ask(video, question):
    instructions, prompt = build_prompt(video, question) # call intriciate `build_prompt`s for video+question(s) with instructions first
    return OpenAI().responses.create(  # made per call
        model=MODEL,
        reasoning={'effort': EFFORT},
        instructions=instructions,
        input=prompt,
    )
