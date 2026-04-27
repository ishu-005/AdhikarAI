-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Create chats table for storing conversations
CREATE TABLE IF NOT EXISTS chats (
  id TEXT PRIMARY KEY,
  messages JSONB NOT NULL DEFAULT '[]',
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create chat_metadata table for storing chat names and metadata
CREATE TABLE IF NOT EXISTS chat_metadata (
  id TEXT PRIMARY KEY REFERENCES chats(id) ON DELETE CASCADE,
  name TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create documents table for storing embeddings
CREATE TABLE IF NOT EXISTS documents (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  content TEXT NOT NULL,
  embedding VECTOR(384),
  metadata JSONB DEFAULT '{}',
  domain TEXT,
  filename TEXT,
  created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
  updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better query performance
CREATE INDEX idx_chats_created_at ON chats(created_at DESC);
CREATE INDEX idx_chat_metadata_created_at ON chat_metadata(created_at DESC);
CREATE INDEX idx_documents_domain ON documents(domain);
CREATE INDEX idx_documents_embedding ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_documents_created_at ON documents(created_at DESC);

-- Add RLS (Row Level Security) policies if needed
ALTER TABLE chats ENABLE ROW LEVEL SECURITY;
ALTER TABLE chat_metadata ENABLE ROW LEVEL SECURITY;
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

-- Create policies for public access (modify as needed for your security model)
CREATE POLICY "Allow public read on chats" ON chats FOR SELECT USING (true);
CREATE POLICY "Allow public insert on chats" ON chats FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow public update on chats" ON chats FOR UPDATE USING (true);
CREATE POLICY "Allow public delete on chats" ON chats FOR DELETE USING (true);

CREATE POLICY "Allow public read on chat_metadata" ON chat_metadata FOR SELECT USING (true);
CREATE POLICY "Allow public insert on chat_metadata" ON chat_metadata FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow public update on chat_metadata" ON chat_metadata FOR UPDATE USING (true);
CREATE POLICY "Allow public delete on chat_metadata" ON chat_metadata FOR DELETE USING (true);

CREATE POLICY "Allow public read on documents" ON documents FOR SELECT USING (true);
CREATE POLICY "Allow public insert on documents" ON documents FOR INSERT WITH CHECK (true);
CREATE POLICY "Allow public update on documents" ON documents FOR UPDATE USING (true);
CREATE POLICY "Allow public delete on documents" ON documents FOR DELETE USING (true);
