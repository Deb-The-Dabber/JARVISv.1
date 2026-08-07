/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        bg: '#070b0f',
        'bg-elevated': '#0d121a',
        'bg-card': '#111820',
        border: 'rgba(79,195,247,0.12)',
        fg: '#c9d1d9',
        'fg-dim': '#4a5568',
        accent: '#4fc3f7',
        'accent-dim': 'rgba(79,195,247,0.15)',
        'accent-glow': 'rgba(79,195,247,0.4)',
        success: '#69ff47',
        warning: '#ffa726',
        danger: '#ef5350',
      },
      fontFamily: {
        mono: ['SF Mono', 'Fira Code', 'monospace'],
        sans: ['-apple-system', 'BlinkMacSystemFont', 'sans-serif'],
      },
      animation: {
        blink: 'blink 2s infinite',
        pulse: 'pulse 2s infinite',
        spin: 'spin 8s linear infinite',
        wave: 'wave 0.6s ease-in-out infinite',
        orbPulse: 'orbPulse 0.8s infinite',
      },
      keyframes: {
        blink: {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.3' },
        },
        pulse: {
          '0%, 100%': { transform: 'scale(1)' },
          '50%': { transform: 'scale(1.05)' },
        },
        spin: {
          from: { transform: 'rotate(0deg)' },
          to: { transform: 'rotate(360deg)' },
        },
        wave: {
          '0%, 100%': { height: '4px' },
          '50%': { height: '30px' },
        },
        orbPulse: {
          '0%, 100%': { transform: 'translate(-50%, -50%) scale(1)' },
          '50%': { transform: 'translate(-50%, -50%) scale(1.08)' },
        },
      },
    },
  },
  plugins: [],
}
