# https://github.com/hayderkharrufa/arabic-buckwalter-transliteration/blob/main/arabic_buckwalter_transliteration/transliteration.py
def buckwalter_to_arabic(buckwalter):
    # Buckwalter to Arabic character map
    b2a = {  # mapping from Buckwalter to Arabic script
    u'b': u'\u0628', u'*': u'\u0630', u'T': u'\u0637', u'm': u'\u0645',
    u't': u'\u062a', u'r': u'\u0631', u'Z': u'\u0638', u'n': u'\u0646',
    u'^': u'\u062b', u'z': u'\u0632', u'E': u'\u0639', u'h': u'\u0647',
    u'j': u'\u062c', u's': u'\u0633', u'g': u'\u063a', u'H': u'\u062d',
    u'q': u'\u0642', u'f': u'\u0641', u'x': u'\u062e', u'S': u'\u0635',
    u'$': u'\u0634', u'd': u'\u062f', u'D': u'\u0636', u'k': u'\u0643',
    u'>': u'\u0623', u'\'': u'\u0621', u'}': u'\u0626', u'&': u'\u0624',
    u'<': u'\u0625', u'|': u'\u0622', u'A': u'\u0627', u'Y': u'\u0649',
    u'p': u'\u0629', u'y': u'\u064a', u'l': u'\u0644', u'w': u'\u0648',
    u'F': u'\u064b', u'N': u'\u064c', u'K': u'\u064d', u'a': u'\u064e',
    u'u': u'\u064f', u'i': u'\u0650', u'~': u'\u0651', u'o': u'\u0652',
    u'C': u'\u0686', u'G': u'\u06AF', u'P': u'\u067E', u'ı': u'\u0640',
    u'V': u'\u06A4', u'L': u'\u06B5', u'O': u'\u06C6', u'e': u'\u06CE'
}

    return ''.join(b2a.get(char, char) for char in buckwalter)

import os

INPUT_DIR = "datasets/arabic/arabic-speech-corpus/lab"
OUTPUT_DIR = "datasets"

os.makedirs(OUTPUT_DIR, exist_ok=True)

res = ''
for filename in os.listdir(INPUT_DIR):
    in_path = os.path.join(INPUT_DIR, filename)

    if not os.path.isfile(in_path):
        continue

    with open(in_path, "r", encoding="utf-8") as f:
        content = f.read()

    converted = f'{buckwalter_to_arabic(content)} | datasets/arabic/arabic-speech-corpus/wav/{filename.replace('lab', 'wav')}\n'
    res += converted
with open(os.path.join(OUTPUT_DIR, "arabic.directory"), "w", encoding="utf-8") as f:
        f.write(res)
print("Done.")