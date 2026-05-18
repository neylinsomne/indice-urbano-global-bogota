#!/usr/bin/env python3
"""
Script de Entrenamiento del Modelo Hedónico de Precios

Entrena modelos de regresión lineal para predecir ln(Precio/m²) 
basado en características estructurales del inmueble.

Modelo por tipo de inmueble:
- ln(precio_m2) = α + β_area·Area + β_hab·Habitaciones + β_banos·Baños + β_parq·Parqueaderos + ε
"""

import os
import sys
import json
import psycopg2
import pandas as pd
import numpy as np
from sklearn.linear_model import LinearRegression
from sklearn.model_selection import train_test_split
from sklearn.metrics import r2_score, mean_squared_error, mean_absolute_error
from datetime import datetime

# Configuración de base de datos
DB_CONFIG = {
    'host': os.getenv('PG_HOST', 'localhost'),
    'port': os.getenv('PG_PORT', '5434'),
    'database': os.getenv('PG_DATABASE', 'postgres'),
    'user': os.getenv('PG_USER', 'postgres'),
    'password': os.getenv('PG_PASSWORD', 'postgres')
}

# Tipos de inmueble a modelar (mínimo 30 muestras)
MIN_SAMPLES = 30

def extraer_datos(conn):
    """Extrae datos de inmuebles válidos desde PostgreSQL"""
    
    query = """
        SELECT 
            id_inmueble,
            tipo_inmueble,
            precio,
            area_construida,
            habitaciones,
            banos,
            parqueadero,
            estrato
        FROM iug.inmueble
        WHERE 
            precio > 0 
            AND area_construida > 0
            AND tipo_inmueble IS NOT NULL
            AND tipo_inmueble != ''
    """
    
    print(f"[INFO] Extrayendo datos de inmuebles...")
    df = pd.read_sql(query, conn)
    
    print(f"[INFO] Total registros extraídos: {len(df)}")
    print(f"[INFO] Distribución por tipo:")
    print(df['tipo_inmueble'].value_counts())
    
    return df

def preparar_datos(df):
    """Prepara datos para el modelo"""
    
    # Calcular precio por m²
    df['precio_m2'] = df['precio'] / df['area_construida']
    
    # Aplicar transformación logarítmica
    df['ln_precio_m2'] = np.log(df['precio_m2'])
    
    # Imputar valores faltantes
    df['habitaciones'] = df['habitaciones'].fillna(df.groupby('tipo_inmueble')['habitaciones'].transform('median'))
    df['banos'] = df['banos'].fillna(df.groupby('tipo_inmueble')['banos'].transform('median'))
    df['parqueadero'] = df['parqueadero'].fillna(0)
    df['estrato'] = df['estrato'].fillna(df['estrato'].median())
    
    # Eliminar outliers extremos (más de 3 desviaciones estándar)
    mean_ln = df['ln_precio_m2'].mean()
    std_ln = df['ln_precio_m2'].std()
    df_clean = df[
        (df['ln_precio_m2'] >= mean_ln - 3*std_ln) & 
        (df['ln_precio_m2'] <= mean_ln + 3*std_ln)
    ].copy()
    
    outliers_removed = len(df) - len(df_clean)
    if outliers_removed > 0:
        print(f"[INFO] Outliers removidos: {outliers_removed} ({100*outliers_removed/len(df):.1f}%)")
    
    return df_clean

def entrenar_modelo(df_tipo, tipo_nombre):
    """Entrena modelo de regresión para un tipo de inmueble"""
    
    print(f"\n[TRAIN] ========== {tipo_nombre} ==========")
    print(f"[TRAIN] Muestras: {len(df_tipo)}")
    
    # Variables independientes (X)
    features = ['area_construida', 'habitaciones', 'banos', 'parqueadero', 'estrato']
    X = df_tipo[features].copy()
    
    # Variable dependiente (y)
    y = df_tipo['ln_precio_m2']
    
    # Split train/test (80/20)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42
    )
    
    # Entrenar modelo
    model = LinearRegression()
    model.fit(X_train, y_train)
    
    # Predicciones
    y_pred_train = model.predict(X_train)
    y_pred_test = model.predict(X_test)
    
    # Métricas
    r2_train = r2_score(y_train, y_pred_train)
    r2_test = r2_score(y_test, y_pred_test)
    rmse_test = np.sqrt(mean_squared_error(y_test, y_pred_test))
    mae_test = mean_absolute_error(y_test, y_pred_test)
    
    print(f"[TRAIN] R² (train): {r2_train:.4f}")
    print(f"[TRAIN] R² (test):  {r2_test:.4f}")
    print(f"[TRAIN] RMSE (test): {rmse_test:.4f}")
    print(f"[TRAIN] MAE (test):  {mae_test:.4f}")
    
    # Coeficientes
    print(f"[TRAIN] Coeficientes:")
    print(f"  - Intercept: {model.intercept_:.6f}")
    for feature, coef in zip(features, model.coef_):
        print(f"  - {feature}: {coef:.6f}")
    
    # Estadísticas del score para normalización futura
    scores_all = model.predict(X)
    
    return {
        'intercept': float(model.intercept_),
        'coef_area': float(model.coef_[0]),
        'coef_habitaciones': float(model.coef_[1]),
        'coef_banos': float(model.coef_[2]),
        'coef_parqueaderos': float(model.coef_[3]),
        'coef_estrato': float(model.coef_[4]),
        'r2_score': float(r2_test),
        'rmse': float(rmse_test),
        'mae': float(mae_test),
        'n_samples': int(len(df_tipo)),
        'min_score': float(scores_all.min()),
        'max_score': float(scores_all.max()),
        'mean_score': float(scores_all.mean()),
        'std_score': float(scores_all.std())
    }

def guardar_coeficientes(conn, tipo_nombre, coefs):
    """Guarda coeficientes en la base de datos"""
    
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO iug.hedonic_model_coefs (
                tipo_inmueble,
                intercept,
                coef_area,
                coef_habitaciones,
                coef_banos,
                coef_parqueaderos,
                coef_estrato,
                r2_score,
                rmse,
                mae,
                n_samples,
                min_score,
                max_score,
                mean_score,
                std_score,
                fecha_entrenamiento,
                version
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT (tipo_inmueble) DO UPDATE SET
                intercept = EXCLUDED.intercept,
                coef_area = EXCLUDED.coef_area,
                coef_habitaciones = EXCLUDED.coef_habitaciones,
                coef_banos = EXCLUDED.coef_banos,
                coef_parqueaderos = EXCLUDED.coef_parqueaderos,
                coef_estrato = EXCLUDED.coef_estrato,
                r2_score = EXCLUDED.r2_score,
                rmse = EXCLUDED.rmse,
                mae = EXCLUDED.mae,
                n_samples = EXCLUDED.n_samples,
                min_score = EXCLUDED.min_score,
                max_score = EXCLUDED.max_score,
                mean_score = EXCLUDED.mean_score,
                std_score = EXCLUDED.std_score,
                fecha_entrenamiento = now(),
                version = iug.hedonic_model_coefs.version + 1
        """, (
            tipo_nombre,
            coefs['intercept'],
            coefs['coef_area'],
            coefs['coef_habitaciones'],
            coefs['coef_banos'],
            coefs['coef_parqueaderos'],
            coefs['coef_estrato'],
            coefs['r2_score'],
            coefs['rmse'],
            coefs['mae'],
            coefs['n_samples'],
            coefs['min_score'],
            coefs['max_score'],
            coefs['mean_score'],
            coefs['std_score'],
            datetime.now(),
            1
        ))
    
    conn.commit()
    print(f"[DB] Coeficientes guardados para '{tipo_nombre}'")

def main():
    """Función principal"""
    
    print("="*60)
    print(" ENTRENAMIENTO MODELO HEDÓNICO DE PRECIOS")
    print("="*60)
    
    # Conectar a base de datos
    print(f"\n[DB] Conectando a PostgreSQL ({DB_CONFIG['host']}:{DB_CONFIG['port']})...")
    conn = psycopg2.connect(**DB_CONFIG)
    
    try:
        # 1. Extraer datos
        df = extraer_datos(conn)
        
        # 2. Preparar datos
        df_clean = preparar_datos(df)
        
        # 3. Entrenar modelo por tipo
        print(f"\n{'='*60}")
        print(" ENTRENAMIENTO POR TIPO DE INMUEBLE")
        print(f"{'='*60}")
        
        resultados = {}
        
        for tipo in df_clean['tipo_inmueble'].unique():
            df_tipo = df_clean[df_clean['tipo_inmueble'] == tipo]
            
            # Solo entrenar si hay suficientes muestras
            if len(df_tipo) >= MIN_SAMPLES:
                coefs = entrenar_modelo(df_tipo, tipo)
                guardar_coeficientes(conn, tipo, coefs)
                resultados[tipo] = coefs
            else:
                print(f"\n[SKIP] {tipo}: Solo {len(df_tipo)} muestras (mínimo {MIN_SAMPLES})")
        
        # 4. Resumen final
        print(f"\n{'='*60}")
        print(" RESUMEN")
        print(f"{'='*60}")
        print(f"Modelos entrenados: {len(resultados)}")
        for tipo, coefs in resultados.items():
            print(f"  {tipo}: R²={coefs['r2_score']:.3f}, RMSE={coefs['rmse']:.3f}, n={coefs['n_samples']}")
        
        print(f"\n[SUCCESS] Modelos guardados en iug.hedonic_model_coefs")
        print(f"[INFO] Próximo paso: Ejecutar trigger para calcular scores en inmuebles existentes")
        
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
