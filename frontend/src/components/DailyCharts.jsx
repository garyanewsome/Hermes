import { useEffect, useState } from 'react';
import { dailyLog } from '../api.js';
import { balanceText } from '../lib/daily.js';
import { Line, PairLine } from './Charts.jsx';
import { number, outline, solid } from '../views/workoutStyles.js';

const MACROS = [
  ['protein_g', 'Protein'],
  ['carbs_g', 'Carbs'],
  ['fat_g', 'Fat'],
];

// Weight, calories and macros over the Charts tab's range.
export default function DailyCharts({ active, weeks }) {
  const [data, setData] = useState(null);
  const [macro, setMacro] = useState('protein_g');

  useEffect(() => {
    if (!active) return undefined;
    let current = true;
    dailyLog(weeks)
      .then((next) => current && setData({ ...next, range: weeks }))
      .catch(() => {});
    return () => {
      current = false;
    };
  }, [active, weeks]);

  if (!data || data.days.length === 0) return null;
  const oldest = [...data.days].reverse();
  const series = (key, unit) => oldest.filter((d) => d[key] !== null).map((d) => ({ date: d.date, value: d[key], detail: `${number(d[key])} ${unit}` }));
  const weight = series('weight', 'lb');
  const calories = oldest
    .filter((d) => d.calories_in !== null || d.burned_total !== null)
    .map((d) => ({
      date: d.date,
      a: d.calories_in,
      b: d.burned_total,
      detail: [d.calories_in !== null && `eaten ${number(d.calories_in)}`, d.burned_total !== null && `burned ${number(d.burned_total)}`, balanceText(d.balance)].filter(Boolean).join(' · '),
    }));
  const name = MACROS.find(([key]) => key === macro)[1];
  const macros = series(macro, 'g');
  const anyMacro = oldest.some((d) => MACROS.some(([key]) => d[key] !== null));
  // Starts at the first number, so a new log isn't squeezed against the edge.
  const range = (points) => ({ start: points[0]?.date || data.start, end: data.today });

  return (
    <>
      {weight.length > 0 && <Line key={`weight-${data.range}`} title="Weight (lb)" valueHeading="Weight" points={weight} {...range(weight)} />}
      {calories.length > 0 && (
        <PairLine key={`calories-${data.range}`} title="Calories eaten and burned" names={['Eaten', 'Burned']} points={calories} {...range(calories)} />
      )}
      {anyMacro && (
        <Line
          key={`${macro}-${data.range}`}
          title={`${name} (g)`}
          valueHeading={name}
          points={macros}
          {...range(macros)}
          controls={
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
              {MACROS.map(([key, text]) => (
                <button key={key} type="button" onClick={() => setMacro(key)} aria-pressed={macro === key} style={{ ...(macro === key ? solid : outline), padding: '5px 12px', fontSize: 12 }}>
                  {text}
                </button>
              ))}
            </div>
          }
        />
      )}
    </>
  );
}
