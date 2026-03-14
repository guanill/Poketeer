# Poketeer — Copilot Instructions

## Project Overview
Pokemon TCG card collection tracker. React + TypeScript + Vite app.

## Architecture
- `src/types/index.ts` — All TypeScript interfaces (PokemonCard, PokemonSet, OwnedCard, etc.)
- `src/services/pokemonTCG.ts` — Pokemon TCG API v2 calls (axios-based)
- `src/store/collectionStore.ts` — Zustand store persisted to localStorage
- `src/components/` — Reusable UI components (CardItem, SetCard, Navbar, etc.)
- `src/pages/` — Route-level pages (Dashboard, Sets, SetDetail, Collection, Wishlist, Search)

## Key Conventions
- Use TailwindCSS v4 utility classes — prefer `bg-linear-to-br` over `bg-gradient-to-br`, `shrink-0` over `flex-shrink-0`
- Use Framer Motion for all animations; wrap lists with `AnimatePresence`
- All Pokemon card data comes from `https://api.pokemontcg.io/v2`
- State is managed via Zustand (`useCollectionStore`)
- Data fetching uses TanStack Query with `staleTime` set to reduce API calls
- Card IDs follow the pattern `{setId}-{cardNumber}` (e.g., `base1-4`)

## Running
```bash
npm run dev    # Development server on :5173
npm run build  # Production build
