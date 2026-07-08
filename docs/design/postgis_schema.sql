-- Legacy PostGIS schema — NOT used. The canonical store is Parquet + DuckDB (see build_store.py / prompt 10). Kept for reference only.

CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS entity (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  entity_type TEXT NOT NULL,
  ticker TEXT,
  lei TEXT,
  cik TEXT,
  country TEXT,
  sector TEXT,
  source TEXT,
  confidence DOUBLE PRECISION,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS asset (
  id TEXT PRIMARY KEY,
  asset_type TEXT NOT NULL CHECK (asset_type IN (
    'data_center',
    'factory',
    'farm',
    'agricultural_complex',
    'power_plant',
    'hydro_facility',
    'industrial_complex',
    'government_facility',
    'house',
    'parcel',
    'franchise_location',
    'agricultural_land',
    'commercial_property',
    'industrial_parcel',
    'data_center_site',
    'warehouse',
    'mixed_use_property'
  )),
  name TEXT NOT NULL,
  owner_entity_id TEXT REFERENCES entity(id),
  operator_entity_id TEXT REFERENCES entity(id),
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  geometry GEOMETRY(Geometry, 4326),
  address TEXT,
  country TEXT,
  state TEXT,
  county TEXT,
  city TEXT,
  area_acres DOUBLE PRECISION,
  status TEXT,
  source TEXT,
  confidence DOUBLE PRECISION,
  updated_at TIMESTAMPTZ DEFAULT now(),
  CHECK ((latitude IS NULL AND longitude IS NULL) OR (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180))
);

CREATE TABLE IF NOT EXISTS permit (
  id TEXT PRIMARY KEY,
  asset_id TEXT REFERENCES asset(id),
  permit_type TEXT,
  issuing_authority TEXT,
  approval_status TEXT,
  approval_date DATE,
  estimated_cost NUMERIC,
  public_url TEXT,
  source TEXT,
  confidence DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS farm_profile (
  asset_id TEXT PRIMARY KEY REFERENCES asset(id) ON DELETE CASCADE,
  farm_type TEXT,
  crop_history JSONB DEFAULT '[]'::jsonb,
  soil_quality TEXT,
  water_access TEXT,
  acres DOUBLE PRECISION,
  estimated_yield NUMERIC,
  annual_revenue_estimate NUMERIC,
  annual_cost_estimate NUMERIC,
  yearly_estimated_gain NUMERIC,
  past_activities JSONB DEFAULT '[]'::jsonb,
  risk_score DOUBLE PRECISION,
  last_sale_price NUMERIC,
  current_estimated_value NUMERIC
);

CREATE TABLE IF NOT EXISTS industrial_profile (
  asset_id TEXT PRIMARY KEY REFERENCES asset(id) ON DELETE CASCADE,
  industrial_type TEXT,
  estimated_project_cost NUMERIC,
  power_capacity_mw DOUBLE PRECISION,
  annual_growth DOUBLE PRECISION,
  demand_score DOUBLE PRECISION,
  revenue_estimate NUMERIC,
  operating_cost_estimate NUMERIC,
  permits_cost NUMERIC,
  owner_gain_loss_estimate NUMERIC,
  risk_score DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS camera_source (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  latitude DOUBLE PRECISION NOT NULL CHECK (latitude BETWEEN -90 AND 90),
  longitude DOUBLE PRECISION NOT NULL CHECK (longitude BETWEEN -180 AND 180),
  source_url TEXT NOT NULL,
  provider TEXT,
  camera_type TEXT,
  refresh_seconds INTEGER,
  legal_public_access BOOLEAN NOT NULL DEFAULT false,
  retention_policy TEXT,
  geometry GEOMETRY(Point, 4326) GENERATED ALWAYS AS (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326)) STORED
);

CREATE TABLE IF NOT EXISTS layer_feature (
  id TEXT PRIMARY KEY,
  layer_type TEXT NOT NULL,
  name TEXT,
  geometry GEOMETRY(Geometry, 4326) NOT NULL,
  properties_json JSONB DEFAULT '{}'::jsonb,
  source TEXT,
  confidence DOUBLE PRECISION,
  updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS asset_listing (
  id TEXT PRIMARY KEY,
  asset_id TEXT REFERENCES asset(id),
  listing_type TEXT,
  asset_type TEXT,
  title TEXT NOT NULL,
  price NUMERIC,
  currency TEXT DEFAULT 'USD',
  price_per_acre NUMERIC,
  price_per_sqft NUMERIC,
  acreage DOUBLE PRECISION,
  square_feet DOUBLE PRECISION,
  bedrooms DOUBLE PRECISION,
  bathrooms DOUBLE PRECISION,
  zoning TEXT,
  address TEXT,
  latitude DOUBLE PRECISION,
  longitude DOUBLE PRECISION,
  geometry GEOMETRY(Geometry, 4326),
  seller_name TEXT,
  broker_name TEXT,
  listing_url TEXT,
  listing_status TEXT,
  listed_date DATE,
  last_updated TIMESTAMPTZ,
  source TEXT,
  confidence DOUBLE PRECISION,
  CHECK ((latitude IS NULL AND longitude IS NULL) OR (latitude BETWEEN -90 AND 90 AND longitude BETWEEN -180 AND 180))
);

CREATE TABLE IF NOT EXISTS asset_relationship (
  id TEXT PRIMARY KEY,
  source_id TEXT NOT NULL,
  target_id TEXT NOT NULL,
  relationship_type TEXT NOT NULL,
  source TEXT,
  confidence DOUBLE PRECISION,
  as_of_date DATE,
  updated_at TIMESTAMPTZ DEFAULT now(),
  status TEXT DEFAULT 'inferred'
);

CREATE TABLE IF NOT EXISTS evidence (
  id TEXT PRIMARY KEY,
  linked_object_type TEXT NOT NULL CHECK (linked_object_type IN (
    'entity', 'asset', 'relationship', 'permit', 'listing', 'valuation',
    'risk_score', 'camera', 'layer_feature'
  )),
  linked_object_id TEXT NOT NULL,
  claim_type TEXT NOT NULL,
  claim_value JSONB,
  source_name TEXT,
  source_url TEXT,
  source_document_id TEXT,
  source_date DATE,
  retrieved_at TIMESTAMPTZ DEFAULT now(),
  confidence DOUBLE PRECISION,
  extraction_method TEXT,
  notes TEXT,
  status TEXT DEFAULT 'inferred'
);

CREATE TABLE IF NOT EXISTS user_override (
  id TEXT PRIMARY KEY,
  object_type TEXT NOT NULL,
  object_id TEXT NOT NULL,
  field_name TEXT NOT NULL,
  old_value JSONB,
  new_value JSONB,
  user_note TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  review_status TEXT DEFAULT 'pending'
);

CREATE OR REPLACE VIEW entity_asset_bridge AS
SELECT
  source_id AS entity_id,
  target_id AS asset_id,
  relationship_type,
  source,
  confidence,
  updated_at,
  status
FROM asset_relationship
WHERE source_id NOT LIKE 'asset:%'
  AND target_id LIKE 'asset:%';

CREATE OR REPLACE VIEW needs_location AS
SELECT id, asset_type, name, source, updated_at
FROM asset
WHERE latitude IS NULL OR longitude IS NULL OR geometry IS NULL;

CREATE INDEX IF NOT EXISTS asset_geometry_gix ON asset USING gist (geometry);
CREATE INDEX IF NOT EXISTS asset_type_idx ON asset (asset_type);
CREATE INDEX IF NOT EXISTS asset_owner_idx ON asset (owner_entity_id);
CREATE INDEX IF NOT EXISTS asset_operator_idx ON asset (operator_entity_id);
CREATE INDEX IF NOT EXISTS permit_asset_idx ON permit (asset_id);
CREATE INDEX IF NOT EXISTS camera_source_geometry_gix ON camera_source USING gist (geometry);
CREATE INDEX IF NOT EXISTS camera_source_public_idx ON camera_source (legal_public_access);
CREATE INDEX IF NOT EXISTS layer_feature_geometry_gix ON layer_feature USING gist (geometry);
CREATE INDEX IF NOT EXISTS layer_feature_type_idx ON layer_feature (layer_type);
CREATE INDEX IF NOT EXISTS asset_listing_geometry_gix ON asset_listing USING gist (geometry);
CREATE INDEX IF NOT EXISTS asset_listing_type_idx ON asset_listing (asset_type);
CREATE INDEX IF NOT EXISTS asset_listing_status_idx ON asset_listing (listing_status);
CREATE INDEX IF NOT EXISTS asset_relationship_source_idx ON asset_relationship (source_id);
CREATE INDEX IF NOT EXISTS asset_relationship_target_idx ON asset_relationship (target_id);
CREATE INDEX IF NOT EXISTS evidence_object_idx ON evidence (linked_object_type, linked_object_id);
CREATE INDEX IF NOT EXISTS evidence_claim_idx ON evidence (claim_type);
CREATE INDEX IF NOT EXISTS user_override_object_idx ON user_override (object_type, object_id);
