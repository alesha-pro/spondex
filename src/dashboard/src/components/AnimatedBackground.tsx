export default function AnimatedBackground() {
  return (
    <div className="animated-bg">
      <svg
        className="blob-svg"
        viewBox="0 0 1000 1000"
        xmlns="http://www.w3.org/2000/svg"
      >
        <defs>
          <linearGradient id="grad1" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#ff0080" />
            <stop offset="100%" stopColor="#ff8c00" />
          </linearGradient>
          <linearGradient id="grad2" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#7928ca" />
            <stop offset="100%" stopColor="#ff0080" />
          </linearGradient>
          <linearGradient id="grad3" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stopColor="#4facfe" />
            <stop offset="100%" stopColor="#00f2fe" />
          </linearGradient>
        </defs>

        <path
          className="blob blob-1"
          fill="url(#grad1)"
          d="M 500,100 C 650,100 800,200 850,350 C 900,500 800,700 650,800 C 500,900 300,850 150,700 C 0,550 100,350 250,200 C 400,50 500,100 500,100 Z"
        />
        <path
          className="blob blob-2"
          fill="url(#grad2)"
          d="M 400,200 C 550,150 750,250 800,400 C 850,550 700,750 550,850 C 400,950 200,800 100,650 C 0,500 150,300 250,200 C 350,100 400,200 400,200 Z"
        />
        <path
          className="blob blob-3"
          fill="url(#grad3)"
          d="M 600,300 C 750,250 900,400 900,550 C 900,700 800,850 650,900 C 500,950 300,800 200,650 C 100,500 250,350 400,250 C 550,150 600,300 600,300 Z"
        />
      </svg>
      <div className="glass-overlay"></div>
    </div>
  )
}
