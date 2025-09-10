from z3 import *

def solver_check(args):
    """Check numeric/temporal constraints using Z3 SMT solver"""
    facts = args.get("facts", {})
    
    if not facts:
        return {"success": False, "error": "facts is required"}
    
    try:
        # Initialize Z3 solver
        solver = Solver()
        variables = {}
        
        # Handle different fact formats
        constraints = []
        
        # Extract constraints from facts
        if "deadlines" in facts:
            # Deadline constraint checking
            deadlines = facts["deadlines"]
            for deadline_id, deadline_days in deadlines.items():
                var_name = f"deadline_{deadline_id.replace('-', '_')}"
                variables[var_name] = Int(var_name)
                solver.add(variables[var_name] == deadline_days)
            
            # Add constraint: all deadlines should be consistent (within reasonable range)
            if len(variables) > 1:
                deadline_vars = list(variables.values())
                for i in range(len(deadline_vars)):
                    for j in range(i + 1, len(deadline_vars)):
                        # Allow up to 7 days difference for "reasonable" consistency
                        diff_constraint = Or(
                            deadline_vars[i] - deadline_vars[j] <= 7,
                            deadline_vars[j] - deadline_vars[i] <= 7
                        )
                        constraints.append(("deadline_consistency", diff_constraint))
        
        if "amounts" in facts:
            # Amount constraint checking
            amounts = facts["amounts"]
            for amount_id, amount_value in amounts.items():
                var_name = f"amount_{amount_id.replace('-', '_')}"
                variables[var_name] = Real(var_name)
                solver.add(variables[var_name] == amount_value)
            
            # Add constraint: amounts should be positive
            amount_vars = [v for k, v in variables.items() if k.startswith("amount_")]
            for var in amount_vars:
                solver.add(var > 0)
                constraints.append(("positive_amount", var > 0))
            
            # Add constraint: amounts shouldn't vary by more than 50%
            if len(amount_vars) > 1:
                for i in range(len(amount_vars)):
                    for j in range(i + 1, len(amount_vars)):
                        # Ratio should be between 0.5 and 2.0
                        ratio_constraint = And(
                            amount_vars[i] / amount_vars[j] >= 0.5,
                            amount_vars[i] / amount_vars[j] <= 2.0
                        )
                        constraints.append(("amount_consistency", ratio_constraint))
        
        if "temporal" in facts:
            # Temporal constraint checking (dates, durations)
            temporal = facts["temporal"]
            
            for temp_id, temp_info in temporal.items():
                if isinstance(temp_info, dict):
                    start_var = f"start_{temp_id.replace('-', '_')}"
                    end_var = f"end_{temp_id.replace('-', '_')}"
                    
                    variables[start_var] = Int(start_var)
                    variables[end_var] = Int(end_var)
                    
                    if "start_day" in temp_info:
                        solver.add(variables[start_var] == temp_info["start_day"])
                    if "end_day" in temp_info:
                        solver.add(variables[end_var] == temp_info["end_day"])
                    
                    # Duration constraint: end >= start
                    duration_constraint = variables[end_var] >= variables[start_var]
                    solver.add(duration_constraint)
                    constraints.append(("temporal_order", duration_constraint))
        
        if "custom_constraints" in facts:
            # Custom constraint expressions
            custom = facts["custom_constraints"]
            for constraint_id, expr in custom.items():
                if isinstance(expr, str):
                    # Simple parsing for basic expressions
                    if ">" in expr:
                        parts = expr.split(">")
                        if len(parts) == 2:
                            left = parts[0].strip()
                            right = parts[1].strip()
                            
                            # Create variables if needed
                            if left not in variables:
                                variables[left] = Int(left)
                            
                            try:
                                right_val = int(right)
                                constraint = variables[left] > right_val
                                solver.add(constraint)
                                constraints.append((f"custom_{constraint_id}", constraint))
                            except ValueError:
                                if right not in variables:
                                    variables[right] = Int(right)
                                constraint = variables[left] > variables[right]
                                solver.add(constraint)
                                constraints.append((f"custom_{constraint_id}", constraint))
        
        # Check satisfiability
        result = solver.check()
        
        response = {
            "success": True,
            "sat": result == sat,
            "result": str(result),
            "variables": list(variables.keys()),
            "constraints_count": len(constraints)
        }
        
        if result == sat:
            # Get model (satisfying assignment)
            model = solver.model()
            assignment = {}
            for var_name, var_obj in variables.items():
                if model[var_obj] is not None:
                    assignment[var_name] = str(model[var_obj])
            
            response["explanation"] = "All constraints are satisfiable"
            response["model"] = assignment
            response["details"] = {
                "constraint_types": list(set(c[0] for c in constraints)),
                "satisfying_assignment": assignment
            }
        
        elif result == unsat:
            # Try to get unsat core for explanation
            solver.set("unsat_core", True)
            
            # Re-add constraints with names for unsat core
            solver_core = Solver()
            named_constraints = []
            
            for i, (constraint_type, constraint) in enumerate(constraints):
                constraint_name = f"c_{i}_{constraint_type}"
                named_constraints.append((constraint_name, constraint))
                solver_core.assert_and_track(constraint, constraint_name)
            
            # Add variable assignments
            for var_name, var_obj in variables.items():
                if any(solver.assertions()):  # If there are existing assertions
                    for assertion in solver.assertions():
                        if str(var_obj) in str(assertion):
                            solver_core.add(assertion)
            
            core_result = solver_core.check()
            if core_result == unsat:
                core = solver_core.unsat_core()
                response["explanation"] = f"Constraints are unsatisfiable. Conflicting constraints: {[str(c) for c in core]}"
                response["unsat_core"] = [str(c) for c in core]
            else:
                response["explanation"] = "Constraints are unsatisfiable"
            
            response["details"] = {
                "constraint_types": list(set(c[0] for c in constraints)),
                "total_constraints": len(constraints)
            }
        
        else:  # unknown
            response["explanation"] = "Z3 could not determine satisfiability (timeout or resource limit)"
            response["details"] = {
                "constraint_types": list(set(c[0] for c in constraints)),
                "reason": "unknown_result"
            }
        
        return response
        
    except Exception as e:
        return {"success": False, "error": f"Z3 solver error: {str(e)}"}

# Export tools
TOOLS = {
    "solver_check": solver_check
}