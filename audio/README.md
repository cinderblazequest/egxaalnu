# Аудиоматериалы

Папка для голосовых метрономов СЛР.

В репозитории уже лежат три mp3-файла, сгенерированные через FFmpeg
(чистый sine-click 1000 Гц, длительность 60 секунд):

- `metronome_100.mp3` — 100 ударов/мин (нижняя граница AHA/ERC).
- `metronome_110.mp3` — 110 ударов/мин (используется по умолчанию).
- `metronome_120.mp3` — 120 ударов/мин (верхняя граница).

Бот автоматически отдаёт `metronome_110.mp3` при нажатии кнопки
«🥁 Метроном» в сценарии СЛР. Если по какой-то причине файла нет —
происходит fallback на текстовый метроном.

## Как пересгенерировать (если нужны другие BPM)

### Способ 0: FFmpeg-скрипт (используется в репозитории)

```bash
for bpm in 100 110 120; do
  PERIOD=$(python3 -c "print(60.0/$bpm)")
  ffmpeg -y -f lavfi -i "sine=frequency=1000:duration=0.04" \
    -af "afade=t=in:st=0:d=0.005,afade=t=out:st=0.03:d=0.01,volume=0.7" \
    -ar 22050 -ac 1 click.wav
  SILENCE=$(python3 -c "print(max(0.01, $PERIOD - 0.04))")
  ffmpeg -y -f lavfi -i "anullsrc=channel_layout=mono:sample_rate=22050" \
    -t $SILENCE silence.wav
  ffmpeg -y -i click.wav -i silence.wav \
    -filter_complex "[0:a][1:a]concat=n=2:v=0:a=1" -ar 22050 -ac 1 one_beat.wav
  BEATS=$(python3 -c "print(int(60 / $PERIOD))")
  python3 -c "print('\n'.join(['file ' + repr('one_beat.wav')] * $BEATS))" > list.txt
  ffmpeg -y -f concat -safe 0 -i list.txt -c:a libmp3lame -b:a 32k -ar 22050 -ac 1 \
    metronome_${bpm}.mp3
done
```

### Способ 1: онлайн-генератор (без установки)

1. Зайти на https://metronomeonline.com/
2. Поставить нужный темп.
3. Записать звук с экрана через приложение «Запись экрана» / OBS.
4. Сконвертировать в mp3 любым онлайн-конвертером.
5. Положить в эту папку.

### Способ 2: FFmpeg (для тех, у кого Python/Linux/macOS)

Один tick + тишина в 60/BPM секунд, повторённый 60 секунд:

```bash
# 110 BPM = 60/110 = 0.5454 сек на удар
ffmpeg -y -f lavfi -i "anullsrc=channel_layout=mono:sample_rate=22050" \
  -t 0.05 -af "asetnsamples=n=110:p=0,sine=frequency=1000:duration=0.05" \
  click.wav

# Затем циклим через ffmpeg concat. См. https://trac.ffmpeg.org/wiki/Concatenate
```

Проще — взять любой готовый клик из открытых источников и нарезать.

### Способ 3: уже сгенерированный mp3

Можно использовать любой бесплатный CC0-метроном. Поиск: «metronome 110 bpm mp3 free download».
