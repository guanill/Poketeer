export interface PokemonSet {
  id: string;
  name: string;
  series: string;
  printedTotal: number;
  total: number;
  releaseDate: string;
  language?: 'en' | 'ja' | 'th';
  images: {
    symbol: string;
    logo: string;
  };
}

export interface CardImage {
  small: string;
  large: string;
}

export interface CardPrice {
  low?: number;
  mid?: number;
  high?: number;
  market?: number;
  directLow?: number;
}

export interface CardTCGPlayer {
  url?: string;
  updatedAt?: string;
  prices?: {
    holofoil?: CardPrice;
    normal?: CardPrice;
    reverseHolofoil?: CardPrice;
    '1stEditionHolofoil'?: CardPrice;
    unlimited?: CardPrice;
  };
}

export interface PokemonCard {
  id: string;
  name: string;
  supertype: string;
  subtypes?: string[];
  hp?: string;
  types?: string[];
  number: string;
  artist?: string;
  rarity?: string;
  set: {
    id: string;
    name: string;
    series: string;
    images: { symbol: string; logo: string };
  };
  images: CardImage;
  tcgplayer?: CardTCGPlayer;
  nationalPokedexNumbers?: number[];
}

export interface OwnedCard {
  cardId: string;
  quantity: number;
  pricePaid?: number;
  dateAdded: string;
  condition: CardCondition;
  notes?: string;
}

export type CardCondition = 'Mint' | 'Near Mint' | 'Excellent' | 'Good' | 'Light Play' | 'Played' | 'Poor';

export interface WishlistItem {
  cardId: string;
  targetPrice?: number;
  priority: 'High' | 'Medium' | 'Low';
  dateAdded: string;
}

export interface CollectionState {
  owned: Record<string, OwnedCard>;
  wishlist: WishlistItem[];
  customPrices: Record<string, number>;
}

export type SortOption = 'number' | 'name' | 'rarity' | 'price' | 'type';
export type FilterOwned = 'all' | 'owned' | 'missing';
