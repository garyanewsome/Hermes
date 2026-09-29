"""Real POD Go 2.50 model names (amps, cabs, and the four effect categories
relevant to passive tone analysis), for suggest_pod_go_tone's grounding
text. Transcribed directly from the user's own "POD Go Edit - Pilots Guide
2.50" PDF (pages 41-54, the Model Lists section) — the authoritative, current
source, not a web page: an earlier draft of this file came from Line 6's
website and had real transcription errors (e.g. "Alpaca Rogue" for the
actual "Alpaca Rouge", "Pillars OD" for the actual "Pillars", "Ratatouille
Dist" for the actual "Ratatoullie Dist") that this version corrects.

Cab models use the current (v2.00+) Cab engine list, not the Legacy Cab
list the PDF also includes for old-preset compatibility — no reason to
double up on near-duplicate names here.

Kept as plain "Name — based-on" text blocks, not parsed further — this
exists to ground the chat model's own reasoning in real product names
instead of letting it invent plausible-sounding fake ones, not to be
queried structurally.
"""

FULL_AMPS = """
WhoWatt 100 — Hiwatt DR-103 Brill
Soup Pro — Supro S6616
Stone Age 185 — Gibson EH-185
Voltage Queen — Victoria Electro King
Tweed Blues Nrm — Fender Bassman (normal channel)
Tweed Blues Brt — Fender Bassman (bright channel)
Fullerton Nrm — Fender 5C3 Tweed Deluxe (normal channel)
Fullerton Brt — Fender 5C3 Tweed Deluxe (bright channel)
Fullerton Jump — Fender 5C3 Tweed Deluxe (jumped)
Grammatico LG Nrm — Grammatico LaGrange (normal channel)
Grammatico LG Brt — Grammatico LaGrange (bright channel)
Grammatico LG Jump — Grammatico LaGrange (jumped)
US Small Tweed — Fender Champ
US Princess — Fender Princeton Reverb
US Super Nrm — Fender Super Reverb (normal channel)
US Super Vib — Fender Super Reverb (vibrato channel)
US Deluxe Nrm — Fender Deluxe Reverb (normal channel)
US Deluxe Vib — Fender Deluxe Reverb (vibrato channel)
US Double Nrm — Fender Twin Reverb (normal channel)
US Double Vib — Fender Twin Reverb (vibrato channel)
Mail Order Twin — Silvertone 1484
Divided Duo — ÷13 JRT 9/15
Interstate Zed — Dr Z Route 66
Derailed Ingrid — Trainwreck Circuits Express
Grammatico GSG — Grammatico GSG100
Jazz Rivet 120 — Roland JC-120 Jazz Chorus
Essex A15 — Vox AC-15
Essex A30 — Vox AC-30 with top boost
A30 Fawn Nrm — Vox AC-30 Fawn (normal channel)
A30 Fawn Brt — Vox AC-30 Fawn (bright channel)
Matchstick Ch1 — Matchless DC30 (channel 1)
Matchstick Ch2 — Matchless DC30 (channel 2)
Matchstick Jump — Matchless DC30 (jumped)
Mandarin 80 — Orange OR80
Mandarin Rocker — Orange Rockerverb 100 MkIII (dirty channel)
Moo)))n Nrm — Sunn Model T (normal channel)
Moo)))n Brt — Sunn Model T (brite channel)
Moo)))n Jump — Sunn Model T (jumped channels)
Brit J45 Nrm — Marshall JTM-45 (normal channel)
Brit J45 Brt — Marshall JTM-45 (bright channel)
Brit Trem Nrm — Marshall JTM-50 (normal channel)
Brit Trem Brt — Marshall JTM-50 (bright channel)
Brit Trem Jump — Marshall JTM-50 (jumped)
Brit Plexi Nrm — Marshall Super Lead 100 (normal channel)
Brit Plexi Brt — Marshall Super Lead 100 (bright channel)
Brit Plexi Jump — Marshall Super Lead 100 (jumped)
Brit P75 Nrm — Park 75 (normal channel)
Brit P75 Brt — Park 75 (bright channel)
Brit 2203 — Marshall JCM-800, 100W, 2203
Brit 2204 — Marshall JCM-800, 50W, 2204
Placater Clean — Friedman BE-100 (clean channel)
Placater Dirty — Friedman BE-100 (BE/HBE channel)
Cartographer — Ben Adrian Cartographer
German Xtra Blue — Bogner Ecstacy 101B, EL34 (blue channel)
German Xtra Red — Bogner Ecstacy 101B, EL34 (red channel)
German Mahadeva — Bogner Shiva
German Ubersonic — Bogner Überschall
Cali Texas Ch 1 — MESA/Boogie Lone Star (clean channel)
Cali Texas Ch 2 — MESA/Boogie Lone Star (drive channel)
Cali IV Rhythm 1 — MESA/Boogie Mark IV (channel I)
Cali IV Rhythm 2 — MESA/Boogie Mark IV (channel II)
Cali IV Lead — MESA/Boogie Mark IV (lead channel)
Cali Rectifire — MESA/Boogie Dual Rectifier
Archetype Clean — Paul Reed Smith Archon (clean channel)
Archetype Lead — Paul Reed Smith Archon (lead channel)
ANGL Meteor — ENGL Fireball 100
Solo Lead Clean — Soldano SLO-100 (clean channel)
Solo Lead Crunch — Soldano SLO-100 (crunch channel)
Solo Lead OD — Soldano SLO-100 (overdrive channel)
PV Panama — Peavey 5150
Revv Gen Purple — Revv Generator 120 (purple/gain 1 channel)
Revv Gen Red — Revv Generator 120 (red/gain 2 channel)
Das Benzin Mega — Diezel VH4 (mega channel)
Das Benzin Lead — Diezel VH4 (lead channel)
Line 6 Clarity — Line 6 Original
Line 6 Aristocrat — Line 6 Original
Line 6 Carillon — Line 6 Original
Line 6 Voltage — Line 6 Original
Line 6 Kinetic — Line 6 Original
Line 6 Oblivion — Line 6 Original
Line 6 Ventoux — Line 6 Original
Line 6 Elmsley — Line 6 Original
Line 6 Elektrik — Line 6 Original
Line 6 Doom — Line 6 Original
Line 6 Epic — Line 6 Original
Line 6 2204 Mod — Line 6 Original
Line 6 Fatality — Line 6 Original
Line 6 Litigator — Line 6 Original
Line 6 Badonk — Line 6 Original

Bass amps:
Ampeg B-15NF — Ampeg B-15NF Portaflex
Ampeg SVT Nrm — Ampeg SVT (normal channel)
Ampeg SVT Brt — Ampeg SVT (bright channel)
Ampeg SVT-4 Pro — Ampeg SVT-4 PRO
US Dripman Nrm — Fender Bassman (Silverface)
Woody Blue — Acoustic 360
Agua Sledge — Aguilar Tone Hammer
Agua 51 — Aguilar DB51
Mandarin Bass 200 — Orange AD200 MkIII
Cali Bass — MESA/Boogie M9 Carbine
Cali 400 Ch1 — MESA/Boogie Bass 400+ (channel 1)
Cali 400 Ch2 — MESA/Boogie Bass 400+ (channel 2)
G Cougar 800 — Gallien-Krueger GK 800RB
Del Sol 300 — Sunn Coliseum 300
Busy One Ch1 — Pearce BC-1 preamp (channel 1)
Busy One Ch2 — Pearce BC-1 preamp (channel 2)
Busy One Jump — Pearce BC-1 preamp (jumped)
Studio Tube Pre — Requisite Y7 mic preamp
""".strip()

FULL_CABS = """
Soup Pro Ellipse — 1x6x9" Supro S6616
1x8 Small Tweed — 1x8" Fender Champ
1x10 US Princess — 1x10" Fender Princeton Reverb
1x12 Fullerton — 1x12" Fender 5C3 Tweed Deluxe
1x12 Grammatico — 1x12" Grammatico LaGrange
1x12 US Deluxe — 1x12" Fender Deluxe Oxford
1x12 Open Cast — 1x12" custom open-back, EVM12L
1x12 Open Cream — 1x12" custom open-back, G12M-65
1x12 Cali EXT — 1x12" MESA/Boogie Extension, EVM12L
1x12 Cali IV — 1x12" MESA/Boogie MkIV combo
1x12 Blue Bell — 1x12" Vox AC-15, Blue Alnico
2x12 Blue Bell — 2x12" Vox AC-30 Fawn Blue
2x12 Silver Bell — 2x12" Vox AC-30TB, Silver Alnico
2x12 Match H30 — 2x12" Matchless DC30, custom G12H-30
2x12 Match G25 — 2x12" Matchless DC30, custom G12M-35
2x12 Double C12N — 2x12" Fender Twin C12N
2x12 Interstate — 2x12" Dr. Z Z Best, V30
2x12 Jazz Rivet — 2x12" Roland JC-120
2x12 Mail C12Q — 2x12" Silvertone 1484, Jensen C12Q
2x12 Mandarin 30 — 2x12" Orange, Vintage 30
4x10 Tweed P10R — 4x10" Fender Bassman P10R
4x10 US Super — 4x10" Fender Super Reverb, CTS alnico
4x12 WhoWatt — 4x12" Hiwatt AP Fane
4x12 Greenback 20 — 4x12" Marshall Basketweave G12M-20
4x12 Greenback 25 — 4x12" Marshall Basketweave G12M-25
4x12 Greenback 30 — 4x12" Marshall Basketweave G12H-30
4x12 1960A T75 — 4x12" Marshall 1960A, G12T-75
4x12 Blackback 30 — 4x12" Park 75, G12-H30
4x12 Brit V30 — 4x12" Marshall 1960AV, Vintage 30
4x12 Cali V30 — 4x12" MESA/Boogie 4FB, Vintage 30
4x12 Mandarin EM — 4x12" Orange, Eminence
4x12 MOO)))N T75 — 4x12" Sunn, G12T-75
4x12 Cartog Guv — 4x12" modified Lee Jackson, Eminence Governor
4x12 Cartog C90 — 4x12" modified Lee Jackson, Mesa C90
4x12 Uber T75 — 4x12" Bogner Uberkab, G12T-75
4x12 Uber V30 — 4x12" Bogner Uberkab, V30
4x12 XXL V30 — 4x12" ENGL XXL, V30
4x12 SoloLead EM — 4x12" Soldano, Eminence 12-5875

Bass cabs:
1x12 Epicenter — 1x12" Epifani Ultralight
1x15 Ampeg B-15 — 1x15" Ampeg B-15
2x15 Brute — 2x15" MESA/Boogie 2x15 EV
2x15 US Dripman — 2x15" Fender Bassman, JBL D130
4x10 Garden — 4x10" Eden D410XLT
4x10 Ampeg Pro — 4x10" Ampeg PR-410HLF
6x10 Cali Power — 6x10" MESA/Boogie PowerHouse
8x10 SVT AV — 8x10" Ampeg SVT-810AV
""".strip()

# The four categories that map onto what tone_analysis.py can actually
# detect from audio (gain character, periodic modulation, echo, decay
# tail). EQ/dynamics/pitch/filter/wah/looper models are real too, but
# nothing in the detection step points at them, so including them would
# just be unused context.
EFFECTS = {
    "distortion": """
Kinky Boost — Xotic EP Booster
Deranged Master — Dallas Rangemaster Treble Booster
Minotaur — Klon Centaur
Teemah! — Paul Cochrane Timmy Overdrive
Heir Apparent — Analogman Prince of Tone
Alpaca Rouge — Way Huge Red Llama
Compulsive Drive — Fulltone OCD
Dhyana Drive — Hermida Zendrive
Horizon Drive — Horizon Precision Drive
Valve Driver — Chandler Tube Driver
Top Secret OD — DOD OD-250
Scream 808 — Ibanez TS808 Tube Screamer
Pillars — Earthquaker Devices Plumes
Hedgehog D9 — MAXON SD9 Sonic Distortion
Stupor OD — BOSS SD-1 Overdrive
Deez One Vintage — BOSS DS-1 Distortion (Made-in-Japan)
Deez One Mod — BOSS DS-1 Distortion (Keeley modded)
Ratatoullie Dist — Pro Co RAT (with LM308 opamp)
Vermin Dist — Pro Co RAT
KWB — Benadrian Kowloon Walled Bunny Distortion
Swedish Chainsaw — Boss HM-2 Heavy Metal Distortion (MIJ)
Arbitrator Fuzz — Arbiter Fuzz Face
Pocket Fuzz — Jordan Boss Tone Fuzz
Bighorn Fuzz — '73 Electro-Harmonix Ram's Head Big Muff Pi
Triangle Fuzz — Electro-Harmonix Big Muff Pi
Dark Dove Fuzz — Electro-Harmonix Russian Big Muff Pi
Ballistic Fuzz — Euthymia ICBM Fuzz
Industrial Fuzz — Z.Vex Fuzz Factory
Tycoctavia Fuzz — Tycobrahe Octavia
Wringer Fuzz — Garbage's modded BOSS FZ-2
Thrifter Fuzz — Line 6 Original
Xenomorph Fuzz — Subdecay Harmonic Antagonizer
Megaphone — Megaphone
Bitcrusher — Line 6 Original
Ampeg Scrambler — Ampeg Scrambler Bass Overdrive
ZeroAmp Bass DI — Tech 21 SansAmp Bass Driver DI V1
Regal Bass DI — Noble Preamp Bass DI
Obsidian 7000 — Darkglass Electronics Microtubes B7K Ultra
Tube Drive — Chandler Tube Driver
Screamer — Ibanez Tube Screamer
Overdrive — DOD Overdrive/Preamp 250
Classic Dist — ProCo RAT
Heavy Dist — BOSS Metal Zone
Colordrive — Colorsound Overdriver
Buzz Saw — Maestro Fuzz Tone
Facial Fuzz — Arbiter Fuzz Face
Jumbo Fuzz — Vox Tone Bender
Fuzz Pi — Electro-Harmonix Big Muff Pi
Jet Fuzz — Roland Jet Phaser
L6 Drive — Colorsound Overdriver (modded)
L6 Distortion — Line 6 Original
Sub Oct Fuzz — PAiA Roctave Divider
Octave Fuzz — Tycobrahe Octavia
Bronze Master — Maestro Bass Brassmaster
Killer Z — Boss Metal Zone MT-2
""".strip(),
    "modulation": """
Optical Trem — Fender optical tremolo circuit
60s Bias Trem — Vox AC-15 Tremolo
Tremolo/Autopan — BOSS PN-2
Harmonic Tremolo — Line 6 Original
Bleat Chop Trem — Lightfoot Labs Goatkeeper
Script Mod Phase — MXR Phase 90
Pebble Phaser — Electro-Harmonix Small Stone phaser
Ubiquitous Vibe — Shin-ei Uni-Vibe
FlexoVibe — Line 6 Original
Deluxe Phaser — Line 6 Original
Gray Flanger — MXR 117 Flanger
Harmonic Flanger — A/DA Flanger
Courtesan Flange — Electro-Harmonix Deluxe EM
Dynamix Flanger — MicMix DynaFlanger
Chorus — Line 6 Original
70s Chorus — BOSS CE-1
PlastiChorus — modded Arion SCH-Z chorus
Ampeg Liquifier — Ampeg Liquifier Chorus
Trinity Chorus — Dytronics Tri-Stereo Chorus
4-Voice Chorus — Line 6 Original
Bubble Vibrato — BOSS VB-2 Vibrato
Vibe Rotary — Fender Vibratone
122 Rotary — Leslie 122
145 Rotary — Leslie 145
Triple Rotary — Yamaha RA-200
Retro Reel — Line 6 Original
Double Take — Line 6 Original
AM Ring Mod — Line 6 Original
Pitch Ring Mod — Line 6 Original
Pattern Tremolo — Line 6 Original
Panner — Line 6 Original
Bias Tremolo — 1960 Vox AC-15 Tremolo
Opto Tremolo — 1964 Fender Deluxe Reverb
Script Phase — MXR Phase 90 (script logo version)
Panned Phaser — Ibanez Flying Pan
Barberpole — Line 6 Original
Dual Phaser — Mu-Tron Bi-Phase
U-Vibe — Shin-ei Uni-Vibe
Phaser — MXR Phase 90
Pitch Vibrato — BOSS VB-2
Dimension — Roland Dimension D
Analog Chorus — BOSS CE-1
Tri Chorus — Dytronics Tri-Stereo Chorus
Analog Flanger — MXR Flanger
Jet Flanger — A/DA Flanger
AC Flanger — MXR Flanger
80A Flanger — A/DA Flanger
Frequency Shift — Line 6 Original
Ring Modulator — Line 6 Original
Rotary Drum — Fender Vibratone
Rotary Drum/Horn — Leslie 145
Tape Eater — Line 6 Original
Warble-Matic — Line 6 Original
Random S&H — Line 6 Original
Sweeper — Line 6 Original
""".strip(),
    "delay": """
Simple Delay — Line 6 Original
Mod/Chorus Echo — Line 6 Original
Dual Delay — Line 6 Original
Multitap 4 — Line 6 Original
Multitap 6 — Line 6 Original
Ping Pong — Line 6 Original
Sweep Echo — Line 6 Original
Ducked Delay — TC Electronic 2290
Reverse Delay — Line 6 Original
Vintage Digital — Line 6 Original
Vintage Swell — Line 6 Original
Pitch Echo — Line 6 Original
Transistor Tape — Maestro Echoplex EP-3
Harmony Delay — Line 6 Original
Bucket Brigade — BOSS DM-2
Adriatic Delay — BOSS DM-2 w/ Adrian Mod
Adriatic Swell — Line 6 Original
Elephant Man — Electro-Harmonix Deluxe Memory Man
Multi Pass — Line 6 Original
Glitch Delay — Line 6 Original
Euclidean Delay — Line 6 Original
ADT — Line 6 Original
Crisscross — Line 6 Original
Tesselator — Line 6 Original
Ratchet — Line 6 Original
Ping Pong Legacy — Line 6 Original
Dynamic — TC Electronic 2290
Stereo — Line 6 Original
Digital — Line 6 Original
Dig w/Mod — Line 6 Original
Reverse — Line 6 Original
Lo Res — Line 6 Original
Tube Echo — Maestro Echoplex EP-1
Tape Echo — Maestro Echoplex EP-3
Echo Platter — Binson EchoRec
Analog Echo — BOSS DM-2
Analog w/Mod — Electro-Harmonix Deluxe Memory Man
Auto-Volume Echo — Line 6 Original
Multi-Head — Roland RE-101 Space Echo
Bubble Echo — Line 6 Original
Phaze Eko — Line 6 Original
""".strip(),
    "reverb": """
Dynamic Hall — Line 6 Original
Dynamic Plate — Line 6 Original
Dynamic Room — Line 6 Original
Dynamic Ambience — Line 6 Original
Shimmer — Line 6 Original
Hot Springs — Line 6 Original
Glitz — Line 6 Original
Ganymede — Line 6 Original
Searchlights — Line 6 Original
Plateaux — Line 6 Original
Double Tank — Line 6 Original
Plate — Line 6 Original
Room — Line 6 Original
Chamber — Line 6 Original
Hall — Line 6 Original
Echo — Line 6 Original
Tile — Line 6 Original
Cave — Line 6 Original
Ducking — Line 6 Original
Octo — Line 6 Original
'63 Spring — Line 6 Original
Spring — Line 6 Original
Particle Verb — Line 6 Original
""".strip(),
}

# Curated, much smaller subsets of the above — used instead of FULL_AMPS/
# FULL_CABS/full effect lists in the actual tool output. Confirmed live
# against gemma4:12b: handing it the complete catalog (~9500 chars) on top
# of this app's full tool-schema list caused it to lose the thread of the
# conversation entirely — at one size it fell back to a generic "here's
# what I can do" greeting, at another it hallucinated an unrelated tool
# call to a nonexistent GitHub repo. A short list (under ~2000 chars)
# answered correctly and used real model names every time it was tried.
# The categorization below (clean/crunch/high-gain) is standard, widely
# agreed-upon guitar-amp lineage — not a personal tonal judgment call —
# same as how any gear reference would group these amps.
AMPS_CLEAN = """
US Small Tweed — Fender Champ
US Princess — Fender Princeton Reverb
US Deluxe Nrm — Fender Deluxe Reverb (normal channel)
US Double Nrm — Fender Twin Reverb (normal channel)
Tweed Blues Nrm — Fender Bassman (normal channel)
Fullerton Nrm — Fender 5C3 Tweed Deluxe (normal channel)
Essex A15 — Vox AC-15
Essex A30 — Vox AC-30 with top boost
Matchstick Ch1 — Matchless DC30 (channel 1)
Jazz Rivet 120 — Roland JC-120 Jazz Chorus
WhoWatt 100 — Hiwatt DR-103 Brill
Soup Pro — Supro S6616
""".strip()

AMPS_CRUNCH = """
Brit J45 Nrm — Marshall JTM-45 (normal channel)
Brit Plexi Nrm — Marshall Super Lead 100 (normal channel)
Brit 2203 — Marshall JCM-800, 100W, 2203
A30 Fawn Brt — Vox AC-30 Fawn (bright channel)
Mandarin 80 — Orange OR80
Placater Clean — Friedman BE-100 (clean channel)
Cali Texas Ch 2 — MESA/Boogie Lone Star (drive channel)
Essex A30 — Vox AC-30 with top boost
Interstate Zed — Dr Z Route 66
Derailed Ingrid — Trainwreck Circuits Express
""".strip()

AMPS_HIGH_GAIN = """
Brit 2204 — Marshall JCM-800, 50W, 2204
Placater Dirty — Friedman BE-100 (BE/HBE channel)
German Ubersonic — Bogner Überschall
German Mahadeva — Bogner Shiva
Cali Rectifire — MESA/Boogie Dual Rectifier
Cali IV Lead — MESA/Boogie Mark IV (lead channel)
Archetype Lead — Paul Reed Smith Archon (lead channel)
ANGL Meteor — ENGL Fireball 100
Solo Lead OD — Soldano SLO-100 (overdrive channel)
PV Panama — Peavey 5150
Revv Gen Red — Revv Generator 120 (red/gain 2 channel)
Das Benzin Lead — Diezel VH4 (lead channel)
Cartographer — Ben Adrian Cartographer
Mandarin Rocker — Orange Rockerverb 100 MkIII (dirty channel)
""".strip()

CABS_COMMON = """
1x12 Fullerton — 1x12" Fender 5C3 Tweed Deluxe
1x12 US Deluxe — 1x12" Fender Deluxe Oxford
4x10 US Super — 4x10" Fender Super Reverb, CTS alnico
2x12 Blue Bell — 2x12" Vox AC-30 Fawn Blue
2x12 Match H30 — 2x12" Matchless DC30, custom G12H-30
2x12 Jazz Rivet — 2x12" Roland JC-120
4x12 Greenback 25 — 4x12" Marshall Basketweave G12M-25
4x12 Brit V30 — 4x12" Marshall 1960AV, Vintage 30
4x12 Cali V30 — 4x12" MESA/Boogie 4FB, Vintage 30
4x12 Uber V30 — 4x12" Bogner Uberkab, V30
4x12 XXL V30 — 4x12" ENGL XXL, V30
4x12 Mandarin EM — 4x12" Orange, Eminence
""".strip()

EFFECTS_SHORT = {
    "distortion": """
Scream 808 — Ibanez TS808 Tube Screamer
Minotaur — Klon Centaur
Teemah! — Paul Cochrane Timmy Overdrive
Compulsive Drive — Fulltone OCD
Stupor OD — BOSS SD-1 Overdrive
Deez One Vintage — BOSS DS-1 Distortion (Made-in-Japan)
Ratatoullie Dist — Pro Co RAT (with LM308 opamp)
Triangle Fuzz — Electro-Harmonix Big Muff Pi
Arbitrator Fuzz — Arbiter Fuzz Face
Killer Z — Boss Metal Zone MT-2
Heavy Dist — BOSS Metal Zone
""".strip(),
    "modulation": """
Chorus — Line 6 Original
70s Chorus — BOSS CE-1
Analog Flanger — MXR Flanger
Phaser — MXR Phase 90
Ubiquitous Vibe — Shin-ei Uni-Vibe
Optical Trem — Fender optical tremolo circuit
Bubble Vibrato — BOSS VB-2 Vibrato
Dimension — Roland Dimension D
122 Rotary — Leslie 122
""".strip(),
    "delay": """
Tape Echo — Maestro Echoplex EP-3
Analog Echo — BOSS DM-2
Elephant Man — Electro-Harmonix Deluxe Memory Man
Vintage Digital — Line 6 Original
Ping Pong — Line 6 Original
Multi-Head — Roland RE-101 Space Echo
Simple Delay — Line 6 Original
""".strip(),
    "reverb": """
Spring — Line 6 Original
Room — Line 6 Original
Plate — Line 6 Original
Hall — Line 6 Original
Chamber — Line 6 Original
Shimmer — Line 6 Original
""".strip(),
}
