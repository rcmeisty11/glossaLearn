import os

INPUT_ROOT = "datasets/english/LibriSpeech/dev-clean"
OUTPUT_FILE = "datasets/english.directory"

with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
    for root, dirs, files in os.walk(INPUT_ROOT):
        for name in files:
            if name.endswith(".trans.txt"):
                path = os.path.join(root, name)

                with open(path, "r", encoding="utf-8") as f:
                    res = ''
                    for line in f.readlines():
                        id, transcription = line.split(' ', 1)
                        first, second, third = id.split('-')
                        res += f'{transcription.strip()} | datasets/english/LibriSpeech/dev-clean/{first}/{second}/{id}.flac\n'
                    out.write(res)

print("Done.")