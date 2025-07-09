"""
Services for managing circuits and simulation history in MongoDB.
"""
from datetime import datetime
from typing import List, Optional
from bson import ObjectId
from fastapi import HTTPException, status

from .database import get_database, CIRCUITS_COLLECTION, SIMULATIONS_COLLECTION
from .models import (
    Circuit, CircuitCreate, CircuitResponse,
    SimulationHistory, SimulationHistoryResponse,
    User, SimulationRequest, SimulationResults
)

class CircuitService:
    """Service for managing user circuits"""
    
    def get_db(self):
        """Get database instance"""
        db = get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")
        return db
    
    async def create_circuit(self, circuit_create: CircuitCreate, user: User) -> CircuitResponse:
        """Create a new circuit for a user"""
        db = self.get_db()
        
        circuit_doc = {
            "name": circuit_create.name,
            "description": circuit_create.description,
            "netlist": circuit_create.netlist,
            "owner_id": user.id,
            "is_public": circuit_create.is_public,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow()
        }
        
        result = await db[CIRCUITS_COLLECTION].insert_one(circuit_doc)
        circuit_doc["_id"] = result.inserted_id
        
        # Convert to response model
        return CircuitResponse(
            id=str(circuit_doc["_id"]),
            name=circuit_doc["name"],
            description=circuit_doc["description"],
            netlist=circuit_doc["netlist"],
            owner_id=str(circuit_doc["owner_id"]),
            is_public=circuit_doc["is_public"],
            created_at=circuit_doc["created_at"],
            updated_at=circuit_doc["updated_at"]
        )
    
    async def get_user_circuits(self, user: User) -> List[CircuitResponse]:
        """Get all circuits for a user"""
        db = self.get_db()
        
        cursor = db[CIRCUITS_COLLECTION].find({"owner_id": user.id})
        circuits = []
        
        async for circuit_doc in cursor:
            circuits.append(CircuitResponse(
                id=str(circuit_doc["_id"]),
                name=circuit_doc["name"],
                description=circuit_doc.get("description"),
                netlist=circuit_doc["netlist"],
                owner_id=str(circuit_doc["owner_id"]),
                is_public=circuit_doc["is_public"],
                created_at=circuit_doc["created_at"],
                updated_at=circuit_doc["updated_at"]
            ))
        
        return circuits
    
    async def get_circuit_by_id(self, circuit_id: str, user: User) -> Optional[CircuitResponse]:
        """Get a specific circuit by ID (must be owned by user)"""
        db = self.get_db()
        
        try:
            circuit_doc = await db[CIRCUITS_COLLECTION].find_one({
                "_id": ObjectId(circuit_id),
                "owner_id": user.id
            })
            
            if not circuit_doc:
                return None
            
            return CircuitResponse(
                id=str(circuit_doc["_id"]),
                name=circuit_doc["name"],
                description=circuit_doc.get("description"),
                netlist=circuit_doc["netlist"],
                owner_id=str(circuit_doc["owner_id"]),
                is_public=circuit_doc["is_public"],
                created_at=circuit_doc["created_at"],
                updated_at=circuit_doc["updated_at"]
            )
        
        except Exception:
            return None
    
    async def update_circuit(self, circuit_id: str, circuit_update: CircuitCreate, user: User) -> Optional[CircuitResponse]:
        """Update a circuit (must be owned by user)"""
        db = self.get_db()
        
        try:
            update_doc = {
                "name": circuit_update.name,
                "description": circuit_update.description,
                "netlist": circuit_update.netlist,
                "is_public": circuit_update.is_public,
                "updated_at": datetime.utcnow()
            }
            
            result = await db[CIRCUITS_COLLECTION].update_one(
                {"_id": ObjectId(circuit_id), "owner_id": user.id},
                {"$set": update_doc}
            )
            
            if result.matched_count == 0:
                return None
            
            return await self.get_circuit_by_id(circuit_id, user)
        
        except Exception:
            return None
    
    async def delete_circuit(self, circuit_id: str, user: User) -> bool:
        """Delete a circuit (must be owned by user)"""
        db = self.get_db()
        
        try:
            result = await db[CIRCUITS_COLLECTION].delete_one({
                "_id": ObjectId(circuit_id),
                "owner_id": user.id
            })
            
            return result.deleted_count > 0
        
        except Exception:
            return False

class SimulationHistoryService:
    """Service for managing simulation history"""
    
    def get_db(self):
        """Get database instance"""
        db = get_database()
        if db is None:
            raise HTTPException(status_code=500, detail="Database not connected")
        return db
    
    async def save_simulation(
        self, 
        user: User, 
        simulation_request: SimulationRequest,
        simulation_results: SimulationResults,
        execution_time: float
    ) -> SimulationHistoryResponse:
        """Save a simulation to user's history"""
        db = self.get_db()
        
        simulation_doc = {
            "user_id": user.id,
            "circuit_id": None,  # We could link to circuit later
            "circuit_name": simulation_request.circuit_name,
            "netlist": simulation_request.netlist_string,
            "analysis_type": simulation_request.analysis_type,
            "analysis_parameters": simulation_request.analysis_parameters,
            "results": simulation_results.model_dump(),
            "success": simulation_results.success,
            "error_message": simulation_results.message if not simulation_results.success else None,
            "execution_time": execution_time,
            "created_at": datetime.utcnow()
        }
        
        result = await db[SIMULATIONS_COLLECTION].insert_one(simulation_doc)
        
        return SimulationHistoryResponse(
            id=str(result.inserted_id),
            user_id=str(user.id),
            circuit_id=None,
            circuit_name=simulation_request.circuit_name,
            analysis_type=simulation_request.analysis_type,
            success=simulation_results.success,
            error_message=simulation_results.message if not simulation_results.success else None,
            execution_time=execution_time,
            created_at=simulation_doc["created_at"]
        )
    
    async def get_user_simulation_history(self, user: User, limit: int = 50) -> List[SimulationHistoryResponse]:
        """Get simulation history for a user"""
        db = self.get_db()
        
        cursor = db[SIMULATIONS_COLLECTION].find(
            {"user_id": user.id}
        ).sort("created_at", -1).limit(limit)
        
        simulations = []
        async for sim_doc in cursor:
            simulations.append(SimulationHistoryResponse(
                id=str(sim_doc["_id"]),
                user_id=str(sim_doc["user_id"]),
                circuit_id=str(sim_doc["circuit_id"]) if sim_doc.get("circuit_id") else None,
                circuit_name=sim_doc["circuit_name"],
                analysis_type=sim_doc["analysis_type"],
                success=sim_doc["success"],
                error_message=sim_doc.get("error_message"),
                execution_time=sim_doc.get("execution_time"),
                created_at=sim_doc["created_at"]
            ))
        
        return simulations
    
    async def get_simulation_by_id(self, simulation_id: str, user: User) -> Optional[SimulationHistory]:
        """Get a specific simulation by ID (must be owned by user)"""
        db = self.get_db()
        
        try:
            sim_doc = await db[SIMULATIONS_COLLECTION].find_one({
                "_id": ObjectId(simulation_id),
                "user_id": user.id
            })
            
            if not sim_doc:
                return None
            
            return SimulationHistory(
                id=sim_doc["_id"],
                user_id=sim_doc["user_id"],
                circuit_id=sim_doc.get("circuit_id"),
                circuit_name=sim_doc["circuit_name"],
                netlist=sim_doc["netlist"],
                analysis_type=sim_doc["analysis_type"],
                analysis_parameters=sim_doc["analysis_parameters"],
                results=sim_doc["results"],
                success=sim_doc["success"],
                error_message=sim_doc.get("error_message"),
                execution_time=sim_doc.get("execution_time"),
                created_at=sim_doc["created_at"]
            )
        
        except Exception:
            return None

# Create service instances
circuit_service = CircuitService()
simulation_history_service = SimulationHistoryService()
