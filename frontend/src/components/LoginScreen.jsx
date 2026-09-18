import { useState } from 'react';
import { login } from '../api.js';

export default function LoginScreen({ onSuccess }) {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [checking, setChecking] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    if (!password || checking) return;
    setChecking(true);
    setError('');
    const ok = await login(password);
    setChecking(false);
    if (ok) {
      onSuccess();
    } else {
      setError('Incorrect password');
      setPassword('');
    }
  }

  return (
    <div
      style={{
        height: '100%',
        width: '100%',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg, #000)',
      }}
    >
      <form
        onSubmit={handleSubmit}
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
          width: 280,
          maxWidth: '85vw',
          padding: 28,
          borderRadius: 14,
          background: '#0a0a0a',
          border: '1px solid #2a6fff',
          boxShadow: '0 0 22px rgba(42,111,255,0.35)',
        }}
      >
        <div style={{ color: '#e8e8e8', fontSize: 20, fontWeight: 600, textAlign: 'center', letterSpacing: 0.5 }}>
          Hermes
        </div>
        <input
          type="password"
          autoFocus
          value={password}
          placeholder="Password"
          onChange={(e) => setPassword(e.target.value)}
          style={{
            background: '#000',
            border: '1px solid #2a6fff',
            color: '#e8e8e8',
            borderRadius: 8,
            padding: '10px 12px',
            fontSize: 14.5,
          }}
        />
        {error && <div style={{ color: '#ff4d4d', fontSize: 13 }}>{error}</div>}
        <button
          type="submit"
          disabled={checking}
          style={{
            background: '#2a6fff',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            padding: '10px 0',
            fontSize: 14.5,
            boxShadow: '0 0 14px rgba(42,111,255,0.5)',
          }}
        >
          {checking ? 'Checking...' : 'Log in'}
        </button>
      </form>
    </div>
  );
}
