# Segment 2 · Sections 5-8 · Lyrics for Suno

> Total target duration: ~2:45
> Sections 5, 7, 8 are largely instrumental.
> Section 6 contains brief vocals (Mandarin version; other language variants below).
> Section 8 ends in near-silence with one final piano note connecting to a companion piece.

---

## Suno Lyrics Block · Mandarin Version

```
[Section 5: Les Amis, stereo separation as structural device, no vocals, left channel cello with male ambient sounds restaurant chatter laughter low frequency, right channel flute with female ambient cafe sounds laughter higher frequency, the two channels never overlap rhythmically, D-flat major 4/4 72 BPM, 30 seconds]

[Instrumental: left channel plays motif fragment D-A on cello with men's voices ambient in background, right channel plays motif fragment B-G on flute with women's voices ambient in background, the channels alternate but never combine, like two parties happening in different rooms]

[Section 6: Le Dernier Dîner, solo cello and solo flute trading short phrases without counterpoint, male and female vocal each saying one line in Mandarin then stopping, hushed close-mic, D-flat major slow 4/4 66 BPM]

[Solo cello plays the first half of the motif D5 then A4, with three beats of silence after]

[Male voice, sung softly, only one phrase, intimate]
你 以后 吃好一点

[Solo flute plays the second half of the motif B4 then G4, with three beats of silence after]

[Female voice, sung softly, only one phrase, intimate]
你也是

[Cello and flute each play one final long sustained note, but in different rhythms, never aligning, then both fade]

[Section 7: La Signature, solo grand piano only, no other instruments, no vocals, no humming, rubato intimate close-mic with audible pedal breath, the motif D-A-B-G played four times each quieter than the last, identical piano tone to a companion piece prelude, G major modulation begins, 60 BPM, 40 seconds]

[Instrumental piano solo: D-A-B-G played at mp, then again at p with longer pause between notes, then again at pp even slower, then once more at ppp almost inaudible, between iterations the piano modulates from D-flat major into G major, the same key as the original story began, this is the circle closing]

[Section 8: Sortir, ambient minimal almost silent, instruments are gone, only environmental sounds and one final piano note, 45 seconds]

[Four seconds of complete silence at the start of this section]

[Then footsteps fade in: left channel man's leather shoes walking on wooden floor at one step per second, right channel woman's high heels walking at the same tempo, both at mp]

[Footsteps continue for ten seconds, gradually panning further apart, left going more left right going more right, getting quieter, adding distant room reverb as if walking down a hallway]

[Then one soft distant female voice in Cantonese, dry but distant, saying just one word]
保重

[Six full seconds of complete silence, no music, no sound, no humming]

[Then one final soft piano note G3, mp, with natural decay over two seconds, this exact piano tone matches the very first note of the companion prelude piece, the trilogy circle closes here]

[End. Silence.]
```

---

## Variant: Cantonese version (Sections 6 and 8 differ)

### Section 6 · Cantonese

```
[Male, sung softly]
你 以後 食好啲

[Female, sung softly]
你都係
```

### Section 8 · Cantonese

The single word is already Cantonese: **保重 (bóu jung)**. No change needed for this variant — Cantonese is the recommended primary language for the final word in all versions because of its "江湖告别" feeling.

---

## Variant: Japanese version

### Section 6

```
[男性 sung softly]
これから ちゃんと食べてね

[女性 sung softly]
あなたもね
```

### Section 8

The final word in Japanese: **元気でね (genki de ne)**. Speak softly, distantly.

---

## Variant: Korean version

### Section 6

```
[남성 sung softly]
앞으로 잘 먹어

[여성 sung softly]
너도
```

### Section 8

The final word in Korean: **잘 지내 (jal jinae)**. Speak softly, distantly.

---

## Notes for Suno generation

### Section 5 · Stereo separation challenge

Suno does not natively control stereo placement well. The best we can do:
- Repeat in metatag: `[left channel only cello, right channel only flute, do not mix]`
- Accept that Suno output may be partially mixed
- In DAW post: re-pan if needed, add ambient samples manually

### Section 6 · The hardest emotional moment

This is the spiritual climax of the entire trilogy. The two single-line vocals must sound:
- Hushed but not whispered
- Sung but barely
- Like they are sitting across from each other at a small table

Reinforce: `[two vocal lines of three syllables each, one male one female, intimate close-mic, sung very softly, like spoken at a small table in candlelight]`

### Section 7 · Critical for trilogy continuity

This piano sound MUST match the first note of the companion piece's first prelude. If the piano timbre is wrong, the trilogy circle does not close.

Reinforce: `[solo grand piano only, very intimate close-mic, single instrument all 40 seconds, no other sounds at all, classical romantic prelude style identical to opening of a companion piece]`

### Section 8 · The biggest Suno risk

Suno will try to fill silence with content. Expected failure rate: 70%.

**Realistic plan:**
1. Get Suno's best approximation of "footsteps + spoken word"
2. In DAW: extract the spoken-word and footstep portions
3. Manually add the silences and the final piano G3 note
4. The final G3 should be **the same recording as the first note of Eight Knots Movement 1**

This last manual step is essential. The bridge between the two pieces is constructed by hand, not generated.

### Cross-segment continuity

- Segment 1 ends with piano playing the stretched motif
- Segment 2 starts with stereo separation ambient
- DAW edit: leave 1 second silence between segments

### Cross-trilogy continuity

- Hodoku Section 8 final piano G3 must seamlessly loop into Eight Knots Movement 1 first piano G3
- On streaming platforms, set as adjacent tracks with gapless playback
- Recommended order for trilogy: Eight Knots → Musubi → Hodoku → loop back to Eight Knots
