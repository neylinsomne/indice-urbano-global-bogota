-- Catálogos base (con nombres cualificados)
CREATE TABLE IF NOT EXISTS iug.cat_tipo_inmueble (
  tipo_inmueble TEXT PRIMARY KEY
);

INSERT INTO iug.cat_tipo_inmueble (tipo_inmueble)
VALUES ('Apartamento'), ('Casa'), ('PH'), ('Lote')
ON CONFLICT DO NOTHING;

CREATE TABLE IF NOT EXISTS iug.cat_estado_inmueble (
  estado TEXT PRIMARY KEY
);

INSERT INTO iug.cat_estado_inmueble (estado)
VALUES ('Nuevos'), ('Usados'), ('En construcción')
ON CONFLICT DO NOTHING;
