-- Indicadores zonales por barrio
CREATE TABLE IF NOT EXISTS iug.indicador_barrio (
  id_barrio INT PRIMARY KEY REFERENCES iug.barrio(id_barrio) ON DELETE CASCADE,
  iacc NUMERIC(6,3),
  iseg NUMERIC(6,3),
  idot NUMERIC(6,3),
  ipnu NUMERIC(6,3),
  iug  NUMERIC(6,3),
  updated_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS iug_idx_ind_barrio_iacc ON iug.indicador_barrio (iacc);
CREATE INDEX IF NOT EXISTS iug_idx_ind_barrio_iseg ON iug.indicador_barrio (iseg);

-- 1) Trigger: cuando cambian indicadores del barrio → propaga y recalcula
CREATE OR REPLACE FUNCTION iug.f_sync_indicadores_barrio()
RETURNS TRIGGER AS $$
DECLARE
  w1 NUMERIC := 1.0;
  w2 NUMERIC := 1.0;
  w3 NUMERIC := 1.0;
  w4 NUMERIC := 1.0;
  w5 NUMERIC := 1.0;
BEGIN
  -- Propagar subíndices
  UPDATE iug.inmueble i
     SET iacc = nb.iacc,
         iseg = nb.iseg,
         idot = nb.idot,
         ipnu = nb.ipnu
    FROM iug.indicador_barrio nb
   WHERE i.id_barrio = nb.id_barrio
     AND nb.id_barrio = NEW.id_barrio;

  -- Recalcular IUG y ratio
  UPDATE iug.inmueble i
     SET iug = ROUND((
            COALESCE(i.ihed,0)*w1 + COALESCE(i.iacc,0)*w2 + COALESCE(i.iseg,0)*w3
          + COALESCE(i.idot,0)*w4 + COALESCE(i.ipnu,0)*w5
         ) / (w1+w2+w3+w4+w5), 3),
         ratio = CASE
           WHEN i.precio_std IS NULL OR i.precio_std = 0 THEN NULL
           ELSE ROUND((
                  (COALESCE(i.ihed,0)*w1 + COALESCE(i.iacc,0)*w2 + COALESCE(i.iseg,0)*w3
                 + COALESCE(i.idot,0)*w4 + COALESCE(i.ipnu,0)*w5) / (w1+w2+w3+w4+w5)
                ) / i.precio_std, 4)
         END
   WHERE i.id_barrio = NEW.id_barrio;

  -- Timestamp
  UPDATE iug.indicador_barrio
     SET updated_at = now()
   WHERE id_barrio = NEW.id_barrio;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sync_ind_barrio ON iug.indicador_barrio;
CREATE TRIGGER trg_sync_ind_barrio
AFTER INSERT OR UPDATE OF iacc, iseg, idot, ipnu, iug
ON iug.indicador_barrio
FOR EACH ROW EXECUTE FUNCTION iug.f_sync_indicadores_barrio();

-- 2) Trigger: si cambia id_barrio / ihed / precio_std del inmueble → recalcula
CREATE OR REPLACE FUNCTION iug.f_inmueble_on_barrio_change()
RETURNS TRIGGER AS $$
DECLARE
  rec iug.indicador_barrio%ROWTYPE;
  w1 NUMERIC := 1.0;
  w2 NUMERIC := 1.0;
  w3 NUMERIC := 1.0;
  w4 NUMERIC := 1.0;
  w5 NUMERIC := 1.0;
BEGIN
  IF NEW.id_barrio IS NOT NULL THEN
    SELECT * INTO rec FROM iug.indicador_barrio WHERE id_barrio = NEW.id_barrio;
    IF FOUND THEN
      NEW.iacc := rec.iacc;
      NEW.iseg := rec.iseg;
      NEW.idot := rec.idot;
      NEW.ipnu := rec.ipnu;
      NEW.iug := ROUND((
          COALESCE(NEW.ihed,0)*w1 + COALESCE(NEW.iacc,0)*w2 + COALESCE(NEW.iseg,0)*w3
        + COALESCE(NEW.idot,0)*w4 + COALESCE(NEW.ipnu,0)*w5
      ) / (w1+w2+w3+w4+w5), 3);
      NEW.ratio := CASE
        WHEN NEW.precio_std IS NULL OR NEW.precio_std = 0 THEN NULL
        ELSE ROUND(NEW.iug / NEW.precio_std, 4)
      END;
    END IF;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_inmueble_barrio_change ON iug.inmueble;
CREATE TRIGGER trg_inmueble_barrio_change
BEFORE INSERT OR UPDATE OF id_barrio, ihed, precio_std
ON iug.inmueble
FOR EACH ROW EXECUTE FUNCTION iug.f_inmueble_on_barrio_change();

-- 3) (Opcional pero muy útil)
--    Si insertas/actualizas geom, auto-asigna barrio/localidad vía overlay
CREATE OR REPLACE FUNCTION iug.f_snap_inmueble_barrios()
RETURNS TRIGGER AS $$
DECLARE
  b_id INT;
  l_id INT;
BEGIN
  IF NEW.geom IS NOT NULL THEN
    SELECT b.id_barrio, b.id_localidad
      INTO b_id, l_id
      FROM iug.barrio b
     WHERE ST_Contains(b.geom, NEW.geom)
     LIMIT 1;

    IF b_id IS NOT NULL THEN
      NEW.id_barrio := b_id;
      NEW.id_localidad := l_id;
    ELSE
      -- fallback por localidad si aplica
      SELECT l.id_localidad
        INTO l_id
        FROM iug.localidad l
       WHERE ST_Contains(l.geom, NEW.geom)
       LIMIT 1;
      IF l_id IS NOT NULL THEN
        NEW.id_localidad := l_id;
      END IF;
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_inmueble_snap_geom ON iug.inmueble;
CREATE TRIGGER trg_inmueble_snap_geom
BEFORE INSERT OR UPDATE OF geom
ON iug.inmueble
FOR EACH ROW EXECUTE FUNCTION iug.f_snap_inmueble_barrios();


-- Backfill por si ya tienes barrios cargados sin id_localidad
UPDATE iug.barrio b
SET id_localidad = l.id_localidad
FROM iug.localidad l
WHERE b.id_localidad IS NULL
  AND ST_Contains(l.geom, ST_PointOnSurface(b.geom));

-- Trigger para mantenerlo a futuro
CREATE OR REPLACE FUNCTION iug.f_snap_barrio_localidad()
RETURNS TRIGGER AS $$
DECLARE
  loc_id INT;
BEGIN
  IF NEW.geom IS NOT NULL THEN
    SELECT id_localidad INTO loc_id
    FROM iug.localidad
    WHERE ST_Contains(geom, ST_PointOnSurface(NEW.geom))
    LIMIT 1;

    IF loc_id IS NOT NULL THEN
      NEW.id_localidad := loc_id;
    END IF;
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_barrio_snap_localidad ON iug.barrio;
CREATE TRIGGER trg_barrio_snap_localidad
BEFORE INSERT OR UPDATE OF geom
ON iug.barrio
FOR EACH ROW EXECUTE FUNCTION iug.f_snap_barrio_localidad();
