/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./dashboard/templates/**/*.html",
    "./dashboard/**/*.py",
    "./templates/**/*.html"
  ],
  theme: {
    extend: {
      colors: {
        xbg: "#FFFFFF",
        xpanel: "#F7F9F9",
        xline: "#EFF3F4",
        xtext: "#000000",
        xmuted: "#333333",
        xblue: "#1D9BF0",
      },
    },
  },
  plugins: [],
}

