# Poketeer 🎴⚡

A Pokemon TCG collection tracker built with React, TypeScript, and Tailwind CSS.

## Features

- **Browse All Sets** — Explore every Pokemon TCG set ever released (100+ sets via the [Pokemon TCG API](https://pokemontcg.io))
- **Track Your Collection** — Mark cards as owned, track price paid, condition, and notes
- **Price Tracking** — Live market prices from TCGPlayer, profit/loss calculation
- **Set Completion Progress** — See how close you are to completing each set
- **Wishlist** — Save cards you want with priority levels and target prices
- **Full-Text Search** — Search any card by name across all sets
- **Collection Value** — Dashboard showing total market value vs. what you spent
- **3D Card Animations** — Tilt-on-hover 3D effect on every card
- **Persistent Storage** — All data saved to localStorage automatically

## Tech Stack

- **React 19** + **TypeScript**
- **Vite** — Build tool
- **Framer Motion** — Animations (3D tilt, page transitions, spring animations)
- **TailwindCSS v4** — Styling
- **TanStack Query** — Data fetching + caching
- **Zustand** — State management (with localStorage persistence)
- **React Router DOM** — Client-side routing
- **Lucide React** — Icons
- **Pokemon TCG API** — Free card data (no API key required for basic use)

## Getting Started

```bash
npm install
npm run dev
```

Open http://localhost:5173 in your browser.

## Pages

| Route | Description |
|-------|-------------|
| `/` | Dashboard — stats, set progress overview |
| `/sets` | Browse & filter all sets |
| `/sets/:setId` | Cards in a specific set |
| `/collection` | Your owned cards with value stats |
| `/wishlist` | Cards you want to acquire |
| `/search` | Search all cards by name |

## API Note

The app uses the free [Pokemon TCG API](https://pokemontcg.io/). Without an API key the rate limit is 1,000 requests/day. For higher limits, get a free API key at pokemontcg.io and add it to `src/services/pokemonTCG.ts`.

