-- =====================================================
-- Extensión pgvector para almacenar embeddings
-- =====================================================
-- Nota: Si pgvector no está disponible en el servidor,
-- esta migración se salta silenciosamente.
-- Para instalar pgvector: apt-get install postgresql-16-pgvector

DO $$
BEGIN
    -- Intentar crear extensión vector
    CREATE EXTENSION IF NOT EXISTS vector;

    -- Si llegamos aquí, pgvector está disponible
    RAISE NOTICE 'pgvector disponible, creando tablas de embeddings...';

    -- Tabla para embeddings de dotaciones
    CREATE TABLE IF NOT EXISTS iug.dotaciones_embeddings (
        id SERIAL PRIMARY KEY,
        dotacion_id INTEGER REFERENCES iug.dotaciones_poi(id) ON DELETE CASCADE,
        nombre TEXT NOT NULL,
        categoria VARCHAR(100),
        embedding vector(1536),
        created_at TIMESTAMP DEFAULT NOW(),
        UNIQUE(dotacion_id)
    );

    CREATE INDEX IF NOT EXISTS idx_dotaciones_embedding_hnsw
    ON iug.dotaciones_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

    CREATE INDEX IF NOT EXISTS idx_dotaciones_embeddings_categoria
    ON iug.dotaciones_embeddings(categoria);

    -- Tabla para cache de queries
    CREATE TABLE IF NOT EXISTS iug.query_embeddings_cache (
        id SERIAL PRIMARY KEY,
        query_text TEXT NOT NULL,
        query_hash VARCHAR(64) UNIQUE NOT NULL,
        embedding vector(1536),
        resultado JSONB,
        hits INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT NOW(),
        last_accessed TIMESTAMP DEFAULT NOW()
    );

    CREATE INDEX IF NOT EXISTS idx_query_cache_hash
    ON iug.query_embeddings_cache(query_hash);

EXCEPTION
    WHEN OTHERS THEN
        RAISE NOTICE 'pgvector no disponible: %. Tablas de embeddings no creadas.', SQLERRM;
END;
$$;

-- Funciones se crean solo si las tablas existen
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='iug' AND table_name='dotaciones_embeddings') THEN
        EXECUTE $func$
            CREATE OR REPLACE FUNCTION iug.buscar_dotaciones_similares(
                query_embedding vector(1536),
                limite INTEGER DEFAULT 20,
                umbral_similitud FLOAT DEFAULT 0.7
            )
            RETURNS TABLE (
                dotacion_id INTEGER,
                nombre TEXT,
                categoria VARCHAR(100),
                similitud FLOAT
            ) AS $inner$
            BEGIN
                RETURN QUERY
                SELECT
                    de.dotacion_id,
                    de.nombre,
                    de.categoria,
                    (1 - (de.embedding <=> query_embedding))::FLOAT as similitud
                FROM iug.dotaciones_embeddings de
                WHERE (1 - (de.embedding <=> query_embedding)) >= umbral_similitud
                ORDER BY de.embedding <=> query_embedding
                LIMIT limite;
            END;
            $inner$ LANGUAGE plpgsql;
        $func$;

        EXECUTE $func$
            CREATE OR REPLACE FUNCTION iug.limpiar_cache_queries(dias_antiguedad INTEGER DEFAULT 7)
            RETURNS INTEGER AS $inner$
            DECLARE
                eliminados INTEGER;
            BEGIN
                DELETE FROM iug.query_embeddings_cache
                WHERE last_accessed < NOW() - (dias_antiguedad || ' days')::INTERVAL;
                GET DIAGNOSTICS eliminados = ROW_COUNT;
                RETURN eliminados;
            END;
            $inner$ LANGUAGE plpgsql;
        $func$;

        RAISE NOTICE 'Funciones de búsqueda semántica creadas.';
    ELSE
        RAISE NOTICE 'Tablas de embeddings no existen, funciones no creadas.';
    END IF;
END;
$$;
