#!/usr/bin/env bash

# run this in 'radialviz'
# run as many times as you'd like without it downloading over and over again

mkdir datasets

ARABIC_SPEECH_CORPUS=./datasets/arabic-speech-corpus.zip
if [ ! -f "$ARABIC_SPEECH_CORPUS" ]; then
  wget -P ./datasets https://en.arabicspeechcorpus.com/arabic-speech-corpus.zip
fi

ENGLISH_SPEECH_CORPUS=./datasets/dev-clean.tar.gz
if [ ! -f "$ENGLISH_SPEECH_CORPUS" ]; then
  wget -P ./datasets https://openslr.trmal.net/resources/12/dev-clean.tar.gz
fi

mkdir ./datasets/arabic
mkdir ./datasets/english

unzip $PWD/datasets/arabic-speech-corpus.zip -d $PWD/datasets/arabic
tar -xzf ./datasets/dev-clean.tar.gz -C ./datasets/english

python ./speech/arabic-speech-corpus-to-arabic.py
python ./speech/standardize-english-corpus.py