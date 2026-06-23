# TradeInsight Frontend

Professional trading analysis dashboard built with Next.js and React.

## Tech Stack

- **Framework:** Next.js 14
- **UI:** React 18 + TypeScript
- **Styling:** Tailwind CSS
- **Charts:** Recharts
- **State:** Zustand
- **HTTP:** Axios
- **Real-time:** WebSocket

## Setup

```bash
cd trade_insight/frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

## Environment Variables

Create `.env.local`:

```bash
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
```

## Building

```bash
npm run build
npm run start
```
