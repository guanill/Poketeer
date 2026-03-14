export type Json =
  | string
  | number
  | boolean
  | null
  | { [key: string]: Json | undefined }
  | Json[]

export type Database = {
  // Allows to automatically instantiate createClient with right options
  // instead of createClient<Database, { PostgrestVersion: 'XX' }>(URL, KEY)
  __InternalSupabase: {
    PostgrestVersion: "14.4"
  }
  public: {
    Tables: {
      card_embeddings: {
        Row: {
          card_id: string
          embedding: string | null
        }
        Insert: {
          card_id: string
          embedding?: string | null
        }
        Update: {
          card_id?: string
          embedding?: string | null
        }
        Relationships: [
          {
            foreignKeyName: "card_embeddings_card_id_fkey"
            columns: ["card_id"]
            isOneToOne: true
            referencedRelation: "cards"
            referencedColumns: ["id"]
          },
        ]
      }
      cards: {
        Row: {
          artist: string
          hp: string
          id: string
          image_large: string
          image_small: string
          name: string
          number: string
          rarity: string
          set_id: string
          subtypes: string[]
          supertype: string
          types: string[]
        }
        Insert: {
          artist?: string
          hp?: string
          id: string
          image_large?: string
          image_small?: string
          name: string
          number?: string
          rarity?: string
          set_id: string
          subtypes?: string[]
          supertype?: string
          types?: string[]
        }
        Update: {
          artist?: string
          hp?: string
          id?: string
          image_large?: string
          image_small?: string
          name?: string
          number?: string
          rarity?: string
          set_id?: string
          subtypes?: string[]
          supertype?: string
          types?: string[]
        }
        Relationships: [
          {
            foreignKeyName: "cards_set_id_fkey"
            columns: ["set_id"]
            isOneToOne: false
            referencedRelation: "sets"
            referencedColumns: ["id"]
          },
        ]
      }
      collections: {
        Row: {
          card_id: string
          condition: string
          date_added: string
          notes: string | null
          price_paid: number | null
          quantity: number
          user_id: string
        }
        Insert: {
          card_id: string
          condition?: string
          date_added?: string
          notes?: string | null
          price_paid?: number | null
          quantity?: number
          user_id: string
        }
        Update: {
          card_id?: string
          condition?: string
          date_added?: string
          notes?: string | null
          price_paid?: number | null
          quantity?: number
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "collections_card_id_fkey"
            columns: ["card_id"]
            isOneToOne: false
            referencedRelation: "cards"
            referencedColumns: ["id"]
          },
        ]
      }
      prices_cache: {
        Row: {
          card_id: string
          failed: boolean
          market_price: number | null
          updated_at: string
        }
        Insert: {
          card_id: string
          failed?: boolean
          market_price?: number | null
          updated_at?: string
        }
        Update: {
          card_id?: string
          failed?: boolean
          market_price?: number | null
          updated_at?: string
        }
        Relationships: [
          {
            foreignKeyName: "prices_cache_card_id_fkey"
            columns: ["card_id"]
            isOneToOne: true
            referencedRelation: "cards"
            referencedColumns: ["id"]
          },
        ]
      }
      sets: {
        Row: {
          id: string
          language: string
          logo_url: string
          name: string
          printed_total: number
          release_date: string
          series: string
          symbol_url: string
          total: number
        }
        Insert: {
          id: string
          language?: string
          logo_url?: string
          name: string
          printed_total?: number
          release_date?: string
          series?: string
          symbol_url?: string
          total?: number
        }
        Update: {
          id?: string
          language?: string
          logo_url?: string
          name?: string
          printed_total?: number
          release_date?: string
          series?: string
          symbol_url?: string
          total?: number
        }
        Relationships: []
      }
      wishlist: {
        Row: {
          card_id: string
          date_added: string
          priority: string
          target_price: number | null
          user_id: string
        }
        Insert: {
          card_id: string
          date_added?: string
          priority?: string
          target_price?: number | null
          user_id: string
        }
        Update: {
          card_id?: string
          date_added?: string
          priority?: string
          target_price?: number | null
          user_id?: string
        }
        Relationships: [
          {
            foreignKeyName: "wishlist_card_id_fkey"
            columns: ["card_id"]
            isOneToOne: false
            referencedRelation: "cards"
            referencedColumns: ["id"]
          },
        ]
      }
    }
    Views: {
      [_ in never]: never
    }
    Functions: {
      match_card: {
        Args: { match_count?: number; query_embedding: string }
        Returns: {
          artist: string
          hp: string
          id: string
          image_large: string
          image_small: string
          name: string
          number: string
          rarity: string
          set_id: string
          similarity: number
          subtypes: string[]
          supertype: string
        }[]
      }
      search_cards_fuzzy: {
        Args: { query: string; result_limit?: number; result_offset?: number }
        Returns: {
          artist: string
          hp: string
          id: string
          image_large: string
          image_small: string
          name: string
          number: string
          rarity: string
          set_id: string
          similarity: number
          subtypes: string[]
          supertype: string
          types: string[]
        }[]
      }
      show_limit: { Args: never; Returns: number }
      show_trgm: { Args: { "": string }; Returns: string[] }
    }
    Enums: {
      [_ in never]: never
    }
    CompositeTypes: {
      [_ in never]: never
    }
  }
}

type DatabaseWithoutInternals = Omit<Database, "__InternalSupabase">

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "public">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] &
        DefaultSchema["Views"])
    ? (DefaultSchema["Tables"] &
        DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
        Row: infer R
      }
      ? R
      : never
    : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Insert: infer I
      }
      ? I
      : never
    : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never,
> = DefaultSchemaTableNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
    ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
        Update: infer U
      }
      ? U
      : never
    : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never,
> = DefaultSchemaEnumNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
    ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
    : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never,
> = PublicCompositeTypeNameOrOptions extends {
  schema: keyof DatabaseWithoutInternals
}
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
    ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
    : never

export const Constants = {
  public: {
    Enums: {},
  },
} as const
