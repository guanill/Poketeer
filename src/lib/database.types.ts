export interface Database {
  public: {
    Tables: {
      sets: {
        Row: {
          id: string;
          name: string;
          series: string;
          printed_total: number;
          total: number;
          release_date: string;
          language: string;
          symbol_url: string;
          logo_url: string;
        };
        Insert: Omit<Database['public']['Tables']['sets']['Row'], never>;
        Update: Partial<Database['public']['Tables']['sets']['Insert']>;
      };
      cards: {
        Row: {
          id: string;
          name: string;
          number: string;
          set_id: string;
          rarity: string;
          image_small: string;
          image_large: string;
          supertype: string;
          subtypes: string[];
          hp: string;
          artist: string;
          types: string[];
        };
        Insert: Omit<Database['public']['Tables']['cards']['Row'], never>;
        Update: Partial<Database['public']['Tables']['cards']['Insert']>;
      };
      card_embeddings: {
        Row: {
          card_id: string;
          embedding: number[];
        };
        Insert: Omit<Database['public']['Tables']['card_embeddings']['Row'], never>;
        Update: Partial<Database['public']['Tables']['card_embeddings']['Insert']>;
      };
      collections: {
        Row: {
          user_id: string;
          card_id: string;
          quantity: number;
          price_paid: number | null;
          condition: string;
          notes: string | null;
          date_added: string;
        };
        Insert: Omit<Database['public']['Tables']['collections']['Row'], 'date_added'> & {
          date_added?: string;
        };
        Update: Partial<Database['public']['Tables']['collections']['Insert']>;
      };
      wishlist: {
        Row: {
          user_id: string;
          card_id: string;
          target_price: number | null;
          priority: string;
          date_added: string;
        };
        Insert: Omit<Database['public']['Tables']['wishlist']['Row'], 'date_added'> & {
          date_added?: string;
        };
        Update: Partial<Database['public']['Tables']['wishlist']['Insert']>;
      };
      prices_cache: {
        Row: {
          card_id: string;
          market_price: number | null;
          updated_at: string;
          failed: boolean;
        };
        Insert: Omit<Database['public']['Tables']['prices_cache']['Row'], 'updated_at' | 'failed'> & {
          updated_at?: string;
          failed?: boolean;
        };
        Update: Partial<Database['public']['Tables']['prices_cache']['Insert']>;
      };
    };
    Functions: {
      match_card: {
        Args: { query_embedding: number[]; match_count: number };
        Returns: {
          id: string;
          name: string;
          number: string;
          set_id: string;
          rarity: string;
          image_small: string;
          image_large: string;
          supertype: string;
          subtypes: string[];
          hp: string;
          artist: string;
          similarity: number;
        }[];
      };
    };
  };
}
