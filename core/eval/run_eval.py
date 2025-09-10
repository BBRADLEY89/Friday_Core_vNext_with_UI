#!/usr/bin/env python3
"""
Automated evaluation script for Friday's reasoning quality.
Tests KG analysis, rules engine, and solver integration.
"""

import json
import os
import sys
import requests
import glob
from pathlib import Path
from typing import Dict, List, Any
import re

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def load_scenario(scenario_path: str) -> Dict[str, Any]:
    """Load a test scenario from JSON file."""
    try:
        with open(scenario_path, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading scenario {scenario_path}: {e}")
        return None

def upsert_kg_data(kg_data: Dict[str, Any], server_url: str = "http://localhost:8767") -> bool:
    """Insert KG data using kg_upsert tool."""
    try:
        payload = {
            "tool_name": "kg_upsert",
            "args": {
                "payload": kg_data
            }
        }
        
        response = requests.post(f"{server_url}/run", json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            return result.get("success", False)
        else:
            print(f"KG upsert failed: HTTP {response.status_code}")
            return False
    except Exception as e:
        print(f"Error during KG upsert: {e}")
        return False

def ask_chat_question(question: str, server_url: str = "http://localhost:8767") -> Dict[str, Any]:
    """Ask Friday a question via /chat endpoint."""
    try:
        payload = {
            "messages": [
                {"role": "user", "content": question}
            ]
        }
        
        response = requests.post(f"{server_url}/chat", json=payload, timeout=45)
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Chat request failed: HTTP {response.status_code}")
            return {}
    except Exception as e:
        print(f"Error during chat request: {e}")
        return {}

def grade_response(response: Dict[str, Any], scenario: Dict[str, Any]) -> Dict[str, Any]:
    """Grade Friday's response against expected criteria."""
    content = response.get("content", "").lower()
    tool_used = response.get("tool_used")
    intermediate = response.get("intermediate", {})
    
    grading = scenario.get("grading", {})
    expected_flags = scenario.get("expected_flags", [])
    expected_mentions = scenario.get("expected_mentions", [])
    
    results = {
        "score": 0,
        "max_score": 0,
        "details": []
    }
    
    # Check if tool was used appropriately
    if tool_used:
        results["details"].append(f"✓ Used tool: {tool_used}")
        results["score"] += 1
    else:
        results["details"].append("✗ No tool used")
    results["max_score"] += 1
    
    # Check for expected flags in response
    flags_found = 0
    for flag in expected_flags:
        if flag.lower() in content:
            results["details"].append(f"✓ Found flag: {flag}")
            flags_found += 1
        else:
            results["details"].append(f"✗ Missing flag: {flag}")
    
    if expected_flags:
        results["score"] += flags_found / len(expected_flags)
        results["max_score"] += 1
    
    # Check for expected mentions
    mentions_found = 0
    for mention in expected_mentions:
        if mention.lower() in content:
            results["details"].append(f"✓ Mentioned: {mention}")
            mentions_found += 1
        else:
            results["details"].append(f"✗ Missing mention: {mention}")
    
    if expected_mentions:
        results["score"] += mentions_found / len(expected_mentions)
        results["max_score"] += 1
    
    # Check specific grading criteria
    if grading.get("contradiction_detected") and scenario.get("should_find_contradictions"):
        if intermediate.get("contradictions") or "contradiction" in content or "conflict" in content:
            results["details"].append("✓ Contradiction detection working")
            results["score"] += 1
        else:
            results["details"].append("✗ Failed to detect contradiction")
        results["max_score"] += 1
    
    if grading.get("missing_clause_detected"):
        if "missing" in content or "incomplete" in content:
            results["details"].append("✓ Missing clause detection working")
            results["score"] += 1
        else:
            results["details"].append("✗ Failed to detect missing clause")
        results["max_score"] += 1
    
    if grading.get("amount_inconsistency_detected"):
        if "inconsistent" in content or "mismatch" in content:
            results["details"].append("✓ Amount inconsistency detection working")
            results["score"] += 1
        else:
            results["details"].append("✗ Failed to detect amount inconsistency")
        results["max_score"] += 1
    
    if grading.get("temporal_analysis"):
        if "timeline" in content or "temporal" in content or "impossible" in content:
            results["details"].append("✓ Temporal analysis performed")
            results["score"] += 1
        else:
            results["details"].append("✗ No temporal analysis detected")
        results["max_score"] += 1
    
    # Check if specific values mentioned
    if grading.get("specific_values_mentioned"):
        values_found = 0
        for value in grading["specific_values_mentioned"]:
            if str(value) in response.get("content", ""):
                values_found += 1
        if values_found > 0:
            results["details"].append(f"✓ Found {values_found}/{len(grading['specific_values_mentioned'])} specific values")
            results["score"] += values_found / len(grading["specific_values_mentioned"])
        else:
            results["details"].append("✗ No specific values mentioned")
        results["max_score"] += 1
    
    return results

def clean_kg_data(contract_id: str, server_url: str = "http://localhost:8767") -> bool:
    """Clean up KG data for a specific contract."""
    try:
        # Use Neo4j to delete the contract and all related clauses
        payload = {
            "tool_name": "kg_neo4j",
            "args": {
                "query": f"MATCH (c:Contract {{id: '{contract_id}'}}) DETACH DELETE c",
                "params": {}
            }
        }
        
        response = requests.post(f"{server_url}/run", json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"Warning: Could not clean up {contract_id}: {e}")
        return False

def run_evaluation(scenarios_dir: str = "eval/scenarios", server_url: str = "http://localhost:8767"):
    """Run evaluation on all scenarios."""
    scenario_files = glob.glob(os.path.join(scenarios_dir, "*.json"))
    
    if not scenario_files:
        print(f"No scenario files found in {scenarios_dir}")
        return
    
    print(f"🧪 Running evaluation on {len(scenario_files)} scenarios...")
    print("=" * 60)
    
    total_score = 0
    total_max_score = 0
    results = []
    
    for scenario_file in sorted(scenario_files):
        scenario_name = Path(scenario_file).stem
        print(f"\n📋 Testing: {scenario_name}")
        
        scenario = load_scenario(scenario_file)
        if not scenario:
            continue
        
        print(f"📝 Description: {scenario.get('description', 'N/A')}")
        
        # Step 1: Upsert KG data
        print("🔄 Upserting KG data...")
        if not upsert_kg_data(scenario["kg_data"], server_url):
            print("❌ Failed to upsert KG data")
            continue
        
        # Step 2: Ask the question
        print(f"❓ Asking: {scenario['question']}")
        response = ask_chat_question(scenario["question"], server_url)
        
        if not response:
            print("❌ Failed to get response")
            continue
        
        # Step 3: Grade the response
        grading_results = grade_response(response, scenario)
        
        # Step 4: Display results
        score = grading_results["score"]
        max_score = grading_results["max_score"]
        percentage = (score / max_score * 100) if max_score > 0 else 0
        
        print(f"📊 Score: {score:.1f}/{max_score:.1f} ({percentage:.1f}%)")
        
        for detail in grading_results["details"]:
            print(f"   {detail}")
        
        if response.get("content"):
            print(f"💬 Response: {response['content'][:200]}...")
        
        # Step 5: Clean up
        contract_ids = [node["id"] for node in scenario["kg_data"]["nodes"] if "Contract" in node["labels"]]
        for contract_id in contract_ids:
            clean_kg_data(contract_id, server_url)
        
        total_score += score
        total_max_score += max_score
        results.append({
            "scenario": scenario_name,
            "score": score,
            "max_score": max_score,
            "percentage": percentage
        })
    
    # Summary
    print("\n" + "=" * 60)
    print("📈 EVALUATION SUMMARY")
    print("=" * 60)
    
    for result in results:
        status = "✅" if result["percentage"] >= 70 else "⚠️" if result["percentage"] >= 50 else "❌"
        print(f"{status} {result['scenario']}: {result['score']:.1f}/{result['max_score']:.1f} ({result['percentage']:.1f}%)")
    
    overall_percentage = (total_score / total_max_score * 100) if total_max_score > 0 else 0
    print(f"\n🎯 Overall Score: {total_score:.1f}/{total_max_score:.1f} ({overall_percentage:.1f}%)")
    
    if overall_percentage >= 70:
        print("🎉 Evaluation PASSED - Reasoning quality is good!")
    elif overall_percentage >= 50:
        print("⚠️ Evaluation PARTIAL - Some issues detected")
    else:
        print("❌ Evaluation FAILED - Major reasoning issues")

def main():
    """Main CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description="Run Friday AI reasoning quality evaluation")
    parser.add_argument("--scenarios", default="eval/scenarios", 
                       help="Directory containing scenario JSON files")
    parser.add_argument("--server", default="http://localhost:8767",
                       help="Friday server URL")
    
    args = parser.parse_args()
    
    # Check if server is running
    try:
        response = requests.get(f"{args.server}/health", timeout=5)
        if response.status_code != 200:
            print(f"❌ Friday server not responding at {args.server}")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Cannot connect to Friday server at {args.server}: {e}")
        sys.exit(1)
    
    run_evaluation(args.scenarios, args.server)

if __name__ == "__main__":
    main()