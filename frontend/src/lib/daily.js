import { number } from '../views/workoutStyles.js';

// Eaten minus burned, worded. The server does the subtraction.
export function balanceText(balance) {
  if (balance === null || balance === undefined) return '';
  if (balance === 0) return 'even';
  return `${number(Math.abs(balance))} ${balance < 0 ? 'deficit' : 'surplus'}`;
}

export const macroText = (day) =>
  [['P', day.protein_g], ['C', day.carbs_g], ['F', day.fat_g]]
    .filter(([, grams]) => grams !== null)
    .map(([letter, grams]) => `${letter} ${number(grams)}`)
    .join(' · ');
