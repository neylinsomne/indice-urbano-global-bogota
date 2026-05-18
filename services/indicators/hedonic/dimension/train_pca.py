#!/usr/bin/env python3
"""
Cálculo de PCA para Indicador de Dimensión (I_Dim)

Calcula la Primera Componente Principal (PC1) de variables estructurales
para capturar el tamaño/envergadura del inmueble de forma no supervisada.

Variables usadas:
- area_construida, area_privada, habitaciones, banos, estrato
"""

import os
import sys
import psycopg2
import pandas as pd
import numpy as np
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
from datetime import datetime

# Configuración
DB_CONFIG = {
    'host': os.getenv('PG_HOST', 'localhost'),
    'port': os.getenv('PG_PORT', '5434'),
    'database': os.getenv('PG_DATABASE', 'postgres'),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD', 'postgres')
}

MIN_SAMPLES = 50  # Mínimo de muestras por tipo para calcular PCA

def extraer_datos(conn):
    """Extrae variables estructurales desde PostgreSQL"""
    
    query = """
        SELECT 
            id_inmueble,
            tipo_inmueble,
            area_construida,
            area_privada,
            habitaciones,
            banos
        FROM iug.inmueble
        WHERE 
            area_construida > 0
            AND tipo_inmueble IS NOT NULL
            AND tipo_inmueble != ''
    """
    
    print(f"[INFO] Extrayendo datos estructurales...")
    df = pd.read_sql(query, conn)
    
    print(f"[INFO] Total registros: {len(df)}")
    print(f"[INFO] Distribución por tipo:")
    print(df['tipo_inmueble'].value_counts())
    
    return df

def calcular_pca_tipo(df_tipo, tipo_nombre):
    """Calcula PCA para un tipo de inmueble"""
    
    print(f"\n[PCA] ========== {tipo_nombre} ==========")
    print(f"[PCA] Muestras: {len(df_tipo)}")
    
    # Variables para PCA (SOLO físicas de tamaño)
    features = ['area_construida', 'area_privada', 'habitaciones', 'banos']
    X = df_tipo[features].copy()
    
    # Estadísticas antes de imputación
    for col in features:
        missing = X[col].isna().sum()
        if missing > 0:
            print(f"[PCA]   {col}: {missing} faltantes ({100*missing/len(X):.1f}%)")
    
    # 1. Imputar valores faltantes con mediana
    imputer = SimpleImputer(strategy='median')
    X_imputed = imputer.fit_transform(X)
    X_imputed = pd.DataFrame(X_imputed, columns=features, index=X.index)
    
    # 2. Estandarizar (Z-score: media 0, std 1)
    scaler = StandardScaler()
    Z = scaler.fit_transform(X_imputed)
    
    # 3. Calcular PCA (solo primera componente)
    pca = PCA(n_components=1)
    PC1 = pca.fit_transform(Z)
    
    # Métricas
    explained_var = pca.explained_variance_ratio_[0]
    loadings = pca.components_[0]
    
    print(f"[PCA] Varianza explicada: {explained_var:.2%}")
    print(f"[PCA] Loadings (φ) - Variables físicas de tamaño:")
    for feature, loading in zip(features, loadings):
        print(f"  - {feature}: {loading:.6f}")
    
    # Retornar loadings y parámetros de estandarización
    return {
        'tipo_inmueble': tipo_nombre,
        'phi_area_construida': float(loadings[0]),
        'phi_area_privada': float(loadings[1]),
        'phi_habitaciones': float(loadings[2]),
        'phi_banos': float(loadings[3]),
        'mean_area_construida': float(scaler.mean_[0]),
        'std_area_construida': float(scaler.scale_[0]),
        'mean_area_privada': float(scaler.mean_[1]),
        'std_area_privada': float(scaler.scale_[1]),
        'mean_habitaciones': float(scaler.mean_[2]),
        'std_habitaciones': float(scaler.scale_[2]),
        'mean_banos': float(scaler.mean_[3]),
        'std_banos': float(scaler.scale_[3]),
        'explained_variance': float(explained_var),
        'n_samples': int(len(df_tipo))
    }

def guardar_loadings(conn, pca_result):
    """Guarda loadings en la base de datos"""
    
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO iug.pca_loadings_dimension (
                tipo_inmueble,
                phi_area_construida,
                phi_area_privada,
                phi_habitaciones,
                phi_banos,
                mean_area_construida,
                std_area_construida,
                mean_area_privada,
                std_area_privada,
                mean_habitaciones,
                std_habitaciones,
                mean_banos,
                std_banos,
                explained_variance,
                n_samples,
                fecha_calculo,
                version
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (tipo_inmueble) DO UPDATE SET
                phi_area_construida = EXCLUDED.phi_area_construida,
                phi_area_privada = EXCLUDED.phi_area_privada,
                phi_habitaciones = EXCLUDED.phi_habitaciones,
                phi_banos = EXCLUDED.phi_banos,
                mean_area_construida = EXCLUDED.mean_area_construida,
                std_area_construida = EXCLUDED.std_area_construida,
                mean_area_privada = EXCLUDED.mean_area_privada,
                std_area_privada = EXCLUDED.std_area_privada,
                mean_habitaciones = EXCLUDED.mean_habitaciones,
                std_habitaciones = EXCLUDED.std_habitaciones,
                mean_banos = EXCLUDED.mean_banos,
                std_banos = EXCLUDED.std_banos,
                explained_variance = EXCLUDED.explained_variance,
                n_samples = EXCLUDED.n_samples,
                fecha_calculo = now(),
                version = iug.pca_loadings_dimension.version + 1
        """, (
            pca_result['tipo_inmueble'],
            pca_result['phi_area_construida'],
            pca_result['phi_area_privada'],
            pca_result['phi_habitaciones'],
            pca_result['phi_banos'],
            pca_result['mean_area_construida'],
            pca_result['std_area_construida'],
            pca_result['mean_area_privada'],
            pca_result['std_area_privada'],
            pca_result['mean_habitaciones'],
            pca_result['std_habitaciones'],
            pca_result['mean_banos'],
            pca_result['std_banos'],
            pca_result['explained_variance'],
            pca_result['n_samples'],
            datetime.now(),
            1
        ))
    
    conn.commit()
    print(f"[DB] Loadings guardados para '{pca_result['tipo_inmueble']}'")

def main():
    """Función principal"""
    
    print("="*60)
    print(" CÁLCULO PCA - INDICADOR DE DIMENSIÓN (I_Dim)")
    print("="*60)
    
    # Conectar a BD
    print(f"\n[DB] Conectando a PostgreSQL ({DB_CONFIG['host']}:{DB_CONFIG['port']})...")
    conn = psycopg2.connect(**DB_CONFIG)
    
    try:
        # 1. Extraer datos
        df = extraer_datos(conn)
        
        # 2. Calcular PCA por tipo de inmueble
        print(f"\n{'='*60}")
        print(" CÁLCULO PCA POR TIPO DE INMUEBLE")
        print(f"{'='*60}")
        
        resultados = []
        
        for tipo in df['tipo_inmueble'].unique():
            df_tipo = df[df['tipo_inmueble'] == tipo]
            
            # Solo calcular si hay suficientes muestras
            if len(df_tipo) >= MIN_SAMPLES:
                pca_result = calcular_pca_tipo(df_tipo, tipo)
                guardar_loadings(conn, pca_result)
                resultados.append(pca_result)
            else:
                print(f"\n[SKIP] {tipo}: Solo {len(df_tipo)} muestras (mínimo {MIN_SAMPLES})")
        
        # 3. Resumen
        print(f"\n{'='*60}")
        print(" RESUMEN")
        print(f"{'='*60}")
        print(f"PCAs calculados: {len(resultados)}")
        for r in resultados:
            print(f"  {r['tipo_inmueble']}: {r['explained_variance']:.1%} varianza, n={r['n_samples']}")
        
        print(f"\n[SUCCESS] PCA completado")
        print(f"[INFO] Loadings guardados en iug.pca_loadings_dimension")
        print(f"[INFO] Próximo paso: Actualizar inmuebles para calcular PC1 scores")
        
    except Exception as e:
        print(f"\n[ERROR] {str(e)}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        sys.exit(1)
    
    finally:
        conn.close()

if __name__ == '__main__':
    main()
