import os

INPUT_FILE = "datasets/greek/transcript.txt"
OUTPUT_FILE = "datasets/greek.directory"

with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
    with open(INPUT_FILE, "r", encoding="utf-8") as f:
        res = ''
        for line in f.readlines():
            file, _, transcription, _ = line.split('|', 3)
            res += f'{transcription.strip()} | datasets/greek/{file}\n'
        out.write(res)
                

print("Done.")