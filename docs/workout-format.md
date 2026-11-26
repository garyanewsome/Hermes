# Workout paste format

Code reads this, not a model. A line it doesn't understand is reported, and
nothing is saved until every line is accepted.

```
WORKOUT 2026-11-26
lift | Bench Press | 135 lb | 8, 8, 7
lift | Bench Press | 145 lb | 5
lift | Pull Up | bw | 3x6
lift | Dip | bw+25 lb | 8, 6
walk | walking pad | 1.5 mi | 30 min
walk | walking pad | 20 min
```

- Start each day with `WORKOUT YYYY-MM-DD`. One paste can hold several days.
- `lift | exercise | weight | reps`
  - weight: `135 lb`, `60 kg`, `bw`, `bw+25 lb`
  - reps: one number per set (`8, 8, 7`) or sets x reps (`3x8`)
  - a change of weight goes on its own line
- `walk | activity | distance and/or time`
  - distance: `1.5 mi`, `2 km`
  - time: `30 min`, `28:30`, `1:05:00`

Saving a day again replaces it by kind: lift lines replace that day's lifts,
walk lines replace its pasted walks (not ones added in the app). So send **all** of a day's lifts together (and
all of its walks together).

Not supported yet: timed holds, assisted (negative) weight, other cardio.

## Prompt for Claude

> Turn this workout into the format below and reply with only the code block.
> Lifting: `lift | exercise | weight | reps`. Walks:
> `walk | activity | distance | time`. Start with `WORKOUT YYYY-MM-DD`. Use the
> same exercise names every time. If something is unreadable or doesn't fit the
> format, ask me instead of guessing.
