import json
from neo4j import GraphDatabase

# Neo4j connection settings
NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "fridaypass"

def get_driver():
    """Get Neo4j driver connection"""
    return GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

def kg_upsert(args):
    """Upsert nodes/edges from a JSON payload"""
    payload = args.get("payload", {})
    
    try:
        driver = get_driver()
        
        with driver.session() as session:
            results = []
            
            # Process nodes
            nodes = payload.get("nodes", [])
            for node in nodes:
                node_id = node.get("id")
                labels = node.get("labels", [])
                properties = node.get("properties", {})
                
                if not node_id or not labels:
                    continue
                    
                # Build MERGE query for node
                label_str = ":".join(labels)
                props_str = ", ".join([f"{k}: ${k}" for k in properties.keys()])
                
                query = f"""
                MERGE (n:{label_str} {{id: $id}})
                SET n += $properties
                RETURN n.id as id
                """
                
                result = session.run(query, id=node_id, properties=properties)
                results.append({"type": "node", "id": node_id, "action": "upserted"})
            
            # Process relationships
            relationships = payload.get("relationships", [])
            for rel in relationships:
                source_id = rel.get("source")
                target_id = rel.get("target")
                rel_type = rel.get("type")
                properties = rel.get("properties", {})
                
                if not all([source_id, target_id, rel_type]):
                    continue
                    
                query = f"""
                MATCH (a {{id: $source_id}})
                MATCH (b {{id: $target_id}})
                MERGE (a)-[r:{rel_type}]->(b)
                SET r += $properties
                RETURN type(r) as relationship_type
                """
                
                result = session.run(query, source_id=source_id, target_id=target_id, properties=properties)
                results.append({"type": "relationship", "source": source_id, "target": target_id, "rel_type": rel_type, "action": "upserted"})
        
        driver.close()
        return {"success": True, "results": results}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def kg_subgraph(args):
    """Fetch a neighborhood around an entity id"""
    entity_id = args.get("entity_id")
    depth = args.get("depth", 2)
    
    if not entity_id:
        return {"success": False, "error": "entity_id is required"}
    
    try:
        driver = get_driver()
        
        with driver.session() as session:
            # Get subgraph with specified depth
            query = f"""
            MATCH path = (start {{id: $entity_id}})-[*1..{depth}]-(connected)
            WITH collect(path) as paths
            CALL apoc.convert.toTree(paths) YIELD value
            RETURN value
            """
            
            # Fallback query if APOC is not available
            fallback_query = f"""
            MATCH (start {{id: $entity_id}})
            OPTIONAL MATCH path = (start)-[r*1..{depth}]-(connected)
            WITH start, collect(DISTINCT connected) as nodes, collect(DISTINCT r) as relationships
            RETURN {{
                center_node: {{id: start.id, labels: labels(start), properties: properties(start)}},
                connected_nodes: [n IN nodes | {{id: n.id, labels: labels(n), properties: properties(n)}}],
                relationships: [rel IN REDUCE(acc = [], rels IN relationships | acc + rels) | {{type: type(rel), properties: properties(rel)}}]
            }} as subgraph
            """
            
            try:
                result = session.run(query, entity_id=entity_id)
                record = result.single()
                if record:
                    return {"success": True, "subgraph": record["value"]}
            except:
                # Use fallback query
                result = session.run(fallback_query, entity_id=entity_id)
                record = result.single()
                if record:
                    return {"success": True, "subgraph": record["subgraph"]}
                    
            return {"success": True, "subgraph": None, "message": "No data found"}
        
        driver.close()
        
    except Exception as e:
        return {"success": False, "error": str(e)}

def kg_find_contradictions(args):
    """Find simple contradictions for a contract id"""
    contract_id = args.get("contract_id")
    
    if not contract_id:
        return {"success": False, "error": "contract_id is required"}
    
    try:
        driver = get_driver()
        
        with driver.session() as session:
            # Find contradictions in payment deadlines  
            query = """
            MATCH (contract:Contract {id: $contract_id})-[:HAS_CLAUSE]->(d1:Clause)
            MATCH (contract)-[:HAS_CLAUSE]->(d2:Clause)
            WHERE d1.type = 'PaymentDeadline' AND d2.type = 'PaymentDeadline'
            AND d1.id < d2.id AND d1.deadline_days <> d2.deadline_days
            RETURN {
                contract_id: contract.id,
                contradiction_type: 'PaymentDeadline',
                clause1: {
                    id: d1.id,
                    deadline_days: d1.deadline_days,
                    description: d1.description
                },
                clause2: {
                    id: d2.id, 
                    deadline_days: d2.deadline_days,
                    description: d2.description
                }
            } as contradiction
            """
            
            result = session.run(query, contract_id=contract_id)
            contradictions = [record["contradiction"] for record in result]
            
            # Also check for general value contradictions
            general_query = """
            MATCH (contract:Contract {id: $contract_id})-[:HAS_CLAUSE]->(c1:Clause)
            MATCH (contract)-[:HAS_CLAUSE]->(c2:Clause)
            WHERE c1.value IS NOT NULL AND c2.value IS NOT NULL AND c1.type = c2.type
            AND c1.id < c2.id AND c1.value <> c2.value
            RETURN {
                contract_id: contract.id,
                contradiction_type: c1.type,
                clause1: {id: c1.id, value: c1.value, description: c1.description},
                clause2: {id: c2.id, value: c2.value, description: c2.description}
            } as contradiction
            """
            
            general_result = session.run(general_query, contract_id=contract_id)
            general_contradictions = [record["contradiction"] for record in general_result]
            
            all_contradictions = contradictions + general_contradictions
            
        driver.close()
        return {"success": True, "contradictions": all_contradictions, "count": len(all_contradictions)}
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# Export tools
TOOLS = {
    "kg_upsert": kg_upsert,
    "kg_subgraph": kg_subgraph,
    "kg_find_contradictions": kg_find_contradictions
}