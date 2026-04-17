# 🚀 BrokerHub - React Frontend

Modern React frontend for the Insurance Broker Workbench, featuring AI-powered chat with unique agent personas.

## Tech Stack

| Technology | Purpose |
|------------|---------|
| React 18 + TypeScript | UI framework with type safety |
| Vite | Fast dev server & build |
| Tailwind CSS | Utility-first styling |
| Shadcn/ui patterns | Accessible component primitives |
| Framer Motion | Smooth animations & transitions |
| Recharts | Data visualization charts |
| Lucide React | Consistent iconography |
| react-markdown | Rich chat message rendering |

## Quick Start

```bash
npm install
npm run dev
```

Dev server runs at http://localhost:3000, proxying API calls to backend at :8000.

## Project Structure

```
src/
├── components/
│   ├── ui/           # Base components (Button, Card, Table, Avatar, etc.)
│   ├── layout/       # Header, Sidebar
│   ├── dashboard/    # PolicyTable, CarrierQuotes, CrossSellOpportunities
│   ├── chat/         # AIChatPanel, SmartInsights
│   └── charts/       # RenewalTrendChart, PolicyDistributionChart
├── hooks/
│   └── useApi.ts     # Data fetching, chat management, suggestions
├── types/
│   └── index.ts      # TypeScript interfaces
└── lib/
    └── utils.ts      # cn() class merge utility
```

## Features

### 🤖 AI Chat Panel
- **Resizable** - Drag left edge to resize (280px-900px), persists in localStorage
- **Unique Agent Avatars** - Each agent has distinct icon and color:
  - Claims Agent: Shield icon, rose/pink theme
  - Cross-Sell Agent: TrendingUp icon, emerald/green theme  
  - Quote Agent: FileText icon, blue theme
- **Markdown Rendering** - Clean formatting with `react-markdown` + typography
- **Smart Suggestions** - Contextual follow-up pills extracted from responses
- **Clear Chat** - One-click reset with fade animation

### 📊 Dashboard
- Policy management table with status badges
- Renewal trend charts (area chart)
- Policy distribution (donut chart)
- Cross-sell opportunity cards
- Carrier quote comparisons

### ✨ UX Polish
- Framer Motion animations on all interactions
- Real-time API connection status indicator
- Loading skeletons during data fetch
- Responsive design (desktop + tablet)

## API Integration

The `useApi` hook manages all backend communication:

```typescript
const { 
  policies, 
  clients, 
  carriers, 
  loading, 
  connected,
  messages,
  suggestions,
  sendMessage 
} = useApi();
```

Vite proxies `/api/*` and `/health` to the FastAPI backend.

## Development

```bash
# Start dev server
npm run dev

# Type check
npm run build

# Preview production build
npm run preview
```

## Environment

The Vite dev server is configured to proxy API requests. No `.env` file needed for local dev - just ensure the backend is running on port 8000.

For production, set `VITE_API_URL` if deploying frontend separately from backend.
