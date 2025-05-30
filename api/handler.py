from flask import Flask, jsonify, request
import requests
import traceback
import wikipedia
import time
import os
import tempfile
import xml.etree.ElementTree as ET 
import http.client # For IncompleteRead
# Bio.Entrez is imported in configure_entrez_and_patch

# --- Monkey Patching و پیکربندی Entrez ---
original_makedirs = os.makedirs
_entrez_module = None
_patch_active = False # یک فلگ برای کنترل فعال بودن پچ

def patched_makedirs_for_biopython_import(name, mode=0o777, exist_ok=False):
    global _patch_active
    if _patch_active:
        if not name.startswith(tempfile.gettempdir()):
            print(f"[PATCH_MAKEDIRS_IMPORT] Suppressing makedirs during Biopython import for non-/tmp path: {name}")
            return None
        else:
            # Ensure exist_ok is handled for original_makedirs if it's True
            if exist_ok and os.path.exists(name):
                 return None
            return original_makedirs(name, mode) # Removed exist_ok for simplicity if not supported by older original_makedirs
    else:
        # Ensure exist_ok is handled for original_makedirs if it's True
        if exist_ok and os.path.exists(name):
            return None
        return original_makedirs(name, mode)


def configure_entrez_and_patch():
    global _entrez_module
    global _patch_active

    _patch_active = True
    os.makedirs = patched_makedirs_for_biopython_import
    print("[CONFIG] os.makedirs patch activated for Biopython import.")

    entrez_successfully_imported = False
    try:
        from Bio import Entrez
        from Bio.Entrez import Parser as EntrezParser # Keep this for DTD configuration
        _entrez_module = Entrez
        entrez_successfully_imported = True
        print("[CONFIG] Bio.Entrez and Parser imported successfully under patch.")

    except ImportError as ie:
        print(f"[CONFIG_FATAL] Could not import Bio.Entrez or Bio.Entrez.Parser even under patch: {ie}")
        _patch_active = False
        os.makedirs = original_makedirs
        print("[CONFIG] os.makedirs restored after import error.")
        raise
    except Exception as e:
        print(f"[CONFIG_FATAL] Unexpected error during patched import: {type(e).__name__} - {e}")
        _patch_active = False
        os.makedirs = original_makedirs
        print("[CONFIG] os.makedirs restored after unexpected import error.")
        raise

    _patch_active = False
    os.makedirs = original_makedirs
    print("[CONFIG] os.makedirs patch deactivated and restored to original.")

    if not entrez_successfully_imported or not _entrez_module:
        print("[CONFIG_FATAL] Entrez module was not loaded correctly.")
        raise ImportError("Failed to load Entrez module correctly.")

    try:
        _entrez_module.email = "kaveh.sarraf@gmail.com" # Actual email
        print(f"[CONFIG] Entrez.email set to: {_entrez_module.email}")

        custom_dtd_dir = os.path.join(tempfile.gettempdir(), "biopython_dtd_cache")
        # Use original_makedirs directly here as patch is deactivated
        if not os.path.exists(custom_dtd_dir):
            original_makedirs(custom_dtd_dir, mode=0o755) # exist_ok=True removed for broader compatibility if original_makedirs is old
        
        # Check if EntrezParser.DataHandler.local_dtd_dir exists and is writable
        if hasattr(EntrezParser, 'DataHandler') and hasattr(EntrezParser.DataHandler, 'local_dtd_dir'):
            EntrezParser.DataHandler.local_dtd_dir = custom_dtd_dir
            print(f"[CONFIG] Bio.Entrez DTD cache directory set to: {EntrezParser.DataHandler.local_dtd_dir}")
        else:
            print("[CONFIG_WARN] Could not set Bio.Entrez DTD cache directory directly on EntrezParser.DataHandler.")


    except Exception as e:
        print(f"[CONFIG_FATAL] Critical error during Entrez configuration (email/DTD path): {type(e).__name__} - {e}")
        raise

# اجرای پیکربندی و پچ در زمان بارگذاری ماژول
configure_entrez_and_patch()
Entrez = _entrez_module


app = Flask(__name__)
GBIF_API_URL_MATCH = "https://api.gbif.org/v1/species/match" # Existing GBIF endpoint

# --- Helper for NCBI API calls (Revised) ---
def _call_entrez_with_retry(action_description, action_func, max_retries=3, base_delay_seconds=0.34):
    """
    Wrapper for executing a function that performs NCBI Entrez operations,
    with retry logic for IncompleteRead and EntrezError.
    
    action_description: string, e.g., "fetching taxonomy details for TaxID X"
    action_func: A no-argument function (e.g., a lambda) that executes the Entrez calls 
                 (including handle opening, reading, and closing) and returns the parsed result.
    """
    last_exception = None
    for attempt in range(max_retries):
        try:
            current_delay = base_delay_seconds + (attempt * base_delay_seconds * 2) 
            time.sleep(current_delay) # Apply delay before each attempt
            
            result = action_func()
            return result
        except http.client.IncompleteRead as e:
            last_exception = e
            print(f"[RETRY_INCOMPLETE_READ] Attempt {attempt + 1}/{max_retries} for {action_description} failed: {e}. Retrying...")
        except Entrez.EntrezError as e: 
            last_exception = e
            print(f"[RETRY_ENTREZ_ERROR] Attempt {attempt + 1}/{max_retries} for {action_description} failed: {e}. Retrying...")
        except Exception as e: 
            last_exception = e
            print(f"[ENTREZ_UNEXPECTED_ERR] Unexpected error during {action_description} on attempt {attempt + 1}: {e}")
            if attempt >= max_retries -1 : 
                 break 
        
        if attempt >= max_retries - 1: 
            print(f"[ENTREZ_CALL_FINAL_FAIL] All {max_retries} attempts failed for {action_description}.")
            break 

    if last_exception:
        raise last_exception 
    return None 


# --- New NCBI Endpoints ---

COMMON_HEADERS = {'Access-Control-Allow-Origin': '*'}
CORS_OPTIONS_HEADERS = {
    **COMMON_HEADERS,
    'Access-Control-Allow-Methods': 'GET, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, X-Requested-With',
    'Access-Control-Max-Age': '3600'
}


@app.route('/api/microbe/search', methods=['GET', 'OPTIONS'])
def microbe_search_endpoint(): # Renamed to avoid confusion with any potential internal 'microbe_search' var/func
    if request.method == 'OPTIONS':
        return ('', 204, CORS_OPTIONS_HEADERS)

    search_term = request.args.get('name')
    gram_filter = request.args.get('gram_filter', 'any').lower() # Default to 'any'

    if not search_term:
        return jsonify({"error": "Parameter 'name' is required."}), 400, COMMON_HEADERS
    
    if gram_filter not in ['any', 'positive', 'negative']:
        return jsonify({"error": "Invalid 'gram_filter' value. Must be 'any', 'positive', or 'negative'."}), 400, COMMON_HEADERS

    initial_results_summary = []
    try:
        print(f"[NCBI_SEARCH_FILTER] Searching taxonomy for: {search_term}, Gram filter: {gram_filter}")
        
        def action_esearch():
            # This specific Entrez call (esearch) might not typically cause IncompleteRead with Entrez.read
            # as Entrez.read is straightforward for esearch results.
            # However, wrapping for consistency and other EntrezErrors.
            handle = Entrez.esearch(db="taxonomy", term=search_term, retmax="30", sort="relevance")
            records = Entrez.read(handle)
            handle.close()
            return records
        search_records = _call_entrez_with_retry(f"esearch for '{search_term}'", action_esearch)

        if not search_records or not search_records.get("IdList"):
            return jsonify([]), 200, COMMON_HEADERS

        id_list = search_records["IdList"]
        
        if gram_filter == 'any':
            def action_esummary():
                handle = Entrez.esummary(db="taxonomy", id=",".join(id_list))
                records = Entrez.read(handle)
                handle.close()
                return records
            summary_records = _call_entrez_with_retry(f"esummary for {len(id_list)} TaxIDs", action_esummary)
            
            for record in summary_records:
                initial_results_summary.append({
                    "scientific_name": record.get("ScientificName", "N/A"),
                    "tax_id": record.get("TaxId", record.get("Id", "N/A"))
                })
            response = jsonify(initial_results_summary)
            response.headers['Cache-Control'] = 'public, max-age=3600' 
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response, 200

        # Step 3: Filter by Gram stain
        filtered_results_summary = []
        # Limit the number of full detail fetches to avoid long processing times
        ids_to_fetch_details_for = id_list[:20] # Process up to 20 initial results for filtering

        for tax_id_str in ids_to_fetch_details_for:
            try:
                details = _fetch_single_microbe_details(tax_id_str) # This function gets gram_stain_derived
                gram_stain_derived = details.get("gram_stain_derived", "Not found").lower()
                
                match = False
                if gram_filter == "positive" and "gram-positive" in gram_stain_derived:
                    match = True
                elif gram_filter == "negative" and "gram-negative" in gram_stain_derived:
                    match = True
                
                if match:
                    filtered_results_summary.append({
                        "scientific_name": details.get("scientific_name", "N/A"),
                        "tax_id": tax_id_str
                    })
            except ValueError: # Raised by _fetch_single_microbe_details if TaxID not found
                print(f"[NCBI_SEARCH_FILTER] TaxID {tax_id_str} not found during detail fetch for filtering. Skipping.")
                continue # Skip this TaxID
            except Exception as detail_fetch_error:
                print(f"[NCBI_SEARCH_FILTER] Error fetching details for TaxID {tax_id_str} during filtering: {detail_fetch_error}. Skipping.")
                continue # Skip this TaxID if there's an unexpected error

        response = jsonify(filtered_results_summary)
        # Filtered results might be cached for a similar duration, or less if data changes often.
        # For now, keeping it consistent.
        response.headers['Cache-Control'] = 'public, max-age=3600' 
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response, 200

    except Exception as e:
        print(f"[API_ERR] /api/microbe/search: {type(e).__name__} - {str(e)}")
        traceback.print_exc()
        return jsonify({"error": f"Server error during NCBI search: {str(e)}"}), 500, COMMON_HEADERS


def parse_biosample_xml(xml_string):
    """Helper to parse BioSample XML for specific attributes, including Gram stain."""
    sample_data = {"attributes": []}
    gram_stain_found = None
    try:
        root = ET.fromstring(xml_string)
        for sample in root.findall('BioSample'):
            sample_data['id'] = sample.get('id')
            sample_data['accession'] = sample.get('accession')
            for desc_element in sample.findall('./Description/*'):
                if desc_element.tag == 'Title':
                    sample_data['title'] = desc_element.text
                if desc_element.tag == 'CommentParagraph' or desc_element.tag == 'Paragraph': # Check CommentParagraph and Paragraph for Gram stain
                    if desc_element.text and ("gram-positive" in desc_element.text.lower() or "gram positive" in desc_element.text.lower()):
                        gram_stain_found = "Gram-positive"
                    elif desc_element.text and ("gram-negative" in desc_element.text.lower() or "gram negative" in desc_element.text.lower()):
                        gram_stain_found = "Gram-negative"

            for attribute in sample.findall('./Attributes/Attribute'):
                attr_name = attribute.get('attribute_name')
                display_name = attribute.get('display_name', attr_name) # Use display_name if available
                value = attribute.text
                sample_data["attributes"].append({"name": display_name, "value": value})
                if attr_name and "gram" in attr_name.lower(): # Check attribute names
                    if value and "positive" in value.lower(): gram_stain_found = "Gram-positive"
                    elif value and "negative" in value.lower(): gram_stain_found = "Gram-negative"
                if display_name and "gram" in display_name.lower(): # Check display names
                    if value and "positive" in value.lower(): gram_stain_found = "Gram-positive"
                    elif value and "negative" in value.lower(): gram_stain_found = "Gram-negative"
            
            # Search within all attribute values for gram stain as a fallback
            if not gram_stain_found:
                for attr_dict in sample_data["attributes"]:
                    val = attr_dict.get("value", "")
                    if val:
                        if "gram-positive" in val.lower() or "gram positive" in val.lower():
                            gram_stain_found = "Gram-positive"
                            break
                        elif "gram-negative" in val.lower() or "gram negative" in val.lower():
                            gram_stain_found = "Gram-negative"
                            break
            if gram_stain_found:
                sample_data["gram_stain_biosample"] = gram_stain_found # Add to sample data if found

    except ET.ParseError as pe:
        print(f"[BIOSAMPLE_PARSE_ERR] XML Parse Error: {pe}")
    except Exception as e:
        print(f"[BIOSAMPLE_PARSE_ERR] Unexpected error parsing BioSample XML: {e}")
    return sample_data


def _fetch_single_microbe_details(tax_id):
    """
    Reusable function to fetch and compile details for a single microbe TaxID.
    Returns a dictionary of details or raises an exception on failure.
    """
    result = {"tax_id": tax_id}
    gram_stain_general = None
    oxygen_requirement_general = None # For stretch goal

    # 1. Fetch Taxonomic Data
    print(f"[NCBI_DETAIL_FUNC] Fetching taxonomy for TaxID: {tax_id}")
    def action_fetch_taxonomy():
        handle = Entrez.efetch(db="taxonomy", id=tax_id, retmode="xml")
        records = Entrez.read(handle)
        handle.close()
        return records
    tax_records = _call_entrez_with_retry(f"efetch taxonomy for TaxID {tax_id}", action_fetch_taxonomy)

    if not (tax_records and tax_records[0]):
        raise ValueError(f"Taxonomic details not found for TaxID {tax_id}.")
    tax_record = tax_records[0]
    result["scientific_name"] = tax_record.get("ScientificName", "N/A")
    result["rank"] = tax_record.get("Rank", "N/A")
    result["lineage"] = [{"rank": l.get("Rank"), "scientific_name": l.get("ScientificName")} for l in tax_record.get("LineageEx", []) if l.get("ScientificName")]

    if tax_record.get("OtherNames") and tax_record["OtherNames"].get("Name"):
        for name_info in tax_record["OtherNames"]["Name"]:
            if isinstance(name_info, dict) and name_info.get('ClassCDE') == 'comment':
                comment_text = name_info.get('DispName', '').lower()
                if not gram_stain_general: # Prioritize first find
                    if "gram-positive" in comment_text or "gram positive" in comment_text:
                        gram_stain_general = "Gram-positive"
                    elif "gram-negative" in comment_text or "gram negative" in comment_text:
                        gram_stain_general = "Gram-negative"
                # Stretch goal: Oxygen requirement from taxonomy comments
                if not oxygen_requirement_general:
                    if "aerobic" in comment_text: oxygen_requirement_general = "Aerobic"
                    elif "anaerobic" in comment_text: oxygen_requirement_general = "Anaerobic"
                    elif "facultative" in comment_text: oxygen_requirement_general = "Facultative" # Could be more specific
    
    if gram_stain_general:
        result["gram_stain_taxonomy_comment"] = gram_stain_general # Keep specific source noted

    # 2. Find and Fetch Nuccore (Genome) Information
    print(f"[NCBI_DETAIL_FUNC] Fetching linked nuccore for TaxID: {tax_id}")
    MAX_NUCCORE_RECORDS = 5
    
    def action_link_nuccore():
        handle = Entrez.elink(dbfrom="taxonomy", db="nuccore", id=tax_id, linkname="taxonomy_nuccore")
        links = Entrez.read(handle)
        handle.close()
        return links
    nuccore_links = _call_entrez_with_retry(f"elink nuccore for TaxID {tax_id}", action_link_nuccore)
    
    result["genome_info"] = []
    if nuccore_links and nuccore_links[0].get("LinkSetDb"):
        nuccore_ids = [link["Id"] for link in nuccore_links[0]["LinkSetDb"][0]["Link"]]
        if nuccore_ids:
            def action_summarize_nuccore():
                handle = Entrez.esummary(db="nuccore", id=",".join(nuccore_ids[:20])) # Check more to find ref
                summaries = Entrez.read(handle)
                handle.close()
                return summaries
            nuc_summaries = _call_entrez_with_retry(f"esummary nuccore for {len(nuccore_ids)} IDs (max 20 checked for ref)", action_summarize_nuccore)
            
            ref_genome_summary = None
            for rec in nuc_summaries:
                title = rec.get("Title", "").lower()
                if "reference genome" in title or "representative genome" in title:
                    ref_genome_summary = rec
                    break
            
            selected_summaries = []
            if ref_genome_summary:
                selected_summaries = [ref_genome_summary]
            else: # Fallback to taking the first few if no clear reference
                selected_summaries = nuc_summaries[:MAX_NUCCORE_RECORDS]

            for nuc_rec in selected_summaries:
                genome_data = {
                    "nuccore_id": nuc_rec.get("Id"),
                    "title": nuc_rec.get("Title", "N/A"),
                    "sequence_length": nuc_rec.get("SLen", "N/A"),
                    "molecule_type": nuc_rec.get("Topology", "N/A"),
                    "definition": nuc_rec.get("Definition", "")
                }
                if genome_data["sequence_length"] == "N/A" and "Extra" in nuc_rec:
                    extra_info = nuc_rec["Extra"]
                    slen_match = next((part.split('=')[1] for part in extra_info.split(' ') if part.startswith("SLen=")), None)
                    if slen_match: genome_data["sequence_length"] = slen_match
                    mol_match = next((part.split('=')[1] for part in extra_info.split(' ') if part.startswith("Mol=")), None)
                    if mol_match: genome_data["molecule_type"] = mol_match
                result["genome_info"].append(genome_data)

    # 3. Find and Fetch BioSample Information
    print(f"[NCBI_DETAIL_FUNC] Fetching linked biosample for TaxID: {tax_id}")
    MAX_BIOSAMPLE_RECORDS = 3
    
    def action_link_biosample():
        handle = Entrez.elink(dbfrom="taxonomy", db="biosample", id=tax_id, linkname="taxonomy_biosample")
        links = Entrez.read(handle)
        handle.close()
        return links
    biosample_links = _call_entrez_with_retry(f"elink biosample for TaxID {tax_id}", action_link_biosample)

    result["biosample_info"] = []
    if biosample_links and biosample_links[0].get("LinkSetDb"):
        biosample_ids = [link["Id"] for link in biosample_links[0]["LinkSetDb"][0]["Link"]][:MAX_BIOSAMPLE_RECORDS]
        if biosample_ids:
            def action_fetch_biosample():
                handle = Entrez.efetch(db="biosample", id=",".join(biosample_ids), retmode="xml")
                xml_data = handle.read() 
                handle.close()
                return xml_data
            biosample_xml_data = _call_entrez_with_retry(f"efetch biosample for {len(biosample_ids)} IDs", action_fetch_biosample)

            if biosample_xml_data:
                if isinstance(biosample_xml_data, bytes):
                    biosample_xml_data = biosample_xml_data.decode('utf-8')
                
                try:
                    root_node_str = f"<BioSampleSet>{biosample_xml_data}</BioSampleSet>" 
                    parsed_biosamples_root = ET.fromstring(root_node_str)
                    for sample_node in parsed_biosamples_root.findall('BioSample'): # Moved loop inside try
                        sample_xml_str = ET.tostring(sample_node, encoding='unicode')
                        parsed_sample_data = parse_biosample_xml(sample_xml_str) # This helper already looks for Gram stain
                        
                        # Stretch goal: Oxygen requirement from BioSample attributes
                        if not oxygen_requirement_general and parsed_sample_data.get("attributes"):
                            for attr in parsed_sample_data["attributes"]:
                                attr_name_lower = attr.get("name", "").lower()
                                attr_val_lower = attr.get("value", "").lower()
                                if "oxygen" in attr_name_lower or "aerobic" in attr_name_lower or "anaerobic" in attr_name_lower:
                                    if "aerobic" in attr_val_lower: oxygen_requirement_general = "Aerobic"
                                    elif "anaerobic" in attr_val_lower: oxygen_requirement_general = "Anaerobic"
                                    elif "facultative" in attr_val_lower: oxygen_requirement_general = "Facultative"
                                    elif "microaerophilic" in attr_val_lower: oxygen_requirement_general = "Microaerophilic"
                                    break 
                        
                        if parsed_sample_data:
                            result["biosample_info"].append(parsed_sample_data)
                            if not gram_stain_general and "gram_stain_biosample" in parsed_sample_data:
                                gram_stain_general = parsed_sample_data["gram_stain_biosample"]
                except ET.ParseError as pe_multi:
                    print(f"[BIOSAMPLE_MULTI_PARSE_ERR] XML Parse Error for BioSampleSet TaxID {tax_id}: {pe_multi}")
                    # Optionally, add a placeholder or error indicator to result["biosample_info"]
                except Exception as e_bs_parse: # Catch any other error during biosample parsing
                    print(f"[BIOSAMPLE_GENERIC_PARSE_ERR] Error parsing BioSample XML for TaxID {tax_id}: {e_bs_parse}")
            
    
    # Consolidate Gram stain and Oxygen requirement
    result["gram_stain_derived"] = gram_stain_general if gram_stain_general else "Not found"
                
                # Stretch goal: Oxygen requirement from BioSample attributes
                if not oxygen_requirement_general and parsed_sample_data.get("attributes"):
                    for attr in parsed_sample_data["attributes"]:
                        attr_name_lower = attr.get("name", "").lower()
                        attr_val_lower = attr.get("value", "").lower()
                        if "oxygen" in attr_name_lower or "aerobic" in attr_name_lower or "anaerobic" in attr_name_lower:
                            if "aerobic" in attr_val_lower: oxygen_requirement_general = "Aerobic"
                            elif "anaerobic" in attr_val_lower: oxygen_requirement_general = "Anaerobic"
                            elif "facultative" in attr_val_lower: oxygen_requirement_general = "Facultative"
                            elif "microaerophilic" in attr_val_lower: oxygen_requirement_general = "Microaerophilic"
                            break # Found one, stop for this sample
                
                if parsed_sample_data:
                    result["biosample_info"].append(parsed_sample_data)
                    if not gram_stain_general and "gram_stain_biosample" in parsed_sample_data:
                        gram_stain_general = parsed_sample_data["gram_stain_biosample"]
    
    # Consolidate Gram stain and Oxygen requirement
    result["gram_stain_derived"] = gram_stain_general if gram_stain_general else "Not found"
    result["oxygen_requirement_derived"] = oxygen_requirement_general if oxygen_requirement_general else "Not found"
    
    # Extract primary isolation source for comparison view (simplified)
    primary_isolation_source = "N/A"
    if result["biosample_info"]:
        for sample in result["biosample_info"]:
            if sample.get("attributes"):
                for attr in sample["attributes"]:
                    if attr.get("name", "").lower() in ["isolation source", "host", "geo_loc_name"]: # Prioritize these
                        primary_isolation_source = attr.get("value", "N/A")
                        break
                if primary_isolation_source != "N/A":
                    break
        if primary_isolation_source == "N/A" and result["biosample_info"][0].get("attributes"): # Fallback to first attribute of first sample
             primary_isolation_source = result["biosample_info"][0]["attributes"][0].get("value", "N/A") if result["biosample_info"][0]["attributes"] else "N/A"

    result["primary_isolation_source"] = primary_isolation_source

    # Extract primary genome size for comparison view
    primary_genome_size_bp = "N/A"
    if result["genome_info"]:
        # Try to find a genome with a valid sequence length
        for genome in result["genome_info"]:
            if genome.get("sequence_length") and genome["sequence_length"] != "N/A":
                primary_genome_size_bp = genome["sequence_length"]
                break
    result["primary_genome_size_bp"] = primary_genome_size_bp


    return result


@app.route('/api/microbe/detail', methods=['GET', 'OPTIONS'])
def microbe_detail_endpoint(): # Renamed to avoid conflict if Flask doesn't like function name same as route part
    if request.method == 'OPTIONS':
        return ('', 204, CORS_OPTIONS_HEADERS)

    tax_id = request.args.get('tax_id')
    if not tax_id:
        return jsonify({"error": "Parameter 'tax_id' is required."}), 400, COMMON_HEADERS

    try:
        details = _fetch_single_microbe_details(tax_id)
        response = jsonify(details)
        response.headers['Cache-Control'] = 'public, max-age=86400' # 1 day
        response.headers['Access-Control-Allow-Origin'] = '*'
        return response, 200
    except ValueError as ve: # Catch specific "not found" error from helper
        print(f"[API_ERR] /api/microbe/detail for TaxID {tax_id}: {str(ve)}")
        return jsonify({"error": str(ve)}), 404, COMMON_HEADERS
    except Exception as e:
        print(f"[API_ERR] /api/microbe/detail for TaxID {tax_id}: {type(e).__name__} - {str(e)}")
        traceback.print_exc()
        return jsonify({"error": f"Server error during NCBI detail fetch for TaxID {tax_id}: {str(e)}"}), 500, COMMON_HEADERS

@app.route('/api/microbes/details', methods=['POST', 'OPTIONS']) # Note: POST method
def microbes_details_batch():
    if request.method == 'OPTIONS':
        # Ensure POST is allowed for CORS preflight
        batch_cors_headers = {**CORS_OPTIONS_HEADERS, 'Access-Control-Allow-Methods': 'POST, OPTIONS'}
        return ('', 204, batch_cors_headers)

    if not request.is_json:
        return jsonify({"error": "Request must be JSON."}), 400, COMMON_HEADERS
    
    data = request.get_json()
    tax_ids = data.get('tax_ids')

    if not tax_ids or not isinstance(tax_ids, list):
        return jsonify({"error": "Parameter 'tax_ids' must be a list."}), 400, COMMON_HEADERS
    
    if not tax_ids: # Empty list check
        return jsonify({"error": "'tax_ids' list cannot be empty."}), 400, COMMON_HEADERS

    MAX_BATCH_SIZE = 20 # Limit batch size to prevent abuse/long requests
    if len(tax_ids) > MAX_BATCH_SIZE:
        return jsonify({"error": f"Maximum batch size is {MAX_BATCH_SIZE}. Received {len(tax_ids)}."}), 400, COMMON_HEADERS


    all_details = []
    errors_encountered = {}

    for tax_id in tax_ids:
        try:
            details = _fetch_single_microbe_details(str(tax_id)) # Ensure tax_id is string
            all_details.append(details)
        except ValueError as ve: # Not found or other value errors from helper
            print(f"[BATCH_API_WARN] Failed to fetch details for TaxID {tax_id}: {str(ve)}")
            errors_encountered[tax_id] = str(ve)
        except Exception as e:
            print(f"[BATCH_API_ERR] Unexpected error fetching details for TaxID {tax_id}: {type(e).__name__} - {str(e)}")
            errors_encountered[tax_id] = f"Unexpected server error: {str(e)}"
            # Optionally, re-raise if one failure should stop the whole batch:
            # return jsonify({"error": f"Server error processing TaxID {tax_id}: {str(e)}"}), 500, COMMON_HEADERS
    
    response_data = {"results": all_details}
    if errors_encountered:
        response_data["errors"] = errors_encountered
        
    response = jsonify(response_data)
    response.headers['Cache-Control'] = 'public, max-age=86400' # 1 day, same as single detail
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response, 200


# --- Existing Endpoints (suggest_scientific_name and main_handler for GBIF/Wikipedia) ---
# ... (keep existing get_wikipedia_data, get_best_ncbi_suggestion_flexible, suggest_name_handler, main_handler) ...
# --- تابع جستجوی تصویر و خلاصه از ویکی‌پدیا ---
def get_wikipedia_data(species_name_from_user, scientific_name_from_gbif=None):
    search_candidates = []
    clean_scientific_name = None
    clean_scientific_name_for_filename = None
    wiki_data = {'imageUrl': None, 'summary': None}

    if scientific_name_from_gbif:
        temp_clean_name = scientific_name_from_gbif.split('(')[0].strip()
        if temp_clean_name:
            clean_scientific_name = temp_clean_name
            search_candidates.append(clean_scientific_name)
            clean_scientific_name_for_filename = clean_scientific_name.lower().replace(" ", "_")

    user_name_for_filename = None
    if species_name_from_user:
        should_add_user_name = True
        if clean_scientific_name:
            if species_name_from_user.lower() == clean_scientific_name.lower():
                should_add_user_name = False
        
        if should_add_user_name:
            search_candidates.append(species_name_from_user)
        
        user_name_for_filename = species_name_from_user.lower().replace(" ", "_")

    if not search_candidates:
        return wiki_data

    wikipedia.set_lang("en") # Ensure English Wikipedia for consistency
    avoid_keywords_in_filename = ["map", "range", "distribution", "locator", "chart", "diagram", "logo", "icon", "disambig", "sound", "audio", "timeline", "scale", "reconstruction", "skeleton", "skull", "footprint", "tracks", "scat", "phylogeny", "cladogram", "taxonomy", "taxobox", "cite_note"]
    priority_keywords = []
    if clean_scientific_name_for_filename:
        priority_keywords.append(clean_scientific_name_for_filename)
        if "_" in clean_scientific_name_for_filename:
            priority_keywords.append(clean_scientific_name_for_filename.split("_")[0])

    if user_name_for_filename:
        if not (clean_scientific_name_for_filename and user_name_for_filename == clean_scientific_name_for_filename):
            priority_keywords.append(user_name_for_filename)
        if "_" in user_name_for_filename:
            user_genus_equivalent = user_name_for_filename.split("_")[0]
            add_user_genus = True
            if clean_scientific_name_for_filename and "_" in clean_scientific_name_for_filename:
                if user_genus_equivalent == clean_scientific_name_for_filename.split("_")[0]:
                    add_user_genus = False
            elif clean_scientific_name_for_filename and user_genus_equivalent == clean_scientific_name_for_filename:
                add_user_genus = False
            if add_user_genus:
                priority_keywords.append(user_genus_equivalent)

    priority_keywords = list(filter(None, dict.fromkeys(priority_keywords)))
    processed_search_terms = set()
    
    if clean_scientific_name and clean_scientific_name not in processed_search_terms:
        search_candidates.insert(0, clean_scientific_name) 

    page_found_for_summary = False

    while search_candidates:
        term_to_search = search_candidates.pop(0)
        if not term_to_search or term_to_search in processed_search_terms:
            continue
        processed_search_terms.add(term_to_search)
        
        try:
            wiki_page = None
            page_title_for_summary = None
            try:
                print(f"[WIKI_DATA] Attempting to get page for: {term_to_search}")
                wiki_page = wikipedia.page(term_to_search, auto_suggest=True, redirect=True)
                page_title_for_summary = wiki_page.title
                print(f"[WIKI_DATA] Page found: {page_title_for_summary}")
            except wikipedia.exceptions.PageError:
                print(f"[WIKI_DATA] PageError for '{term_to_search}'. Trying search.")
                search_results = wikipedia.search(term_to_search, results=1)
                if not search_results:
                    print(f"[WIKI_DATA] No search results for '{term_to_search}'.")
                    continue
                page_title_to_get = search_results[0]
                if page_title_to_get in processed_search_terms:
                    continue
                print(f"[WIKI_DATA] Search found '{page_title_to_get}'. Attempting to get page.")
                wiki_page = wikipedia.page(page_title_to_get, auto_suggest=False, redirect=True)
                page_title_for_summary = wiki_page.title
                print(f"[WIKI_DATA] Page found via search: {page_title_for_summary}")
            
            if wiki_page:
                if not wiki_data['summary'] and page_title_for_summary and not page_found_for_summary:
                    try:
                        print(f"[WIKI_DATA] Attempting to get summary for: {page_title_for_summary}")
                        summary_text = wikipedia.summary(page_title_for_summary, sentences=2)
                        if len(summary_text) < 100 or "may refer to" in summary_text.lower():
                             summary_text_longer = wikipedia.summary(page_title_for_summary, sentences=3)
                             if len(summary_text_longer) > len(summary_text):
                                 summary_text = summary_text_longer
                        
                        wiki_data['summary'] = summary_text
                        page_found_for_summary = True 
                        print(f"[WIKI_DATA] Summary found for '{page_title_for_summary}'.")
                    except wikipedia.exceptions.DisambiguationError as de_summ:
                        print(f"[WIKI_SUMM_ERR] DisambiguationError for summary '{page_title_for_summary}': {de_summ.options[:2]}")
                    except wikipedia.exceptions.PageError:
                        print(f"[WIKI_SUMM_ERR] PageError for summary '{page_title_for_summary}'.")
                    except Exception as e_summ:
                        print(f"[WIKI_SUMM_ERR] Generic for summary '{page_title_for_summary}': {type(e_summ).__name__} - {str(e_summ)}")

                if not wiki_data['imageUrl'] and wiki_page.images:
                    candidate_images_with_scores = []
                    for img_url in wiki_page.images:
                        img_url_lower = img_url.lower()
                        if not any(ext in img_url_lower for ext in ['.png', '.jpg', '.jpeg']):
                            continue
                        if any(keyword in img_url_lower for keyword in avoid_keywords_in_filename):
                            continue
                        
                        score = 0
                        for pk_word in priority_keywords:
                            if pk_word in img_url_lower:
                                score += 5
                                filename_part = img_url_lower.split('/')[-1]
                                if filename_part.startswith(pk_word):
                                    score += 3
                                if pk_word == clean_scientific_name_for_filename and pk_word in filename_part:
                                    score += 5
                        if "taxobox" in img_url_lower: score += 2 
                        if img_url_lower.endswith('.svg'): score -= 1
                        candidate_images_with_scores.append({'url': img_url, 'score': score})
                    
                    if candidate_images_with_scores:
                        sorted_images = sorted(candidate_images_with_scores, key=lambda x: x['score'], reverse=True)
                        if sorted_images and sorted_images[0]['score'] >= 0: 
                            best_image_url = sorted_images[0]['url']
                            if best_image_url.startswith("//"): best_image_url = "https:" + best_image_url
                            wiki_data['imageUrl'] = best_image_url
                            print(f"[WIKI_IMG] Best image for '{term_to_search}': {best_image_url} (Score: {sorted_images[0]['score']})")
                
                if wiki_data['summary'] and wiki_data['imageUrl']:
                    if term_to_search == clean_scientific_name:
                        print("[WIKI_DATA] Both summary and image found from GBIF scientific name. Returning.")
                        return wiki_data
                    if not (clean_scientific_name and clean_scientific_name not in processed_search_terms):
                         print("[WIKI_DATA] Both summary and image found. Returning.")
                         return wiki_data

        except wikipedia.exceptions.DisambiguationError as e:
            print(f"[WIKI_DATA_ERR] DisambiguationError for '{term_to_search}': {e.options[:2]}")
            if e.options and not page_found_for_summary : 
                for option in e.options[:2]: 
                     if option not in processed_search_terms and option not in search_candidates:
                        search_candidates.append(option)
        except wikipedia.exceptions.PageError:
            print(f"[WIKI_DATA_ERR] PageError for '{term_to_search}' (second attempt).")
        except Exception as e:
            print(f"[WIKI_DATA_ERR] Generic for '{term_to_search}': {type(e).__name__} - {str(e)}")
    
    if not wiki_data['imageUrl'] and not wiki_data['summary']:
        print(f"[WIKI_DATA] No image or summary found for user input: '{species_name_from_user}'.")
    
    return wiki_data

def get_best_ncbi_suggestion_flexible(common_name, max_ids_to_check=5):
    global Entrez 
    print(f"[NCBI_SUGGEST] Processing '{common_name}' (Email: {Entrez.email if Entrez and hasattr(Entrez, 'email') else 'Email Not Set'})")
    scientific_name_suggestion = None
    if not Entrez or not hasattr(Entrez, 'email') or not Entrez.email: 
        print("[NCBI_SUGGEST_ERR] Entrez module not properly configured or email not set.")
        return None
    try:
        search_term = f"{common_name}[Common Name] OR {common_name}[Organism]"
        
        def action_suggest_esearch1():
            h = Entrez.esearch(db="taxonomy", term=search_term, retmax=max_ids_to_check, sort="relevance")
            r = Entrez.read(h)
            h.close()
            return r
        record = _call_entrez_with_retry(f"suggest_esearch1 for '{common_name}'", action_suggest_esearch1)
        id_list = record.get("IdList", [])

        if not id_list:
            def action_suggest_esearch2():
                h = Entrez.esearch(db="taxonomy", term=common_name, retmax=max_ids_to_check, sort="relevance")
                r = Entrez.read(h)
                h.close()
                return r
            record = _call_entrez_with_retry(f"suggest_esearch2 for '{common_name}'", action_suggest_esearch2)
            id_list = record.get("IdList", [])
            if not id_list:
                print(f"  [NCBI_SUGGEST] No TaxIDs for '{common_name}' after retry.")
                return None
        
        ids_to_fetch = id_list[:max_ids_to_check] 
        if not ids_to_fetch: return None

        def action_suggest_esummary():
            h = Entrez.esummary(db="taxonomy", id=",".join(ids_to_fetch), retmode="xml")
            r = Entrez.read(h)
            h.close()
            return r
        summary_records = _call_entrez_with_retry(f"suggest_esummary for {len(ids_to_fetch)} IDs", action_suggest_esummary)

        candidates = {"species": None, "subspecies": None, "genus": None, "family": None, "other_valid": None}
        for summary_record in summary_records:
            sci_name = summary_record.get("ScientificName")
            rank_ncbi = summary_record.get("Rank", "N/A").lower()
            if sci_name:
                if rank_ncbi == "species" and not candidates["species"]: candidates["species"] = sci_name
                elif rank_ncbi == "subspecies" and not candidates["subspecies"]: candidates["subspecies"] = sci_name
                elif rank_ncbi == "genus" and not candidates["genus"]: candidates["genus"] = sci_name
                elif rank_ncbi == "family" and not candidates["family"]: candidates["family"] = sci_name
                elif not candidates["other_valid"]: candidates["other_valid"] = sci_name
        if candidates["species"]: scientific_name_suggestion = candidates["species"]
        elif candidates["subspecies"]:
            parts = candidates["subspecies"].split()
            scientific_name_suggestion = " ".join(parts[:2]) if len(parts) >= 2 else candidates["subspecies"]
        elif candidates["genus"]: scientific_name_suggestion = candidates["genus"]
        elif candidates["family"]: scientific_name_suggestion = candidates["family"]
        elif candidates["other_valid"]: scientific_name_suggestion = candidates["other_valid"]
    except Exception as e:
        print(f"  [NCBI_SUGGEST_ERR] Querying NCBI for '{common_name}': {type(e).__name__} - {e}")
        if isinstance(e, OSError) and hasattr(e, 'errno') and e.errno == 30:
            traceback.print_exc() 
        elif "HTTP Error 400" in str(e) or "Bad Request" in str(e):
            print("  [NCBI_SUGGEST_WARN] Received HTTP 400 Bad Request. Check Entrez email and request rate.")
            traceback.print_exc() 
    if scientific_name_suggestion:
        print(f"  [NCBI_SUGGEST] Suggestion for '{common_name}': {scientific_name_suggestion}")
    else:
        print(f"  [NCBI_SUGGEST] No suggestion for '{common_name}'.")
    return scientific_name_suggestion

@app.route('/api/suggest_scientific_name', methods=['GET', 'OPTIONS'])
def suggest_name_handler():
    if request.method == 'OPTIONS':
        return ('', 204, CORS_OPTIONS_HEADERS)
    common_name_query = request.args.get('common_name')
    if not common_name_query:
        return jsonify({"error": "پارامتر 'common_name' مورد نیاز است."}), 400, COMMON_HEADERS
    try:
        suggested_name = get_best_ncbi_suggestion_flexible(common_name_query)
        if suggested_name:
            # No specific caching for this one, as it's more of a utility endpoint
            return jsonify({"suggested_scientific_name": suggested_name, "common_name_searched": common_name_query}), 200, COMMON_HEADERS
        else:
            return jsonify({"message": f"نام علمی برای '{common_name_query}' توسط NCBI پیشنهاد نشد.", "common_name_searched": common_name_query}), 404, COMMON_HEADERS
    except Exception as e:
        print(f"[API_ERR] suggest_name_handler for '{common_name_query}': {type(e).__name__} - {str(e)}")
        traceback.print_exc()
        return jsonify({"error": "خطای داخلی سرور هنگام پردازش پیشنهاد نام."}), 500, COMMON_HEADERS

@app.route('/', defaults={'path': ''}, methods=['GET', 'POST', 'OPTIONS'])
@app.route('/<path:path>', methods=['GET', 'POST', 'OPTIONS'])
def main_handler(path=None):
    # This existing main_handler is for the GBIF/Wikipedia search.
    # It will coexist with the new /api/microbe/* endpoints.
    # All Flask routes are distinct.
    if request.method == 'OPTIONS':
        # Broader CORS for this specific pre-existing endpoint if it needs to support POST etc.
        main_cors_headers = {**COMMON_HEADERS, 'Access-Control-Allow-Methods': 'GET, POST, OPTIONS', 'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-Requested-With', 'Access-Control-Max-Age': '3600'}
        return ('', 204, main_cors_headers)
        
    species_name_query = ""
    if request.method == 'GET': species_name_query = request.args.get('name')
    elif request.method == 'POST':
        try:
            data_post = request.get_json()
            if data_post: species_name_query = data_post.get('name')
            else: return jsonify({"error": "درخواست نامعتبر: بدنه JSON خالی."}), 400, COMMON_HEADERS
        except: return jsonify({"error": "خطا در خواندن بدنه JSON."}), 400, COMMON_HEADERS
    
    if not species_name_query: return jsonify({"error": "پارامتر 'name' نیاز است."}), 400, COMMON_HEADERS
    
    params_gbif = {"name": species_name_query, "verbose": "true"}
    classification_data = {}
    gbif_error_message = None
    gbif_scientific_name = None
    try:
        api_response_gbif = requests.get(GBIF_API_URL_MATCH, params=params_gbif, timeout=10)
        api_response_gbif.raise_for_status()
        data_gbif = api_response_gbif.json()
        if not data_gbif or data_gbif.get("matchType") == "NONE" or data_gbif.get("confidence", 0) < 30:
            gbif_error_message = f"موجودی '{species_name_query}' در GBIF پیدا نشد یا اطمینان کم بود."
            classification_data = {"searchedName": species_name_query, "matchType": data_gbif.get("matchType", "NONE"), "confidence": data_gbif.get("confidence")}
        else:
            gbif_scientific_name = data_gbif.get("scientificName")
            classification_data = {"searchedName": species_name_query, "scientificName": gbif_scientific_name, "kingdom": data_gbif.get("kingdom"), "phylum": data_gbif.get("phylum"), "class": data_gbif.get("class"), "order": data_gbif.get("order"), "family": data_gbif.get("family"), "genus": data_gbif.get("genus"), "species": data_gbif.get("species") if data_gbif.get("speciesKey") and data_gbif.get("species") else None, "usageKey": data_gbif.get("usageKey"), "confidence": data_gbif.get("confidence"), "matchType": data_gbif.get("matchType"), "status": data_gbif.get("status"), "rank": data_gbif.get("rank")}    
    except requests.exceptions.Timeout:
        gbif_error_message = "خطا: GBIF Timeout."
        print(f"[GBIF_ERR] Timeout: {species_name_query}")
    except requests.exceptions.HTTPError as http_err_gbif:
        gbif_error_message = f"خطا از GBIF: {http_err_gbif}"
        try:
            gbif_error_details = api_response_gbif.json()
            gbif_error_message += f" - پیام: {gbif_error_details.get('message', api_response_gbif.text[:100])}"
        except: pass
        print(f"[GBIF_ERR] HTTPError: {gbif_error_message}")
    except requests.exceptions.RequestException as e_gbif_req:
        gbif_error_message = f"خطا در ارتباط با GBIF: {str(e_gbif_req)}"
        print(f"[GBIF_ERR] RequestException: {str(e_gbif_req)}")
    except Exception as e_gbif_generic:
        gbif_error_message = "خطای داخلی GBIF."
        print(f"[GBIF_ERR] Generic Error: {str(e_gbif_generic)}")
        traceback.print_exc()

    wiki_content = get_wikipedia_data(species_name_query, gbif_scientific_name)
    if wiki_content['imageUrl']:
        classification_data["imageUrl"] = wiki_content['imageUrl']
    if wiki_content['summary']:
        classification_data["wikipediaSummary"] = wiki_content['summary']
        
    final_data = {k: v for k, v in classification_data.items() if v is not None}

    if gbif_error_message and not final_data.get("scientificName"): 
        if final_data.get("imageUrl") or final_data.get("wikipediaSummary"):
            # This endpoint (original main_handler) can also have caching if desired, e.g. 1 hour
            response = jsonify({"message": gbif_error_message, **final_data})
            # response.headers['Cache-Control'] = 'public, max-age=3600' 
            response.headers['Access-Control-Allow-Origin'] = '*'
            return response, 200 # 200 because we have some data
        return jsonify({"message": gbif_error_message, "searchedName": species_name_query}), 404, COMMON_HEADERS

    if not final_data.get("scientificName") and not final_data.get("imageUrl") and not final_data.get("wikipediaSummary") and not gbif_error_message :
        return jsonify({"message": f"اطلاعاتی برای '{species_name_query}' یافت نشد."}), 404, COMMON_HEADERS
    
    # This endpoint (original main_handler) can also have caching if desired, e.g. 1 hour
    response = jsonify(final_data)
    # response.headers['Cache-Control'] = 'public, max-age=3600'
    response.headers['Access-Control-Allow-Origin'] = '*'
    return response, 200

# if __name__ == "__main__":
#    app.run(debug=True, port=5004)
