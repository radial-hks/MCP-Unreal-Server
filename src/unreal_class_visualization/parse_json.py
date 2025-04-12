import json
import os

def parse_unreal_json(json_path):
    """
    Reads and parses the Unreal Engine class information from a JSON file.

    Args:
        json_path (str): The path to the JSON file.

    Returns:
        dict: The parsed JSON data, or None if an error occurs.
    """
    if not os.path.exists(json_path):
        print(f"Error: JSON file not found at {json_path}")
        return None

    try:
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data
    except json.JSONDecodeError as e:
        print(f"Error decoding JSON: {e}")
        return None
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        return None

def calculate_references(data):
    """
    Calculates 'references' and 'referenced_by' counts for each class.

    Args:
        data (dict): The dictionary containing Unreal class information.

    Returns:
        dict: The data dictionary updated with 'references' and 'referenced_by'.
    """
    if not data:
        return data

    all_class_names = set(data.keys())

    # First Pass: Initialize and calculate 'references'
    for class_name, class_info in data.items():
        class_info['references'] = {}
        class_info['referenced_by'] = {} # Initialize referenced_by here

        # Calculate references from parent
        parent = class_info.get('parent')
        if parent and parent in all_class_names:
            class_info['references'][parent] = class_info['references'].get(parent, 0) + 1

        # Calculate references from editor properties
        for _, prop_type in class_info.get('editor_properties', []):
            if prop_type in all_class_names:
                class_info['references'][prop_type] = class_info['references'].get(prop_type, 0) + 1

    # Second Pass: Calculate 'referenced_by'
    for referencing_class_name, referencing_class_info in data.items():
        # Check references from editor properties of the referencing class
        for _, prop_type in referencing_class_info.get('editor_properties', []):
            if prop_type in all_class_names:
                # If prop_type is a valid class, increment its referenced_by count
                # for the referencing_class_name
                if prop_type in data: # Ensure the referenced class exists in data
                    data[prop_type]['referenced_by'][referencing_class_name] = \
                        data[prop_type]['referenced_by'].get(referencing_class_name, 0) + 1

    return data


def print_traverse_data(data):
    """
    Traverses the parsed and calculated JSON data and prints class information.

    Args:
        data (dict): The dictionary containing Unreal class information with calculated references.
    """
    if not data:
        print("No data to traverse.")
        return

    print("Traversing Unreal Class Data:")
    print("-" * 30)

    for class_name, class_info in data.items():
        print(f"Class Name: {class_name}")

        # Print basic info if available
        if "parent" in class_info:
            print(f"  Parent: {class_info['parent']}")
        if "grand_parent" in class_info:
            print(f"  Grand Parent: {class_info['grand_parent']}")
        if "generation" in class_info:
            print(f"  Generation: {class_info['generation']}")

        # Print editor properties
        if "editor_properties" in class_info and class_info["editor_properties"]:
            print("  Editor Properties:")
            for prop_name, prop_type in class_info["editor_properties"]:
                print(f"    - {prop_name} ({prop_type})")
        else:
            print("  Editor Properties: None")

        # Print methods
        if "methods" in class_info and class_info["methods"]:
            print("  Methods:")
            for method in class_info["methods"]:
                print(f"    - {method}")
        else:
            print("  Methods: None")

        # Print children
        if "children" in class_info and class_info["children"]:
            print(f"  Children: {', '.join(class_info['children'])}")
        else:
            print("  Children: None")

        # Print calculated references
        if "references" in class_info and class_info["references"]:
            print("  References:")
            for ref_name, count in sorted(class_info["references"].items()): # Sort for consistent output
                print(f"    - {ref_name} (Count: {count})")
        else:
            print("  References: None")

        # Print calculated referenced by
        if "referenced_by" in class_info and class_info["referenced_by"]:
            print("  Referenced By:")
            for ref_name, count in sorted(class_info["referenced_by"].items()): # Sort for consistent output
                print(f"    - {ref_name} (Count: {count})")
        else:
            print("  Referenced By: None")


        print("-" * 30)

if __name__ == "__main__":
    # Construct the path relative to the script's location
    script_dir = os.path.dirname(os.path.abspath(__file__))
    json_file_path = os.path.join(script_dir, 'data', 'unreal.json')

    unreal_data = parse_unreal_json(json_file_path)

    if unreal_data:
        calculated_data = calculate_references(unreal_data)
        # print_traverse_data(calculated_data)
        # Optionally, save the updated data back to a file
        output_json_path = os.path.join(script_dir, 'data', 'unreal_calculated.json')
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(calculated_data, f, indent=2)
        print(f"Calculated data saved to {output_json_path}")
    else:
        print("Failed to parse JSON data.")