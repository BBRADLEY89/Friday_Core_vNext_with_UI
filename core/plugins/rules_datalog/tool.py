def rules_run(args):
    """Run simple rules on a given subgraph JSON"""
    subgraph = args.get("subgraph", {})
    
    if not subgraph:
        return {"success": False, "error": "subgraph is required"}
    
    try:
        flags = []
        
        # Extract nodes and relationships from subgraph
        nodes = []
        relationships = []
        
        # Handle different subgraph formats
        if "has_clause" in subgraph:
            # Neo4j subgraph format from kg_subgraph
            center_node = {
                "id": subgraph.get("id"),
                "type": subgraph.get("_type", "Contract"),
                "properties": {k: v for k, v in subgraph.items() if not k.startswith("_") and k != "has_clause"}
            }
            nodes.append(center_node)
            
            # Extract clause nodes
            for clause in subgraph.get("has_clause", []):
                clause_node = {
                    "id": clause.get("id"),
                    "type": clause.get("_type", "Clause"),
                    "properties": {k: v for k, v in clause.items() if not k.startswith("_")}
                }
                nodes.append(clause_node)
                
                # Create relationship
                relationships.append({
                    "source": subgraph.get("id"),
                    "target": clause.get("id"),
                    "type": "HAS_CLAUSE"
                })
        else:
            # Standard format with nodes and relationships arrays
            nodes = subgraph.get("nodes", [])
            relationships = subgraph.get("relationships", [])
        
        # Rule 1: Payment Deadline Conflicts
        payment_clauses = [node for node in nodes 
                          if node.get("properties", {}).get("type") == "PaymentDeadline" or 
                             node.get("type") == "PaymentDeadline"]
        
        if len(payment_clauses) > 1:
            # Check for conflicting deadlines
            deadlines = {}
            for clause in payment_clauses:
                props = clause.get("properties", clause)
                deadline_days = props.get("deadline_days")
                clause_id = clause.get("id")
                
                if deadline_days is not None:
                    if deadline_days in deadlines:
                        # Same deadline - potential redundancy
                        continue
                    else:
                        deadlines[deadline_days] = clause_id
            
            if len(deadlines) > 1:
                # Found conflicting deadlines
                clause_ids = list(deadlines.values())
                deadline_values = list(deadlines.keys())
                
                flags.append({
                    "rule": "PAYMENT_CONFLICT",
                    "nodes": clause_ids,
                    "reason": f"Conflicting payment deadlines found: {deadline_values} days",
                    "severity": "high",
                    "details": {
                        "deadlines": deadlines,
                        "clause_count": len(payment_clauses)
                    }
                })
        
        # Rule 2: Amount Inconsistencies
        amount_clauses = [node for node in nodes 
                         if "amount" in node.get("properties", {}) or 
                            "value" in node.get("properties", {})]
        
        if len(amount_clauses) > 1:
            amounts = []
            for clause in amount_clauses:
                props = clause.get("properties", clause)
                amount = props.get("amount") or props.get("value")
                clause_id = clause.get("id")
                
                if amount is not None:
                    try:
                        numeric_amount = float(str(amount).replace("$", "").replace(",", ""))
                        amounts.append((clause_id, numeric_amount))
                    except (ValueError, TypeError):
                        continue
            
            # Check for significant amount discrepancies
            if len(amounts) > 1:
                amounts.sort(key=lambda x: x[1])
                min_amount = amounts[0][1]
                max_amount = amounts[-1][1]
                
                if min_amount > 0 and (max_amount / min_amount) > 2:  # More than 2x difference
                    flags.append({
                        "rule": "AMOUNT_INCONSISTENCY",
                        "nodes": [a[0] for a in amounts],
                        "reason": f"Large amount discrepancy: ${min_amount} to ${max_amount}",
                        "severity": "medium",
                        "details": {
                            "min_amount": min_amount,
                            "max_amount": max_amount,
                            "ratio": max_amount / min_amount
                        }
                    })
        
        # Rule 3: Missing Required Clauses
        contract_nodes = [node for node in nodes 
                         if node.get("type") == "Contract" or 
                            node.get("properties", {}).get("type") == "Contract"]
        
        if contract_nodes:
            clause_types = set()
            for node in nodes:
                props = node.get("properties", node)
                if props.get("type") and props.get("type") != "Contract":
                    clause_types.add(props.get("type"))
            
            required_clauses = {"PaymentDeadline", "DeliveryDate", "TerminationClause"}
            missing_clauses = required_clauses - clause_types
            
            if missing_clauses:
                flags.append({
                    "rule": "MISSING_CLAUSES",
                    "nodes": [node.get("id") for node in contract_nodes],
                    "reason": f"Missing required clauses: {', '.join(missing_clauses)}",
                    "severity": "medium",
                    "details": {
                        "missing": list(missing_clauses),
                        "present": list(clause_types)
                    }
                })
        
        # Rule 4: Circular Dependencies
        if relationships:
            # Build adjacency list
            graph = {}
            for rel in relationships:
                source = rel.get("source")
                target = rel.get("target")
                if source and target:
                    if source not in graph:
                        graph[source] = []
                    graph[source].append(target)
            
            # Simple cycle detection using DFS
            visited = set()
            rec_stack = set()
            
            def has_cycle(node):
                if node in rec_stack:
                    return True
                if node in visited:
                    return False
                
                visited.add(node)
                rec_stack.add(node)
                
                for neighbor in graph.get(node, []):
                    if has_cycle(neighbor):
                        return True
                
                rec_stack.remove(node)
                return False
            
            for node_id in graph:
                if node_id not in visited:
                    if has_cycle(node_id):
                        flags.append({
                            "rule": "CIRCULAR_DEPENDENCY",
                            "nodes": list(graph.keys()),
                            "reason": "Circular dependency detected in contract structure",
                            "severity": "high",
                            "details": {
                                "graph_size": len(graph),
                                "relationship_count": len(relationships)
                            }
                        })
                        break
        
        return {
            "success": True,
            "flags": flags,
            "summary": {
                "total_flags": len(flags),
                "high_severity": len([f for f in flags if f.get("severity") == "high"]),
                "medium_severity": len([f for f in flags if f.get("severity") == "medium"]),
                "nodes_analyzed": len(nodes),
                "relationships_analyzed": len(relationships)
            }
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

# Export tools
TOOLS = {
    "rules_run": rules_run
}