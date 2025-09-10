#!/usr/bin/env python3
"""
Contract extraction script for Friday AI system.
Reads contract text and extracts structured data using OpenAI and ontology validation.
"""

import json
import os
import sys
import argparse
import requests
from pathlib import Path
from typing import Dict, List, Any
from openai import OpenAI

# Add parent directories to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

def load_ontology(ontology_path: str = "kg/ontology/base.json") -> Dict[str, Any]:
    """Load the base ontology definition."""
    try:
        with open(ontology_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Ontology file not found at {ontology_path}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in ontology file: {e}")
        sys.exit(1)

def read_contract_text(file_path: str) -> str:
    """Read contract text from file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except FileNotFoundError:
        print(f"Error: Contract file not found at {file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading contract file: {e}")
        sys.exit(1)

def create_extraction_prompt(contract_text: str, ontology: Dict[str, Any], contract_id: str) -> str:
    """Create the OpenAI prompt for contract extraction."""
    
    entity_descriptions = []
    for entity_type, entity_info in ontology["entities"].items():
        props = ", ".join(entity_info["props"])
        entity_descriptions.append(f"- {entity_type}: properties [{props}]")
    
    relation_descriptions = []
    for rel_type, rel_info in ontology["relations"].items():
        relation_descriptions.append(f"- {rel_type}: {rel_info['description']}")
    
    clause_types = ", ".join(ontology["clause_types"])
    
    prompt = f"""You are an expert contract analysis AI. Extract structured data from the following contract text according to the specified ontology.

CONTRACT TEXT:
{contract_text}

ONTOLOGY:
Entities:
{chr(10).join(entity_descriptions)}

Relations:
{chr(10).join(relation_descriptions)}

Clause Types: {clause_types}

EXTRACTION REQUIREMENTS:
1. Create one Contract entity with id="{contract_id}"
2. Extract all significant clauses as Clause entities
3. Each clause should have:
   - Unique ID (format: clause-001, clause-002, etc.)
   - Appropriate type from the clause_types list
   - The actual text content
   - Any numeric values (deadlines, amounts, etc.)
4. Create PART_OF relationships from each clause to the contract
5. Identify contradictions and create CONTRADICTS relationships
6. Look for exceptions and create EXCEPTION_TO relationships

OUTPUT FORMAT:
Return valid JSON with this exact structure:
{{
  "nodes": [
    {{
      "id": "contract_id",
      "labels": ["Contract"],
      "properties": {{
        "id": "contract_id",
        "title": "extracted title",
        "effective_date": "date if found",
        "law": "governing law if mentioned"
      }}
    }},
    {{
      "id": "clause_id", 
      "labels": ["Clause"],
      "properties": {{
        "id": "clause_id",
        "number": "section number",
        "type": "clause_type",
        "text": "full clause text",
        "scope": "what it applies to",
        "value": "numeric value if any",
        "deadline_days": numeric_value_for_deadlines
      }}
    }}
  ],
  "relationships": [
    {{
      "source": "clause_id",
      "target": "contract_id", 
      "type": "PART_OF",
      "properties": {{}}
    }}
  ]
}}

Extract comprehensive information but focus on clauses that contain:
- Payment terms and deadlines
- Delivery requirements  
- Termination conditions
- Liability and warranty terms
- Confidentiality requirements
- Intellectual property clauses

Be thorough and accurate. Extract specific numeric values for deadlines, amounts, and dates."""

    return prompt

def extract_with_openai(prompt: str, api_key: str) -> Dict[str, Any]:
    """Use OpenAI to extract structured data from contract text."""
    try:
        import httpx
        client = OpenAI(
            api_key=api_key,
            http_client=httpx.Client()  # Fresh HTTP client without proxy inheritance
        )
        
        response = client.chat.completions.create(
            model="gpt-4",
            messages=[
                {"role": "system", "content": "You are a precise contract analysis expert. Return only valid JSON matching the exact format requested."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=4000
        )
        
        content = response.choices[0].message.content.strip()
        
        # Try to extract JSON from response
        if content.startswith('```json'):
            content = content[7:]
        if content.endswith('```'):
            content = content[:-3]
        
        return json.loads(content)
    
    except json.JSONDecodeError as e:
        print(f"Error: OpenAI returned invalid JSON: {e}")
        print(f"Raw response: {content}")
        sys.exit(1)
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        sys.exit(1)

def validate_extraction(data: Dict[str, Any], ontology: Dict[str, Any]) -> bool:
    """Validate extracted data against ontology."""
    try:
        # Check required structure
        if "nodes" not in data or "relationships" not in data:
            print("Error: Missing 'nodes' or 'relationships' in extracted data")
            return False
        
        # Validate nodes
        valid_entity_types = set(ontology["entities"].keys())
        valid_clause_types = set(ontology["clause_types"])
        
        for node in data["nodes"]:
            if "id" not in node or "labels" not in node:
                print(f"Error: Node missing id or labels: {node}")
                return False
            
            # Check entity type is valid
            for label in node["labels"]:
                if label not in valid_entity_types:
                    print(f"Error: Invalid entity type '{label}' in node {node['id']}")
                    return False
            
            # Special validation for clauses
            if "Clause" in node["labels"]:
                props = node.get("properties", {})
                clause_type = props.get("type")
                if clause_type and clause_type not in valid_clause_types:
                    print(f"Warning: Clause type '{clause_type}' not in standard types")
        
        # Validate relationships
        valid_relation_types = set(ontology["relations"].keys())
        node_ids = {node["id"] for node in data["nodes"]}
        
        for rel in data["relationships"]:
            if not all(key in rel for key in ["source", "target", "type"]):
                print(f"Error: Relationship missing required fields: {rel}")
                return False
            
            if rel["type"] not in valid_relation_types:
                print(f"Error: Invalid relationship type '{rel['type']}'")
                return False
            
            if rel["source"] not in node_ids or rel["target"] not in node_ids:
                print(f"Error: Relationship references non-existent nodes: {rel}")
                return False
        
        print(f"✓ Validation passed: {len(data['nodes'])} nodes, {len(data['relationships'])} relationships")
        return True
    
    except Exception as e:
        print(f"Error during validation: {e}")
        return False

def upsert_to_kg(data: Dict[str, Any], server_url: str = "http://localhost:8767") -> bool:
    """Send extracted data to knowledge graph via kg_upsert."""
    try:
        payload = {
            "tool_name": "kg_upsert",
            "args": {
                "payload": data
            }
        }
        
        response = requests.post(f"{server_url}/run", json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            if result.get("success"):
                print(f"✓ Successfully upserted to knowledge graph")
                print(f"  Results: {len(result.get('results', []))} operations")
                return True
            else:
                print(f"Error from kg_upsert: {result.get('error', 'Unknown error')}")
                return False
        else:
            print(f"Error: HTTP {response.status_code} from server")
            print(f"Response: {response.text}")
            return False
    
    except requests.exceptions.RequestException as e:
        print(f"Error connecting to server: {e}")
        return False
    except Exception as e:
        print(f"Error during upsert: {e}")
        return False

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Extract contract data to knowledge graph")
    parser.add_argument("--in", dest="input_file", required=True, 
                       help="Input contract file (.txt)")
    parser.add_argument("--contract_id", required=True,
                       help="Contract ID (e.g., C-2025-001)")
    parser.add_argument("--ontology", default="kg/ontology/base.json",
                       help="Path to ontology file")
    parser.add_argument("--server", default="http://localhost:8767", 
                       help="Friday server URL")
    parser.add_argument("--output", help="Save extracted JSON to file")
    parser.add_argument("--dry-run", action="store_true",
                       help="Extract and validate only, don't upsert")
    
    args = parser.parse_args()
    
    # Get OpenAI API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("Error: OPENAI_API_KEY environment variable not set")
        sys.exit(1)
    
    print(f"🔍 Extracting contract: {args.input_file} -> {args.contract_id}")
    
    # Load ontology
    ontology = load_ontology(args.ontology)
    print(f"✓ Loaded ontology: {len(ontology['entities'])} entities, {len(ontology['relations'])} relations")
    
    # Read contract text
    contract_text = read_contract_text(args.input_file)
    print(f"✓ Read contract: {len(contract_text)} characters")
    
    # Create extraction prompt
    prompt = create_extraction_prompt(contract_text, ontology, args.contract_id)
    
    # Extract with OpenAI
    print("🤖 Extracting with OpenAI...")
    extracted_data = extract_with_openai(prompt, api_key)
    
    # Validate extraction
    print("✅ Validating extraction...")
    if not validate_extraction(extracted_data, ontology):
        print("❌ Validation failed")
        sys.exit(1)
    
    # Save to file if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(extracted_data, f, indent=2)
        print(f"💾 Saved extraction to {args.output}")
    
    # Upsert to KG unless dry run
    if not args.dry_run:
        print("📤 Upserting to knowledge graph...")
        if upsert_to_kg(extracted_data, args.server):
            print("✅ Contract successfully extracted and stored!")
        else:
            print("❌ Failed to upsert to knowledge graph")
            sys.exit(1)
    else:
        print("✅ Dry run complete - extraction successful!")

if __name__ == "__main__":
    main()