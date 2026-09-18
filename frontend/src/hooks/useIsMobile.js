import { useEffect, useState } from 'react';

// Below this, treat as a phone: nav/conversation drawers become overlays
// instead of permanent columns, and multi-column layouts (task quadrants,
// habit rows) stack. Above it — including the "small tablet" the app is
// actually meant to run on — the existing desktop-style layout already fits.
const BREAKPOINT = 700;

export default function useIsMobile() {
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= BREAKPOINT);

  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${BREAKPOINT}px)`);
    const handler = (e) => setIsMobile(e.matches);
    mq.addEventListener('change', handler);
    return () => mq.removeEventListener('change', handler);
  }, []);

  return isMobile;
}
