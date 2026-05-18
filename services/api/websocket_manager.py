"""
WebSocket Connection Manager para Sistema de Indicadores

Maneja conexiones WebSocket y broadcast de eventos cuando:
- Se completa un batch de scraping
- Se actualizan pesos PCA
- Se refrescan scores de indicadores
"""
from fastapi import WebSocket
from typing import Dict, List, Optional
import asyncio
import json
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self):
        # {client_id: [websocket1, websocket2, ...]}
        self.active_connections: Dict[str, List[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str = "default"):
        """Acepta conexión WebSocket y la registra"""
        await websocket.accept()
        
        if client_id not in self.active_connections:
            self.active_connections[client_id] = []
        
        self.active_connections[client_id].append(websocket)
        logger.info(f"Cliente {client_id} conectado. Total conexiones: {self.total_connections}")
    
    def disconnect(self, websocket: WebSocket, client_id: str = "default"):
        """Desconecta un WebSocket específico"""
        if client_id in self.active_connections:
            try:
                self.active_connections[client_id].remove(websocket)
                logger.info(f"Cliente {client_id} desconectado")
                
                # Limpiar lista vacía
                if not self.active_connections[client_id]:
                    del self.active_connections[client_id]
            except ValueError:
                pass
    
    async def send_personal(self, message: dict, client_id: str):
        """Envía mensaje a un cliente específico"""
        if client_id not in self.active_connections:
            return
        
        dead_connections = []
        for connection in self.active_connections[client_id]:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.error(f"Error enviando a {client_id}: {e}")
                dead_connections.append(connection)
        
        # Limpiar conexiones muertas
        for conn in dead_connections:
            self.disconnect(conn, client_id)
    
    async def broadcast(self, message: dict, exclude_client: Optional[str] = None):
        """
        Envía mensaje a TODOS los clientes conectados
        
        Args:
            message: Diccionario con el mensaje
            exclude_client: ID de cliente a excluir (opcional)
        """
        dead_connections = []
        
        for client_id, connections in self.active_connections.items():
            if exclude_client and client_id == exclude_client:
                continue
            
            for connection in connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.error(f"Error en broadcast a {client_id}: {e}")
                    dead_connections.append((connection, client_id))
        
        # Limpiar conexiones muertas
        for conn, cid in dead_connections:
            self.disconnect(conn, cid)
    
    @property
    def total_connections(self) -> int:
        """Total de conexiones activas"""
        return sum(len(conns) for conns in self.active_connections.values())
    
    @property
    def total_clients(self) -> int:
        """Total de clientes únicos"""
        return len(self.active_connections)


# Instancia global
manager = ConnectionManager()
