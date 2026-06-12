-- ╔═════════════════════════════════════════════════════════════════╗
-- ║ AdhikarAI - Supabase pgvector Migration Script                 ║
-- ║ Run this in Supabase SQL Editor to set up vector DB            ║
-- ╚═════════════════════════════════════════════════════════════════╝

-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Create legal_documents table with vector embeddings
CREATE TABLE IF NOT EXISTS legal_documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  domain TEXT NOT NULL DEFAULT 'general',
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  embedding vector(1024),
  source TEXT DEFAULT 'ingested',
  url TEXT,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'legal_documents'
  ) THEN
    ALTER TABLE legal_documents ADD COLUMN IF NOT EXISTS url TEXT;
  END IF;
END $$;

-- 3. Create indexes for performance
DROP INDEX IF EXISTS legal_docs_url_idx;
CREATE INDEX IF NOT EXISTS legal_docs_embedding_idx 
  ON legal_documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX IF NOT EXISTS legal_docs_domain_idx 
  ON legal_documents(domain);

CREATE INDEX IF NOT EXISTS legal_docs_source_idx 
  ON legal_documents(source);

CREATE INDEX IF NOT EXISTS legal_docs_url_idx 
  ON legal_documents(url);

CREATE INDEX IF NOT EXISTS legal_docs_content_idx 
  ON legal_documents USING GIN(to_tsvector('english', content));

-- 4. Create search function for pgvector similarity search
CREATE OR REPLACE FUNCTION search_legal_documents(
  query_embedding vector(1024),
  search_domain TEXT DEFAULT 'general',
  match_count INT DEFAULT 5
)
RETURNS TABLE(
  id UUID,
  title TEXT,
  content TEXT,
  domain TEXT,
  source TEXT,
  metadata JSONB,
  similarity FLOAT8
) AS $$
BEGIN
  RETURN QUERY
  SELECT 
    legal_documents.id,
    legal_documents.title,
    legal_documents.content,
    legal_documents.domain,
    legal_documents.source,
    legal_documents.metadata,
    1 - (legal_documents.embedding <=> query_embedding) as similarity
  FROM legal_documents
  WHERE 
    (search_domain = 'general' OR legal_documents.domain = search_domain OR legal_documents.domain = 'general')
  ORDER BY legal_documents.embedding <=> query_embedding
  LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- 5. Enable Row Level Security (RLS) - Optional but recommended
ALTER TABLE legal_documents ENABLE ROW LEVEL SECURITY;

-- 6. Create policy for public read access
DROP POLICY IF EXISTS "Allow public read" ON legal_documents;
CREATE POLICY "Allow public read" 
  ON legal_documents FOR SELECT 
  TO public 
  USING (true);

-- 7. Create policy for authenticated insert/update
DROP POLICY IF EXISTS "Allow authenticated users to insert" ON legal_documents;
CREATE POLICY "Allow authenticated users to insert" 
  ON legal_documents FOR INSERT 
  TO authenticated 
  WITH CHECK (true);

DROP POLICY IF EXISTS "Allow authenticated users to update" ON legal_documents;
CREATE POLICY "Allow authenticated users to update" 
  ON legal_documents FOR UPDATE 
  TO authenticated 
  USING (true);

-- 8. Create conversations table for chat history
CREATE TABLE IF NOT EXISTS conversations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT DEFAULT 'New Chat',
  domain TEXT DEFAULT 'general',
  language TEXT DEFAULT 'en',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- 9. Create messages table linked to conversations
CREATE TABLE IF NOT EXISTS messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id UUID NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS messages_conversation_idx 
  ON messages(conversation_id);

CREATE INDEX IF NOT EXISTS conversations_domain_idx 
  ON conversations(domain);

-- 10. Enable RLS on conversations and messages
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow public read conversations" ON conversations;
CREATE POLICY "Allow public read conversations" 
  ON conversations FOR SELECT TO public USING (true);

DROP POLICY IF EXISTS "Allow public read messages" ON messages;
CREATE POLICY "Allow public read messages" 
  ON messages FOR SELECT TO public USING (true);

DROP POLICY IF EXISTS "Allow authenticated insert conversations" ON conversations;
CREATE POLICY "Allow authenticated insert conversations" 
  ON conversations FOR INSERT TO authenticated WITH CHECK (true);

DROP POLICY IF EXISTS "Allow authenticated insert messages" ON messages;
CREATE POLICY "Allow authenticated insert messages" 
  ON messages FOR INSERT TO authenticated WITH CHECK (true);

-- 11. Create updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = NOW();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS update_legal_documents_updated_at ON legal_documents;
CREATE TRIGGER update_legal_documents_updated_at
  BEFORE UPDATE ON legal_documents
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_conversations_updated_at ON conversations;
CREATE TRIGGER update_conversations_updated_at
  BEFORE UPDATE ON conversations
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- 12. Full-text (keyword / BM25-style) search function for hybrid retrieval
CREATE OR REPLACE FUNCTION fulltext_search_legal_documents(
  query_text TEXT,
  search_domain TEXT DEFAULT 'general',
  match_count INT DEFAULT 5
)
RETURNS TABLE(
  id UUID,
  title TEXT,
  content TEXT,
  domain TEXT,
  source TEXT,
  metadata JSONB,
  similarity FLOAT8
) AS $$
BEGIN
  RETURN QUERY
  SELECT
    legal_documents.id,
    legal_documents.title,
    legal_documents.content,
    legal_documents.domain,
    legal_documents.source,
    legal_documents.metadata,
    ts_rank(
      to_tsvector('english', legal_documents.content),
      plainto_tsquery('english', query_text)
    )::FLOAT8 AS similarity
  FROM legal_documents
  WHERE
    (search_domain = 'general' OR legal_documents.domain = search_domain OR legal_documents.domain = 'general')
    AND to_tsvector('english', legal_documents.content) @@ plainto_tsquery('english', query_text)
  ORDER BY similarity DESC
  LIMIT match_count;
END;
$$ LANGUAGE plpgsql;

-- 13. Chat persistence tables (JSONB transcript + optional name metadata)
CREATE TABLE IF NOT EXISTS chats (
  id TEXT PRIMARY KEY,
  messages JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS chat_metadata (
  id TEXT PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,
  name TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chats_updated_at ON chats(updated_at DESC);

ALTER TABLE chats ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_metadata ENABLE ROW LEVEL SECURITY;

-- Public can read; only the service role (used by the backend) may write.
DROP POLICY IF EXISTS "Allow public read chats" ON chats;
CREATE POLICY "Allow public read chats" ON chats FOR SELECT TO public USING (true);
DROP POLICY IF EXISTS "Allow service write chats" ON chats;
CREATE POLICY "Allow service write chats" ON chats FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP POLICY IF EXISTS "Allow public read chat_metadata" ON chat_metadata;
CREATE POLICY "Allow public read chat_metadata" ON chat_metadata FOR SELECT TO public USING (true);
DROP POLICY IF EXISTS "Allow service write chat_metadata" ON chat_metadata;
CREATE POLICY "Allow service write chat_metadata" ON chat_metadata FOR ALL TO service_role USING (true) WITH CHECK (true);

DROP TRIGGER IF EXISTS update_chats_updated_at ON chats;
CREATE TRIGGER update_chats_updated_at
  BEFORE UPDATE ON chats
  FOR EACH ROW
  EXECUTE FUNCTION update_updated_at_column();

-- 14. Verify setup
SELECT 'pgvector extension' as check_item, EXISTS(SELECT 1 FROM pg_extension WHERE extname = 'vector') as result
UNION ALL
SELECT 'legal_documents table', EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'legal_documents')
UNION ALL
SELECT 'vector search function', EXISTS(SELECT 1 FROM pg_proc WHERE proname = 'search_legal_documents')
UNION ALL
SELECT 'fulltext search function', EXISTS(SELECT 1 FROM pg_proc WHERE proname = 'fulltext_search_legal_documents')
UNION ALL
SELECT 'chats table', EXISTS(SELECT 1 FROM information_schema.tables WHERE table_name = 'chats');
