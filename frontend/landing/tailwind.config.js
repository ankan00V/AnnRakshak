/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        // Instrument Serif has no Devanagari. Falling to the sans face the Hindi
        // or Marathi farmer already has costs nothing; a serif Devanagari font
        // cost 124 KB to draw one word on Home (the crop name).
        'instrument-serif': ['"Instrument Serif"', '"Noto Sans Devanagari"', 'serif'],
        sans: ['Inter', '"Noto Sans Devanagari"', '"Noto Sans Bengali"', '"Noto Sans Tamil"', '"Noto Sans Telugu"',
          '"Noto Sans Kannada"', '"Noto Sans Malayalam"', '"Noto Sans Gujarati"', '"Noto Sans Gurmukhi"', '"Noto Sans Oriya"',
          'system-ui', 'sans-serif'],
      },
      colors: {
        soil: {
          dark: '#2b1d12',
          DEFAULT: '#4a3423',
        },
        leaf: {
          deep: '#1f3d2b',
          DEFAULT: '#3d6b4a',
        },
        ochre: '#c8862d',
        cream: '#f7f3ec',
        ember: '#b0472a',
      },
      backgroundImage: {
        // The closing panel's scrim. Solid leaf-deep across the top, where the
        // sources strip is, and across the bottom behind the footer; open
        // through the middle so the harvest playing behind it can actually be
        // seen under the headline. Tuned against the footage, not guessed.
        'cta-scrim': 'linear-gradient(to bottom, #1f3d2b 0%, #1f3d2b 30%, rgba(31,61,43,0.10) 58%, rgba(31,61,43,0.70) 78%, #1f3d2b 94%)',
      },
      keyframes: {
        // Movement only, never opacity: a screen that starts invisible stays
        // invisible wherever the animation does not run to its end — a
        // background tab, a throttled phone, a screenshot.
        fadein: {
          from: { transform: 'translateY(4px)' },
          to: { transform: 'translateY(0)' },
        },
        scan: {
          '0%': { top: '-20%' },
          '50%': { top: '85%' },
          '100%': { top: '-20%' },
        },
      },
      animation: {
        fadein: 'fadein 0.25s ease-out',
      },
    },
  },
  plugins: [],
}
